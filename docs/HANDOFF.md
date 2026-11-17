# Handoff: continue on another device (updated 2026-11-12)

## State
Three pull requests, branch `feat/more-callable-leads` in each repo. Nothing is merged or deployed.
| Repo | PR | Tests |
| --- | --- | --- |
| leads-agent | https://github.com/rohnshrma/leads-agent/pull/1 | 197 pass |
| webigeeks-digital-backend | https://github.com/rohnshrma/webigeeks-digital-backend/pull/1 | 488 pass, tsc clean |
| webigeeks-digital-frontend | https://github.com/rohnshrma/webigeeks-digital-frontend/pull/1 | 108 pass |

## Start on a new machine
1. Clone the three repos side by side, then `git checkout feat/more-callable-leads` in each.
2. Agent tests: `python -m pytest` (Python 3; on the old PC it was `/c/Users/rohn1/anaconda3/python.exe`).
3. Backend tests: `npm ci && npm test`. Needs env `MONGODB_URI`, `JWT_SECRET` (32+ chars), `ADMIN_EMAIL`, `ADMIN_DEFAULT_PASSWORD` (tests use mongodb-memory-server).
4. Frontend: `npm ci && npm test` (Vitest). `AGENTS.md` warns this Next.js is non-standard; read it before editing.
5. Read, in order: this file, `PIPELINE_AUDIT.md`, `COST_SAFETY.md`, `COMPLIANCE.md`, `ABUSE_REVIEW.md`, each repo's `CHANGES.md` and `memory.md`.

## Do these by hand (nothing in code can do them)
1. Four steps in `COST_SAFETY.md`: Google quotas (Text Search 48/day, Place Details 30/day, others 0), restrict keys to Places API (New), billing alerts Rs 1,000 and Rs 2,000, GitHub secret scanning and outside-contributor approval.
2. Run `gitleaks` or `trufflehog` once on leads-agent history (only a pattern scan was done).
3. Register free with the National DNCL operator and enter the number in the red CRM banner. Calls stay blocked until then.
4. Render env on the backend: `GOOGLE_MAPS_API_KEY` (a second key), `API_PUBLIC_URL`, optional `RUNNER_MINUTES_BUDGET`. Optionally move `CRM_URL` to a GitHub secret.
5. Delete old public artifacts in the leads-agent Actions tab.
6. Review the draft `/terms` and `/privacy` pages, remove the DRAFT notice, and get a Canadian lawyer to read `COMPLIANCE.md`.
7. Merge order: backend PR, deploy it, then the agent PR, then the frontend PR.

## Not done
- Step 9: clicking through the running app in a browser, opening a finished run's public log logged out, archiving a market during a running fetch.
- A real end-to-end run (live Google, GitHub, Overture). Everything is mocked; the agent and backend ingest were tested separately.
- Provincial statutory holidays; a `phoneKey` backfill for old leads; the "number belongs to WebiGeeks" clause in the partner agreement; US compliance review.
- City coordinates (two decimals) were not individually verified.
- Per-account rate limiters are only checked to exist, not load-tested.
- Still undecided from earlier: Quo versus a backup calling provider.

## Rules that must not be broken
- Only the Google `place_id` is stored; Google name, phone, website, address are shown live with "Google Maps" attribution.
- Hard ceiling Rs 2,000/month: Text Search at most 48/day and 1,500/month, Place Details fixed 30/950.
- The leads-agent repo is public: no secrets, no lead data, no artifacts, counts-only logs.
- US market stays off.
- Google Cloud work only under rohan@webigeeksdigital.com; the owner puts the API key into GitHub secrets.
