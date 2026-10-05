#!/usr/bin/env python3
"""Send a run's results to the WebiGeeks Digital CRM.

Reads the newest out/leads-*.csv and POSTs its rows to
$CRM_URL/api/outreach/ingest, authenticated with $CRM_INGEST_TOKEN.
The CRM skips leads it already has, so re-sending is safe.

Usage:
  push_to_crm.py            send the newest CSV
  push_to_crm.py --failed   tell the CRM this run failed

Environment:
  CRM_URL, CRM_INGEST_TOKEN   required (the step is skipped when unset)
  CRM_RUN_ID                  set when the run was started from the CRM button
  GITHUB_SERVER_URL, GITHUB_REPOSITORY, GITHUB_RUN_ID   set by GitHub Actions
"""
import csv
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request


def read_rows() -> list[dict]:
    files = sorted(glob.glob("out/leads-*.csv"))
    if not files:
        return []
    with open(files[-1], newline="", encoding="utf-8") as f:
        text = f.read()
    # The agent writes a one-line note instead of a CSV when nothing new was found.
    if text.startswith("no new leads"):
        return []
    return list(csv.DictReader(text.splitlines()))


def run_url() -> str | None:
    server, repo, run = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run}" if server and repo and run else None


def post(payload: dict) -> None:
    url = os.environ["CRM_URL"].rstrip("/") + "/api/outreach/ingest"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['CRM_INGEST_TOKEN']}",
        },
        method="POST",
    )
    # The API may be asleep (free hosting): allow a slow first response and retry.
    last = None
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                print(f"CRM accepted the run (HTTP {r.status}): {r.read().decode()[:300]}")
                return
        except urllib.error.HTTPError as e:
            if e.code < 500:  # a 4xx will not fix itself on retry
                sys.exit(f"CRM rejected the request: HTTP {e.code} {e.read().decode()[:300]}")
            last = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError) as e:
            last = str(e)
        print(f"attempt {attempt} failed ({last}); retrying in {attempt * 15}s")
        time.sleep(attempt * 15)
    sys.exit(f"CRM unreachable after retries: {last}")


def main() -> None:
    if not (os.environ.get("CRM_URL") and os.environ.get("CRM_INGEST_TOKEN")):
        print("CRM_URL / CRM_INGEST_TOKEN not set - skipping CRM push")
        return
    payload = {"runId": os.environ.get("CRM_RUN_ID") or None, "githubRunUrl": run_url()}
    if "--failed" in sys.argv:
        payload.update(status="failed", error="The GitHub workflow failed. See the run log.")
    else:
        payload["rows"] = read_rows()
        print(f"sending {len(payload['rows'])} rows")
    post(payload)


if __name__ == "__main__":
    main()
