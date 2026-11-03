"""
Free quality filters, applied before any website is audited.

The free map data (OpenStreetMap) produces three kinds of lead nobody can sell to:

  * CHAINS and multi-location groups (LensCrafters, Hakim Optical, a clinic group with
    fifteen sites). Their website is run by head office, so there is nothing to sell.
  * "No website" that is really "nobody typed the website into the map". A business
    whose email is on its own domain (info@theirclinic.ca) almost always has a site.
  * Records with no phone number. A no-website business can only be reached by phone.

Each filter is switchable in config (quality_filters:) and none of them needs a key.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict

# Mailbox providers: an address here says nothing about the business owning a website.
FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.ca", "ymail.com", "hotmail.com",
    "hotmail.ca", "outlook.com", "live.com", "live.ca", "msn.com", "icloud.com", "me.com",
    "aol.com", "proton.me", "protonmail.com", "gmx.com", "mail.com", "zoho.com",
    # Canadian and US internet providers that hand out mailboxes
    "shaw.ca", "rogers.com", "sympatico.ca", "bell.net", "telus.net", "videotron.ca",
    "cogeco.ca", "eastlink.ca", "mts.net", "sasktel.net", "execulink.com", "nbnet.nb.ca",
    "comcast.net", "verizon.net", "att.net", "sbcglobal.net", "cox.net", "charter.net",
}

# Well-known chains and franchises in the niches the finder hunts. Extend in config:
# quality_filters.chain_names (matched anywhere in the business name, case-insensitive).
DEFAULT_CHAIN_NAMES = [
    "lenscrafters", "hakim optical", "specsavers", "pearle vision", "costco", "walmart",
    "shoppers drug mart", "jean coutu", "london drugs", "lifemark", "physiomed", "cbi health",
    "optimum wellness", "dentalcorp", "aspen dental", "heartland dental", "banfield",
    "vca ", "petsmart", "petco", "massage envy", "hand & stone", "hand and stone",
    "the joint", "elements massage", "orangetheory", "goodlife", "anytime fitness",
    "planet fitness", "great clips", "sport clips",
]

# Words that do not identify a business ("Smile Dental Clinic Inc." -> "smile").
_GENERIC = {
    "the", "and", "of", "inc", "ltd", "llc", "corp", "co", "clinic", "clinics", "centre",
    "centres", "center", "centers", "dental", "dentistry", "chiropractic", "chiropractor",
    "physiotherapy", "physio", "massage", "therapy", "health", "wellness", "optical",
    "optometry", "family", "group", "office", "care", "veterinary", "vet", "animal",
    "hospital", "medical", "professional",
}


def normalise_name(name: str) -> str:
    """Brand part of a name: drop a " - Location" suffix, punctuation and generic words."""
    head = re.split(r"\s[-–—|]\s", name or "", maxsplit=1)[0]
    words = re.findall(r"[a-z0-9]+", head.lower())
    kept = [w for w in words if w not in _GENERIC]
    return " ".join(kept) or " ".join(words)


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def multi_location_keys(found: list, min_locations: int = 3, apart_km: float = 1.0) -> set[str]:
    """Normalised names that show up at `min_locations`+ separate places in today's results."""
    groups: dict[str, list] = defaultdict(list)
    for b in found:
        key = normalise_name(b.name)
        if len(key) >= 4:
            groups[key].append(b)
    chains = set()
    for key, members in groups.items():
        clusters: list[tuple[float, float] | str] = []
        for b in members:
            where = (b.lat, b.lng) if b.lat is not None and b.lng is not None else (b.address or b.city_query)
            near = False
            for c in clusters:
                if isinstance(c, tuple) and isinstance(where, tuple):
                    near = _km(c, where) < apart_km
                else:
                    near = c == where
                if near:
                    break
            if not near:
                clusters.append(where)
        if len(clusters) >= min_locations:
            chains.add(key)
    return chains


def own_domain(email: str, free_domains: set[str] | None = None) -> str:
    """The business's own domain from its email address, or "" when it is a mailbox provider."""
    free = free_domains if free_domains is not None else FREE_EMAIL_DOMAINS
    if not email or "@" not in email:
        return ""
    domain = email.rsplit("@", 1)[1].strip().lower().strip(".")
    if not domain or "." not in domain or domain in free:
        return ""
    return domain


def digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def has_phone(b) -> bool:
    return len(digits(b.phone)) >= 10


def chain_reason(b, chain_names: list[str], multi_keys: set[str], skip_branded: bool) -> str:
    """Why this business looks like a chain, or "" when it does not."""
    low = (b.name or "").lower()
    for n in chain_names:
        if n and n.lower() in low:
            return f"known chain ({n.strip()})"
    if skip_branded and b.brand:
        return f"branded location ({b.brand})"
    if normalise_name(b.name) in multi_keys:
        return "same name at several locations"
    return ""


def apply(found: list, fresh: list, cfg: dict) -> tuple[list, dict]:
    """
    Filter `fresh` (businesses not seen before). Chain detection looks at everything found today
    (`found`) so a group is recognised even when most of its sites were seen on earlier days.
    Returns (kept, report) where report counts what was dropped and what was inferred.
    """
    q = cfg.get("quality_filters") or {}
    report = {"chains": 0, "no_phone": 0, "website_inferred": 0, "dropped_names": []}
    if not q.get("enabled", True):
        return fresh, report

    names = list(DEFAULT_CHAIN_NAMES) + list(q.get("chain_names") or [])
    multi = set()
    if q.get("skip_chains", True):
        multi = multi_location_keys(found, int(q.get("chain_min_locations", 3)))
    free = FREE_EMAIL_DOMAINS | {d.lower() for d in (q.get("free_email_domains") or [])}

    kept = []
    for b in fresh:
        if q.get("skip_chains", True):
            why = chain_reason(b, names, multi, bool(q.get("skip_branded", True)))
            if why:
                report["chains"] += 1
                report["dropped_names"].append(f"{b.name} ({why})")
                continue
        if q.get("require_phone", True) and not has_phone(b):
            report["no_phone"] += 1
            continue
        if q.get("infer_website_from_email", True) and not b.website:
            dom = own_domain(b.email, free)
            if dom:
                b.website = f"https://{dom}"
                b.website_inferred = True
                report["website_inferred"] += 1
        kept.append(b)
    return kept, report
