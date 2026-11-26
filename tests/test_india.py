"""India (the owner's own market, Gurgaon first): config, phone numbers, rotation, chains and business types."""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run  # noqa: E402
from leadagent import categorize, fetch_options, phones, quality  # noqa: E402
from leadagent.google_places import GoogleDiscovery  # noqa: E402
from leadagent.sources import Business  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config-in.yaml").read_text(encoding="utf-8"))
BACKEND_IN_NICHES = [
    "dental clinic", "orthodontist", "skin and hair clinic", "coaching institute", "interior designer",
    "physiotherapist", "eye clinic", "veterinary clinic", "preschool", "gym fitness studio", "real estate agent",
]


@pytest.fixture
def india():
    phones.use_country("IN")
    yield
    phones.use_country("US")


def test_config_is_india_with_gurgaon_first():
    assert CFG["country"] == "IN"
    assert CFG["niches"] == BACKEND_IN_NICHES                 # must match IN_NICHES in the CRM
    assert set(CFG["overture_categories"]) == set(CFG["niches"])
    first = CFG["cities"][0]
    assert "Gurugram" in first["name"] and first["priority"] is True
    prio = [c for c in CFG["cities"] if c.get("priority")]
    assert prio and all("Gurugram" in c["name"] or "Manesar" in c["name"] for c in prio)
    assert CFG["outreach"]["your_name"] == "Rohan"
    assert "justdial.com" in CFG["website_audit"]["social_only_domains"]


def test_each_run_is_mostly_gurgaon():
    for seed in range(20):
        pairs = run.todays_pairs(CFG, 45, seed=seed)
        assert len(pairs) == 45
        gurgaon = sum(1 for _, c in pairs if c.get("priority"))
        assert gurgaon == round(45 * CFG["priority_share"])     # 32 Gurgaon searches, 13 for the rest of NCR


def test_a_config_without_priorities_rotates_as_before():
    cfg = {"cities": [{"name": "A"}, {"name": "B"}], "niches": ["x", "y"]}
    assert len(run.todays_pairs(cfg, 3, seed=1)) == 3


def test_typing_gurgaon_finds_the_gurugram_area():
    hit = fetch_options.match_configured_city("gurgaon", CFG["cities"])
    assert hit == {"name": "Gurugram, Haryana", "lat": 28.4595, "lng": 77.0266}
    assert fetch_options.match_configured_city("Sohna Road", CFG["cities"])["name"] == "Sohna Road, Gurugram"


def test_indian_numbers_in_an_india_run(india):
    for raw in ["+91 98765 43210", "098765 43210", "919876543210", "9876543210"]:
        assert phones.normalize_e164(raw) == "+919876543210"
    assert phones.normalize_e164("0124 456 7890") == "+911244567890"      # Gurgaon landline
    assert phones.normalize_e164("+1 905 726 2688") == ""
    assert phones.find_phone_in_text("Call us: +91 98111 22334 (10am-7pm)") == "+919811122334"


def test_north_american_runs_are_unchanged():
    phones.use_country("CA")
    try:
        assert phones.normalize_e164("+91 98765 43210") == ""
        assert phones.normalize_e164("(905) 726-2688") == "+19057262688"
    finally:
        phones.use_country("US")


def test_google_searches_india_when_the_run_is_indian():
    sent = []

    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"places": []}

    class Budget:
        refused_reason = ""

        @staticmethod
        def reserve(kind):
            return True

    def post(url, data=None, **kw):
        sent.append(data)
        return R()

    g = GoogleDiscovery("k", Budget(), post=post, max_pages=1, country="IN")
    g.search("dental clinic", {"name": "Sohna Road, Gurugram", "lat": 28.41, "lng": 77.04})
    assert '"textQuery": "dental clinic in Sohna Road, Gurugram, India"' in sent[0]
    assert '"regionCode": "IN"' in sent[0]


@pytest.mark.parametrize("name", ["Clove Dental - Sector 14", "Lenskart.com at DLF Phase 4", "Aakash Institute Gurugram",
                                  "Kidzee Sohna Road", "cult.fit Golf Course Road", "Livspace Experience Centre"])
def test_indian_chains_are_skipped(name):
    b = Business(source="overture", source_id="1", name=name)
    assert quality.chain_reason(b, list(quality.DEFAULT_CHAIN_NAMES), set(), False)


def g(name, niche, types=""):
    return Business(source="google", source_id=name, name=name, category=types, niche_query=niche)


@pytest.mark.parametrize("name,niche,types,want", [
    ("Gupta Classes for NEET", "dental clinic", "", ("relabel", "coaching institute")),
    ("Studio Nest Interiors", "real estate agent", "", ("relabel", "interior designer")),
    ("Little Steps Play School", "gym fitness studio", "", ("relabel", "preschool")),
    ("Iron Paradise Gym", "gym fitness studio", "gym", ("keep", "gym fitness studio")),
    ("Skin & Hair Solutions", "skin and hair clinic", "", ("keep", "skin and hair clinic")),
    ("Sharma Properties", "real estate agent", "real_estate_agency", ("keep", "real estate agent")),
    ("Netra Eye Centre", "eye clinic", "", ("keep", "eye clinic")),
    ("Bright Smile Dental", "dental clinic", "dentist", ("keep", "dental clinic")),
])
def test_indian_business_types_by_name(name, niche, types, want):
    assert categorize.decide(g(name, niche, types), BACKEND_IN_NICHES) == want
