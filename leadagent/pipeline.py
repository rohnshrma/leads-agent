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

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import audit, dedupe, enrich, google_verify, quality
from .budget import Budget
from .sources import Business, DeadlineReached

TIME_LIMIT_SECONDS = 40 * 60
SOURCE_ORDER = ("google", "overture", "overpass")

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


def _discover(cfg: dict, pairs: list, sources: dict, deadline: float, summary: dict) -> list[Business]:
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


def run(cfg: dict, pairs: list, *, sources: dict, budget: Budget, ledger=None, include_seen: bool = False,
        time_limit: float = TIME_LIMIT_SECONDS, fetch=None, clock=time.monotonic) -> tuple[list[Business], dict]:
    """Execute one fetch. Returns (businesses that pass the score threshold, summary)."""
    start = clock()
    deadline = start + time_limit
    summary: dict = {
        "sources": {n: {"found": 0, "failed": 0, "calls": 0} for n in SOURCE_ORDER},
        "failures": [], "notes": [], "dropped": Counter(), "merge": {}, "phone": {},
        "google_check": {}, "enrich": {},
    }
    found = _discover(cfg, pairs, sources, deadline, summary)
    summary["found_total"] = len(found)

    # --- merge the same business seen by different sources (in memory) --------------------------
    merged, mstats = dedupe.merge(found)
    summary["merge"] = mstats

    # --- already seen on an earlier run (ledger) ------------------------------------------------
    fresh, seen = [], 0
    for b in merged:
        if not b.source_id:
            summary["dropped"]["no_id"] += 1
            continue
        if include_seen or ledger is None or ledger.is_new(b.source_id):
            fresh.append(b)
        else:
            seen += 1
    summary["dropped"]["already_seen"] = seen

    # --- free quality filters: chains out; a missing phone is KEPT and marked --------------------
    fresh, qrep = quality.apply(merged, fresh, cfg)
    summary["dropped"]["chain"] = qrep["chains"]
    summary["website_inferred"] = qrep["website_inferred"]

    # --- audit websites, then score --------------------------------------------------------------
    if cfg.get("website_audit", {}).get("enabled", True):
        todo = [b for b in fresh if time.monotonic() < deadline]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda b: audit.audit_site(b.website, cfg), todo))
        for b, a in zip(todo, results):
            b.audit = a
        for b in fresh[len(todo):]:
            b.audit = {"verdict": "NO_WEBSITE" if not b.website else "OK"}
    else:
        for b in fresh:
            b.audit = {"verdict": "NO_WEBSITE" if not b.website else "OK"}
    for b in fresh:
        audit.score(b, cfg)
        b.fetched_at = b.fetched_at or now_iso()

    # --- phone enrichment, then the Google check, on the same budget ------------------------------
    verifier = google_verify.build(cfg, budget) if sources.get("google") is not None else None
    pool = [b for b in found if b.source == "google"]
    summary["enrich"] = enrich.enrich_phones(
        fresh, pool, verifier, fetch=fetch or enrich.safeurl.safe_get,
        should_stop=lambda: time.monotonic() >= deadline)

    threshold = cfg.get("min_score_to_report", 40)
    if verifier is not None:
        cands = sorted((b for b in fresh if b.opportunity_score >= threshold), key=lambda b: -b.opportunity_score)
        summary["google_check"] = verifier.run(cands)
        if verifier.budget_reached:
            summary["notes"].append("Google call budget reached during the check")
        per = summary["sources"]["google"]
        per["calls"] += verifier.calls_this_run

    reported = sorted((b for b in fresh if b.opportunity_score >= threshold), key=lambda b: -b.opportunity_score)
    summary["dropped"]["below_min_score"] = len(fresh) - len(reported)
    summary["reported"] = len(reported)
    summary["phone"] = dict(Counter((b.phone_status or ("found" if b.phone else "missing")) for b in reported))
    summary["dropped"] = dict(summary["dropped"])
    summary["seconds"] = round(clock() - start)
    return reported, summary


def public_summary(summary: dict) -> dict:
    """The summary as posted to the CRM: counts and queue results only (the CRM stores it with the run)."""
    s = {k: v for k, v in summary.items() if k != "pair_status"}
    return s
