# US Lead Agent

Every morning it finds US businesses that need a website, grades the ones that
already have one, and hands you a ranked call list with phone numbers and the
exact IST time to dial.

**Cost: ₹0. No API key, no credit card, no billing account, ever.**

---

## 1. Install (2 minutes, one time)

```bash
pip install -r requirements.txt
```

That's the whole setup. No accounts to create.

## 2. Check it can reach the data

```bash
python3 run.py --check-source
```

You should see a list of real businesses with phone numbers, and a count of
how many have no website. If it fails, the message tells you what to switch.

```bash
python3 run.py --dry-run     # sample data, no network at all
python3 run.py               # the real thing
python3 run.py --queries 3   # small test run
python3 run.py --all         # ignore the ledger, re-show everything
```

Output lands in `out/`:
- `leads-YYYY-MM-DD.html` — open in a browser, read over chai
- `leads-YYYY-MM-DD.csv` — import into your CRM

## 3. Make it run at 8am automatically

**Option A — GitHub Actions (free, runs with your laptop off)**

Push this folder to a GitHub repo, enable Actions, done. No secrets to set,
because there is no API key. Reports appear as downloadable artifacts each
morning. Uses ~2 minutes/day of the free 2,000 minutes/month.

**Option B — cron on your own machine**

```bash
crontab -e
# add:
0 8 * * * /full/path/to/us-lead-agent/run_daily.sh
```

**Option C — Windows Task Scheduler**: Basic Task, daily 8:00 AM,
action `python`, arguments `run.py`, start-in this folder.

---

## The two free data sources

Both need **no key, no account and no card**. Set `source:` in `config.yaml`.

| | `source: "osm"` (default) | `source: "overture"` |
|---|---|---|
| **Cost** | Free forever | Free forever |
| **Setup** | None | Downloads a DuckDB extension on first run |
| **Coverage** | Businesses with premises | ~76M POIs, includes service-area trades |
| **Phone numbers** | Yes, when mapped | Yes, when known |
| **Websites** | Yes, when mapped | Yes, when known |
| **Reviews/ratings** | No | No |
| **Licence** | ODbL — attribution required | CDLA-Permissive-2.0 — **fully yours** |
| **Freshness** | Community-edited, varies | Monthly releases |

**Start with `osm`.** It works the second you run it. Switch to `overture`
once you want roofers, plumbers, HVAC and other trades that have no storefront
for OSM to map — that's where Overture is much stronger.

If you ever want a business-lead database you can legally **keep or resell**,
use `overture`. Its licence permits that; OSM's requires attribution and
share-alike on derived databases, and Google's forbids storage entirely.

### Why not Google Places?

Google's free tier is genuinely generous (1,000 requests/month × 20 results),
and it is the only source with **review counts**, which are the best signal of
whether a business can actually pay you. But Google requires a **billing
account with a credit card** on the project even to use the free tier. That's
why it isn't the default here. The code still supports `source: "google"` if
that ever changes for you.

### The honest trade-off you're accepting

Without Google you lose review counts, so you can't see that a business has
213 reviews at 4.8 stars before you call. The agent substitutes three signals:

- **A listed phone number** (+14, and −25 if missing) — a business that
  published a phone is operating properly, and it's the only way to reach a
  no-website lead anyway
- **How many datasets agreed the place exists** (+8) — Overture conflates Meta
  and Microsoft; agreement means it's real
- **Category value tier** (+12 / +6 / −8) — a dental clinic can afford a
  $1,500 site; a nail salon usually can't

This is weaker than review counts. You'll qualify more on the call itself
instead of before it. Practically: check the business's Google listing by hand
before dialling your top few leads each day — that's free, takes 30 seconds,
and gives you the review count for the ones that matter.

---

## What the scores mean

| Lead type | What it means | How hard to sell |
|---|---|---|
| **NO WEBSITE** | Nothing listed at all | Easiest |
| **SOCIAL ONLY** | "Website" is Facebook / Linktree / `business.site` | Easy — they think they have one |
| **BROKEN SITE** | Domain listed but won't load | Easy — they're paying for nothing |
| **PLACEHOLDER** | "Coming soon" page | Easy |
| **WEAK SITE** | Real site, but no HTTPS / not mobile / stale | Medium — needs a specific critique |
| **HAS GOOD SITE** | Leave them alone | Skip |

A lead with **no phone number is penalised hard**, because you cannot reach it.
A no-website business has no website to scrape an email from either — so the
phone is the whole channel.

## Tuning it

Everything is in `config.yaml`:

- **Not enough leads?** Add cities, add niches, lower `min_score_to_report`.
- **Too many weak leads?** Raise `min_score_to_report` to 50.
- **Only no-website businesses?** Set it to 55.
- **Want trades (roofers, plumbers)?** Switch to `source: "overture"` first —
  OSM barely has them. Then add them to `niches`.
- **New niche?** Check `leadagent/osm_tags.py` for the 46 mapped ones. An
  unmapped niche falls back to a name search, which works but is less precise.

## Why these cities

The defaults are all **East and Central** time. Their 9–11am is your
**6:30–9:30pm IST**, so you can call after your classes finish without
wrecking your sleep. They also deliberately avoid FL, OK, WA, MD, CO, MS, PA
and TX, which have state telemarketing laws with no B2B exemption.

## Being a good citizen

The OSM Overpass API is **donated infrastructure**, not a paid service. The
agent pauses 2 seconds between queries, identifies itself, and falls back
across mirrors instead of retrying one. Don't raise `queries_per_run` much
above the default 20, and don't lower `pause_seconds`. If you need higher
volume, switch to `overture`, which reads from cloud storage built for it.

## Files

```
run.py                  the runner
config.yaml             everything you tune
leadagent/sources.py    OSM/Overpass + Overture + (optional) Google
leadagent/osm_tags.py   niche -> OpenStreetMap tag mapping
leadagent/audit.py      website grading + scoring
leadagent/ledger.py     dedupe (never shows a lead twice)
leadagent/report.py     CSV + HTML output, IST call windows, attribution
run_daily.sh            cron entry point
.github/workflows/      free 8am scheduler
data/leads.db           your ledger - back this up
out/                    daily reports
```
