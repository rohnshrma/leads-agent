"""Overpass retries and mirrors, and Google Places discovery (field mask, paging, budget, failure modes)."""
import json
import sys
from pathlib import Path
from unittest import mock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from leadagent import google_places  # noqa: E402
from leadagent.budget import Budget  # noqa: E402
from leadagent.sources import DeadlineReached, OverpassSource, SearchFailed  # noqa: E402

CITY = {"name": "Hamilton, ON", "lat": 43.2557, "lng": -79.8711}
M1, M2, M3 = "https://m1.example/api", "https://m2.example/api", "https://m3.example/api"


class R:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code, self._p, self.headers = status, payload, headers or {}

    def json(self):
        if self._p is None:
            raise ValueError("not json")
        return self._p


ELEMENT = {"elements": [{"type": "node", "id": 1, "lat": 43.25, "lon": -79.87,
                         "tags": {"name": "Hillside Dental", "amenity": "dentist", "phone": "+1 905-526-1234"}}]}


def source(post, **kw):
    sleeps = []
    s = OverpassSource(max_places=100, pause=0, radius_km=10, mirrors=[M1, M2, M3], post=post,
                       sleep=sleeps.append, **kw)
    s.sleeps = sleeps
    return s


# ---------------------------------------------------------------- overpass
def test_timeout_on_the_first_mirror_succeeds_on_the_second():
    calls = []

    def post(url, **kw):
        calls.append(url)
        if url == M1:
            raise requests.Timeout()
        return R(200, ELEMENT)

    s = source(post)
    got = s.search("dental clinic", CITY)
    assert len(got) == 1 and got[0].name == "Hillside Dental"
    assert calls[0] == M1 and calls[-1] == M2
    assert calls.count(M1) == 4                           # first try + three backed-off retries
    assert s.failures == []


def test_backoff_grows_and_has_jitter():
    s = source(lambda url, **kw: R(503) if url != M3 else R(200, ELEMENT))
    s.search("dental clinic", CITY)
    first = s.sleeps[:3]
    assert 2 <= first[0] <= 2.5 and 5 <= first[1] <= 6.25 and 12 <= first[2] <= 15


def test_retry_after_is_respected_and_capped():
    seq = [R(429, headers={"Retry-After": "7"}), R(200, ELEMENT)]
    s = source(lambda url, **kw: seq.pop(0))
    s.search("dental clinic", CITY)
    assert s.sleeps == [7.0]
    seq = [R(429, headers={"Retry-After": "9999"}), R(200, ELEMENT)]
    s = source(lambda url, **kw: seq.pop(0))
    s.search("dental clinic", CITY)
    assert s.sleeps == [OverpassSource.MAX_RETRY_AFTER]


def test_a_400_is_not_retried_on_the_same_mirror():
    calls = []

    def post(url, **kw):
        calls.append(url)
        return R(400) if url == M1 else R(200, ELEMENT)

    source(post).search("dental clinic", CITY)
    assert calls.count(M1) == 1


def test_all_mirrors_failing_is_a_recorded_failure_not_zero_results():
    s = source(lambda url, **kw: R(504))
    with pytest.raises(SearchFailed):
        s.search("dental clinic", CITY)
    assert s.failures and s.failures[0]["type"] == "dental clinic" and s.failures[0]["error"] == "HTTP 504"


def test_garbage_answer_moves_on_to_the_next_mirror():
    seq = {M1: R(200, None), M2: R(200, ELEMENT)}
    s = source(lambda url, **kw: seq[url])
    assert len(s.search("dental clinic", CITY)) == 1


def test_query_timeout_and_http_timeout_agree():
    seen = {}

    def post(url, data=None, timeout=None, **kw):
        seen["q"], seen["t"] = data["data"], timeout
        return R(200, ELEMENT)

    source(post).search("dental clinic", CITY)
    assert f"[timeout:{OverpassSource.QUERY_TIMEOUT}]" in seen["q"]
    assert seen["t"] > OverpassSource.QUERY_TIMEOUT


def test_user_agent_names_a_contact():
    seen = {}
    source(lambda url, **kw: seen.update(kw) or R(200, ELEMENT)).search("dental clinic", CITY)
    assert "rohan@webigeeksdigital.com" in seen["headers"]["User-Agent"]


def test_large_areas_are_split_into_tiles_and_results_merged():
    queries = []

    def post(url, data=None, **kw):
        queries.append(data["data"])
        return R(200, ELEMENT)                           # the same element from every tile

    s = OverpassSource(max_places=100, pause=0, radius_km=25, tile_km=25, mirrors=[M1], post=post,
                       sleep=lambda x: None)
    got = s.search("dental clinic", CITY)
    assert len(queries) == 4 and len(got) == 1           # 2 x 2 tiles, one business after merging
    assert len(set(queries)) == 4


def test_one_failed_tile_is_reported_but_the_rest_are_kept():
    n = {"i": 0}

    def post(url, **kw):
        n["i"] += 1
        return R(504) if n["i"] <= 4 else R(200, ELEMENT)      # tile 1 fails on its 4 tries, then all succeed

    s = OverpassSource(max_places=100, pause=0, radius_km=25, tile_km=25, mirrors=[M1], post=post,
                       sleep=lambda x: None)
    got = s.search("dental clinic", CITY)
    assert len(got) == 1 and "1 of 4 parts failed" in s.failures[0]["error"]


def test_no_new_request_starts_after_the_deadline():
    s = OverpassSource(pause=0, mirrors=[M1], post=lambda *a, **k: R(200, ELEMENT), sleep=lambda x: None,
                       deadline=0.0)
    with pytest.raises(DeadlineReached):
        s.search("dental clinic", CITY)


def test_never_more_than_two_requests_at_once():
    import threading
    import time
    live, peak, lock = [0], [0], threading.Lock()

    def post(url, **kw):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.02)
        with lock:
            live[0] -= 1
        return R(200, ELEMENT)

    srcs = [OverpassSource(pause=0, radius_km=5, mirrors=[M1], post=post, sleep=lambda x: None) for _ in range(8)]
    ts = [threading.Thread(target=s.search, args=("dental clinic", CITY)) for s in srcs]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert peak[0] <= 2


# ---------------------------------------------------------------- google discovery
class Meter(Budget):
    def __init__(self, allow):
        self.allow, self.granted, self.refused_reason, self.asked = allow, 0, "", 0

    def reserve(self, kind="text_search"):
        self.asked += 1
        if self.granted >= self.allow:
            self.refused_reason = "daily cap reached"
            return False
        self.granted += 1
        return True


def place(i, status="OPERATIONAL"):
    return {"id": f"ChIJ{i:04d}abcdefghij", "displayName": {"text": f"Clinic {i}"}, "formattedAddress": f"{i} Main St",
            "location": {"latitude": 43.2, "longitude": -79.8}, "types": ["dentist"], "businessStatus": status,
            "nationalPhoneNumber": f"(905) 232-{i:04d}", "websiteUri": "", "googleMapsUri": "https://maps.google.com/?cid=1"}


def pager(pages):
    seq = list(pages)
    calls = []

    def post(url, data=None, headers=None, **kw):
        calls.append({"url": url, "body": json.loads(data), "headers": headers})
        return seq.pop(0)

    post.calls = calls
    return post


class Page:
    def __init__(self, places, token="", status=200):
        self.status_code, self._d = status, {"places": places, **({"nextPageToken": token} if token else {})}

    def json(self):
        return self._d


def test_the_field_mask_is_exactly_the_approved_list():
    assert google_places.FIELD_MASK == (
        "places.id,places.displayName,places.formattedAddress,places.location,places.types,"
        "places.businessStatus,places.nationalPhoneNumber,places.internationalPhoneNumber,"
        "places.websiteUri,places.googleMapsUri,nextPageToken")
    for banned in ("rating", "userRatingCount", "reviews", "photos", "regularOpeningHours", "currentOpeningHours",
                   "editorialSummary", "priceLevel", "primaryType"):
        assert banned not in google_places.FIELD_MASK


def test_the_mask_is_sent_on_every_request_and_the_endpoint_is_text_search():
    post = pager([Page([place(1)], "t1"), Page([place(2)])])
    g = google_places.GoogleDiscovery("k", Meter(10), post=post)
    g.search("dental clinic", {"name": "Hamilton, ON", "lat": 43.2, "lng": -79.8})
    assert all(c["url"] == "https://places.googleapis.com/v1/places:searchText" for c in post.calls)
    assert all(c["headers"]["X-Goog-FieldMask"] == google_places.FIELD_MASK for c in post.calls)
    assert post.calls[0]["body"]["textQuery"] == "dental clinic in Hamilton, ON, Canada"
    assert post.calls[1]["body"]["pageToken"] == "t1"


def test_paging_stops_at_three_pages_and_each_page_reserves_a_call():
    post = pager([Page([place(i)], f"t{i}") for i in range(1, 6)])
    meter = Meter(100)
    g = google_places.GoogleDiscovery("k", meter, post=post)
    got = g.search("dental clinic", {"name": "Hamilton, ON"})
    assert len(post.calls) == 3 and meter.granted == 3 and g.calls == 3
    assert len(got) == 3


def test_a_reservation_is_made_before_each_request():
    order = []

    class M(Meter):
        def reserve(self, kind="text_search"):
            order.append("reserve")
            return super().reserve(kind)

    def post(*a, **k):
        order.append("post")
        return Page([place(1)])

    google_places.GoogleDiscovery("k", M(5), post=post).search("dental clinic", {"name": "X, ON"})
    assert order == ["reserve", "post"]


def test_a_refused_reservation_stops_discovery_cleanly_without_calling_google(capsys):
    post = pager([Page([place(1)], "t1"), Page([place(2)])])
    g = google_places.GoogleDiscovery("k", Meter(1), post=post)
    got = g.search("dental clinic", {"name": "Hamilton, ON"})
    assert len(post.calls) == 1 and len(got) == 1
    assert g.budget_reached and not g.usable
    assert g.search("dentist", {"name": "Toronto, ON"}) == []          # later areas: no call, no error
    assert len(post.calls) == 1
    assert "budget reached" in capsys.readouterr().out


@pytest.mark.parametrize("status", [400, 401, 403, 429])
def test_google_errors_stop_places_for_the_run_and_never_print_the_key(status, capsys):
    key = "AIzaSySECRETKEY1234567890abcdefghijk"
    post = pager([Page([], status=status)])
    g = google_places.GoogleDiscovery(key, Meter(5), post=post)
    assert g.search("dental clinic", {"name": "Hamilton, ON"}) == []
    assert g.stopped and f"HTTP {status}" in g.stopped
    out = capsys.readouterr()
    assert key not in out.out + out.err
    assert out.out.count("not used") == 1                                # one clear line
    assert g.search("x", {"name": "Y, ON"}) == [] and len(post.calls) == 1


def test_a_missing_key_means_no_calls_and_one_line(capsys):
    post = pager([])
    g = google_places.GoogleDiscovery("", Meter(5), post=post)
    assert g.search("dental clinic", {"name": "Hamilton, ON"}) == []
    assert post.calls == [] and "no API key" in capsys.readouterr().out


def test_permanently_closed_places_are_skipped():
    post = pager([Page([place(1), place(2, "CLOSED_PERMANENTLY"), place(3, "CLOSED_TEMPORARILY")])])
    got = google_places.GoogleDiscovery("k", Meter(5), post=post).search("dental clinic", {"name": "X, ON"})
    assert [b.name for b in got] == ["Clinic 1", "Clinic 3"]


def test_network_error_is_a_failure_not_a_crash(capsys):
    def post(*a, **k):
        raise requests.ConnectionError("boom with key AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXX")

    g = google_places.GoogleDiscovery("k", Meter(5), post=post)
    assert g.search("dental clinic", {"name": "X, ON"}) == []
    assert g.failed == 1 and "AIza" not in capsys.readouterr().out


def test_results_are_marked_as_google_so_they_are_never_stored_whole():
    post = pager([Page([place(1)])])
    b = google_places.GoogleDiscovery("k", Meter(5), post=post).search("dental clinic", {"name": "X, ON"})[0]
    assert b.from_google and b.source == "google" and b.google_place_id == b.source_id
