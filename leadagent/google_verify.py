"""
Optional Google Places check for the best candidates. OFF unless you turn it on.

The free map data cannot tell whether a business has a website the map lacks, whether it has closed,
or whether anyone uses it. Google can. This module looks up each top candidate once and then:

  * drops it when Google says the business is closed;
  * re-grades it when Google lists a real website (so a false "NO WEBSITE" is not reported);
  * marks it "not found on Google" (score penalty) when no listing matches name and place;
  * adds a score bonus from Google's review count and rating when it is verified and has no site.

It runs only when BOTH are true:
  1. google_verify.enabled: true in the config, and
  2. the API key is in the environment variable named by google_api_key_env.

Money guard-rails (Text Search with phone/website/rating is Google's "Enterprise" SKU: the first 1,000
requests a month are free, then $35 per 1,000):
  * monthly_call_cap (default 900) is counted in the ledger database and never exceeded;
  * max_per_run (default 40) limits one morning's run;
  * also set a daily quota in the Google Cloud console - that is the cap Google itself enforces.

Licence: Google lets you store place IDs indefinitely but not its other content. So by default only the
place ID and a status are kept (google_place_id, google_status). Google's website, phone, rating and
review count are used to decide, then discarded. Set keep_google_fields: true only if you have checked
Google's current terms and accept that.
"""

from __future__ import annotations

import math
import os
import re
import sqlite3
from datetime import datetime
from difflib import SequenceMatcher

import requests

from . import audit, quality

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.location",
    "places.businessStatus", "places.websiteUri", "places.nationalPhoneNumber",
    "places.rating", "places.userRatingCount",
])
CHECKED_TYPES = {"NO WEBSITE", "BROKEN SITE", "SOCIAL ONLY", "PLACEHOLDER"}
FREE_MONTHLY_ENTERPRISE_CALLS = 1000


class UsageMeter:
    """Counts Google requests per calendar month in the ledger's SQLite database."""

    def __init__(self, con: sqlite3.Connection):
        self.con = con
        self.con.execute("CREATE TABLE IF NOT EXISTS google_usage (month TEXT PRIMARY KEY, calls INTEGER)")
        self.con.commit()

    @staticmethod
    def month() -> str:
        return datetime.now().strftime("%Y-%m")

    def used(self) -> int:
        row = self.con.execute("SELECT calls FROM google_usage WHERE month=?", (self.month(),)).fetchone()
        return int(row[0]) if row else 0

    def add(self, n: int = 1) -> None:
        self.con.execute(
            "INSERT INTO google_usage (month, calls) VALUES (?, ?) "
            "ON CONFLICT(month) DO UPDATE SET calls = calls + excluded.calls", (self.month(), n))
        self.con.commit()


def _alnum(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _scrub(reason: str) -> str:
    """Remove Google's numbers (review count, rating) from a score reason so they are not stored."""
    reason = re.sub(r"\(\d+ Google reviews\)", "(strong on Google)", reason)
    reason = re.sub(r"\(\d+(\.\d+)?\*\)", "(on Google)", reason)
    return re.sub(r"only \d+ reviews", "only a few reviews", reason)


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
    def __init__(self, cfg: dict, api_key: str, meter: UsageMeter):
        g = cfg.get("google_verify") or {}
        self.cfg = cfg
        self.api_key = api_key
        self.meter = meter
        self.cap = int(g.get("monthly_call_cap", 900))
        self.per_run = int(g.get("max_per_run", 40))
        self.min_sim = float(g.get("min_name_similarity", 0.6))
        self.max_dist = float(g.get("max_distance_m", 400))
        self.keep = bool(g.get("keep_google_fields", False))
        self.penalty = int(g.get("no_match_penalty", 20))
        self.region = (cfg.get("country") or "US").upper()
        self.calls_this_run = 0
        self.stopped = ""          # why checking stopped early (bad key, quota...), if it did
        self.social = [d.lower() for d in (cfg.get("website_audit", {}) or {}).get("social_only_domains", [])]

    # ---- budget ---------------------------------------------------------------------------
    def remaining(self) -> int:
        if self.stopped:
            return 0
        return max(0, min(self.per_run - self.calls_this_run, self.cap - self.meter.used()))

    # ---- the one billable call ----------------------------------------------------------------
    def search(self, b) -> list[dict]:
        body = {
            "textQuery": f"{b.name} {b.address or b.city_query}".strip(),
            "pageSize": 3,
            "regionCode": self.region,
        }
        if b.lat is not None and b.lng is not None:
            body["locationBias"] = {"circle": {"center": {"latitude": b.lat, "longitude": b.lng}, "radius": 1000.0}}
        self.meter.add(1)                      # count before sending: a failed call may still be billed
        self.calls_this_run += 1
        r = requests.post(
            ENDPOINT, json=body, timeout=30,
            headers={"Content-Type": "application/json", "X-Goog-Api-Key": self.api_key,
                     "X-Goog-FieldMask": FIELD_MASK},
        )
        if r.status_code in (400, 401, 403, 429):
            self.stopped = f"Google answered HTTP {r.status_code}: {r.text[:160]}"
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
        except Exception as ex:                     # network trouble or a stop condition
            b.google_status = "error"
            print(f"  ! Google check failed for {b.name}: {ex}")
            return "error"
        p = self.best_match(b, places)
        if p is None:
            b.google_status = "no_match"
            b.opportunity_score = max(0, b.opportunity_score - self.penalty)
            b.reasons.append("Not found on Google: the name or phone may be out of date")
            return "no_match"

        b.google_status = "matched"
        b.google_place_id = p.get("id", "")
        status = p.get("businessStatus", "")
        if status and status != "OPERATIONAL":
            b.business_status = status
            audit.score(b, self.cfg)               # zeroes the score and says why
            return "closed"

        site = (p.get("websiteUri") or "").strip()
        if site:
            b.audit = audit.audit_site(site, self.cfg)
            if not self.keep:                      # Google's URL is Google content: keep the verdict, not the link
                b.audit["listed_url"] = ""
                b.audit["final_url"] = ""
            audit.score(b, self.cfg)
            b.reasons.append("Google lists a website for this business (the map data lacked it)")
            return "website_found"

        # Verified, operating, no website on Google: use reviews as a demand signal for the score only.
        b.rating, b.review_count = p.get("rating"), p.get("userRatingCount")
        audit.score(b, self.cfg)
        b.reasons.append("Verified on Google: operating, no website listed")
        if not self.keep:
            b.rating = b.review_count = None
            b.reasons = [_scrub(w) for w in b.reasons]
        return "verified"

    def run(self, candidates: list) -> dict:
        """Check the best candidates (already sorted best first) within today's budget."""
        summary = {"checked": 0, "verified": 0, "no_match": 0, "closed": 0, "website_found": 0,
                   "error": 0, "not_checked": 0}
        for b in candidates:
            if b.lead_type not in CHECKED_TYPES:
                continue
            if self.remaining() <= 0:
                b.google_status = "not_checked"
                summary["not_checked"] += 1
                continue
            outcome = self.check(b)
            summary["checked"] += 1
            summary[outcome] = summary.get(outcome, 0) + 1
        return summary


def build(cfg: dict, ledger) -> GoogleVerifier | None:
    """The verifier, or None when the check is switched off or has no key."""
    g = cfg.get("google_verify") or {}
    if not g.get("enabled", False):
        return None
    key = os.environ.get(cfg.get("google_api_key_env", "GOOGLE_MAPS_API_KEY"), "").strip()
    if not key:
        print("google_verify is enabled but no API key is set - skipping the Google check")
        return None
    cap = int(g.get("monthly_call_cap", 900))
    if cap > FREE_MONTHLY_ENTERPRISE_CALLS:
        print(f"WARNING: monthly_call_cap {cap} is above Google's {FREE_MONTHLY_ENTERPRISE_CALLS} free requests; "
              "calls beyond that are billed")
    return GoogleVerifier(cfg, key, UsageMeter(ledger.con))
