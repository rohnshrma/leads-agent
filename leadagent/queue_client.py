"""
The national area queue lives in the CRM backend (it must survive between runs and be claimed atomically,
which a stateless runner cannot do). The agent asks for the next batch; after the run, the ingest payload
tells the backend which items completed and which failed.

If the backend cannot be reached, the agent falls back to the old local rotation so a run is never empty.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def claim_batch(limit: int, opener=urllib.request.urlopen) -> dict | None:
    """{"items": [{"id", "niche", "city": {"name","lat","lng"}}], "progress": {...}} or None."""
    base, token = os.environ.get("CRM_URL", ""), os.environ.get("CRM_INGEST_TOKEN", "")
    if not (base and token):
        return None
    req = urllib.request.Request(
        base.rstrip("/") + "/api/outreach/queue/claim", method="POST",
        data=json.dumps({"runId": os.environ.get("CRM_RUN_ID") or None, "limit": int(limit)}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with opener(req, timeout=60) as r:
            data = json.loads(r.read().decode() or "{}")
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    data = data.get("data", data) if isinstance(data, dict) else {}
    items = [i for i in (data.get("items") or []) if isinstance(i, dict) and i.get("id") and i.get("niche")
             and isinstance(i.get("city"), dict) and i["city"].get("name")
             and i["city"].get("lat") is not None and i["city"].get("lng") is not None]
    return {"items": items, "progress": data.get("progress") or {}}
