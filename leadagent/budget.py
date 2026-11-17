"""
The Google Places call budget lives in the CRM backend, not here.

A GitHub runner is stateless (its disk is a cache that can be evicted, and two runs can overlap), so a
counter kept in the runner can reset or be double-spent. Before EVERY billable request the agent asks the
backend to reserve one call; the backend does an atomic "increment only if under the cap" on a counter
keyed by UTC day and UTC month, and answers granted or refused. A refusal is a normal outcome ("budget
reached"), not an error. If the backend cannot be reached the answer is "refused": no call is made.

The caps and their hard ceilings are enforced by the backend. Nothing here can raise them.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

KIND_TEXT_SEARCH = "text_search"


class Budget:
    """Interface. `reserve` must be called once per billable request, before sending it."""

    granted = 0
    refused_reason = ""

    def reserve(self, kind: str = KIND_TEXT_SEARCH) -> bool:   # pragma: no cover - interface
        raise NotImplementedError


class NoBudget(Budget):
    """Used when there is no backend to ask (local runs, dry runs): no Places call is ever made."""

    def __init__(self, reason: str = "no budget available"):
        self.refused_reason = reason

    def reserve(self, kind: str = KIND_TEXT_SEARCH) -> bool:
        return False


class BackendBudget(Budget):
    def __init__(self, base_url: str, token: str, run_id: str | None, opener=urllib.request.urlopen):
        self.url = base_url.rstrip("/") + "/api/outreach/places/reserve"
        self.token = token
        self.run_id = run_id
        self._open = opener
        self.granted = 0
        self.refused_reason = ""

    def reserve(self, kind: str = KIND_TEXT_SEARCH) -> bool:
        body = json.dumps({"runId": self.run_id, "kind": kind}).encode()
        req = urllib.request.Request(
            self.url, data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"})
        try:
            with self._open(req, timeout=60) as r:
                data = json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            self.refused_reason = f"backend answered HTTP {e.code}"
            return False
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            self.refused_reason = f"backend not reachable ({type(e).__name__})"
            return False
        payload = data.get("data", data) if isinstance(data, dict) else {}
        if payload.get("granted") is True:
            self.granted += 1
            return True
        self.refused_reason = str(payload.get("reason") or "cap reached")[:80]
        return False


def from_env() -> Budget:
    """The real budget when running in the workflow, otherwise one that refuses everything."""
    url, token = os.environ.get("CRM_URL", ""), os.environ.get("CRM_INGEST_TOKEN", "")
    if url and token:
        return BackendBudget(url, token, os.environ.get("CRM_RUN_ID") or None)
    return NoBudget("not running against the CRM")
