"""Cross-source de-duplication, phone enrichment order, and a fully mocked end-to-end fetch."""
import csv
import json
import re
import sys
from pathlib import Path
from unittest import mock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run as run_mod  # noqa: E402
from leadagent import dedupe, enrich, google_places, pipeline, safeurl  # noqa: E402
from leadagent.budget import Budget  # noqa: E402
from leadagent.google_verify import GoogleVerifier  # noqa: E402
from leadagent.sources import Business, OverpassSource, OvertureSource  # noqa: E402


def biz(name, source="osm", sid=None, phone="", website="", lat=43.25, lng=-79.87, pid="", **kw):
    return Business(source=source, source_id=sid or f"{source}/{name}", name=name, phone=phone, website=website,
                    lat=lat, lng=lng, google_place_id=pid, from_google=(source == "google"), city_query="Hamilton, ON",
                    niche_query="dental clinic", business_status="OPERATIONAL", **kw)


# ---------------------------------------------------------------- de-dup, each rule
def test_matches_by_place_id():
    a = biz("Hillside Dental", pid="ChIJx", lat=43.2, lng=-79.8)
    b = biz("Totally Different Name", "google", sid="ChIJx", pid="ChIJx", lat=43.201, lng=-79.801)
    out, st = dedupe.merge([a, b])
    assert len(out) == 1 and st["by_place_id"] >= 1


def test_matches_by_normalised_phone_written_differently():
    a = biz("Hillside Dental", phone="+1 905-526-1234")
    b = biz("Hillside Dental Care", "overture", phone="(905) 526 1234", lat=43.2501, lng=-79.8701)
    out, st = dedupe.merge([a, b])
    assert len(out) == 1 and st["by_phone"] == 1


def test_matches_by_website_domain_ignoring_www_and_scheme():
    a = biz("Hillside Dental", website="https://www.hillsidedental.ca/contact")
    b = biz("Hillside Family Dentistry", "overture", website="http://hillsidedental.ca", lat=43.2501, lng=-79.8701)
    out, st = dedupe.merge([a, b])
    assert len(out) == 1 and st["by_domain"] == 1


def test_social_and_builder_domains_never_merge_different_businesses():
    a = biz("Alpha Massage", website="https://facebook.com/alphamassage", lat=43.1)
    b = biz("Beta Massage", website="https://facebook.com/betamassage", lat=43.4)
    c = biz("Gamma Spa", website="https://gamma.wixsite.com/x", lat=43.5)
    d = biz("Delta Spa", website="https://delta.wixsite.com/y", lat=43.6)
    assert len(dedupe.merge([a, b, c, d])[0]) == 4


def test_matches_by_name_within_75_metres():
    a = biz("Hillside Dental", lat=43.25000, lng=-79.87000)
    b = biz("Hillside Dental Inc.", "overture", lat=43.25030, lng=-79.87010)       # about 35 m
    out, st = dedupe.merge([a, b])
    assert len(out) == 1 and st["by_name"] == 1


def test_same_name_two_kilometres_apart_is_two_businesses():
    a = biz("Hillside Dental", lat=43.2500, lng=-79.8700)
    b = biz("Hillside Dental", "overture", lat=43.2680, lng=-79.8700)              # about 2 km
    assert len(dedupe.merge([a, b])[0]) == 2


def test_a_shared_head_office_phone_does_not_merge_far_apart_branches():
    a = biz("Smile Care Hamilton", phone="+19055261234", lat=43.25, lng=-79.87)
    b = biz("Smile Care Ottawa", "overture", phone="+19055261234", lat=45.42, lng=-75.69)
    assert len(dedupe.merge([a, b])[0]) == 2


def test_the_same_osm_record_found_by_two_searches_is_one_lead():
    a, b = biz("Eye Place", sid="node/9"), biz("Eye Place", sid="node/9")
    assert len(dedupe.merge([a, b])[0]) == 1


def test_stored_data_wins_over_google_and_google_fields_are_not_copied():
    osm = biz("Hillside Dental", phone="+19055261234")
    g = biz("Hillside Dental Centre", "google", sid="ChIJ1", pid="ChIJ1", phone="+19055261234",
            website="https://hillsidedental.ca", lat=43.2501, lng=-79.8701)
    out, _ = dedupe.merge([g, osm])                      # Google listed first, as in a real run
    assert len(out) == 1
    kept = out[0]
    assert kept.source == "osm" and kept.google_place_id == "ChIJ1"
    assert kept.website == "" and kept.name == "Hillside Dental"       # nothing of Google's was copied over


def test_missing_fields_are_filled_from_another_stored_source():
    osm = biz("Hillside Dental", phone="+19055261234")
    ov = biz("Hillside Dental", "overture", phone="+19055261234", website="https://hillsidedental.ca", lat=43.2501)
    kept = dedupe.merge([osm, ov])[0][0]
    assert kept.website == "https://hillsidedental.ca"


# ---------------------------------------------------------------- enrichment order a -> b -> c
class Meter(Budget):
    def __init__(self, allow=100):
        self.allow, self.granted, self.refused_reason = allow, 0, ""

    def reserve(self, kind="text_search"):
        if self.granted >= self.allow:
            self.refused_reason = "cap"
            return False
        self.granted += 1
        return True


def no_phone_lead(name="Hillside Dental", website="", lead_type="NO WEBSITE", lat=43.25, lng=-79.87):
    b = biz(name, website=website, lat=lat, lng=lng)
    b.lead_type, b.phone_status = lead_type, "missing"
    return b


def verifier(post=None, meter=None):
    cfg = {"country": "CA", "google_verify": {"enabled": True, "max_per_run": 5}}
    return GoogleVerifier(cfg, "k", meter or Meter(), post=post or mock.Mock())


def gplace(name, phone="(905) 526-1234", pid="ChIJp1"):
    return {"id": pid, "displayName": {"text": name}, "nationalPhoneNumber": phone,
            "location": {"latitude": 43.2501, "longitude": -79.8701}, "businessStatus": "OPERATIONAL"}


def test_step_a_uses_google_results_already_fetched_and_makes_no_call():
    b = no_phone_lead()
    pool = [biz("Hillside Dental", "google", sid="ChIJp1", pid="ChIJp1", phone="+19055261234", lat=43.2501, lng=-79.8701)]
    post = mock.Mock()
    v = verifier(post)
    stats = enrich.enrich_phones([b], pool, v)
    post.assert_not_called()
    assert stats["from_google_pool"] == 1 and b.phone_status == "google_live" and b.phone == "" and b.google_place_id == "ChIJp1"


def test_step_b_does_one_lookup_only_when_a_finds_nothing():
    b = no_phone_lead()
    resp = mock.Mock(status_code=200)
    resp.json.return_value = {"places": [gplace("Hillside Dental")]}
    post = mock.Mock(return_value=resp)
    stats = enrich.enrich_phones([b], [], verifier(post))
    assert post.call_count == 1 and stats["from_google_lookup"] == 1
    assert b.phone == "" and b.phone_status == "google_live"            # the number itself is not copied


def test_step_b_respects_the_shared_budget():
    b = no_phone_lead()
    post = mock.Mock()
    stats = enrich.enrich_phones([b], [], verifier(post, Meter(allow=0)))
    post.assert_not_called()
    assert b.phone_status == "missing" and stats["still_missing"] == 1


def test_step_c_reads_the_leads_own_website_and_stores_that_phone():
    b = no_phone_lead(website="https://hillsidedental.ca", lead_type="BROKEN SITE")
    page = mock.Mock(status_code=200, text='<a href="tel:+1-905-526-1234">Call</a>')
    fetch = mock.Mock(return_value=page)
    stats = enrich.enrich_phones([b], [], None, fetch=fetch)
    assert b.phone == "+19055261234" and b.phone_status == "found" and stats["from_own_site"] == 1
    assert fetch.call_args.kwargs["need_robots"] is True and fetch.call_args.kwargs["timeout"] == 10.0


def test_step_c_finds_a_phone_in_plain_text_only_with_the_strict_pattern():
    b = no_phone_lead(website="https://hillsidedental.ca", lead_type="BROKEN SITE")
    fetch = mock.Mock(return_value=mock.Mock(status_code=200, text="<p>Phone: (905) 526-1234 | ref 1234567890123</p>"))
    enrich.enrich_phones([b], [], None, fetch=fetch)
    assert b.phone == "+19055261234"


def test_social_sites_are_never_fetched_and_the_lead_stays_phone_missing():
    b = no_phone_lead(website="https://www.facebook.com/hillside", lead_type="SOCIAL ONLY")
    fetch = mock.Mock()
    stats = enrich.enrich_phones([b], [], None, fetch=fetch)
    fetch.assert_not_called()
    assert b.phone_status == "missing" and stats["still_missing"] == 1


def test_a_slow_or_failing_own_site_is_skipped_without_crashing():
    for exc in (requests.Timeout(), requests.ConnectionError(), RuntimeError("x"), safeurl.FetchRefused("robots")):
        b = no_phone_lead(website="https://hillsidedental.ca", lead_type="BROKEN SITE")
        enrich.enrich_phones([b], [], None, fetch=mock.Mock(side_effect=exc))
        assert b.phone_status == "missing" and b.phone == ""


def test_order_is_a_then_b_then_c():
    calls = []
    b = no_phone_lead(website="https://hillsidedental.ca", lead_type="BROKEN SITE")
    post = mock.Mock(side_effect=lambda *a, **k: calls.append("b") or mock.Mock(status_code=200, json=lambda: {"places": []}))
    fetch = mock.Mock(side_effect=lambda *a, **k: calls.append("c") or mock.Mock(status_code=200, text="call 905 526 1234"))
    enrich.enrich_phones([b], [], verifier(post), fetch=fetch)
    assert calls == ["b", "c"] and b.phone == "+19055261234"


def test_no_email_is_ever_extracted():
    b = no_phone_lead(website="https://hillsidedental.ca", lead_type="BROKEN SITE")
    page = mock.Mock(status_code=200, text="write to owner@hillsidedental.ca or call (905) 526-1234")
    enrich.enrich_phones([b], [], None, fetch=mock.Mock(return_value=page))
    assert b.email == "" and "owner@" not in json.dumps(b.as_row(), default=str)


# ---------------------------------------------------------------- the whole fetch, mocked
class Page:
    def __init__(self, places):
        self.status_code, self._d = 200, {"places": places}

    def json(self):
        return self._d


def google_place(pid, name, phone, lat, lng, website=""):
    return {"id": pid, "displayName": {"text": name}, "formattedAddress": "1 Secret Street, Hamilton",
            "location": {"latitude": lat, "longitude": lng}, "types": ["dentist"], "businessStatus": "OPERATIONAL",
            "nationalPhoneNumber": phone, "websiteUri": website, "googleMapsUri": "https://maps.google.com/?cid=7"}


GOOGLE_PLACES = [
    google_place("ChIJdup0000000001", "Hillside Dental", "(905) 526-1234", 43.2501, -79.8701),     # same as OSM + Overture
    google_place("ChIJonly0000000002", "Only On Google Dental", "(905) 232-9999", 43.30, -79.90),
    google_place("ChIJsite0000000003", "Googleweb Dental", "(905) 232-7777", 43.31, -79.91, "https://googleweb.ca"),
]
OSM_ELEMENTS = {"elements": [
    {"type": "node", "id": 11, "lat": 43.2500, "lon": -79.8700,
     "tags": {"name": "Hillside Dental", "amenity": "dentist", "phone": "+1 905-526-1234", "email": "owner@hillside.ca"}},
    {"type": "node", "id": 12, "lat": 43.40, "lon": -79.70, "tags": {"name": "No Phone Dental", "amenity": "dentist"}},
]}
OVERTURE_ROWS = [
    {"id": "ov1", "name": "Hillside Dental Inc.", "category": "dentist", "street": "1 A St", "locality": "Hamilton",
     "region": "ON", "website": "", "phone": "+19055261234", "email": "", "confidence": 0.9, "source_count": 2,
     "lat": 43.2501, "lng": -79.8701},
    {"id": "ov2", "name": "Overture Only Dental", "category": "dentist", "street": "2 B St", "locality": "Hamilton",
     "region": "ON", "website": "", "phone": "+19055550111", "email": "", "confidence": 0.9, "source_count": 2,
     "lat": 43.5, "lng": -79.5},
]
CFG = {
    "country": "CA", "min_score_to_report": 0, "niches": ["dental clinic"],
    "discovery": ["google", "overture", "overpass"],
    "website_audit": {"enabled": True, "social_only_domains": ["facebook.com"]},
    "google_verify": {"enabled": True, "max_per_run": 5},
    "quality_filters": {"enabled": True},
    "scoring": {}, "output": {"dir": "out", "write_csv": True, "write_html": False},
}
AREAS = [("dental clinic", {"name": f"Area {i}, ON", "lat": 43.2 + i / 100, "lng": -79.8}) for i in range(3)]


def fake_audit(url, cfg):
    return {"verdict": "NO_WEBSITE"} if not url else {"verdict": "WEAK", "https": False, "mobile_friendly": False,
                                                       "load_seconds": 1, "has_meta_description": False, "title": "x"}


def make_sources(meter, google_pages):
    post = mock.Mock(side_effect=lambda *a, **k: google_pages.pop(0) if google_pages else Page([]))
    g = google_places.GoogleDiscovery("secretkey", meter, post=post)
    op = OverpassSource(pause=0, radius_km=5, mirrors=["https://m1.example/a"], sleep=lambda x: None,
                        post=lambda *a, **k: mock.Mock(status_code=200, headers={}, json=lambda: OSM_ELEMENTS))
    ov = OvertureSource(query=lambda n, c: OVERTURE_ROWS)
    return {"google": g, "overture": ov, "overpass": op}, post


def test_one_all_of_canada_fetch_merges_dedupes_scores_and_respects_the_cap():
    meter = Meter(allow=2)                                            # only 2 Google calls allowed this run
    sources, post = make_sources(meter, [Page(GOOGLE_PLACES), Page(GOOGLE_PLACES), Page(GOOGLE_PLACES)])
    with mock.patch("leadagent.pipeline.audit.audit_site", side_effect=fake_audit), \
            mock.patch("leadagent.safeurl.safe_get", side_effect=safeurl.FetchRefused("n/a")):
        rows, summary = pipeline.run(CFG, AREAS, sources=sources, budget=meter)

    assert meter.granted <= 2 and post.call_count <= 2                # the cap held, even mid-run
    assert summary["sources"]["google"]["calls"] <= 2
    assert summary["sources"]["google"]["found"] >= 1
    assert any("budget reached" in n for n in summary["notes"])       # a normal outcome, not an error
    assert summary["sources"]["overture"]["found"] == 2 * len(AREAS)
    assert summary["sources"]["overpass"]["found"] == 2 * len(AREAS)
    assert summary["pairs"]["completed"] == len(AREAS) and summary["pairs"]["failed"] == 0

    # the one business all three sources found is ONE lead, and it is the stored (OSM) record
    names = [b.name for b in rows]
    assert names.count("Hillside Dental") == 1
    merged = next(b for b in rows if b.name == "Hillside Dental")
    assert merged.source == "osm" and merged.google_place_id == "ChIJdup0000000001"
    assert summary["merge"]["merged"] > 0
    assert "Overture Only Dental" in names and "No Phone Dental" in names     # no-phone lead kept
    nophone = next(b for b in rows if b.name == "No Phone Dental")
    assert nophone.phone == "" and nophone.phone_status in ("missing", "google_live")
    assert all(b.lead_type for b in rows)                              # everything scored and typed


def test_google_sourced_leads_are_saved_as_place_id_and_scores_only():
    meter = Meter(allow=10)
    sources, _ = make_sources(meter, [Page(GOOGLE_PLACES)])
    with mock.patch("leadagent.pipeline.audit.audit_site", side_effect=fake_audit), \
            mock.patch("leadagent.safeurl.safe_get", side_effect=safeurl.FetchRefused("n/a")):
        rows, _ = pipeline.run(CFG, AREAS[:1], sources={"google": sources["google"]}, budget=meter)
    google_rows = [pipeline.to_row(b, CFG) for b in rows if b.source == "google"]
    assert len(google_rows) == 3
    blob = json.dumps(google_rows)
    for secret in ("Only On Google", "Googleweb", "Secret Street", "905) 232", "232-9999", "googleweb.ca", "maps.google",
                   "dentist", "43.30"):
        assert secret not in blob, secret
    for r in google_rows:
        assert set(r) <= set(pipeline.GOOGLE_ROW_FIELDS)
        assert r["source"] == "google" and r["place_id"].startswith("ChIJ") and r["fetched_at"]
        assert r["phone_status"] == "google_live"
        assert not any(k in r for k in ("name", "address", "phone", "website", "email", "lat", "lng", "category"))


def test_nothing_google_says_reaches_a_file_a_log_or_the_summary(tmp_path, monkeypatch, capsys):
    meter = Meter(allow=10)
    sources, _ = make_sources(meter, [Page(GOOGLE_PLACES)])
    monkeypatch.setattr(run_mod, "ROOT", tmp_path)
    monkeypatch.setattr(run_mod, "build_sources", lambda cfg, budget, dry, deadline: sources)
    monkeypatch.setattr(run_mod.queue_client, "claim_batch", lambda n: {
        "items": [{"id": f"q{i}", "niche": n_, "city": c} for i, (n_, c) in enumerate(AREAS)], "progress": {}})
    monkeypatch.setattr(run_mod.budget_mod, "from_env", lambda: meter)
    cfg_path = tmp_path / "cfg.yaml"
    import yaml
    cfg_path.write_text(yaml.safe_dump({**CFG, "cities": [c for _, c in AREAS]}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["run.py", "--config", str(cfg_path)])
    with mock.patch("leadagent.pipeline.audit.audit_site", side_effect=fake_audit), \
            mock.patch("leadagent.safeurl.safe_get", side_effect=safeurl.FetchRefused("n/a")):
        assert run_mod.main() == 0

    out = capsys.readouterr()
    log = out.out + out.err
    banned = [r"\(\d{3}\)\s*\d{3}", r"\+1[\s-]?\d{3}", r"\b\d{3}[-. ]\d{3}[-. ]\d{4}\b", r"@[a-z0-9-]+\.", r"https?://",
              r"ChIJ", r"node/\d", "Hillside", "Dental", "Secret Street", "secretkey", "Area 0", "Hamilton"]
    for pat in banned:
        assert not re.search(pat, log), (pat, log)
    assert "reported" in log and "pairs" in log                         # but the counts are there

    files = {p.name: p.read_text(encoding="utf-8") for p in (tmp_path / "out").glob("*") if p.is_file()}
    assert "summary.json" in files and any(n.endswith(".csv") for n in files)
    for name, text in files.items():
        for secret in ("Only On Google", "Googleweb", "Secret Street", "232-9999", "googleweb.ca", "maps.google.com"):
            assert secret not in text, (name, secret)
        assert "owner@hillside.ca" not in text                           # emails are never saved
    assert not any(n.endswith(".html") for n in files)                   # no lead pages are written for display
    s = json.loads(files["summary.json"])
    assert s["mode"] == "queue" and len(s["queue"]) == len(AREAS)
    assert "Area 0" in json.dumps(s["failures"]) or s["failures"] == []   # the summary may name areas, never businesses

    csv_text = next(t for n, t in files.items() if n.endswith(".csv"))
    rows = list(csv.DictReader(csv_text.splitlines()))
    assert rows and all(r["email"] == "" for r in rows if "email" in r)


def test_a_search_that_fails_is_a_failure_in_the_summary_not_zero_results():
    meter = Meter(allow=0)
    op = OverpassSource(pause=0, radius_km=5, mirrors=["https://m1.example/a"], sleep=lambda x: None,
                        post=lambda *a, **k: mock.Mock(status_code=504, headers={}, json=lambda: {}))
    with mock.patch("leadagent.pipeline.audit.audit_site", side_effect=fake_audit):
        rows, s = pipeline.run(CFG, AREAS[:2], sources={"overpass": op}, budget=meter)
    assert rows == [] and s["sources"]["overpass"]["failed"] == 2 and s["sources"]["overpass"]["found"] == 0
    assert s["pairs"] == {"planned": 2, "completed": 0, "failed": 2, "not_run": 0}
    assert s["failures"][0]["type"] == "dental clinic" and s["failures"][0]["error"] == "HTTP 504"


def test_the_run_stops_itself_at_the_time_limit_and_reports_the_rest_as_not_run():
    t = {"now": 0.0}

    def clock():
        return t["now"]

    class Slow:
        def search(self, niche, city):
            t["now"] += 700.0                       # each search "takes" 11+ minutes
            return [biz("Slow Dental", sid=f"node/{city['name']}", phone="+19055261234", lat=43.0 + len(city['name']))]

    with mock.patch("leadagent.pipeline.time.monotonic", clock), \
            mock.patch("leadagent.pipeline.audit.audit_site", side_effect=fake_audit):
        rows, s = pipeline.run(CFG, AREAS + AREAS, sources={"overpass": Slow()}, budget=Meter(0),
                               time_limit=40 * 60, clock=clock)
    assert s["stopped_early"] == "time limit"
    assert s["pairs"]["completed"] == 4 and s["pairs"]["not_run"] == 2         # a 5th would start at 2,800 s > 40 min; the rest is requeued
    assert rows                                                                # what was found is still returned


def test_leads_without_a_phone_are_kept_through_the_whole_pipeline():
    class Src:
        def search(self, niche, city):
            return [biz("Quiet Dental", sid="node/1", phone="", lat=43.7)]

    with mock.patch("leadagent.pipeline.audit.audit_site", side_effect=fake_audit), \
            mock.patch("leadagent.safeurl.safe_get", side_effect=safeurl.FetchRefused("n/a")):
        rows, s = pipeline.run(CFG, AREAS[:1], sources={"overpass": Src()}, budget=Meter(0))
    assert [b.name for b in rows] == ["Quiet Dental"]
    assert rows[0].phone_status == "missing" and s["phone"] == {"missing": 1}
    assert "no_phone" not in s["dropped"]
