"""
One fetch, end to end, as a function that can be tested without a network.

    discover (Google -> Overture -> Overpass)  ->  merge + de-duplicate  ->  quality filters
    -> website audit + score  ->  phone enrichment  ->  Google check  ->  rows + a counts-only summary

Rules this module enforces:
  * the run stops by itself at the time limit (40 minutes by default), posts what it has, and reports the
    rest of the batch as "not run" so the backend leaves it in the queue;
  * a search that fails is counted as FAILED, never as "0 results";
  * Google data is used in memory only; `to_row` writes a Google-sourced lead as place_id + score + lead
    type + timestamp and nothing else;
  * the summary and the log contain counts only - no names, phones, addresses, URLs, place ids or areas.
"""

from __future__ import annotations

import copy
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import audit, categorize, dedupe, enrich, google_verify, quality
from .budget import Budget
from .sources import Business, DeadlineReached

TIME_LIMIT_SECONDS = 40 * 60
SOURCE_ORDER = ("google", "overture", "overpass")

# What we sell to each kind of lead. A business with a good website is never reported.
NO_WEBSITE_TYPES = ("NO WEBSITE", "SOCIAL ONLY")                     # build them a website
BAD_WEBSITE_TYPES = ("BROKEN SITE", "PLACEHOLDER", "WEAK SITE")       # rebuild, SEO, CRM


def bucket_of(b) -> str:
    """'no_website', 'bad_website' or '' (a good site, or not graded) for a scored Business."""
    if b.lead_type in NO_WEBSITE_TYPES:
        return "no_website"
    if b.lead_type in BAD_WEBSITE_TYPES:
        return "bad_website"
    return ""


def lead_mix(cfg: dict) -> dict:
    """{"no_website": n, "bad_website": n} from config `lead_mix`; {} means no per-run targets."""
    m = cfg.get("lead_mix") or {}
    out = {k: int(m[k]) for k in ("no_website", "bad_website") if m.get(k) not in (None, "")}
    return {k: v for k, v in out.items() if v > 0}

# The only fields a Google-sourced lead is saved with. Everything else Google said stays in memory.
GOOGLE_ROW_FIELDS = (
    "source", "source_id", "google_place_id", "place_id", "opportunity_score", "lead_type", "reasons",
    "fetched_at", "city_query", "niche_query", "country", "phone_status", "site_verdict", "google_status",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_row(b: Business, cfg: dict) -> dict:
    """The dict that is posted to the CRM and written to the run's local CSV."""
    row = b.as_row()
    row["country"] = cfg.get("country", "US")
    row["place_id"] = b.google_place_id
    row["fetched_at"] = b.fetched_at or now_iso()
    row["phone_status"] = b.phone_status or ("found" if b.phone else "missing")
    row["email"] = ""                      # addresses are never collected automatically (CASL)
    if b.source == "google":
        slim = {k: row.get(k, "") for k in GOOGLE_ROW_FIELDS}
        slim["source"] = "google"
        slim["phone_status"] = "google_live"
        slim["source_id"] = b.google_place_id
        slim["place_id"] = b.google_place_id
        return slim
    # A stored (OpenStreetMap / Overture) lead that merely matched a Google listing keeps its own data;
    # Google's name, address, phone and website are never copied onto it.
    return row


def _discover(cfg: dict, pairs: list, sources: dict, deadline: float, summary: dict, enough=None) -> list[Business]:
    found: list[Business] = []
    per = summary["sources"]
    status = ["not_run"] * len(pairs)
    for i, (niche, city) in enumerate(pairs):
        if time.monotonic() >= deadline:
            summary["stopped_early"] = "time limit"
            break
        ok = True
        stop = False
        for name in SOURCE_ORDER:
            src = sources.get(name)
            if src is None:
                continue
            if name == "google":
                if not src.usable:
                    continue
                before = src.failed
                got = src.search(niche, city)
                per["google"]["found"] += len(got)
                per["google"]["failed"] += src.failed - before
                found.extend(got)
                continue
            try:
                got = src.search(niche, city)
            except DeadlineReached:
                summary["stopped_early"] = "time limit"
                stop = True
                break
            except Exception as ex:                         # a failed search is a FAILURE, not "0 found"
                per[name]["failed"] += 1
                summary["failures"].append({"source": name, "type": niche, "area": city["name"],
                                            "error": type(ex).__name__ if name != "overpass" else str(ex)[:60]})
                ok = False
                continue
            per[name]["found"] += len(got)
            found.extend(got)
        if stop:
            break
        status[i] = "completed" if ok else "failed"
        if enough is not None and enough(found):
            summary["stopped_early"] = "lead targets reached"
            break
    summary["pairs"] = {"planned": len(pairs), "completed": status.count("completed"),
                        "failed": status.count("failed"), "not_run": status.count("not_run")}
    summary["pair_status"] = status
    g = sources.get("google")
    if g is not None:
        per["google"]["calls"] = g.calls
        if g.budget_reached:
            summary["notes"].append("Google call budget reached; other sources carried on")
        elif g.stopped:
            summary["notes"].append(f"Google Places not used: {g.stopped}")
    return found


def _classify(cfg: dict, found: list, *, ledger, include_seen: bool, deadline: float, summary: dict,
              audits: dict) -> list[Business]:
    """merge -> already-seen -> quality filters -> website audit -> score. Audits are cached by URL in
    `audits`, so classifying again (to check the lead targets) never fetches a site twice."""
    # Google answers a search with "related" places too: keep, relabel or drop each one by its name and types.
    found, crep = categorize.apply(found, cfg)
    summary["dropped"]["wrong_category"] = crep["wrong_category"]
    summary["relabelled"] = crep["relabelled"]
    merged, mstats = dedupe.merge(found)
    summary["merge"] = mstats
    fresh, seen, no_id = [], 0, 0
    for b in merged:
        if not b.source_id:
            no_id += 1
            continue
        if include_seen or ledger is None or ledger.is_new(b.source_id):
            fresh.append(b)
        else:
            seen += 1
    if no_id:
        summary["dropped"]["no_id"] = no_id
    summary["dropped"]["already_seen"] = seen

    # --- free quality filters: chains out; a missing phone is KEPT and marked --------------------
    fresh, qrep = quality.apply(merged, fresh, cfg)
    summary["dropped"]["chain"] = qrep["chains"]
    summary["website_inferred"] = qrep["website_inferred"]

    # --- audit websites, then score. Google's website (memory only) is graded when the stored record has none.
    def site_of(b):
        return b.website or getattr(b, "google_site", "")

    def fallback_of(b):
        """Google's current website, when the stored one differs (the business may have moved site)."""
        g = getattr(b, "google_site", "")
        return g if g and b.website and g != b.website else ""

    if cfg.get("website_audit", {}).get("enabled", True):
        todo = list(dict.fromkeys(site_of(b) for b in fresh if site_of(b) and site_of(b) not in audits))
        if todo and time.monotonic() < deadline:
            with ThreadPoolExecutor(max_workers=8) as pool:
                for url, a in zip(todo, pool.map(lambda u: audit.audit_site(u, cfg), todo)):
                    audits[url] = a
        for b in fresh:
            url = site_of(b)
            if not url:
                b.audit = audit.audit_site("", cfg)
            else:
                b.audit = audits.get(url) or {"verdict": "OK"}     # not checked before the time limit
        # A dead stored website is often just an old address: grade the site Google lists now instead.
        retry = [b for b in fresh if b.audit.get("verdict") == "BROKEN" and fallback_of(b)]
        todo = list(dict.fromkeys(fallback_of(b) for b in retry if fallback_of(b) not in audits))
        if todo and time.monotonic() < deadline:
            with ThreadPoolExecutor(max_workers=8) as pool:
                for url, a in zip(todo, pool.map(lambda u: audit.audit_site(u, cfg), todo)):
                    audits[url] = a
        for b in retry:
            a = audits.get(fallback_of(b))
            if a and a.get("verdict") != "BROKEN":
                b.audit = a
                b.google_site_used = True
    else:
        for b in fresh:
            b.audit = {"verdict": "NO_WEBSITE" if not site_of(b) else "OK"}
    for b in fresh:
        audit.score(b, cfg)
        if getattr(b, "google_site_used", False):
            b.reasons.append("Old website is dead; graded the website Google lists now")
        elif not b.website and getattr(b, "google_site", ""):
            b.reasons.append("Website graded from Google's listing (the map data lacked it)")
        b.fetched_at = b.fetched_at or now_iso()
    return fresh


def run(cfg: dict, pairs: list, *, sources: dict, budget: Budget, ledger=None, include_seen: bool = False,
        time_limit: float = TIME_LIMIT_SECONDS, fetch=None, clock=time.monotonic) -> tuple[list[Business], dict]:
    """Execute one fetch. Returns (businesses to report, summary)."""
    start = clock()
    deadline = start + time_limit
    summary: dict = {
        "sources": {n: {"found": 0, "failed": 0, "calls": 0} for n in SOURCE_ORDER},
        "failures": [], "notes": [], "dropped": Counter(), "merge": {}, "phone": {},
        "google_check": {}, "enrich": {},
    }
    threshold = cfg.get("min_score_to_report", 40)
    targets = lead_mix(cfg)
    audits: dict = {}

    def enough(found_so_far: list) -> bool:
        """After each area/type pair: stop searching once every bucket has its target, plus a little
        spare because the Google check can still re-grade a few."""
        trial = _classify(cfg, copy.deepcopy(found_so_far), ledger=ledger, include_seen=include_seen,
                          deadline=deadline, summary={"dropped": Counter()}, audits=audits)
        have = Counter(bucket_of(b) for b in trial if b.opportunity_score >= threshold)
        return all(have[k] >= v + max(1, v // 4) for k, v in targets.items())

    found = _discover(cfg, pairs, sources, deadline, summary, enough=enough if targets else None)
    summary["found_total"] = len(found)
    fresh = _classify(cfg, found, ledger=ledger, include_seen=include_seen, deadline=deadline,
                      summary=summary, audits=audits)

    # --- phone enrichment, then the Google check, on the same budget ------------------------------
    verifier = google_verify.build(cfg, budget) if sources.get("google") is not None else None
    pool = [b for b in found if b.source == "google"]
    summary["enrich"] = enrich.enrich_phones(
        fresh, pool, verifier, fetch=fetch or enrich.safeurl.safe_get,
        should_stop=lambda: time.monotonic() >= deadline)

    if verifier is not None:
        cands = sorted((b for b in fresh if b.opportunity_score >= threshold and bucket_of(b)),
                       key=lambda b: -b.opportunity_score)
        summary["google_check"] = verifier.run(cands)
        if verifier.budget_reached:
            summary["notes"].append("Google call budget reached during the check")
        per = summary["sources"]["google"]
        per["calls"] += verifier.calls_this_run

    ranked = sorted(fresh, key=lambda b: -b.opportunity_score)
    reported, taken = [], Counter()
    share = float((cfg.get("lead_mix") or {}).get("max_broken_share", 1.0))
    max_broken = int(targets.get("bad_website", 0) * share)
    for b in ranked:
        kind = bucket_of(b)
        if b.lead_type == "UNCHECKED":
            summary["dropped"]["site_refused_check"] += 1        # could not look: never guess "broken"
        elif not kind:
            summary["dropped"]["good_site"] += 1                 # a good website: nothing to sell them
        elif b.opportunity_score < threshold:
            summary["dropped"]["below_min_score"] += 1
        elif targets and taken[kind] >= targets.get(kind, 0):
            summary["dropped"]["over_target"] += 1
        elif kind == "bad_website" and b.lead_type == "BROKEN SITE" and targets.get("bad_website") \
                and taken["broken"] >= max_broken:
            summary["dropped"]["broken_over_share"] += 1        # keep room for weak sites (SEO / CRM pitch)
        else:
            taken[kind] += 1
            if b.lead_type == "BROKEN SITE":
                taken["broken"] += 1
            reported.append(b)
    # Broken sites skipped for the share limit come back if there were not enough weak sites to fill the spot.
    if targets.get("bad_website"):
        spare = targets["bad_website"] - taken["bad_website"]
        for b in [b for b in ranked if b.lead_type == "BROKEN SITE" and b not in reported
                  and b.opportunity_score >= threshold][:max(spare, 0)]:
            reported.append(b)
            taken["bad_website"] += 1
            taken["broken"] += 1
            summary["dropped"]["broken_over_share"] -= 1
    summary["mix"] = dict(taken)
    summary["reported"] = len(reported)
    summary["phone"] = dict(Counter((b.phone_status or ("found" if b.phone else "missing")) for b in reported))
    summary["dropped"] = dict(summary["dropped"])
    summary["seconds"] = round(clock() - start)
    return reported, summary


def public_summary(summary: dict) -> dict:
    """The summary as posted to the CRM: counts and queue results only (the CRM stores it with the run)."""
    s = {k: v for k, v in summary.items() if k != "pair_status"}
    return s
