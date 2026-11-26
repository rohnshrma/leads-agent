"""Fixes from the first India run (2026-11-26): each test is one thing that came in wrong."""
import sys
from pathlib import Path
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from leadagent import audit, categorize, dedupe, pipeline, quality, safeurl  # noqa: E402
from leadagent.budget import Budget  # noqa: E402
from leadagent.sources import Business  # noqa: E402

IN_NICHES = ["dental clinic", "orthodontist", "skin and hair clinic", "coaching institute", "interior designer",
             "physiotherapist", "eye clinic", "veterinary clinic", "preschool", "gym fitness studio",
             "real estate agent"]


def ov(name, niche="skin and hair clinic", sid=None, **kw):
    return Business(source="overture", source_id=sid or name, name=name, niche_query=niche, **kw)


# --- business type ---------------------------------------------------------------------------------
def test_the_india_settings_turn_on_the_other_trade_check():
    import yaml
    cfg = yaml.safe_load((Path(__file__).resolve().parent.parent / "config-in.yaml").read_text(encoding="utf-8"))
    assert cfg["drop_other_trades"] is True and cfg["lead_mix"]["max_per_search"] == 6


def test_an_events_company_filed_under_a_skin_category_is_dropped():
    out, rep = categorize.apply([ov("Example Corporate Events")], {"niches": IN_NICHES, "drop_other_trades": True})
    assert out == [] and rep["wrong_category"] == 1


def test_other_trade_words_need_whole_words_and_never_beat_our_type():
    keep = [ov("Contours Skin Clinic"), ov("Skin Cafe & Laser Clinic"), ov("Preventive Physio Care", "physiotherapist"),
            ov("Glow Aesthetics")]
    out, rep = categorize.apply(keep, {"niches": IN_NICHES, "drop_other_trades": True})
    assert len(out) == 4 and rep["wrong_category"] == 0


# --- duplicates ------------------------------------------------------------------------------------
def test_same_clinic_with_the_site_on_one_record_and_the_email_on_the_other_is_one_lead():
    a = ov("Dr. Example - Dermatology Clinic", website="http://skinclinic.example/", phone="+919800000001",
           lat=28.46, lng=77.08)
    b = ov("Example Derma", email="info@skinclinic.example", phone="+919800000002", lat=28.4609, lng=77.0806)
    merged, stats = dedupe.merge([a, b])
    assert len(merged) == 1 and stats["by_domain"] == 1


def test_a_shared_free_mailbox_never_merges_two_clinics():
    a = ov("Glow Skin Clinic", email="glowskin@rediffmail.com", lat=28.46, lng=77.08)
    b = ov("Hair Studio Plus", email="hairplus@rediffmail.com", lat=28.4601, lng=77.0801)
    assert len(dedupe.merge([a, b])[0]) == 2


def test_an_indian_mailbox_is_never_taken_as_the_business_website():
    for mail in ("clinic@rediffmail.com", "clinic@yahoo.co.in", "clinic@outlook.in"):
        assert quality.own_domain(mail) == ""
    assert quality.own_domain("info@skinclinic.example") == "skinclinic.example"


# --- website grading -------------------------------------------------------------------------------
def test_a_dead_web_address_is_broken_and_says_so_in_plain_words():
    with mock.patch("leadagent.safeurl.safe_get", side_effect=safeurl.FetchRefused("host does not resolve")):
        a = audit.audit_site("http://www.hairclinic.example/", {})
    assert a["verdict"] == "BROKEN" and a["broken_reason"] == "the web address no longer exists"


def test_a_site_we_would_not_read_is_not_called_broken():
    for why in ("page too large", "too many redirects"):
        with mock.patch("leadagent.safeurl.safe_get", side_effect=safeurl.FetchRefused(why)):
            assert audit.audit_site("https://bigsite.in/", {})["verdict"] == "BLOCKED"


def test_a_timeout_reads_as_did_not_answer():
    with mock.patch("leadagent.safeurl.safe_get", side_effect=requests.Timeout("slow")), \
            mock.patch("leadagent.audit.time.sleep"):
        a = audit.audit_site("https://slow-clinic.in/", {})
    assert a["verdict"] == "BROKEN" and a["broken_reason"] == "the site did not answer"


# --- variety ---------------------------------------------------------------------------------------
def test_capped_keeps_the_best_few_of_each_search():
    leads = [ov(f"Clinic {i}") for i in range(5)] + [ov("Physio One", "physiotherapist")]
    for b in leads[:5]:
        b.search_pair = "skin and hair clinic|DLF"
    leads[5].search_pair = "physiotherapist|Sector 84"
    out = pipeline.capped(leads, 2)
    assert [b.name for b in out] == ["Clinic 0", "Clinic 1", "Physio One"]
    assert pipeline.capped(leads, 0) == leads


def test_a_run_takes_at_most_the_cap_from_one_search_and_keeps_searching():
    class Src:
        def __init__(self):
            self.calls = []

        def search(self, niche, city):
            self.calls.append(city["name"])
            return [Business(source="overpass", source_id=f"{city['name']}/{i}", name=f"{city['name']} Skin Clinic {i}",
                             phone=f"+9198{abs(hash(city['name'])) % 10**4:04d}{i:04d}", lat=28.4 + i / 100,
                             lng=77.0 + len(self.calls) / 10, niche_query=niche, city_query=city["name"],
                             business_status="OPERATIONAL") for i in range(10)]

    cfg = {"country": "IN", "min_score_to_report": 0, "niches": ["skin and hair clinic"],
           "website_audit": {"enabled": True}, "quality_filters": {"enabled": True}, "scoring": {},
           "lead_mix": {"no_website": 6, "bad_website": 0, "max_per_search": 3}}
    pairs = [("skin and hair clinic", {"name": n, "lat": 28.4, "lng": 77.0}) for n in ("DLF", "Sohna Road", "Palam Vihar")]
    src = Src()
    with mock.patch("leadagent.pipeline.audit.audit_site", side_effect=lambda url, cfg: {"verdict": "NO_WEBSITE"}), \
            mock.patch("leadagent.safeurl.safe_get", side_effect=safeurl.FetchRefused("n/a")):
        rows, s = pipeline.run(cfg, pairs, sources={"overpass": src}, budget=Budget())
    by_area = {}
    for b in rows:
        by_area[b.city_query] = by_area.get(b.city_query, 0) + 1
    assert len(src.calls) >= 2 and max(by_area.values()) <= 3 and len(rows) == 6
    assert s["dropped"].get("over_search_share", 0) > 0


def test_the_lead_note_gives_the_plain_reason():
    b = Business(source="overture", source_id="1", name="Example Hair Clinic", website="http://www.hairclinic.example/")
    b.audit = {"verdict": "BROKEN", "http_status": "FetchRefused", "broken_reason": "the web address no longer exists"}
    audit.score(b, {})
    assert "Site listed but does not load (the web address no longer exists)" in b.reasons
    assert b.lead_type == "BROKEN SITE"
