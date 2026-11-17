"""Phone normalisation, safe fetching (SSRF, robots, social sites) and log masking."""
import io
import sys
from pathlib import Path
from unittest import mock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from leadagent import phones, safelog, safeurl  # noqa: E402


# ---------------------------------------------------------------- phones
@pytest.mark.parametrize("raw,expected", [
    ("(905) 726-2688", "+19057262688"),
    ("+1-905-726-2688", "+19057262688"),
    ("+1 905-332-7758", "+19053327758"),
    ("1.905.574.3274", "+19055743274"),
    ("905 389 9135", "+19053899135"),
    ("+19024220254", "+19024220254"),
    ("(905) 726-2688 ext. 12", "+19057262688"),
    ("905-726-2688 x4", "+19057262688"),
    ("905-726-2688 #77", "+19057262688"),
    ("  +1 (587) 998-4357  ", "+15879984357"),
])
def test_valid_numbers_become_e164(raw, expected):
    assert phones.normalize_e164(raw) == expected


@pytest.mark.parametrize("raw", [
    "", None, "abc", "12345", "905-726-268", "905-726-26888", "+44 20 7946 0958", "+91 98765 43210",
    "011 44 20 7946 0958", "(055) 123-4567", "(905) 055-1234", "911", "905-411-2345", "1-800-FLOWERS",
    "905-555-0123", "x" * 80, "905 726 2688 and 905 332 7758 and more text here",
])
def test_invalid_or_non_north_american_numbers_become_empty(raw):
    assert phones.normalize_e164(raw) == ""


def test_the_same_number_written_differently_compares_equal():
    assert phones.last10("+1 (905) 726-2688") == phones.last10("905.726.2688") == "9057262688"
    assert phones.last10("12345") == ""


def test_phone_in_text_is_strict():
    assert phones.find_phone_in_text("Call us: (905) 726-2688 today") == "+19057262688"
    assert phones.find_phone_in_text("Order #1234567890123 ref 12-34") == ""
    assert phones.find_phone_in_text("fax 000-000-0000") == ""


# ---------------------------------------------------------------- safe urls
def resolver(*addrs):
    return lambda host, port: [(2, 1, 6, "", (a, 0)) for a in addrs]


@pytest.mark.parametrize("url", [
    "http://localhost/admin", "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/", "http://192.168.1.1/", "http://172.16.0.1/", "http://[::1]/", "http://0.0.0.0/",
    "http://[::ffff:127.0.0.1]/", "ftp://example.com/", "file:///etc/passwd", "javascript:alert(1)",
    "http://user:pass@example.com/", "http://example.com:8080/", "http://example.com:22/",
])
def test_private_or_odd_addresses_are_refused(url):
    with pytest.raises(safeurl.FetchRefused):
        safeurl.check_url(url, resolver("93.184.216.34"))


def test_a_public_name_that_resolves_to_a_private_address_is_refused():
    with pytest.raises(safeurl.FetchRefused):
        safeurl.check_url("http://sneaky.example/", resolver("93.184.216.34", "10.0.0.1"))   # any private answer
    with pytest.raises(safeurl.FetchRefused):
        safeurl.check_url("http://rebind.example/", resolver("169.254.169.254"))


def test_a_public_address_passes():
    assert safeurl.check_url("https://clinic.example/", resolver("93.184.216.34")).startswith("https://")


@pytest.mark.parametrize("url", [
    "https://www.facebook.com/x", "https://m.facebook.com/x", "http://instagram.com/x", "https://linktr.ee/x",
    "https://www.linkedin.com/company/x", "https://tiktok.com/@x", "https://x.com/x", "https://www.yelp.ca/biz/x",
    "https://maps.google.com/?cid=1", "https://g.page/x", "https://www.google.com/maps/place/x",
    "https://www.yellowpages.ca/bus/x", "https://www.ratemds.com/x",
])
def test_social_and_directory_sites_are_never_fetched(url):
    assert safeurl.is_never_fetch(url)
    session = mock.Mock()
    with pytest.raises(safeurl.FetchRefused):
        safeurl.safe_get(url, session=session, resolver=resolver("93.184.216.34"))
    session.get.assert_not_called()


def test_a_business_site_is_not_on_the_never_list():
    assert not safeurl.is_never_fetch("https://hillsidedental.ca")
    assert not safeurl.is_never_fetch("https://notfacebook.com")      # suffix match is on whole labels only


class Resp:
    def __init__(self, status=200, text="", headers=None, content=None):
        self.status_code, self.text, self.headers = status, text, headers or {}
        self.content = content if content is not None else text.encode()


def test_a_redirect_to_a_private_address_is_refused():
    session = mock.Mock()
    session.get.return_value = Resp(302, headers={"Location": "http://169.254.169.254/latest/"})
    res = {"clinic.example": ["93.184.216.34"], "169.254.169.254": ["169.254.169.254"]}
    with pytest.raises(safeurl.FetchRefused):
        safeurl.safe_get("https://clinic.example/", session=session,
                         resolver=lambda h, p: [(2, 1, 6, "", (a, 0)) for a in res[h]])
    assert session.get.call_count == 1                                  # never followed to the private hop


def test_redirect_loops_stop():
    session = mock.Mock()
    session.get.return_value = Resp(302, headers={"Location": "https://clinic.example/again"})
    with pytest.raises(safeurl.FetchRefused):
        safeurl.safe_get("https://clinic.example/", session=session, resolver=resolver("93.184.216.34"))


def test_robots_txt_disallow_is_respected():
    session = mock.Mock()
    session.get.side_effect = [Resp(200, "User-agent: *\nDisallow: /\n"), Resp(200, "hello")]
    with pytest.raises(safeurl.FetchRefused):
        safeurl.safe_get("https://clinic.example/contact", session=session, resolver=resolver("93.184.216.34"),
                         need_robots=True)
    assert session.get.call_count == 1                                  # the page itself was never requested


def test_robots_txt_that_allows_us_lets_the_page_through():
    session = mock.Mock()
    session.get.side_effect = [Resp(200, "User-agent: *\nDisallow: /private\n"), Resp(200, "hello")]
    r = safeurl.safe_get("https://clinic.example/contact", session=session, resolver=resolver("93.184.216.34"),
                         need_robots=True)
    assert r.text == "hello"


def test_a_missing_robots_txt_means_allowed_but_an_unreadable_one_means_no():
    ok = mock.Mock()
    ok.get.side_effect = [Resp(404), Resp(200, "page")]
    assert safeurl.safe_get("https://a.example/", session=ok, resolver=resolver("93.184.216.34"), need_robots=True)
    bad = mock.Mock()
    bad.get.side_effect = requests.Timeout()
    with pytest.raises(safeurl.FetchRefused):
        safeurl.safe_get("https://a.example/", session=bad, resolver=resolver("93.184.216.34"), need_robots=True)
    err = mock.Mock()
    err.get.return_value = Resp(500)
    with pytest.raises(safeurl.FetchRefused):
        safeurl.safe_get("https://a.example/", session=err, resolver=resolver("93.184.216.34"), need_robots=True)


def test_requests_identify_us():
    session = mock.Mock()
    session.get.return_value = Resp(200, "x")
    safeurl.safe_get("https://a.example/", session=session, resolver=resolver("93.184.216.34"))
    assert "rohan@webigeeksdigital.com" in session.get.call_args.kwargs["headers"]["User-Agent"]


# ---------------------------------------------------------------- log masking
@pytest.mark.parametrize("text", [
    "call +1 905-726-2688 now", "(905) 726-2688", "mail me at owner@clinic.ca please", "https://crm.example.com/api/x?token=1",
    "key AIzaSyA1234567890abcdefghijklmnopqrstuv", "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "place ChIJN1t_tDeuEmsRUsoyG83frY4", "node/123456789", "Authorization: Bearer abc.def.ghi",
    "x-goog-api-key: secretvalue", "token 0123456789abcdef0123456789abcdef0123",
])
def test_mask_hides_personal_and_secret_looking_text(text):
    out = safelog.mask(text)
    for needle in ("905", "owner@", "crm.example", "AIza", "ghp_", "ChIJ", "123456789", "abc.def", "secretvalue",
                   "0123456789abcdef"):
        assert needle not in out, (needle, out)


def test_installed_masking_covers_print_and_stderr():
    buf_out, buf_err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "stdout", buf_out), mock.patch.object(sys, "stderr", buf_err):
        safelog.install()
        print("Clinic at (905) 726-2688 https://x.example/a")
        print("owner@x.ca", file=sys.stderr)
    assert "905" not in buf_out.getvalue() and "x.example" not in buf_out.getvalue()
    assert "owner@" not in buf_err.getvalue()


def test_counts_survive_masking():
    assert safelog.mask("overpass found 120 failed 2 calls 7") == "overpass found 120 failed 2 calls 7"
