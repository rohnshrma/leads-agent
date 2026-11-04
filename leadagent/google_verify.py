"""
Optional Google Places check of the best candidates, sharing the discovery call budget.

The free map data cannot tell whether a business has a website the map lacks, whether it has closed, or
whether it is a real, operating place. Google can. For each top candidate this module does one Text
Search and then:

  * drops it when Google says the business is closed;
  * re-grades it when Google lists a real website (so a false "NO WEBSITE" is not reported);
  * marks it "not found on Google" (score penalty) when no listing matches name and place;
  * remembers the place_id, and - for a lead with no phone - that Google has one (phone_status
    "google_live": the CRM shows it live from Google; it is never stored).

Google's terms allow keeping a place_id and nothing else. Everything else Google says is used to decide
and then dropped from memory. There is no switch to keep it.

Money: every request first reserves a call from the SAME backend budget as discovery (budget.py), so the
check and discovery together can never pass the daily or monthly cap. A refusal stops the check cleanly.
`max_per_run` additionally limits one run.
"""

from __future__ import annotations

import math
import os
import re
from difflib import SequenceMatcher

import requests

from . import audit, quality
from .budget import Budget, KIND_TEXT_SEARCH
from .google_places import ENDPOINT, FIELD_MASK

CHECKED_TYPES = {"NO WEBSITE", "BROKEN SITE", "SOCIAL ONLY", "PLACEHOLDER"}


def _alnum(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (s or "").lower()))


def name_similarity(a: str, b: str) -> float:
    a, b = _alnum(a), _alnum(b)
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return max(ratio, 0.85 * overlap)


def distance_m(lat1, lng1, lat2, lng2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class GoogleVerifier:
    def __init__(self, cfg: dict, api_key: str, budget: Budget, post=None):
        g = cfg.get("google_verify") or {}
        self.cfg = cfg
        self.api_key = api_key
        self.budget = budget
        self._post = post or requests.post
        self.per_run = int(g.get("max_per_run", 15))
        self.min_sim = float(g.get("min_name_similarity", 0.6))
        self.max_dist = float(g.get("max_distance_m", 400))
        self.penalty = int(g.get("no_match_penalty", 20))
        self.region = (cfg.get("country") or "CA").upper()
        self.calls_this_run = 0
        self.stopped = ""          # why checking stopped early (bad key, quota, budget...), if it did
        self.budget_reached = False

    # ---- budget ---------------------------------------------------------------------------
    def remaining(self) -> int:
        if self.stopped:
            return 0
        return max(0, self.per_run - self.calls_this_run)

    # ---- the one billable call ----------------------------------------------------------------
    def search(self, b) -> list[dict]:
        if self.stopped:
            raise RuntimeError(self.stopped)
        if not self.budget.reserve(KIND_TEXT_SEARCH):               # reserve BEFORE sending
            self.budget_reached = True
            self.stopped = f"call budget reached ({self.budget.refused_reason or 'cap'})"
            raise RuntimeError(self.stopped)
        body = {
            "textQuery": f"{b.name} {b.address or b.city_query}".strip(),
            "pageSize": 3,
            "regionCode": self.region,
        }
        if b.lat is not None and b.lng is not None:
            body["locationBias"] = {"circle": {"center": {"latitude": b.lat, "longitude": b.lng}, "radius": 1000.0}}
        self.calls_this_run += 1
        import json
        r = self._post(
            ENDPOINT, data=json.dumps(body), timeout=30,
            headers={"Content-Type": "application/json", "X-Goog-Api-Key": self.api_key,
                     "X-Goog-FieldMask": FIELD_MASK},
        )
        if r.status_code in (400, 401, 403, 429):
            self.stopped = f"Google answered HTTP {r.status_code}"      # no body: it can echo the request
            raise RuntimeError(self.stopped)
        if r.status_code != 200:
            raise RuntimeError(f"Google answered HTTP {r.status_code}")
        return r.json().get("places", [])

    # ---- matching -----------------------------------------------------------------------------
    def best_match(self, b, places: list[dict]) -> dict | None:
        mine = quality.digits(b.phone)[-10:]
        best, best_score = None, 0.0
        for p in places:
            sim = name_similarity(b.name, (p.get("displayName") or {}).get("text", ""))
            phone_hit = bool(mine) and quality.digits(p.get("nationalPhoneNumber", ""))[-10:] == mine
            loc = p.get("location") or {}
            near = True
            if b.lat is not None and b.lng is not None and loc.get("latitude") is not None:
                near = distance_m(b.lat, b.lng, loc["latitude"], loc["longitude"]) <= self.max_dist
            # A shared phone number alone is not enough: directories mix numbers up between businesses,
            # so it only counts when the names are at least partly alike too.
            ok = (sim >= self.min_sim and near) or (phone_hit and sim >= 0.4)
            score = sim + (1.0 if phone_hit else 0.0)
            if ok and score > best_score:
                best, best_score = p, score
        return best

    # ---- decide and apply ---------------------------------------------------------------------
    def check(self, b) -> str:
        """Look one business up and update it. Returns the outcome label."""
        try:
            places = self.search(b)
        except Exception:                                    # network trouble or a stop condition
            b.google_status = "error"
            return "error"
        p = self.best_match(b, places)
        if p is None:
            b.google_status = "no_match"
            b.opportunity_score = max(0, b.opportunity_score - self.penalty)
            b.reasons.append("Not found on Google: the name or phone may be out of date")
            return "no_match"

        b.google_status = "matched"
        b.google_place_id = p.get("id", "")                 # the one Google field that may be stored
        if not b.phone and (p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber")):
            b.phone_status = "google_live"                  # shown live in the CRM; the number is NOT kept
        status = p.get("businessStatus", "")
        if status and status != "OPERATIONAL":
            b.business_status = status
            audit.score(b, self.cfg)                         # zeroes the score and says why
            return "closed"

        site = (p.get("websiteUri") or "").strip()
        if site and not b.website:
            # Grade Google's website in memory; keep the verdict, never the link.
            b.audit = audit.audit_site(site, self.cfg)
            b.audit["listed_url"] = ""
            b.audit["final_url"] = ""
            audit.score(b, self.cfg)
            b.reasons.append("Google lists a website for this business (the map data lacked it)")
            return "website_found"

        audit.score(b, self.cfg)
        b.reasons.append("Verified on Google: operating" + ("" if site else ", no website listed"))
        return "verified"

    def run(self, candidates: list) -> dict:
        """Check the best candidates (already sorted best first) within the budget."""
        summary = {"checked": 0, "verified": 0, "no_match": 0, "closed": 0, "website_found": 0,
                   "error": 0, "not_checked": 0, "skipped_already_known": 0}
        for b in candidates:
            if b.lead_type not in CHECKED_TYPES:
                continue
            if b.from_google or b.google_place_id:
                summary["skipped_already_known"] += 1         # discovery already gave phone and website
                continue
            if self.remaining() <= 0:
                b.google_status = "not_checked"
                summary["not_checked"] += 1
                continue
            outcome = self.check(b)
            summary["checked"] += 1
            summary[outcome] = summary.get(outcome, 0) + 1
        return summary


def build(cfg: dict, budget: Budget) -> GoogleVerifier | None:
    """The verifier, or None when the check is switched off or there is no key."""
    g = cfg.get("google_verify") or {}
    if not g.get("enabled", False):
        return None
    key = os.environ.get(cfg.get("google_api_key_env", "GOOGLE_MAPS_API_KEY"), "").strip()
    if not key:
        print("Google check skipped: no API key is set")
        return None
    return GoogleVerifier(cfg, key, budget)
