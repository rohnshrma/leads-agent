# Abuse review: 1,000 accounts trying to break it

Assume 1,000 accounts (partners or someone with a stolen session). Backend test files are in `webigeeks-digital-backend/tests/`,
agent tests in `leads-agent/tests/`.

## Step 8: scenarios

| # | Scenario | How it broke, or why it did not | Fix | Test |
| --- | --- | --- | --- | --- |
| 1 | 1,000 people click Fetch at once | Did not break: a unique index allows one running fetch per market, so a second insert is refused by the database, not by a read-then-write check. The existing 4,000-request stress test and a 100-click race still pass | kept the unique partial index; "Start over" only for runs older than the cooldown | `fetchStress.test.ts`, `fetchControls.test.ts` |
| 2 | Parallel runs drain the Google budget | A read-then-write counter would overspend. Built as one atomic update ("increment only if under both caps") on a UTC day and month document | `placesBudget.ts` | `placesBudget.test.ts` (300 simultaneous reservations grant exactly 30; 60 over two runs grant 30) |
| 3 | GitHub minutes or concurrency used up | The old workflow had no timeout or concurrency. A public repo is free, but a stuck run could still pile up | per-market concurrency group, 45-minute timeout, agent stops itself at 40, private-repo minutes budget | `test_compliance_static.py`, `placesBudget.test.ts` (GitHub run time) |
| 4 | Ingest called with fake rows, huge payloads, replays | The old ingest took any rows for any run id. Now a request is accepted only for a fetch that is running, in chunks of at most 600 rows and 5,000 per run, each chunk number once, the run completes on its final chunk and then takes nothing more | see note on tokens below | `areaQueueIngest.test.ts` |
| 5 | Same lead from two runs at once | The old insert threw on a duplicate key and lost the whole batch. Now unique indexes on `placeId` and `(country, phoneKey)`, and the insert keeps the rest when one duplicate slips in | `outreachImport.ts` | `areaQueueIngest.test.ts` (two identical posts import once; two runs with one place id give one lead) |
| 6 | Two runs take the same queue batch | Each item is claimed with its own atomic update | `areaQueue.ts` | `areaQueueIngest.test.ts` (50 simultaneous claims, 300 distinct items) |
| 7 | Overpass mirrors ban the IP | Searches were serial but had no backoff and read no `Retry-After` | backoff with jitter, `Retry-After`, mirror failover, at most 2 requests at once | `test_overpass_google.py` |
| 8 | A non-owner raises limits or enables auto-fetch | Did not break: owner-only route. Added: every owner change is audit-logged with the old values | | `placesBudget.test.ts`, `compliance.test.ts` |
| 9 | Partner scrapes the whole CRM | Did not break: partners see only their own claimed leads; list size is capped at 500. Added a per-account limiter | `listAccountLimiter` | `compliance.test.ts` |
| 10 | Per-IP limits bypassed from many IPs | True for the old limiters | per-account limiters for fetch, Google details, lead list and call | `compliance.test.ts` (existence); the limiters are off under test, so this is a code check, not a load test |
| 11 | Script or huge text in business data | React escapes on render. The API did not cap lengths or filter links | strip control characters, cap every field, keep only http(s) links | `areaQueueIngest.test.ts`, `compliance-ui.test.tsx` (a rendered name with `<img onerror>` injects nothing) |
| 12 | Page fetch used for SSRF | The old auditor followed redirects anywhere | public addresses only, resolved and re-checked on every redirect, no social sites, `robots.txt` honoured | `test_phones_safeurl_log.py` |
| 13 | Month rollover resets the cap early | The old counter used local time | UTC everywhere, boundary tested to the millisecond | `placesBudget.test.ts` |
| 14 | A stuck "running" fetch blocks everyone | It took 4 hours to time out | times out after 60 minutes (the workflow is killed at 45), queue items released, late results can still complete it | `outreachFetch.test.ts` |

**Note on the "signed, single-use, per-run token" (item 4).** The workflow's inputs are visible on the public run page, so a
per-run token cannot be sent to the runner that way. The run is the scope instead: the shared ingest token (a GitHub secret) is
only honoured for a fetch that is in the running state, and a finished run takes nothing. A stolen ingest token therefore cannot
add rows unless a fetch is running, and is limited to 600 rows a request and 5,000 a run. The remaining risk is a leaked ingest
token used while a fetch is running; rotate `INGEST_TOKEN` if you ever suspect that.

**Trade-offs and limits found.**
- The unique phone index only covers leads saved after this change. Older leads have no normalised phone, so a new lead can still
  duplicate an old one by number. A one-off backfill would fix that; it was not run because it would touch every existing lead.
- Two different businesses that share one phone number cannot both be saved (one lead per number per market).
- The per-account rate limiters are not load-tested, only checked to exist.

## Step 9: break it yourself as a user

**Not done in a browser.** I did not click through the running app or the staging site, and I did not open a real workflow run
logged out. What was done is the same attempts at API level in automated tests. Please treat everything in the "browser" column as
still to do.

| Attempt | Outcome | Where covered |
| --- | --- | --- |
| Double-click and rapid-click Fetch; two tabs | one run, the rest refused (409/429) | `fetchStress.test.ts` (API) - browser not tried |
| All of Canada, then a specific area, then blank | blank and All of Canada use the queue; a specific area never touches it | `areaQueueIngest.test.ts` (API) |
| 81 characters, emoji, `<script>`, Saint-Jean-sur-Richelieu, St. John's, Montreal | too long, emoji, script refused; the three real names accepted | `areaQueueIngest.test.ts`, `compliance-ui.test.tsx` |
| Caps of 0, negative, 49, 1,501, 31, text | refused except 0 (allowed: it switches Google off); Place Details cannot be set | `placesBudget.test.ts` |
| Open one Google lead 50 times; 40 different leads in a day | 1 call; 30 calls then the limit message, CRM data still shown | `compliance.test.ts` |
| 11 fetches in a day as one person | refused above the ceiling of 10 | `fetchControls.test.ts` |
| Remove the Places key and run a fetch | Google skipped with one log line; the other sources run | `test_overpass_google.py`, `test_dedupe_enrich_pipeline.py` |
| Cut the network during a run; refresh mid-run | a failed search is counted as failed, not zero; the run times out after 60 minutes if nothing arrives | `test_dedupe_enrich_pipeline.py`, `outreachFetch.test.ts` |
| Log in as Arian and try every owner-only action | all refused (403/404) | `compliance.test.ts` |
| Archive a market during a running fetch | not tested as a combination | **not done** |
| Open a finished run's public log and artifacts logged out | not done; the workflow no longer uploads artifacts and a test fails if a log holds a phone, email, URL, place id or key | **not done** (browser) |
