#!/usr/bin/env python3
"""Send a run's results to the WebiGeeks Digital CRM.

Reads the newest out/leads-*.csv and out/summary.json and POSTs them to
$CRM_URL/api/outreach/ingest, authenticated with $CRM_INGEST_TOKEN.

Rows go in chunks of CHUNK_ROWS. Every chunk carries `seq` and the last one `final: true`; the CRM
ignores a chunk it has already seen, so re-sending is safe, and it completes the run on the final one.
The summary (counts only) and the queue results travel with the final chunk.

Usage:
  push_to_crm.py            send the newest CSV
  push_to_crm.py --failed   tell the CRM this run failed

Environment: CRM_URL, CRM_INGEST_TOKEN (the step is skipped when unset), CRM_RUN_ID, MARKET,
GITHUB_SERVER_URL, GITHUB_REPOSITORY, GITHUB_RUN_ID. Nothing here prints a row, a URL or a token.
"""
import csv
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request

CHUNK_ROWS = 500


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


def read_summary() -> dict:
    try:
        with open("out/summary.json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def run_url() -> str | None:
    server, repo, run = (os.environ.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{server}/{repo}/actions/runs/{run}" if server and repo and run else None


def chunks(rows: list[dict], size: int = CHUNK_ROWS) -> list[list[dict]]:
    return [rows[i:i + size] for i in range(0, len(rows), size)] or [[]]


def build_payloads(rows: list[dict], summary: dict, base: dict, size: int = CHUNK_ROWS) -> list[dict]:
    parts = chunks(rows, size)
    out = []
    for i, part in enumerate(parts):
        p = {**base, "rows": part, "seq": i, "final": i == len(parts) - 1, "totalRows": len(rows)}
        if p["final"]:
            p["summary"] = summary
            p["queue"] = summary.get("queue", [])
        out.append(p)
    return out


def post(payload: dict, opener=urllib.request.urlopen, sleep=time.sleep) -> None:
    url = os.environ["CRM_URL"].rstrip("/") + "/api/outreach/ingest"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ['CRM_INGEST_TOKEN']}"})
    # The API may be asleep (free hosting): allow a slow first response and retry.
    last = None
    for attempt in range(1, 6):
        try:
            with opener(req, timeout=120) as r:
                print(f"CRM accepted chunk {payload.get('seq', 0)} (HTTP {r.status})")
                return
        except urllib.error.HTTPError as e:
            if e.code < 500:  # a 4xx will not fix itself on retry
                sys.exit(f"CRM rejected the request: HTTP {e.code}")
            last = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError) as e:
            last = type(e).__name__
        print(f"attempt {attempt} failed ({last}); retrying in {attempt * 15}s")
        sleep(attempt * 15)
    sys.exit(f"CRM unreachable after retries: {last}")


def main() -> None:
    if not (os.environ.get("CRM_URL") and os.environ.get("CRM_INGEST_TOKEN")):
        print("CRM_URL / CRM_INGEST_TOKEN not set - skipping CRM push")
        return
    base = {
        "runId": os.environ.get("CRM_RUN_ID") or None,
        "githubRunUrl": run_url(),
        "market": os.environ.get("MARKET") or "us",
    }
    if "--failed" in sys.argv:
        post({**base, "status": "failed", "error": "The GitHub workflow failed. See the run log."})
        return
    rows = read_rows()
    print(f"sending {len(rows)} rows")
    for payload in build_payloads(rows, read_summary(), base):
        post(payload)


if __name__ == "__main__":
    main()
