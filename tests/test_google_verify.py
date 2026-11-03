"""The optional Google check: off by default, capped, and it keeps only what Google's licence allows."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from leadagent import audit, google_verify  # noqa: E402
from leadagent.ledger import Ledger  # noqa: E402
from leadagent.sources import Business  # noqa: E402

CFG = {
    "country": "CA",
    "google_api_key_env": "TEST_GOOGLE_KEY",
    "google_verify": {"enabled": True, "monthly_call_cap": 5, "max_per_run": 3},
    "website_audit": {"social_only_domains": ["facebook.com"]},
    "scoring": {"reviews_bonus_tiers": [[200, 15], [75, 12], [25, 8], [5, 4]]},
}


def lead(name="Whyte Ridge Dental Centre", phone="+1 204-489-3100", lead_type="NO WEBSITE", score=81):
    b = Business(source="osm", source_id=f"node/{name}", name=name, phone=phone, lat=49.8168, lng=-97.1957,
                 address="147 Scurfield Boulevard", city_query="Winnipeg, MB", business_status="OPERATIONAL",
                 category="dentist", niche_query="dental clinic", source_count=1)
    b.audit = {"verdict": "NO_WEBSITE"}
    b.lead_type, b.opportunity_score, b.reasons = lead_type, score, ["No website at all"]
    return b


def place(name="Whyte Ridge Dental Centre", status="OPERATIONAL", site="", phone="(204) 489-3100", rating=4.8, count=259,
          lat=49.8169, lng=-97.1958):
    return {"id": "ChIJtest", "displayName": {"text": name}, "businessStatus": status, "websiteUri": site,
            "nationalPhoneNumber": phone, "rating": rating, "userRatingCount": count,
            "location": {"latitude": lat, "longitude": lng}}


class Response:
    def __init__(self, status=200, places=None):
        self.status_code, self._places, self.text = status, places or [], "error body"

    def json(self):
        return {"places": self._places}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(str(Path(self.tmp.name) / "leads.db"))
        os.environ["TEST_GOOGLE_KEY"] = "test-key"

    def tearDown(self):
        os.environ.pop("TEST_GOOGLE_KEY", None)
        self.ledger.con.close()
        self.tmp.cleanup()

    def verifier(self, **over):
        cfg = {**CFG, "google_verify": {**CFG["google_verify"], **over}}
        return google_verify.build(cfg, self.ledger)


class SwitchTests(Base):
    def test_off_by_default_and_without_a_key(self):
        self.assertIsNone(google_verify.build({"google_verify": {"enabled": False}}, self.ledger))
        self.assertIsNone(google_verify.build({}, self.ledger))
        os.environ.pop("TEST_GOOGLE_KEY")
        self.assertIsNone(google_verify.build(CFG, self.ledger))

    def test_turns_on_only_with_the_flag_and_a_key(self):
        self.assertIsNotNone(self.verifier())

    def test_the_shipped_configs_stay_inside_the_free_allowance(self):
        """Google check is on (owner's choice) but the two markets together must stay under 1,000 requests a month."""
        import yaml
        root = Path(__file__).resolve().parent.parent
        per_day = monthly = 0
        for name in ("config.yaml", "config-ca.yaml"):
            cfg = yaml.safe_load((root / name).read_text(encoding="utf-8"))
            gv = cfg["google_verify"]
            self.assertTrue(gv["enabled"], name)
            self.assertFalse(gv["keep_google_fields"], name)
            per_day += gv["max_per_run"]
            monthly += gv["monthly_call_cap"]
        self.assertLessEqual(per_day, 30)
        self.assertLessEqual(monthly, 1000)


class BudgetTests(Base):
    def test_per_run_limit_and_monthly_cap_are_never_exceeded(self):
        gv = self.verifier(monthly_call_cap=5, max_per_run=3)
        leads = [lead(f"Clinic {i}") for i in range(6)]
        with mock.patch("leadagent.google_verify.requests.post", return_value=Response(places=[])) as post:
            gv.run(leads)
        self.assertEqual(post.call_count, 3)                              # max_per_run
        self.assertEqual([b.google_status for b in leads[3:]], ["not_checked"] * 3)
        gv2 = self.verifier(monthly_call_cap=5, max_per_run=10)           # a new morning, same month
        self.assertEqual(gv2.remaining(), 2)                              # 3 of 5 already used
        with mock.patch("leadagent.google_verify.requests.post", return_value=Response(places=[])) as post:
            gv2.run([lead(f"Other {i}") for i in range(5)])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(gv2.meter.used(), 5)

    def test_only_leads_that_need_checking_are_looked_up(self):
        gv = self.verifier()
        keep = [lead("Has Good Site", lead_type="HAS GOOD SITE"), lead("Weak", lead_type="WEAK SITE")]
        with mock.patch("leadagent.google_verify.requests.post") as post:
            gv.run(keep)
        post.assert_not_called()

    def test_a_bad_key_stops_the_run_and_the_rest_pass_through_unchecked(self):
        gv = self.verifier(max_per_run=10)
        leads = [lead(f"Clinic {i}") for i in range(4)]
        with mock.patch("leadagent.google_verify.requests.post", return_value=Response(status=403)) as post:
            summary = gv.run(leads)
        self.assertEqual(post.call_count, 1)
        self.assertIn("403", gv.stopped)
        self.assertEqual(summary["error"], 1)
        self.assertEqual(summary["not_checked"], 3)


class MatchTests(Base):
    def test_name_and_place_must_agree(self):
        gv = self.verifier()
        b = lead()
        self.assertIsNotNone(gv.best_match(b, [place()]))
        self.assertIsNone(gv.best_match(b, [place(name="Totally Different Plumbing")]))    # even with the same phone
        far = place(phone="(204) 000-0000", lat=49.9, lng=-97.3)
        self.assertIsNone(gv.best_match(b, [far]))                                         # same name, too far away
        # a shared phone makes up for distance only when the names are partly alike
        self.assertIsNotNone(gv.best_match(b, [place(lat=49.9, lng=-97.3)]))
        action = lead("Action Chiropractic", phone="+1 403-243-8114")
        self.assertIsNotNone(gv.best_match(action, [place(name="Action Health", phone="(403) 243-8114",
                                                          lat=49.8168, lng=-97.1957)]))
        self.assertIsNotNone(gv.best_match(lead("Avenida Chiropractic & Massage", phone=""),
                                           [place(name="Avenida Chiropractic Clinic")]))   # near-identical name


class OutcomeTests(Base):
    def run_one(self, places, **over):
        gv = self.verifier(**over)
        b = lead()
        with mock.patch("leadagent.google_verify.requests.post", return_value=Response(places=places)):
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
        self.assertTrue(any("Not found on Google" in r for r in b.reasons))

    def test_a_website_google_knows_is_graded_and_its_link_is_not_stored(self):
        graded = {"verdict": "OK", "https": True, "mobile_friendly": True, "load_seconds": 1, "has_meta_description": True,
                  "title": "Cor-Dent", "listed_url": "https://cor-dent.com", "final_url": "https://cor-dent.com/"}
        with mock.patch("leadagent.google_verify.audit.audit_site", return_value=dict(graded)):
            b = self.run_one([place(site="https://cor-dent.com")])
        self.assertEqual(b.lead_type, "HAS GOOD SITE")                    # no longer a "no website" lead
        self.assertLess(b.opportunity_score, 40)
        self.assertEqual(b.audit["final_url"], "")
        self.assertEqual(b.website, "")

    def test_verified_no_website_gets_a_review_bonus_but_google_numbers_are_not_kept(self):
        b = self.run_one([place()])
        self.assertEqual(b.google_status, "matched")
        self.assertEqual(b.google_place_id, "ChIJtest")
        self.assertIsNone(b.rating)
        self.assertIsNone(b.review_count)
        text = " ".join(b.reasons)
        self.assertIn("Verified on Google", text)
        self.assertNotIn("259", text)
        self.assertNotIn("4.8", text)
        self.assertNotIn("(4.8*)", text)
        self.assertGreater(b.opportunity_score, 81 - 20)                  # reviews counted in the score

    def test_google_fields_are_kept_only_when_asked(self):
        b = self.run_one([place()], keep_google_fields=True)
        self.assertEqual(b.rating, 4.8)
        self.assertEqual(b.review_count, 259)
        self.assertIn("259", " ".join(b.reasons))

    def test_the_csv_row_carries_the_place_id_and_status(self):
        b = self.run_one([place()])
        row = b.as_row()
        self.assertEqual(row["google_place_id"], "ChIJtest")
        self.assertEqual(row["google_status"], "matched")
        self.assertEqual(row["rating"], None)


if __name__ == "__main__":
    unittest.main()
