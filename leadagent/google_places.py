"""
Google Places as a DISCOVERY source (Places API (New), Text Search).

Google's terms let an app keep a place_id forever but not Google's other content. So this module follows
one rule: Google fields (name, address, phone, website, types, location) are held in memory while the run
scores and types the lead, and are NEVER written to any file, log, cache, artifact or database. What
leaves this module for storage is the place_id, source = "google", the score, the lead type and a
timestamp (see pipeline.to_row). Anyone who opens the lead later sees the details fetched live.

Cost control: every request, including each result page, first reserves a call from the backend's shared
budget (budget.py). A refusal stops discovery cleanly; the other sources carry on.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import requests

from .budget import Budget, KIND_TEXT_SEARCH
from .sources import Business

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"

# EXACTLY these fields, nothing else: billing is set by the highest tier of any field requested, so a
# stray rating or opening-hours field would change the price. A unit test fails if this string changes.
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.location,places.types,"
    "places.businessStatus,places.nationalPhoneNumber,places.internationalPhoneNumber,"
    "places.websiteUri,places.googleMapsUri,nextPageToken"
)
MAX_PAGES = 3          # 20 results a page, 60 in all
PAGE_SIZE = 20


class GoogleDiscovery:
    def __init__(self, api_key: str, budget: Budget, post=None, max_pages: int = MAX_PAGES):
        self.api_key = (api_key or "").strip()
        self.budget = budget
        self._post = post or requests.post
        self.max_pages = min(int(max_pages), MAX_PAGES)
        self.calls = 0                  # requests actually sent
        self.found = 0
        self.stopped = ""               # "" while usable; otherwise why Places is no longer used this run
        self.budget_reached = False     # a normal outcome, not an error
        self.failed = 0

    @property
    def usable(self) -> bool:
        return bool(self.api_key) and not self.stopped

    def _stop(self, why: str) -> None:
        if not self.stopped:
            self.stopped = why
            print(f"Google Places not used for the rest of this run: {why}")   # one clear line, no details

    def search(self, niche: str, city: dict) -> list[Business]:
        """Businesses of one type in one area. [] once Places has stopped (check `usable` / `stopped`)."""
        if not self.api_key:
            self._stop("no API key set")
            return []
        out: list[Business] = []
        token = ""
        for _page in range(self.max_pages):
            if not self.usable:
                break
            if not self.budget.reserve(KIND_TEXT_SEARCH):          # reserve BEFORE the request
                self.budget_reached = True
                self._stop(f"call budget reached ({self.budget.refused_reason or 'cap'})")
                break
            body = {
                "textQuery": f"{niche} in {city['name']}, Canada",
                "pageSize": PAGE_SIZE,
                "regionCode": "CA",
                "includePureServiceAreaBusinesses": True,
            }
            if token:
                body["pageToken"] = token
            if city.get("lat") is not None and city.get("lng") is not None and not token:
                body["locationBias"] = {"circle": {"center": {"latitude": city["lat"], "longitude": city["lng"]},
                                                   "radius": 35000.0}}
            self.calls += 1
            try:
                r = self._post(
                    ENDPOINT, data=json.dumps(body), timeout=30,
                    headers={"Content-Type": "application/json", "X-Goog-Api-Key": self.api_key,
                             "X-Goog-FieldMask": FIELD_MASK})
            except requests.RequestException as ex:
                self.failed += 1
                print(f"Google Places request failed ({type(ex).__name__})")
                break
            if r.status_code in (400, 401, 403, 429):
                self._stop(f"Google answered HTTP {r.status_code}")
                break
            if r.status_code != 200:
                self.failed += 1
                break
            try:
                data = r.json()
            except ValueError:
                self.failed += 1
                break
            out.extend(self._to_businesses(data.get("places") or [], niche, city))
            token = data.get("nextPageToken") or ""
            if not token:
                break
        self.found += len(out)
        return out

    @staticmethod
    def _to_businesses(places: list[dict], niche: str, city: dict) -> list[Business]:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        out = []
        for p in places:
            pid = (p.get("id") or "").strip()
            if not pid or p.get("businessStatus") == "CLOSED_PERMANENTLY":
                continue
            loc = p.get("location") or {}
            out.append(Business(
                source="google",
                source_id=pid,
                google_place_id=pid,
                name=(p.get("displayName") or {}).get("text", ""),
                category=", ".join(p.get("types") or [])[:120],
                address=p.get("formattedAddress", ""),
                city_query=city["name"],
                niche_query=niche,
                phone=p.get("nationalPhoneNumber") or p.get("internationalPhoneNumber") or "",
                website=p.get("websiteUri") or "",
                business_status=p.get("businessStatus") or "OPERATIONAL",
                maps_url=p.get("googleMapsUri", ""),
                lat=loc.get("latitude"), lng=loc.get("longitude"),
                from_google=True, fetched_at=now,
            ))
        return out
