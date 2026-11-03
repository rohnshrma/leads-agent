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

## Cutting out the junk leads (free, on by default)

The map data lists businesses nobody can sell to. Before any website is audited, `quality_filters:` in the
config drops or fixes three kinds. On the 84 Canadian leads of 25 Oct, hand-checking a sample found chains
(LensCrafters, Hakim Optical, Optimum Wellness), a clinic with a site the map lacked (Cor-Dent), and
records with wrong or missing phones.

| Filter | What it does |
|---|---|
| `skip_chains` | Drops known chains, anything OpenStreetMap tags with a `brand`, and one name found at 3+ separate places. Add your own in `chain_names`. |
| `require_phone` | Drops records with no usable phone number. A no-website lead can only be reached by phone. |
| `infer_website_from_email` | An email on the business's own domain (`info@theirclinic.ca`) means it has a website. That site is audited instead of being called "NO WEBSITE". |

The auditor also retries once, with a longer wait, before calling a slow site "BROKEN". Each run prints how many
leads were dropped and why. Switch any filter off in `config.yaml` / `config-ca.yaml`.

## Google check (optional, OFF)

The free sources cannot see closed businesses, websites missing from the map, or demand. A Google Places lookup
of the best candidates can. It is built but switched off. It runs only when `google_verify.enabled: true` **and**
the key in `GOOGLE_MAPS_API_KEY` is set (add it as a GitHub Actions secret). It then:

- drops businesses Google says are closed;
- re-grades a lead when Google lists a website the map lacked, so false "NO WEBSITE" leads are not reported;
- takes points off a lead Google cannot find (name or phone probably out of date);
- adds points for reviews when the business is verified and has no website.

**Cost and limits.** It uses Text Search with phone/website/rating, Google's Enterprise SKU: the first 1,000
requests a month are free, then $35 per 1,000. It makes one request per candidate. `monthly_call_cap` (default
900, counted in the ledger) and `max_per_run` (default 40) stop it spending; a bad key or quota error stops the
run. Also set a daily quota in the Google Cloud console, which is the cap Google itself enforces. A billing
account is required.

**Licence.** Google allows storing place IDs but not its other content, so by default only `google_place_id`
and `google_status` are kept; Google's website, rating and review count are used to decide and then discarded.
`keep_google_fields: true` keeps them, but check Google's current Maps Platform terms first. Whether Google's
terms allow building lead lists was not confirmed; read them before turning this on for real use.

**Try it before trusting it.** Run it for a week on the free allowance and compare, on one checklist, how many of
the leads it passes versus the ones it would have dropped are genuinely callable.

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
leadagent/quality.py    free filters: chains, no-phone records, website inferred from email
leadagent/google_verify.py  optional Google Places check (off by default, capped)
tests/                  python -m unittest discover -s tests
leadagent/ledger.py     dedupe (never shows a lead twice)
leadagent/report.py     CSV + HTML output, IST call windows, attribution
run_daily.sh            cron entry point
.github/workflows/      free 8am scheduler
data/leads.db           your ledger - back this up
out/                    daily reports
```

---

## Sending results to the WebiGeeks Digital CRM

Every run (the 8 AM schedule, or a manual run) can push its new leads straight
into the CRM, and the CRM has a **Fetch new leads** button that starts a run.

```
CRM button -> GitHub Actions (this workflow) -> scripts/push_to_crm.py -> CRM /api/outreach/ingest
8 AM schedule ---------------------------------^
```

Setup, once:

1. In this GitHub repo: Settings -> Secrets and variables -> Actions
   - **Variable** `CRM_URL` = your CRM API address, e.g. `https://webigeeks-digital-api.onrender.com`
   - **Secret** `CRM_INGEST_TOKEN` = a long random string
2. In the CRM API's settings (Render): `INGEST_TOKEN` = the same random string.
3. For the button: create a fine-grained GitHub token limited to this repo with
   **Actions: read and write**, and set it as `GITHUB_TOKEN` in the CRM API settings.

Until those exist the push step is skipped and the workflow behaves as before
(the CSV is still attached to each run as a downloadable artifact).

---

## Fetching by hand: area, filters and the on/off switches

The CRM's **Fetch new leads** button can start a run with choices (Area & filters), and the owner has a
**Fetch settings** box. These reach this repo as inputs of the workflow and as `run.py` options:

```bash
python3 run.py --config config-ca.yaml --area "Brampton, ON" --radius-km 15 --niches "med spa,dental clinic" --min-score 55
```

- `--area` searches just that place (a configured city needs no lookup; anything else is looked up on
  OpenStreetMap's Nominatim, restricted to the market's country). Without it, the usual cities rotate.
- `--niches` must be from the config's list; `--radius-km` is 1-50; `--min-score` is 0-100. Bad values stop the run
  with exit code 2 before anything is fetched. The ledger still hides businesses already found.
- **Automatic runs are off by default.** The two crons still fire, but the first workflow step
  (`scripts/check_auto_fetch.py`) asks the CRM and stops unless the owner switched on "Fetch automatically" and that
  country. If the CRM cannot be reached it stops (fails closed). Runs started from the CRM button always go ahead.
- The workflow passes typed values to `run.py` as quoted environment variables, never pasted into a shell command.
- How often a person may click Fetch (default once per 24 hours each, changeable by the owner) is enforced by the CRM, not here.
- Tests: `python -m unittest discover -s tests` (includes 1,000 hostile area strings).
