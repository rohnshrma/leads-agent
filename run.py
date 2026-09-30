#!/usr/bin/env python3
"""
US Lead Agent - runs once, every morning, and hands you a ranked list of
US businesses that need the thing you sell.

    python3 run.py                 # normal daily run
    python3 run.py --check-source  # is my data source reachable?
    python3 run.py --dry-run       # use built-in sample data, no network
    python3 run.py --queries 5     # smaller run
    python3 run.py --all           # ignore the ledger, re-show everything

What it does, in order:
  1. Picks today's (city x niche) search pairs, rotating so you cover the
     whole map over a week instead of hammering one city.
  2. Pulls businesses from Google Places (or Overture).
  3. Drops anything it has already shown you (ledger, by place id).
  4. Visits each listed website and grades it.
  5. Scores every business on how badly it needs you.
  6. Writes a CSV to work from and an HTML page to read.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from leadagent import audit, report                       # noqa: E402
from leadagent.ledger import Ledger                       # noqa: E402
from leadagent.sources import (Business, build_source,      # noqa: E402
                               check_source)

ROOT = Path(__file__).parent


def load_cfg(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def todays_pairs(cfg: dict, n: int) -> list[tuple[str, dict]]:
    """Rotate deterministically by day-of-year so coverage spreads out."""
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
         phone="(864) 555-0142", website="", rating=4.8, review_count=213),
    dict(name="Rocket City Heating & Air", category="HVAC contractor",
         address="2210 Clinton Ave W, Huntsville, AL 35805, USA",
         phone="(256) 555-0119",
         website="https://www.facebook.com/rocketcityheating", rating=4.6,
         review_count=88),
    dict(name="Treasure Valley Roofing", category="Roofing contractor",
         address="4501 W Emerald St, Boise, ID 83706, USA",
         phone="(208) 555-0177", website="http://tvroofing-example.invalid",
         rating=4.9, review_count=41),
    dict(name="Scenic City Dental", category="Dentist",
         address="1400 McCallie Ave, Chattanooga, TN 37404, USA",
         phone="(423) 555-0155", website="https://example.com",
         rating=4.4, review_count=132),
    dict(name="Summit Legal Group", category="Law firm",
         address="927 S Calhoun St, Fort Wayne, IN 46802, USA",
         phone="(260) 555-0188", website="", rating=4.1, review_count=3),
]


def sample_businesses() -> list[Business]:
    out = []
    for i, s in enumerate(SAMPLE):
        out.append(Business(
            source="sample", source_id=f"sample-{i}",
            city_query=s["address"].split(",")[1].strip(),
            niche_query=s["category"], business_status="OPERATIONAL", **s))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--queries", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="use built-in sample data, make no API calls")
    ap.add_argument("--all", action="store_true",
                    help="ignore the ledger and report everything found")
    ap.add_argument("--check-source", action="store_true",
                    help="verify the data source is reachable, then exit")
    args = ap.parse_args()

    cfg = load_cfg(Path(args.config))
    if args.check_source:
        return check_source(cfg)
    outdir = ROOT / (cfg.get("output", {}).get("dir") or "out")
    outdir.mkdir(parents=True, exist_ok=True)
    ledger = Ledger(str(ROOT / "data" / "leads.db"))

    n = args.queries or cfg.get("queries_per_run", 25)
    found: list[Business] = []
    queries_made = 0

    if args.dry_run:
        found = sample_businesses()
        queries_made = len(SAMPLE)
        src_name = "sample data (dry run)"
        print(f"[dry-run] {len(found)} sample businesses")
    else:
        src = build_source(cfg)
        src_name = cfg.get("source", "google")
        for niche, city in todays_pairs(cfg, n):
            try:
                got = src.search(niche, city)
                queries_made += 1
                found.extend(got)
                print(f"  {city['name']:<22} {niche:<24} {len(got):>3} found")
            except Exception as ex:
                print(f"  ! {city['name']} / {niche}: {ex}", file=sys.stderr)

    # Dedupe against the ledger (place ids only).
    fresh = []
    seen_now = set()
    for b in found:
        if not b.source_id or b.source_id in seen_now:
            continue
        seen_now.add(b.source_id)
        if args.all or ledger.is_new(b.source_id):
            fresh.append(b)
    print(f"\n{len(found)} businesses, {len(fresh)} not seen before")

    # Audit websites in parallel - this is the slow part.
    if cfg.get("website_audit", {}).get("enabled", True):
        print(f"auditing {len(fresh)} websites...")
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda b: audit.audit_site(b.website, cfg), fresh))
        for b, a in zip(fresh, results):
            b.audit = a
    else:
        for b in fresh:
            b.audit = {"verdict": "NO_WEBSITE" if not b.website else "OK"}

    for b in fresh:
        audit.score(b, cfg)
        ledger.remember(b)

    threshold = cfg.get("min_score_to_report", 40)
    reported = sorted(
        (b for b in fresh if b.opportunity_score >= threshold),
        key=lambda b: -b.opportunity_score)

    stamp = datetime.now().strftime("%Y-%m-%d")
    meta = dict(date=stamp, queries=queries_made, found=len(found),
                fresh=len(fresh), reported=len(reported), source=src_name)

    rows = [b.as_row() for b in reported]
    mk = cfg.get("mockups", {}) or {}
    if mk.get("enabled") and rows:
        from leadagent.mockups import build_mockups
        mdir = outdir / (mk.get("dir") or "mockups")
        base = (mk.get("base_url") or "").rstrip("/")
        owner = {"company": cfg.get("outreach", {}).get("your_company", ""),
                 "email": cfg.get("outreach", {}).get("your_email", "")}
        built = build_mockups(rows, mdir, owner=owner)
        by_id = {(r["source_id"]): m for r, m in built}
        for r in rows:
            m = by_id.get(r["source_id"])
            r["mockup_path"] = m["path"] if m else ""
            r["mockup_url"] = f"{base}/{m['slug']}/" if (m and base) else ""
        print(f"mockups -> {mdir} ({len(built)} built)")
    if cfg.get("output", {}).get("write_csv", True):
        p = outdir / f"leads-{stamp}.csv"
        report.write_csv(rows, p)
        print(f"CSV  -> {p}")
    if cfg.get("output", {}).get("write_html", True):
        p = outdir / f"leads-{stamp}.html"
        report.write_html(reported, p, meta)
        print(f"HTML -> {p}")

    ledger.log_run(queries_made, len(found), len(fresh), len(reported))
    (outdir / "last-run.json").write_text(json.dumps(meta, indent=2))

    print(f"\n{len(reported)} leads scored >= {threshold}. "
          f"Ledger knows {ledger.stats()['total_known']} businesses.")
    for b in reported[:5]:
        print(f"  {b.opportunity_score:>3}  {b.lead_type:<14} {b.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
