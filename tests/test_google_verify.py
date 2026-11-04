"""The Google check: off by default, shares the backend call budget, keeps only the place_id."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from leadagent import audit, google_verify  # noqa: E402
from leadagent.budget import Budget  # noqa: E402
from leadagent.sources import Business  # noqa: E402

CFG = {
    "country": "CA",
    "google_api_key_env": "TEST_GOOGLE_KEY",
    "google_verify": {"enabled": True, "max_per_run": 3},
    "website_audit": {"social_only_domains": ["facebook.com"]},
    "scoring": {},
}


class FakeBudget(Budget):
    """Grants `allow` reservations, then refuses."""

    def __init__(self, allow=1000):
        self.allow, self.granted, self.refused_reason = allow, 0, ""

    def reserve(self, kind="text_search"):
        if self.granted >= self.allow:
            self.refused_reason = "daily cap reached"
            return False
        self.granted += 1
        return True


def lead(name="Whyte Ridge Dental Centre", phone="+1 204-489-3100", lead_type="NO WEBSITE", score=81):
    b = Business(source="osm", source_id=f"node/{name}", name=name, phone=phone, lat=49.8168, lng=-97.1957,
                 address="147 Scurfield Boulevard", city_query="Winnipeg, MB", business_status="OPERATIONAL",
                 category="dentist", niche_query="dental clinic", source_count=1)
    b.audit = {"verdict": "NO_WEBSITE"}
    b.lead_type, b.opportunity_score, b.reasons = lead_type, score, ["No website at all"]
    return b


def place(name="Whyte Ridge Dental Centre", status="OPERATIONAL", site="", phone="(204) 489-3100",
          lat=49.8169, lng=-97.1958):
    return {"id": "ChIJtest", "displayName": {"text": name}, "businessStatus": status, "websiteUri": site,
            "nationalPhoneNumber": phone, "location": {"latitude": lat, "longitude": lng}}


class Response:
    def __init__(self, status=200, places=None):
        self.status_code, self._places, self.text = status, places or [], "error body with the key"

    def json(self):
        return {"places": self._places}


class Base(unittest.TestCase):
    def setUp(self):
        os.environ["TEST_GOOGLE_KEY"] = "test-key"

    def tearDown(self):
        os.environ.pop("TEST_GOOGLE_KEY", None)

    def verifier(self, budget=None, post=None, **over):
        cfg = {**CFG, "google_verify": {**CFG["google_verify"], **over}}
        v = google_verify.build(cfg, budget or FakeBudget())
        if post is not None:
            v._post = post
        return v


class SwitchTests(Base):
    def test_off_by_default_and_without_a_key(self):
        self.assertIsNone(google_verify.build({"google_verify": {"enabled": False}}, FakeBudget()))
        self.assertIsNone(google_verify.build({}, FakeBudget()))
        os.environ.pop("TEST_GOOGLE_KEY")
        self.assertIsNone(google_verify.build(CFG, FakeBudget()))

    def test_turns_on_only_with_the_flag_and_a_key(self):
        self.assertIsNotNone(self.verifier())

    def test_there_is_no_switch_to_keep_google_content(self):
        import yaml
        root = Path(__file__).resolve().parent.parent
        for name in ("config.yaml", "config-ca.yaml"):
            gv = yaml.safe_load((root / name).read_text(encoding="utf-8"))["google_verify"]
            self.assertNotIn("keep_google_fields", gv, name)
            self.assertNotIn("monthly_call_cap", gv, name)      # the cap lives in the backend now


class BudgetTests(Base):
    def test_per_run_limit_is_respected(self):
        post = mock.Mock(return_value=Response(places=[]))
        gv = self.verifier(post=post, max_per_run=3)
        leads = [lead(f"Clinic {i}") for i in range(6)]
        gv.run(leads)
        self.assertEqual(post.call_count, 3)
        self.assertEqual([b.google_status for b in leads[3:]], ["not_checked"] * 3)

    def test_every_request_reserves_a_call_first(self):
        order = []

        class B(FakeBudget):
            def reserve(self, kind="text_search"):
                order.append("reserve")
                return super().reserve(kind)

        post = mock.Mock(side_effect=lambda *a, **k: order.append("post") or Response(places=[]))
        gv = self.verifier(budget=B(), post=post, max_per_run=2)
        gv.run([lead("A"), lead("B")])
        self.assertEqual(order, ["reserve", "post", "reserve", "post"])

    def test_a_refused_reservation_stops_the_check_without_calling_google(self):
        post = mock.Mock(return_value=Response(places=[]))
        gv = self.verifier(budget=FakeBudget(allow=1), post=post, max_per_run=10)
        leads = [lead(f"Clinic {i}") for i in range(4)]
        summary = gv.run(leads)
        self.assertEqual(post.call_count, 1)
        self.assertTrue(gv.budget_reached)
        self.assertEqual(summary["not_checked"] + summary["error"], 3)

    def test_leads_discovery_already_enriched_are_not_checked_again(self):
        post = mock.Mock(return_value=Response(places=[]))
        gv = self.verifier(post=post)
        known = lead("Known")
        known.from_google = True
        has_id = lead("HasId")
        has_id.google_place_id = "ChIJabc"
        summary = gv.run([known, has_id])
        post.assert_not_called()
        self.assertEqual(summary["skipped_already_known"], 2)

    def test_only_leads_that_need_checking_are_looked_up(self):
        post = mock.Mock()
        gv = self.verifier(post=post)
        gv.run([lead("Has Good Site", lead_type="HAS GOOD SITE"), lead("Weak", lead_type="WEAK SITE")])
        post.assert_not_called()

    def test_a_bad_key_stops_the_run_and_the_rest_pass_through_unchecked(self):
        post = mock.Mock(return_value=Response(status=403))
        gv = self.verifier(post=post, max_per_run=10)
        leads = [lead(f"Clinic {i}") for i in range(4)]
        summary = gv.run(leads)
        self.assertEqual(post.call_count, 1)
        self.assertIn("403", gv.stopped)
        self.assertNotIn("error body", gv.stopped)           # Google's body can echo the request: never kept
        self.assertEqual(summary["error"], 1)
        self.assertEqual(summary["not_checked"], 3)


class MatchTests(Base):
    def test_name_and_place_must_agree(self):
        gv = self.verifier()
        b = lead()
        self.assertIsNotNone(gv.best_match(b, [place()]))
        self.assertIsNone(gv.best_match(b, [place(name="Totally Different Plumbing")]))
        far = place(phone="(204) 000-0000", lat=49.9, lng=-97.3)
        self.assertIsNone(gv.best_match(b, [far]))
        self.assertIsNotNone(gv.best_match(b, [place(lat=49.9, lng=-97.3)]))
        self.assertIsNotNone(gv.best_match(lead("Avenida Chiropractic & Massage", phone=""),
                                           [place(name="Avenida Chiropractic Clinic")]))


class OutcomeTests(Base):
    def run_one(self, places, **over):
        gv = self.verifier(post=mock.Mock(return_value=Response(places=places)), **over)
        b = lead()
        gv.run([b])
        return b

    def test_closed_business_is_dropped(self):
        b = self.run_one([place(status="CLOSED_PERMANENTLY")])
        self.assertEqual(b.opportunity_score, 0)
        self.assertIn("CLOSED_PERMANENTLY", b.reasons[0])

    def test_no_match_costs_score_and_says_so(self):
        b = self.run_one([])
        self.assertEqual(b.google_status, "no_match")
        self.assertEqual(b.opportunity_score, 81 - 20)

    def test_a_website_google_knows_is_graded_and_its_link_is_not_stored(self):
        b = lead(phone="")
        graded = {"verdict": "OK", "https": True, "mobile_friendly": True, "load_seconds": 1,
                  "has_meta_description": True, "title": "Cor-Dent", "listed_url": "https://cor-dent.com",
                  "final_url": "https://cor-dent.com/"}
        gv = self.verifier(post=mock.Mock(return_value=Response(places=[place(site="https://cor-dent.com")])))
        with mock.patch("leadagent.google_verify.audit.audit_site", return_value=dict(graded)):
            gv.run([b])
        self.assertEqual(b.lead_type, "HAS GOOD SITE")
        self.assertEqual(b.audit["final_url"], "")
        self.assertEqual(b.website, "")

    def test_only_the_place_id_is_kept_and_the_phone_is_not_copied(self):
        b = lead(phone="")
        gv = self.verifier(post=mock.Mock(return_value=Response(places=[place()])))
        gv.run([b])
        self.assertEqual(b.google_status, "matched")
        self.assertEqual(b.google_place_id, "ChIJtest")
        self.assertEqual(b.phone, "")                         # Google's number is shown live, never copied
        self.assertEqual(b.phone_status, "google_live")
        self.assertIsNone(b.rating)
        self.assertIsNone(b.review_count)

    def test_the_csv_row_carries_the_place_id_and_status(self):
        b = self.run_one([place()])
        row = b.as_row()
        self.assertEqual(row["google_place_id"], "ChIJtest")
        self.assertEqual(row["google_status"], "matched")


if __name__ == "__main__":
    unittest.main()
