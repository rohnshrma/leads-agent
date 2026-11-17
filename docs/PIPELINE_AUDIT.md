# Pipeline audit (Step 0)

Read-only audit of the fetch path before any change. Written 2026-11-04 against:
leads-agent `459fa4b`, backend `fb852bb`, frontend `99bb3d6`.

## 0. Baseline tests

| Repo | Command | Result |
| --- | --- | --- |
| leads-agent | `python -m unittest discover -s tests` | 53 passed, 0 failed (pytest 9.0.3 is installed; the existing suite is unittest and also runs under pytest) |
| frontend | `npx vitest run` | 83 passed in 12 files |
| backend | `npx jest` (needs MONGODB_URI, JWT_SECRET, ADMIN_EMAIL, ADMIN_DEFAULT_PASSWORD) | 379 passed at commit `fb852bb` (last full run); re-run recorded in the PR |

Known, unrelated: one pre-existing frontend lint error (setState in effect, PipelineTab).
The baseline is green, so work continues.

## 1. The path, end to end

```
FetchPanel.tsx  "Fetch new Canada leads"
  -> POST /api/outreach/fetch            outreachFetch.controller.ts:140 triggerFetch
       enforceStartLimits                outreachFetch.controller.ts:118
       FetchRun created (unique partial index: one running run per market)
       GitHub workflow_dispatch          outreachFetch.controller.ts:58
  -> daily-leads.yml                     .github/workflows/daily-leads.yml
       gate step                         scripts/check_auto_fetch.py  (reads GET /api/outreach/ingest/config)
       "Hunt" step                       run.py  --config config-ca.yaml [--area --radius-km --niches --min-score]
       "Send results" step               scripts/push_to_crm.py  (reads newest out/leads-*.csv)
  -> POST /api/outreach/ingest           outreachFetch.controller.ts:269 ingestResults
       importRowsAllowEmpty              services/outreachImport.ts:106
       OutreachLead.insertMany           services/outreachImport.ts:146
  -> Today / Pipeline / Leads tabs       outreach.controller.ts (getToday, list)
```

## 2. Every place a business can be dropped

Agent (`leads-agent`):

| # | Where | Rule | Visible afterwards? |
| --- | --- | --- | --- |
| A1 | `sources.py:244` (`parse`) | OSM element with no `name` tag is skipped | No |
| A2 | `sources.py:216` (`out center tags {max_places}`), `config-ca.yaml:181` (`max_places_per_query: 40`) | Overpass returns at most 40 elements per business type per area. Everything past 40 is never seen. | No |
| A3 | `sources.py:389` (`LIMIT {max_places}`) | Same cap for Overture. Overture is also only used when `source: overture`; the shipped configs use `osm`, so Overture does not run at all today. | No |
| A4 | `run.py:143-144` | Any exception from `src.search(...)` is printed to stderr and the (type, area) pair is dropped. Run still exits 0. | Only in the log |
| A5 | `sources.py:299` | After 2 passes over 3 mirrors with a 30 s pause, `RuntimeError("all Overpass mirrors failed twice")` becomes A4. A failed type looks the same as a type with 0 results in the CRM. | Only in the log |
| A6 | `run.py:149-154` | Ledger: a `source_id` already in the SQLite ledger (`data/leads.db`, restored from the Actions cache) is dropped as "not seen before". The ledger is keyed by source id only. | No |
| A7 | `quality.py:148-152` | Chains: known chain names (`quality.py:34`), OSM `brand` tag, and the same normalised name at 3+ places in one run | Count only (`dropped_chains`) |
| A8 | `quality.py:153-155` | `require_phone: true` drops every record without a phone of 10+ digits. **This is the "no phone" filter.** | Count only (`dropped_no_phone`) |
| A9 | `run.py:198-200` | `min_score_to_report: 40` (`config-ca.yaml:293`) or `--min-score`. A lead below it is not written to the CSV. Google-checked leads can fall under it (`google_verify.py:180`, minus 20). | No |
| A10 | `audit.py:332-334` | Business status not OPERATIONAL sets score 0, then A9 drops it | No |
| A11 | `run.py:178-179` and `audit.py:244` | `HAS GOOD SITE` gets few points, so it falls under A9 by design | No |
| A12 | `google_verify.py:188-190` | Google says closed: score zeroed, then A9 | Count in `google_check` |
| A13 | `fetch_options.py:96` | Niche not in config list: the run refuses to start (exit code 2) | Yes, run fails |

Workflow / transport:

| # | Where | Rule |
| --- | --- | --- |
| W1 | `push_to_crm.py:35` | A CSV starting with "no new leads" sends 0 rows |
| W2 | `push_to_crm.py:28-37` | Only the newest `out/leads-*.csv` is read. Two runs on one day overwrite the same file name (`leads-YYYY-MM-DD.csv`, `run.py:202`). |
| W3 | `daily-leads.yml:139` | `continue-on-error: true` on the push step: if the CRM is unreachable the run still shows green and the leads exist only in the artifact |
| W4 | `daily-leads.yml` | No `timeout-minutes` (GitHub default is 360 min) and no `concurrency` group |

Backend:

| # | Where | Rule |
| --- | --- | --- |
| B1 | `outreachImport.ts:101` | More than 2,000 rows in one request is rejected as a whole |
| B2 | `outreachImport.ts:118` | No business name: skipped |
| B3 | `outreachImport.ts:119` | **No phone and no email: skipped.** A second "no phone" filter, after A8. |
| B4 | `outreachImport.ts:123` | Duplicate key inside the file |
| B5 | `outreachImport.ts:128-134` | Key already in the CRM (`dedupeKey` = `agent:<source_id>` if present, else `phone:<digits>`, else name+city; `outreachImport.ts:85-89`). A business seen by OSM and then by Overture has two different source ids, so it is imported twice. |
| B6 | `outreachFetch.controller.ts:281` | Scheduled run refused with 403 when auto-fetch is off or the country is disabled |
| B7 | `app.ts:78` | JSON body limit 10 MB (413 above) |
| B8 | `outreachImport.ts:146` | `insertMany(..., {ordered:false})`; a unique-key race throws and the whole batch result is lost, because the exception is not caught per document |

Frontend:

| # | Where | Rule |
| --- | --- | --- |
| F1 | Today queue (`outreach.controller.ts:207-219`) | Only leads with a due next action; leads archived or marked do-not-contact are hidden |

Why the last Halifax fetch gave 1 new lead: 12 business types x 1 area = 12 searches of at most 40 results each (A2), three of them failed on all mirrors (A5), the ledger had already seen most of what Halifax holds from earlier rotations (A6), then chains (A7), no-phone (A8) and score (A9) removed more.

## 3. Google Places today

There are two separate pieces of code.

**GooglePlacesSource** (`sources.py:87-160`) is a discovery source selected by `source: google`. It is not used by the shipped configs. Its field mask (`sources.py:92-105`) includes `places.rating`, `places.userRatingCount` and `places.primaryTypeDisplayName`. It has no call counter and no cap.

**GoogleVerifier** (`google_verify.py`) is the "Google check" that is live:

| Item | Value | Where |
| --- | --- | --- |
| Endpoint | `POST https://places.googleapis.com/v1/places:searchText` | `google_verify.py:41` |
| Field mask | `places.id, displayName, formattedAddress, location, businessStatus, websiteUri, nationalPhoneNumber, rating, userRatingCount` | `google_verify.py:42-46` |
| Query | `"<name> <address>"`, `pageSize 3`, 1 km location bias | `google_verify.py:128-135` |
| Per-run cap | `google_verify.max_per_run` = 15 | `google_verify.py:110`, `config-ca.yaml:233` |
| Monthly cap | `google_verify.monthly_call_cap` = 450 | `google_verify.py:109`, `config-ca.yaml:232` |
| Where the cap is enforced | `remaining()` at `google_verify.py:121-124`, counter `UsageMeter` at `google_verify.py:51-71` | |
| Daily cap | None in code. 32/day is a Google Cloud console quota only. | |
| Stop conditions | HTTP 400/401/403/429 sets `self.stopped` (`google_verify.py:142-144`) | |
| Key handling | Read from env `GOOGLE_MAPS_API_KEY` (`google_verify.py:233`); the key is only in the request header, not printed | |

**Weaknesses found**

1. The monthly counter lives in `data/leads.db` (SQLite, `google_verify.py:56`), restored from a GitHub Actions cache (`daily-leads.yml:85-94`). Caches are evicted after 7 days without use and are per branch. The counter can reset, and two concurrent runs each read their own copy. It is not a real cap.
2. The month key uses local time, `datetime.now()` (`google_verify.py:61`), not UTC.
3. `meter.add(1)` is not atomic across runs.
4. The 32/day Google quota is the only daily limit.
5. The check is only called for `CHECKED_TYPES` (`google_verify.py:47`), so a fetch with no such leads makes no calls.
6. Licence: the module deliberately discards Google's website, phone, rating and review count (`google_verify.py:22-26`, `keep_google_fields: false`). See section 8.

## 4. Overpass errors and timeouts

`OverpassSource.search` (`sources.py:278-299`):

- Mirrors (`sources.py:175-179`), in order: overpass-api.de, overpass.private.coffee, overpass.kumi.systems.
- Query timeout `[timeout:90]` (`sources.py:215`), HTTP timeout 120 s (`sources.py:288`). They do not match.
- Pass 1 tries each mirror once; on any non-200 or exception it moves to the next. After all three, it waits 30 s (`RETRY_PAUSE`) and makes a second pass. Then it raises.
- No exponential backoff, no jitter, `Retry-After` is not read, no distinction between 429, 504 and 400.
- `_throttle` (`sources.py:198-202`) sleeps 2 s between calls. Searches run serially, so concurrency is 1 (fine), but there is no global limit if the code is ever parallelised.
- Failure is raised to `run.py:143`, printed, and lost (A4/A5).
- The User-Agent already names rohan@webigeeksdigital.com.
- One query contains every tag for the type in a 25 km bbox for both nodes and ways, with a cap of 40 results; large areas are not split.

## 5. When Overture runs

Only when `source: overture` in the config (`sources.py:411`). Both shipped configs use `source: osm`, so Overture never runs in production. `OvertureSource` (`sources.py:305-389`) needs DuckDB, reads `s3://overturemaps-us-west-2/release/<release>`, filters by a 35 km bbox, `confidence >= 0.5`, and a LIKE on the category/name terms, and returns at most `max_places`. There is no cache between runs, so each query reads parquet over the network.

## 6. How areas and cities are chosen

- **Area given:** `fetch_options.apply_options` (`fetch_options.py:148-167`) sanitises it, matches a configured city (`fetch_options.py:106-116`) or geocodes it with Nominatim restricted to the country (`fetch_options.py:119-137`), and returns one (niche, city) pair per niche. It runs all niches against that one area.
- **Area blank:** `todays_pairs` (`run.py:47-55`) builds every (niche, city) pair from the 35 configured cities, shuffles them with the day-of-year as seed, rotates by `seed * n`, and takes `queries_per_run` = 45 pairs (`config-ca.yaml:180`). There is no memory of which pairs were searched, so pairs can repeat and others never come up for weeks. The list is Ontario-heavy but not in population order, and Quebec is excluded on purpose (`config-ca.yaml:38-41`).
- The Halifax fetch used the "area" path with 12 niches and 25 km.

## 7. CRM display and phone handling

- `mapRow` (`outreachImport.ts:36-83`) keeps the phone exactly as the source wrote it (`+1-905-726-2688`, `+1 905-332-7758`, `+19024220254` all appear in the CRM). There is no E.164 normalisation, and `dedupeKeyFor` uses raw digits (`outreachImport.ts:87`).
- The next action for a lead with a phone and no email is a call due now (`outreachImport.ts:142-144`), which puts it straight into Today.
- `OutreachLead` has no `place_id` or `phone_status` field, and no `places_fetched_at`.
- The Fetch panel shows one line per run (`FetchPanel.tsx`), built from `FetchRun.imported/skipped`.

## 8. Risks that the task has to deal with

1. **Google licence.** The existing code treats Google content (phone, website, rating) as not storable, apart from `place_id`, and discards it (`google_verify.py:22-26`, `ledger.py:1-8`). The Maps Platform terms restrict caching and storing Places content beyond `place_id` (and short-term lat/lng) and restrict using it to build outside databases. Using Places as a discovery source and saving its phone and website permanently in the CRM goes against that, and a key suspension would also stop the existing Google check. The plan below mitigates this and the owner should read the current terms and decide. See `CHANGES.md`.
2. **Overture and OSM data are free to store** (ODbL with attribution, CDLA-Permissive), so they are the safe base for permanent storage.
3. **Ledger and counters in a cache.** Anything that must be exact (the Places budget, the area cursor) has to live in the backend database, not in `data/leads.db`.
4. **Ingest is a bearer token shared by all runs** (`outreachFetch.controller.ts:250`). A run-scoped token is needed for the abuse review.
5. **`continue-on-error` on the push step** means a green workflow can hide a failed delivery.

## 9. Corrections to the plan this audit implies

- The cap of 40 per query (A2) is the single largest reason for few leads; the plan's area queue and splitting by type help, but the cap itself must be raised or paged (Overpass has no paging, so split by smaller bbox tiles).
- `require_phone` (A8) and the backend "no phone or email" skip (B3) must both change, or phone-less rows are still lost at the second one.
- Overture must be switched on as an additional source, not as a replacement for `source: osm`; today `source` is a single string.
