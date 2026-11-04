"""
Find a phone number for a lead that has none. Tried in this order, each within its budget:

  (a) match it against the Google results already fetched this run (name + nearby location). Free:
      no extra call.
  (b) one Places Text Search for "<name> <address>", if the shared call budget allows.
  (c) its OWN website (never a social network or directory): one page, 10 s timeout, only if
      robots.txt allows it, with our descriptive User-Agent, and a strict North American phone regex.
      No crawling past that one page.

Storage rule: a number learned from Google in (a) or (b) is NOT copied onto the lead. The lead only gets
the place_id and phone_status = "google_live", and the CRM shows the number live from Google. A number
read from the business's own website in (c) is the business's own public information and is stored.

Email addresses are never extracted here or anywhere else (CASL).
"""

from __future__ import annotations

import re

from . import phones, safeurl
from .dedupe import metres
from .google_verify import CHECKED_TYPES, GoogleVerifier, name_similarity

NEAR_M = 150.0
MIN_NAME_SIM = 0.7
_TEL_HREF = re.compile(r'href=["\']tel:([^"\']{7,30})["\']', re.I)


def _pool_match(b, pool: list):
    best, best_sim = None, 0.0
    for g in pool:
        sim = name_similarity(b.name, g.name)
        if sim < MIN_NAME_SIM:
            continue
        if metres(b, g) > NEAR_M:
            continue
        if sim > best_sim:
            best, best_sim = g, sim
    return best


def phone_from_own_site(b, fetch=safeurl.safe_get) -> tuple[str, str]:
    """(phone, outcome). outcome is 'found', 'none', 'refused' or 'error'. Never raises."""
    if not b.website or safeurl.is_never_fetch(b.website):
        return "", "refused"
    url = b.website if b.website.lower().startswith(("http://", "https://")) else "https://" + b.website
    try:
        r = fetch(url, timeout=10.0, need_robots=True)
    except safeurl.FetchRefused:
        return "", "refused"
    except Exception:                                 # timeouts and network errors: skip, do not crash
        return "", "error"
    if getattr(r, "status_code", 0) != 200:
        return "", "none"
    html = (r.text or "")[:600_000]
    for m in _TEL_HREF.finditer(html):                # a tel: link is the most reliable signal
        p = phones.normalize_e164(m.group(1))
        if p:
            return p, "found"
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    p = phones.find_phone_in_text(text)
    return (p, "found") if p else ("", "none")


def enrich_phones(businesses: list, google_pool: list, verifier: GoogleVerifier | None,
                  *, own_site_limit: int = 120, google_lookup_limit: int = 10,
                  fetch=safeurl.safe_get, should_stop=lambda: False) -> dict:
    """Try to give every phone-less callable lead a phone. Returns counts only."""
    stats = {"missing_before": 0, "from_google_pool": 0, "from_google_lookup": 0,
             "from_own_site": 0, "still_missing": 0, "own_site_failed": 0, "own_site_refused": 0}
    own_used = lookups = 0
    for b in businesses:
        if b.phone or b.phone_status in ("google_live",):
            continue
        if b.lead_type not in CHECKED_TYPES and b.lead_type != "WEAK SITE":
            continue
        stats["missing_before"] += 1
        if should_stop():
            stats["still_missing"] += 1
            continue
        # (a) results we already have this run
        g = _pool_match(b, google_pool) if google_pool else None
        if g is not None:
            b.google_place_id = b.google_place_id or g.google_place_id
            if g.phone:
                b.phone_status = "google_live"
                stats["from_google_pool"] += 1
                continue
        # (b) one lookup, if the shared budget allows
        if verifier is not None and verifier.remaining() > 0 and lookups < google_lookup_limit:
            lookups += 1
            try:
                places = verifier.search(b)
                p = verifier.best_match(b, places)
            except Exception:
                p = None
            if p is not None:
                b.google_place_id = b.google_place_id or p.get("id", "")
                if p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber"):
                    b.phone_status = "google_live"
                    stats["from_google_lookup"] += 1
                    continue
        # (c) the business's own website: one page
        if b.website and not safeurl.is_never_fetch(b.website) and own_used < own_site_limit:
            own_used += 1
            phone, outcome = phone_from_own_site(b, fetch)
            if phone:
                b.phone, b.phone_status = phone, "found"
                stats["from_own_site"] += 1
                continue
            stats["own_site_refused" if outcome == "refused" else "own_site_failed"] += 1
        stats["still_missing"] += 1
        b.phone_status = "missing"
    return stats
