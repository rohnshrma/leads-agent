# Cost safety: what you must do by hand

The app has its own limits, but an app can have a bug. These four steps are set in Google and GitHub, outside the code, so
that even an infinite loop cannot cost more than about **Rs 1,800 a month**. The CRM shows an amber warning until you tick
each one (Fetch settings area, top of the Outreach page).

## What the app already limits

| Thing | Default | Most you can set | Enforced where |
| --- | --- | --- | --- |
| Google Text Search calls | 30 a day, 950 a month | 48 a day, 1,500 a month | CRM database counter, atomic, UTC day and month; the server rejects higher values |
| Google Place Details (opening a Google lead) | 30 a day, 950 a month | fixed, cannot be raised | same counter |
| Calls one fetch may reserve | 80 | fixed | per run |
| Fetches per person per 24 hours | 1 | 10 | server |
| GitHub runner time | free (public repo) | private repo: 1,800 min a month | `RUNNER_MINUTES_BUDGET`, only used if the repo is private |

Google prices used (global list, checked 4 Nov 2026): Text Search Enterprise and Place Details Enterprise each give 1,000 free
requests a month, then $35 and $20 per 1,000. Do not assume India pricing: it needs most of the usage to be in India, and this
tool searches Canada. Prices and the exchange rate (Rs 88 per dollar) are in `src/config/places.ts` in the backend.

Worst case with every limit at its ceiling: 500 paid Text Search calls = $17.50, plus 18% GST, at Rs 88 = **about Rs 1,817**.

## The four steps

1. **Google Cloud quotas.** Google Cloud console, project `webigeeks-digital`, APIs & Services, Places API (New), Quotas.
   Per day: Text Search **48**, Place Details **30**, every other Places method (Nearby Search, Autocomplete, Photos, Place Details
   Essentials and Pro) **0**. Google enforces these, not us.
2. **Restrict the API key.** Credentials, the key, API restrictions: **Places API (New) only**. Application restrictions: it is used
   from GitHub's runners and from the CRM server, which have no fixed address, so restrict by API and keep the key secret. Never
   put the key in the website (frontend). Use one key for the GitHub secret and a second key for the CRM server (`GOOGLE_MAPS_API_KEY`
   in Render), so one can be rotated without the other.
3. **Billing alerts** at Rs 1,000 and Rs 2,000. Google has no hard spending cap for this API, so these only email you.
4. **GitHub.** `leads-agent` is **public**, so standard GitHub-hosted runners are free and unlimited: nothing to set. If you ever
   make it private, set the Actions budget to $0 with "stop usage when budget is reached" (a private repo on GitHub Free gets
   $12 of compute a month, about 2,000 Linux minutes), and the CRM will start counting minutes by itself.

Also confirm **secret scanning** and **push protection** are on (Settings, Code security; free for public repos), and under
Settings, Actions, General, set "Approval for workflows from outside contributors" to require approval for all of them.

## Secrets and variables (GitHub, repo `leads-agent`)

| Name | Where | Notes |
| --- | --- | --- |
| `CRM_URL` | Secret (a variable still works, but a secret is better) | the CRM server address |
| `CRM_INGEST_TOKEN` | Secret | must equal `INGEST_TOKEN` on the CRM server |
| `GOOGLE_MAPS_API_KEY` | Secret | restricted to Places API (New) |

New on the CRM server (Render): `GOOGLE_MAPS_API_KEY` (second key, for the live details card), `API_PUBLIC_URL` (the server's own
public address, used in the unsubscribe link), and optionally `RUNNER_MINUTES_BUDGET`.

## The workflow is locked down

Only `workflow_dispatch` (from the CRM) and `schedule` start it. No `pull_request`, `pull_request_target` or `issue_comment`
trigger exists, so nobody outside can make it run with secrets. Token permission is `contents: read`. It has a per-market
concurrency group and a 45-minute timeout; the agent stops itself at 40 minutes. No artifact is uploaded, and the only cache is
Overture's open data. Logs print counts only (a test runs a full mocked fetch and fails if a phone, email, URL, place id or key
appears).

Note: `workflow_dispatch` inputs (area, radius, types, provinces, run id) are visible on the public run page. Nothing secret is
ever sent that way.

## Git history scan (4 Nov 2026)

Scanned all 16 commits of `leads-agent` with a local pattern scan (no tool was installed, so no download was needed) for Google
keys, GitHub tokens, AWS keys, Slack tokens, private keys, database URLs, password or token assignments, and for any `.csv`,
`.db`, `.env`, `.pem`, `.key` or `out/` data file ever committed.

**Findings: none.** No secret, token, key, `.env` file, lead data or CSV was ever committed. History was not rewritten.
`.gitignore` now also covers `.env*`, `*.csv`, `*.pem`, `*.key`, `data/`, `out/`, `cache/`.

A pattern scan is not as thorough as `gitleaks` or `trufflehog`. Please run one of them once on your own machine and add anything
it finds here. If a key was ever committed, it is public even if the file was deleted, so rotate it.

## Public-repo exposure fixed

The old workflow uploaded `out/` (the lead CSV and HTML) as an artifact kept 30 days, and printed business names in its log.
On a public repo, anyone signed in to GitHub could download that artifact. Both are gone. Runs that were already uploaded may
still be visible: delete old artifacts under the repo's Actions tab, or let the 30 days run out.

## Licence

No `LICENSE` file is added. Public code is visible but not licensed for reuse. Add one only if you decide to.
