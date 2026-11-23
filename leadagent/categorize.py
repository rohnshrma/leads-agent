"""
Check that a Google result really is the business type we searched for.

Google's Text Search answers "dental clinic in Maple" with whatever it thinks is related: a therapist, an allergy
clinic, an optical shop. The lead's type picks the mockup layout, so a wrong type means a wrong mockup.
Overture results are already matched on exact categories (sources.py), so only Google results are checked.

Evidence, strongest first:
  1. the business name ("Millrose Chiropractic" is a chiropractor whatever we searched for);
  2. Google's own types (only some of our niches have one: there is no Google type for orthodontists,
     optometrists, hearing clinics, psychologists or dermatologists, so those need the name);
  3. a "not ours" type (nail salon, gym, pharmacy, hospital, pet store) with no supporting name drops it.

Result per business: keep the searched type, relabel to another of the types chosen for this run, or drop.
"""

from __future__ import annotations

import re

# Name words per niche. Checked in this order, so the more specific niche wins ("orthodontics" before "dental").
NAME_WORDS: list[tuple[str, str]] = [
    ("orthodontist", r"ortho(?!tic|p(a|e)d)|braces|invisalign|aligner"),
    ("dental clinic", r"dental|dentist|dentistry|denture|smile|teeth|tooth|\bdds\b|\bdmd\b|endodont|periodont"),
    ("chiropractor", r"chiro"),
    ("physiotherapist", r"physio|rehab|physical therap|sports? injur|kinesi"),
    ("massage therapy clinic", r"massage|\brmt\b|bodywork"),
    ("podiatrist", r"podiat|chiropod|\bfoot\b|\bfeet\b|orthotic"),
    ("hearing clinic", r"hearing|audiolog|\baudio\b|\bear\b"),
    ("optometrist", r"optom|\beyes?\b|vision|optical|optic|eyewear|ophthal"),
    ("veterinary clinic", r"\bvets?\b|veterin|animal|pet hospital|\bcat clinic"),
    ("dermatology clinic", r"derma"),
    ("med spa", r"med(ical)? ?spa|medi ?spa|aesthetic|laser|botox|injector|skin|cosmetic (clinic|surgery)"),
    ("psychology clinic", r"psycholog|psychotherap|counsel|mental health"),
]

# Weak name words: used only when Google's types say nothing ("Therapy Point" with Google type
# physiotherapist stays a physio; "Erin Griffin Therapy" with no useful type becomes a psychology clinic).
WEAK_NAME_WORDS: list[tuple[str, str]] = [
    ("psychology clinic", r"\btherapy\b|therapist"),
]

# Google types that confirm a niche on their own.
GOOGLE_TYPES: dict[str, set[str]] = {
    "dental clinic": {"dentist", "dental_clinic"},
    "chiropractor": {"chiropractor"},
    "physiotherapist": {"physiotherapist"},
    "massage therapy clinic": {"massage", "massage_spa"},
    "podiatrist": {"foot_care"},
    "veterinary clinic": {"veterinary_care"},
    "med spa": {"skin_care_clinic"},
}

# Types that mean "not a business we sell to" unless the name says otherwise.
NOT_OURS = {
    "nail_salon", "hair_salon", "hair_care", "beauty_salon", "barber_shop", "beautician", "makeup_artist",
    "body_art_service", "cosmetics_store", "gym", "fitness_center", "sports_club", "sports_coaching",
    "yoga_studio", "pharmacy", "drugstore", "hospital", "general_hospital", "medical_lab", "pet_store",
    "pet_boarding_service", "tanning_studio", "sauna",
}

_COMPILED = [(n, re.compile(p, re.I)) for n, p in NAME_WORDS]
_WEAK = [(n, re.compile(p, re.I)) for n, p in WEAK_NAME_WORDS]


def name_niches(name: str) -> list[str]:
    """Niches the name points to, most specific first."""
    return [n for n, rx in _COMPILED if rx.search(name or "")]


def google_types(b) -> set[str]:
    return {t.strip() for t in (b.category or "").split(",") if t.strip()}


def decide(b, wanted: list[str]) -> tuple[str, str]:
    """("keep" | "relabel" | "drop", niche or reason) for one Google result searched as `b.niche_query`."""
    q = (b.niche_query or "").lower()
    allowed = [w.lower() for w in wanted]
    by_name = [n for n in name_niches(b.name) if n in allowed]
    types = google_types(b)
    if q in by_name:
        return "keep", q
    if by_name:
        return "relabel", by_name[0]
    # The name says nothing either way: Google's types decide.
    if types & GOOGLE_TYPES.get(q, set()):
        return "keep", q
    by_type = [n for n in allowed if types & GOOGLE_TYPES.get(n, set())]
    if by_type:
        return "relabel", by_type[0]
    weak = [n for n, rx in _WEAK if rx.search(b.name or "") and n in allowed]
    if q in weak:
        return "keep", q
    if weak:
        return "relabel", weak[0]
    if types & NOT_OURS:
        return "drop", "not one of our business types"
    return "drop", f"nothing shows it is a {q or 'business we search for'}"


def apply(found: list, cfg: dict) -> tuple[list, dict]:
    """Check every Google result; relabel or drop the ones that are not what was searched for."""
    wanted = [n.lower() for n in (cfg.get("niches") or [])]
    report = {"wrong_category": 0, "relabelled": 0}
    if not wanted:
        return found, report
    out = []
    for b in found:
        if b.source != "google":
            out.append(b)
            continue
        verdict, niche = decide(b, wanted)
        if verdict == "drop":
            report["wrong_category"] += 1
            continue
        if verdict == "relabel":
            report["relabelled"] += 1
            b.niche_query = niche
        out.append(b)
    return out, report
