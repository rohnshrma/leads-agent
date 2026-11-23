"""Free quality filters: chains, no-phone records, websites hiding behind an email domain, slow-site retry."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from leadagent import audit, quality  # noqa: E402
from leadagent.sources import Business  # noqa: E402


def biz(name, phone="+1 403-243-8114", email="", website="", lat=51.0, lng=-114.0, brand="", city="Calgary, AB", sid=None):
    return Business(source="osm", source_id=sid or f"node/{abs(hash((name, lat, lng)))}", name=name, phone=phone,
                    email=email, website=website, lat=lat, lng=lng, brand=brand, city_query=city,
                    address="", business_status="OPERATIONAL")


class NameTests(unittest.TestCase):
    def test_location_suffix_and_generic_words_are_dropped(self):
        self.assertEqual(quality.normalise_name("Optimum Wellness Centres - Macleod Trail"), "optimum")
        self.assertEqual(quality.normalise_name("Optimum Wellness Centre"), "optimum")
        self.assertEqual(quality.normalise_name("Smile Dental Clinic Inc."), "smile")


class ChainTests(unittest.TestCase):
    cfg = {"quality_filters": {}}

    def kept(self, found):
        out, rep = quality.apply(found, list(found), self.cfg)
        return [b.name for b in out], rep

    def test_known_chains_from_the_real_run_are_dropped(self):
        names, rep = self.kept([biz("LensCrafters"), biz("Hakim Optical"), biz("Optimum Wellness Centre"),
                                biz("Whyte Ridge Dental Centre", lat=49.8, lng=-97.2)])
        self.assertEqual(names, ["Whyte Ridge Dental Centre"])
        self.assertEqual(rep["chains"], 3)

    def test_osm_brand_tag_marks_a_chain(self):
        names, _ = self.kept([biz("Corner Optical", brand="Some Franchise"), biz("Corner Clinic")])
        self.assertEqual(names, ["Corner Clinic"])

    def test_one_name_at_three_separate_places_is_a_chain_but_two_is_not(self):
        three = [biz("Prairie Smiles", lat=51.0, lng=-114.0), biz("Prairie Smiles", lat=51.1, lng=-114.1),
                 biz("Prairie Smiles", lat=51.2, lng=-114.2)]
        names, rep = self.kept(three)
        self.assertEqual(names, [])
        self.assertEqual(rep["chains"], 3)
        names, _ = self.kept(three[:2])
        self.assertEqual(len(names), 2)

    def test_the_same_building_listed_three_times_is_not_three_locations(self):
        dup = [biz("Prairie Smiles", lat=51.0, lng=-114.0), biz("Prairie Smiles", lat=51.0001, lng=-114.0),
               biz("Prairie Smiles", lat=51.0002, lng=-114.0)]
        names, _ = self.kept(dup)
        self.assertEqual(len(names), 3)

    def test_chain_is_recognised_from_todays_results_even_if_only_one_site_is_new(self):
        found = [biz("Prairie Smiles", lat=51.0 + i / 10, lng=-114.0) for i in range(3)]
        out, _ = quality.apply(found, found[:1], self.cfg)   # two of the three were seen on earlier days
        self.assertEqual(out, [])

    def test_custom_chain_names_come_from_config(self):
        cfg = {"quality_filters": {"chain_names": ["Smiles Dental Group"]}}
        out, _ = quality.apply([biz("Smiles Dental Group Kensington")], [biz("Smiles Dental Group Kensington")], cfg)
        self.assertEqual(out, [])

    def test_filters_can_be_switched_off(self):
        found = [biz("LensCrafters")]
        out, _ = quality.apply(found, found, {"quality_filters": {"enabled": False}})
        self.assertEqual(len(out), 1)


class PhoneAndEmailTests(unittest.TestCase):
    def test_records_without_a_usable_phone_are_kept_and_marked(self):
        found = [biz("No Phone Clinic", phone=""), biz("Short Number", phone="555-0100"), biz("Good Clinic")]
        out, rep = quality.apply(found, found, {})
        self.assertEqual(sorted(b.name for b in out), ["Good Clinic", "No Phone Clinic", "Short Number"])
        self.assertEqual(rep["phone_missing"], 2)
        status = {b.name: b.phone_status for b in out}
        self.assertEqual(status, {"No Phone Clinic": "missing", "Short Number": "missing", "Good Clinic": "found"})

    def test_a_kept_phone_is_stored_in_e164(self):
        found = [biz("Good Clinic", phone="(403) 243-8114 ext 5")]
        out, _ = quality.apply(found, found, {})
        self.assertEqual(out[0].phone, "+14032438114")

    def test_own_domain_email_becomes_a_website_to_audit(self):
        b = biz("Cor-Dent Dental Centre", email="info@cor-dent.com")
        out, rep = quality.apply([b], [b], {})
        self.assertEqual(out[0].website, "https://cor-dent.com")
        self.assertTrue(out[0].website_inferred)
        self.assertEqual(rep["website_inferred"], 1)

    def test_mailbox_providers_do_not_imply_a_website(self):
        for email in ("owner@gmail.com", "owner@shaw.ca", "owner@yahoo.ca", "owner@rogers.com", "nonsense", ""):
            b = biz("Clinic", email=email)
            out, _ = quality.apply([b], [b], {})
            self.assertEqual(out[0].website, "", email)
            self.assertFalse(out[0].website_inferred)

    def test_a_website_already_in_the_map_is_never_overwritten(self):
        b = biz("Clinic", email="info@other.com", website="https://real.example")
        out, _ = quality.apply([b], [b], {})
        self.assertEqual(out[0].website, "https://real.example")
        self.assertFalse(out[0].website_inferred)

    def test_the_score_says_when_the_website_was_inferred(self):
        b = biz("Cor-Dent Dental Centre", email="info@cor-dent.com")
        quality.apply([b], [b], {})
        b.audit = {"verdict": "OK", "https": True, "mobile_friendly": True, "load_seconds": 1,
                   "has_meta_description": True, "title": "x"}
        audit.score(b, {})
        self.assertTrue(any("inferred from the email domain" in r for r in b.reasons))
        self.assertEqual(b.lead_type, "HAS GOOD SITE")


class FakeResponse:
    def __init__(self, status=200, text="<html><head><title>T</title></head><body>" + "welcome " * 80 + "</body></html>"):
        self.status_code, self.text, self.url = status, text, "https://slow.example/"
        self.content = text.encode()


class SlowSiteRetryTests(unittest.TestCase):
    def test_one_timeout_is_retried_and_a_slow_site_is_not_called_broken(self):
        # the first request times out; every later one (including contact-page lookups) succeeds
        replies = [requests.Timeout()] + [FakeResponse()] * 8
        with mock.patch("leadagent.audit.safeurl.safe_get", side_effect=replies) as get, \
                mock.patch("leadagent.audit.time.sleep"):
            res = audit.audit_site("https://slow.example", {"website_audit": {"timeout_seconds": 12}})
        self.assertNotEqual(res["verdict"], "BROKEN")
        self.assertEqual(get.call_args_list[0].kwargs["timeout"], 12)
        self.assertGreater(get.call_args_list[1].kwargs["timeout"], 12)   # second try waits longer
        self.assertEqual(get.call_count, 2)                                # and no contact-page crawl follows

    def test_two_failures_are_still_broken(self):
        with mock.patch("leadagent.audit.safeurl.safe_get", side_effect=requests.ConnectionError()), \
                mock.patch("leadagent.audit.time.sleep"):
            res = audit.audit_site("https://dead.example", {})
        self.assertEqual(res["verdict"], "BROKEN")
        self.assertEqual(res["http_status"], "ConnectionError")
        self.assertEqual(res["listed_url"], "https://dead.example")

    def test_dead_www_host_falls_back_to_the_bare_domain(self):
        def get(url, timeout):
            if "://www." in url:
                raise requests.ConnectionError()
            return FakeResponse()
        with mock.patch("leadagent.audit.safeurl.safe_get", side_effect=get) as g, \
                mock.patch("leadagent.audit.time.sleep"):
            res = audit.audit_site("http://www.kingsway.example/", {})
        self.assertNotEqual(res["verdict"], "BROKEN")
        self.assertEqual(g.call_args_list[2].args[0], "http://kingsway.example/")

    def test_www_twin(self):
        self.assertEqual(audit._www_twin("https://www.a.ca/x"), "https://a.ca/x")
        self.assertEqual(audit._www_twin("http://a.ca"), "http://www.a.ca")
        self.assertEqual(audit._www_twin("http://10.0.0.1/"), "")


    def test_empty_202_is_a_bot_wall_not_a_placeholder(self):
        r = FakeResponse(status=202, text="")
        with mock.patch("leadagent.audit.safeurl.safe_get", return_value=r):
            res = audit.audit_site("https://walled.example", {})
        self.assertEqual(res["verdict"], "BLOCKED")

    def test_chain_inside_a_grocery_store_is_a_chain(self):
        from leadagent import quality
        b = mock.Mock(name="b", website="", brand="")
        b.name = "Theodore & Pringle in No Frills"
        self.assertTrue(quality.chain_reason(b, quality.DEFAULT_CHAIN_NAMES, set(), True))


class FranchiseTests(unittest.TestCase):
    def test_overture_brand_only_counts_for_real_chains(self):
        from leadagent.sources import chain_brand
        self.assertEqual(chain_brand({"brand": "Lifemark", "brand_known": True, "brand_locations": 1}), "Lifemark")
        self.assertEqual(chain_brand({"brand": "Van Rehab", "brand_known": False, "brand_locations": 5}), "Van Rehab")
        self.assertEqual(chain_brand({"brand": "Smile Clinic", "brand_known": False, "brand_locations": 2}), "")
        self.assertEqual(chain_brand({}), "")

    def test_one_website_at_three_places_is_a_group(self):
        from types import SimpleNamespace as B
        from leadagent import quality
        mk = lambda lat, site: B(name=f"Clinic {lat}", website=site, lat=lat, lng=-79.5, address="", city_query="x", brand="")
        found = [mk(43.70, "https://vanrehab.ca/a"), mk(43.80, "http://www.vanrehab.ca"), mk(43.90, "https://vanrehab.ca/"),
                 mk(43.75, "https://solo.ca"), mk(43.85, "https://twoplaces.ca"), mk(43.95, "https://twoplaces.ca")]
        keys = quality.shared_site_keys(found)
        self.assertEqual(keys, {"vanrehab.ca"})
        self.assertEqual(quality.chain_reason(found[0], [], keys, True), "same website at several locations")
        self.assertEqual(quality.chain_reason(found[3], [], keys, True), "")

    def test_independent_names_are_not_caught_by_franchise_words(self):
        from leadagent import quality
        for name in ("Oak Park Dental", "West Coast Dental Care", "Clearly Smiles Orthodontics", "Maple Physiotherapy"):
            from types import SimpleNamespace
            b = SimpleNamespace(name=name, website="", brand="", google_site="")
            self.assertEqual(quality.chain_reason(b, quality.DEFAULT_CHAIN_NAMES, set(), True), "", name)
        for name in ("Massage Addict Vaughan", "HearingLife - Woodbridge", "FYidoctors Maple", "Docbraces Brampton"):
            from types import SimpleNamespace
            b = SimpleNamespace(name=name, website="", brand="", google_site="")
            self.assertNotEqual(quality.chain_reason(b, quality.DEFAULT_CHAIN_NAMES, set(), True), "", name)


if __name__ == "__main__":
    unittest.main()
