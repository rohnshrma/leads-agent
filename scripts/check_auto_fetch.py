#!/usr/bin/env python3
"""Decide whether this workflow run should hunt for leads.

A run started by hand (the CRM's Fetch button, or "Run workflow" on GitHub) always goes ahead:
the CRM already checked the person is allowed to. A run started by the clock goes ahead only if
the CRM says automatic fetching is switched on AND this market's country is enabled.

It fails closed: if the CRM cannot be reached or answers anything odd, the scheduled run is
skipped. A missed morning is better than leads fetched against the owner's wishes.

Writes `proceed=true|false` to $GITHUB_OUTPUT (and prints it).

Environment: EVENT_NAME, MARKET, CRM_URL, CRM_INGEST_TOKEN, GITHUB_OUTPUT
"""
import json
import os
import sys
import urllib.error
import urllib.request

COUNTRY_OF_MARKET = {"us": "US", "ca": "CA"}


def decide(event_name: str, market: str, config: dict | None) -> tuple[bool, str]:
    """Pure decision, easy to test. Returns (proceed, reason)."""
    if event_name != "schedule":
        return True, "started by hand"
    if not isinstance(config, dict):
        return False, "could not read the CRM settings"
    if config.get("autoFetch") is not True:
        return False, "automatic fetching is switched off in the CRM"
    country = COUNTRY_OF_MARKET.get((market or "").lower())
    enabled = config.get("enabledCountries")
    if not country or not isinstance(enabled, dict) or enabled.get(country) is not True:
        return False, f"{country or market} leads are switched off in the CRM"
    return True, "automatic fetching is on"


def read_config() -> dict | None:
    base, token = os.environ.get("CRM_URL", "").strip(), os.environ.get("CRM_INGEST_TOKEN", "").strip()
    if not base or not token:
        return None
    req = urllib.request.Request(
        base.rstrip("/") + "/api/outreach/ingest/config",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = json.loads(r.read().decode())
        data = body.get("data")
        return data if isinstance(data, dict) else None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def main() -> int:
    event = os.environ.get("EVENT_NAME", "")
    config = read_config() if event == "schedule" else None
    proceed, why = decide(event, os.environ.get("MARKET", ""), config)
    print(f"proceed={'true' if proceed else 'false'} ({why})")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"proceed={'true' if proceed else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
