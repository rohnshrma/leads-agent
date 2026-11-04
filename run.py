#!/usr/bin/env python3
"""
Lead agent - one fetch, started from the CRM's Fetch button (or by hand).

    python3 run.py --config config-ca.yaml                 # continue the national queue ("All of Canada")
    python3 run.py --config config-ca.yaml --area "Halifax" # one specific area; does not move the queue
    python3 run.py --dry-run                               # built-in sample data, no network
    python3 run.py --check-source                          # is the data source reachable?

What it does (see leadagent/pipeline.py):
  1. Takes its (business type x area) pairs: the one area asked for, or the next batch of the national
     queue from the CRM, or - if the CRM cannot be reached - the old local rotation.
  2. Searches Google Places (only within the shared call budget), Overture and OpenStreetMap, merges and
     de-duplicates them in memory.
  3. Keeps leads without a phone (marked), audits websites, scores, looks for missing phones, and runs the
     optional Google check on the same budget.
  4. Writes a CSV for the push step and a counts-only summary. The log contains counts only: this
     repository is public, so a run's log can be read by anyone.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import date, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from leadagent import budget as budget_mod, fetch_options, pipeline, queue_client, report, safelog  # noqa: E402
from leadagent.google_places import GoogleDiscovery                       # noqa: E402
from leadagent.ledger import Ledger                                       # noqa: E402
from leadagent.sources import Business, OvertureSource, build_overture, build_source, check_source  # noqa: E402

ROOT = Path(__file__).parent


def load_cfg(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def todays_pairs(cfg: dict, n: int) -> list[tuple[str, dict]]:
    """Old local rotation, used only when the CRM's queue cannot be reached."""
    cities, niches = cfg["cities"], cfg["niches"]
    pairs = [(nq, c) for c in cities for nq in niches]
    seed = date.today().toordinal()
    random.Random(seed).shuffle(pairs)
    offset = (seed * n) % max(len(pairs), 1)
    rotated = pairs[offset:] + pairs[:offset]
    return rotated[:n]


SAMPLE = [
    dict(name="Palmetto Driving Academy", category="Driving school",
         address="118 W Stone Ave, Greenville, SC 29609, USA",
         phone="(864) 232-0142", website="", rating=4.8, review_count=213),
    dict(name="Treasure Valley Roofing", category="Roofing contractor",
         address="4501 W Emerald St, Boise, ID 83706, USA",
         phone="(208) 232-0177", website="http://tvroofing-example.invalid",
         rating=4.9, review_count=41),
    dict(name="Summit Legal Group", category="Law firm",
         address="927 S Calhoun St, Fort Wayne, IN 46802, USA",
         phone="(260) 232-0188", website="", rating=4.1, review_count=3),
]


class SampleSource:
    """A source that returns built-in sample businesses (for --dry-run)."""

    def search(self, niche, city):
        return [Business(source="sample", source_id=f"sample-{i}", city_query=s["address"].split(",")[1].strip(),
                         niche_query=s["category"], business_status="OPERATIONAL", **s)
                for i, s in enumerate(SAMPLE)]


def build_sources(cfg: dict, budget, dry_run: bool, deadline: float) -> dict:
    """The discovery sources named in config `discovery:`, in the order google -> overture -> overpass."""
    if dry_run:
        return {"overpass": SampleSource()}
    wanted = [s.lower() for s in (cfg.get("discovery") or [cfg.get("source", "osm")])]
    out: dict = {}
    if "google" in wanted:
        key = os.environ.get(cfg.get("google_api_key_env", "GOOGLE_MAPS_API_KEY"), "").strip()
        if key:
            out["google"] = GoogleDiscovery(key, budget)
        else:
            print("Google Places is not used: no API key is set")
    if "overture" in wanted:
        out["overture"] = build_overture(cfg)
    if any(s in wanted for s in ("overpass", "osm", "openstreetmap")):
        o = cfg.get("overpass", {}) or {}
        from leadagent.sources import OverpassSource
        out["overpass"] = OverpassSource(
            max_places=cfg.get("max_places_per_query", 100), pause=o.get("pause_seconds", 2.0),
            radius_km=o.get("radius_km", 25.0), mirrors=o.get("mirrors") or None, tile_km=o.get("tile_km", 25.0),
            deadline=deadline)
    return out


def main() -> int:
    safelog.install()                                   # the log is public: mask anything personal
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--queries", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="use built-in sample data, make no API calls")
    ap.add_argument("--all", action="store_true", help="ignore the ledger and report everything found")
    ap.add_argument("--check-source", action="store_true", help="verify the data source is reachable, then exit")
    ap.add_argument("--area", default=None, help="search one area instead of continuing the national queue")
    ap.add_argument("--radius-km", default=None, help="search radius around --area, 1-50 km")
    ap.add_argument("--niches", default=None, help="comma-separated business types from the config's list")
    ap.add_argument("--min-score", default=None, help="only report leads at or above this score, 0-100")
    ap.add_argument("--time-limit-min", type=float, default=pipeline.TIME_LIMIT_SECONDS / 60)
    args = ap.parse_args()

    cfg = load_cfg(Path(args.config))
    try:
        cfg, area_pairs = fetch_options.apply_options(
            cfg, area=args.area, radius=args.radius_km, niches_csv=args.niches, min_score=args.min_score)
    except fetch_options.OptionError as ex:
        print(f"Cannot run with those options: {ex}", file=sys.stderr)
        return 2
    if args.check_source:
        return check_source(cfg)

    outdir = ROOT / (cfg.get("output", {}).get("dir") or "out")
    outdir.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(str(ROOT / "data" / "leads.db"))
    n = args.queries or cfg.get("queries_per_run", 45)
    started = time.monotonic()
    deadline = started + args.time_limit_min * 60

    # --- which (type x area) pairs ---------------------------------------------------------------
    queue_ids: list[str] = []
    progress: dict = {}
    if area_pairs:
        pairs = area_pairs
        print(f"one specific area, {len(pairs)} business types")
    else:
        if args.dry_run:
            n = 1
        batch = None if args.dry_run else queue_client.claim_batch(n)
        if batch and batch["items"]:
            pairs = [(i["niche"], i["city"]) for i in batch["items"]]
            queue_ids = [i["id"] for i in batch["items"]]
            progress = batch["progress"]
            print(f"national queue: {len(pairs)} items claimed")
        else:
            pairs = todays_pairs(cfg, n)
            print(f"local rotation (the CRM queue was not available): {len(pairs)} items")

    budget = budget_mod.from_env() if not args.dry_run else budget_mod.NoBudget("dry run")
    sources = build_sources(cfg, budget, args.dry_run, deadline)
    reported, summary = pipeline.run(
        cfg, pairs, sources=sources, budget=budget, ledger=ledger, include_seen=args.all,
        time_limit=args.time_limit_min * 60)

    rows = [pipeline.to_row(b, cfg) for b in reported]
    stamp = datetime.now().strftime("%Y-%m-%d")
    if cfg.get("output", {}).get("write_csv", True):
        report.write_csv(rows, outdir / f"leads-{stamp}.csv")

    # Counts only. `queue` tells the CRM which claimed items finished so it can advance its cursor.
    status = summary.pop("pair_status", [])
    summary["queue"] = [{"id": qid, "status": status[i] if i < len(status) else "not_run"}
                        for i, qid in enumerate(queue_ids)]
    summary["queue_progress"] = progress
    summary["mode"] = "area" if area_pairs else ("queue" if queue_ids else "rotation")
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    s = summary
    print("\nsummary (counts only)")
    for name, v in s["sources"].items():
        if name in sources:
            print(f"  {name:<9} found {v['found']:>4}  failed {v['failed']:>3}  calls {v['calls']:>3}")
    print(f"  merged {s['merge'].get('merged', 0)} duplicates; dropped {s['dropped']}")
    print(f"  phones {s['phone']}; enrichment {s['enrich']}")
    print(f"  reported {s['reported']} leads; pairs {s['pairs']}; {s['seconds']}s")
    for note in s["notes"]:
        print(f"  note: {note}")
    if s.get("stopped_early"):
        print(f"  stopped early: {s['stopped_early']} (the rest stays in the queue)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
