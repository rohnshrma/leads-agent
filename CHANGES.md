# Changes: lead pipeline upgrade (leads-agent)

## What changed
- **Sources:** Google Places (Text Search, only inside a shared call budget kept by the CRM backend), then Overture on every fetch (cached per area), then OpenStreetMap. Merged and de-duplicated in memory by place id, phone, website domain, then name within 75 m (branches more than 5 km apart are never merged).
- **Google data is held in memory only.** A Google lead leaves the agent as place_id, source, score, type and time. The field mask is exactly the approved list; a test fails if it changes.
- **Leads with no phone are kept** and marked `phone_status = missing`. A phone is looked for in this order: Google results already fetched, one Places lookup (if budget remains), the lead's own website (one page, `robots.txt` honoured, 10 s, strict pattern; never social or directory sites). Phones are saved as +1XXXXXXXXXX.
- **Overpass:** three mirrors from config, backoff with jitter (2, 5, 12 s), `Retry-After`, matching query and HTTP timeouts, large areas split into tiles, at most 2 requests at once, and a failed search is recorded as failed, never as 0 results.
- **Public-repo hardening:** read-only token, only `workflow_dispatch` and `schedule`, per-market concurrency, 45-minute timeout (the agent stops itself at 40 and requeues the rest), no artifact upload, a cache holding only Overture open data and pip packages, counts-only logs with a masking filter, chunked ingest, and a failed delivery now fails the step.
- **Email scraping removed** (the auditor no longer reads emails from websites; finder rows carry no email).
- **Safe fetching:** public addresses only, every redirect re-checked, no social or directory sites, `robots.txt` honoured.

## Settings (config-ca.yaml)
| Setting | Default |
| --- | --- |
| `discovery` | `[google, overture, overpass]` (US config: `[overpass]`) |
| `overpass.mirrors` / `tile_km` | three mirrors / 25 |
| `overture.cache_dir` | `cache/overture` |
| `max_places_per_query` | 100 (was 40) |
| `google_verify.enabled` / `max_per_run` | true / 15 (US: false) |
| `output.write_html` | false |
Removed: `google_verify.monthly_call_cap`, `keep_google_fields`, `quality_filters.require_phone`.

## Secrets and variables
`CRM_URL` (secret preferred, variable still works), `CRM_INGEST_TOKEN`, `GOOGLE_MAPS_API_KEY`. New workflow input `provinces` (set by the CRM).

## Compliance fixes (existing code that broke the rules)
- The workflow uploaded the lead CSV and HTML as public artifacts and printed business names in the log. Both removed.
- The lead ledger was cached between runs (lead ids in a cache). Removed; the CRM de-duplicates.
- The Google check kept its own call counter in a cached SQLite file (could reset, double-spend). Now uses the backend budget.
- The auditor harvested email addresses from business websites. Removed.
- A missing phone cost 25 score points, which pushed leads under the minimum and dropped them. No longer.

## Not done / notes
- Provincial statutory holidays are not built in.
- Overture was not downloaded for real in tests (mocked); the first real run will download and cache it.
- No `LICENSE` file was added (public code is visible but not licensed for reuse). Add one only if you want to.
- Old runs' artifacts may still be visible on GitHub until they expire; delete them from the Actions tab.
