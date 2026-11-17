"""
Merge the same business found by different sources, in memory, before anything is posted.

Two records are the same business when, checked in this order, any of these agree:
  1. place_id        (Google place id)
  2. normalised phone (last ten digits)
  3. website domain  (www. stripped; social networks and website builders never count)
  4. normalised name AND within 75 m of each other

Guards, so that two different businesses are not fused:
  * a phone or domain match is ignored when both records have coordinates more than 5 km apart
    (branches of one chain share a head-office number and site);
  * name + distance needs real coordinates on both sides, so the same name 2 km apart stays two leads.

Which record survives: OpenStreetMap / Overture records are kept in preference to Google ones, because
their data may be stored and Google's may not. The survivor keeps its own fields, gains the Google place
id (the one Google field that may be stored) and any phone/website/email the other non-Google record had.
"""

from __future__ import annotations

import math
import re

from . import phones
from .safeurl import NEVER_FETCH, host_of

NAME_MATCH_M = 75.0
FAR_KM = 5.0
# Shared hosting / builders: a domain here says nothing about who owns the business.
SHARED_DOMAINS = set(NEVER_FETCH) | {
    "wixsite.com", "weebly.com", "godaddysites.com", "square.site", "business.site", "sites.google.com",
    "blogspot.com", "wordpress.com", "squarespace.com", "booksy.com", "vagaro.com", "mindbodyonline.com",
}
SOURCE_RANK = {"osm": 0, "overture": 1, "sample": 2, "google": 9}


def norm_name(name: str) -> str:
    s = re.sub(r"['’`]", "", (name or "").lower())
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\b(inc|ltd|llc|corp|co|the)\b", " ", s).replace("  ", " ").strip()


def domain_of(url: str) -> str:
    h = host_of(url or "")
    h = h[4:] if h.startswith("www.") else h
    if not h or any(h == d or h.endswith("." + d) for d in SHARED_DOMAINS):
        return ""
    return h


def metres(a, b) -> float:
    if None in (a.lat, a.lng, b.lat, b.lng):
        return math.inf
    r = 6371000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lng - a.lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class _Sets:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def _place_id(b) -> str:
    return (b.google_place_id or (b.source_id if b.source == "google" else "")).strip()


def _score_for_survival(b) -> tuple:
    return (SOURCE_RANK.get(b.source, 5), 0 if phones.last10(b.phone) else 1, 0 if b.website else 1)


def merge(businesses: list) -> tuple[list, dict]:
    """Return (merged records, {"merged": n, "by_place_id": n, "by_phone": n, "by_domain": n, "by_name": n})."""
    n = len(businesses)
    sets = _Sets(n)
    reasons = {"by_place_id": 0, "by_phone": 0, "by_domain": 0, "by_name": 0}

    def far(i, j) -> bool:
        return metres(businesses[i], businesses[j]) > FAR_KM * 1000

    def link(index: dict, key: str, i: int, reason: str, guard: bool) -> None:
        if not key:
            return
        for j in index.get(key, []):
            if sets.find(i) != sets.find(j) and not (guard and far(i, j)):
                sets.union(i, j)
                reasons[reason] += 1
        index.setdefault(key, []).append(i)

    by_pid: dict = {}
    by_srcid: dict = {}
    by_phone: dict = {}
    by_dom: dict = {}
    by_name: dict = {}
    for i, b in enumerate(businesses):
        link(by_pid, _place_id(b), i, "by_place_id", False)
        link(by_srcid, f"{b.source}:{b.source_id}" if b.source_id else "", i, "by_place_id", False)  # same record found twice
        link(by_phone, phones.last10(b.phone), i, "by_phone", True)
        link(by_dom, domain_of(b.website), i, "by_domain", True)
        key = norm_name(b.name)
        if key:
            for j in by_name.get(key, []):
                if sets.find(i) != sets.find(j) and metres(b, businesses[j]) < NAME_MATCH_M:
                    sets.union(i, j)
                    reasons["by_name"] += 1
            by_name.setdefault(key, []).append(i)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(sets.find(i), []).append(i)

    out = []
    for idxs in groups.values():
        members = sorted((businesses[i] for i in idxs), key=_score_for_survival)
        keep = members[0]
        for other in members[1:]:
            pid = _place_id(other)
            if pid and not keep.google_place_id:
                keep.google_place_id = pid
            if other.source == "google":
                keep.from_google = keep.from_google or other.from_google
                continue                          # nothing of Google's is copied onto a stored record
            for attr in ("phone", "website", "email", "address", "brand"):
                if not getattr(keep, attr) and getattr(other, attr):
                    setattr(keep, attr, getattr(other, attr))
            keep.source_count = (keep.source_count or 1) + (other.source_count or 1)
        out.append(keep)
    stats = {"merged": n - len(out), **reasons}
    return out, stats
