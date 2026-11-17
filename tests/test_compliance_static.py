"""Rules that must hold for this PUBLIC repository, checked from the files themselves."""
import importlib.util
import re
import sys
from pathlib import Path
from unittest import mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def workflow():
    return yaml.safe_load((ROOT / ".github" / "workflows" / "daily-leads.yml").read_text(encoding="utf-8"))


def test_workflow_can_only_be_started_by_dispatch_or_schedule():
    on = workflow().get("on") or workflow().get(True)       # YAML 1.1 reads a bare `on` as True
    assert set(on) == {"schedule", "workflow_dispatch"}
    text = (ROOT / ".github" / "workflows" / "daily-leads.yml").read_text(encoding="utf-8")
    for bad in ("pull_request", "issue_comment", "pull_request_target", "workflow_run", "issues:", "push:"):
        assert bad not in text.replace("# Two ways it starts - and ONLY these two (no pull_request, no issue_comment", ""), bad


def test_workflow_token_is_read_only_and_runs_are_bounded():
    wf = workflow()
    assert wf["permissions"] == {"contents": "read"}
    assert wf["jobs"]["hunt"]["timeout-minutes"] == 45
    assert "group" in wf["concurrency"] and wf["concurrency"]["cancel-in-progress"] is False


def test_no_artifact_is_uploaded_and_only_open_data_is_cached():
    text = (ROOT / ".github" / "workflows" / "daily-leads.yml").read_text(encoding="utf-8")
    assert "upload-artifact" not in text
    paths = [s.get("with", {}).get("path") for s in workflow()["jobs"]["hunt"]["steps"] if "cache" in s.get("uses", "")]
    assert paths == ["cache/overture"]                         # never data/, out/ or mockups


def test_secrets_come_from_github_secrets_and_the_workflow_prints_no_values():
    text = (ROOT / ".github" / "workflows" / "daily-leads.yml").read_text(encoding="utf-8")
    assert "secrets.GOOGLE_MAPS_API_KEY" in text and "secrets.CRM_INGEST_TOKEN" in text and "secrets.CRM_URL" in text
    assert not re.search(r"echo\s+.*\$\{?(CRM_URL|CRM_INGEST_TOKEN|GOOGLE_MAPS_API_KEY)", text)
    assert "continue-on-error: true" not in text.split("Send results to the CRM")[1].split("Tell the CRM")[0]


def test_the_hunt_step_stops_itself_before_the_job_timeout():
    hunt = next(s for s in workflow()["jobs"]["hunt"]["steps"] if s.get("name") == "Hunt")
    assert "--time-limit-min 40" in hunt["run"]


def test_no_code_path_extracts_email_addresses():
    banned = [r"EMAIL_RE", r"harvest", r"emails_found", r"mailto:", r"\[a-zA-Z0-9\._%\+\\?-\]\+@", r"findall\([^)]*@"]
    for path in list((ROOT / "leadagent").rglob("*.py")) + [ROOT / "run.py", ROOT / "scripts" / "push_to_crm.py"]:
        if "mockups" in path.parts:
            continue
        src = path.read_text(encoding="utf-8")
        for pat in banned:
            assert not re.search(pat, src), (path.name, pat)


def test_rows_never_carry_an_email_address():
    from leadagent import pipeline
    from leadagent.sources import Business
    b = Business(source="osm", source_id="node/1", name="X", email="owner@x.ca", phone="+19055261234")
    assert pipeline.to_row(b, {"country": "CA"})["email"] == ""


def test_the_google_key_is_only_ever_read_from_the_environment():
    for path in (ROOT / "leadagent").rglob("*.py"):
        assert not re.search(r"AIza[0-9A-Za-z_\-]{20,}", path.read_text(encoding="utf-8")), path.name
    for name in ("config.yaml", "config-ca.yaml"):
        assert "AIza" not in (ROOT / name).read_text(encoding="utf-8")


def test_gitignore_keeps_secrets_and_lead_data_out():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for needle in (".env*", "*.csv", "data/", "out/", "cache/"):
        assert needle in ignore


def test_shipped_configs_use_the_safe_defaults():
    ca = yaml.safe_load((ROOT / "config-ca.yaml").read_text(encoding="utf-8"))
    assert ca["discovery"] == ["google", "overture", "overpass"]
    assert ca["output"]["write_html"] is False
    assert len(ca["overpass"]["mirrors"]) == 3 and ca["overpass"]["mirrors"][0].startswith("https://overpass-api.de")
    us = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert us["discovery"] == ["overpass"] and us["google_verify"]["enabled"] is False     # US stays off


# ---------------------------------------------------------------- push script
def load_push():
    spec = importlib.util.spec_from_file_location("push_to_crm", ROOT / "scripts" / "push_to_crm.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_five_thousand_rows_go_in_chunks_with_one_final():
    push = load_push()
    rows = [{"source_id": f"node/{i}"} for i in range(5000)]
    parts = push.build_payloads(rows, {"queue": [{"id": "q1", "status": "completed"}]}, {"runId": "r1", "market": "ca"})
    assert len(parts) == 10 and all(len(p["rows"]) <= push.CHUNK_ROWS for p in parts)
    assert [p["seq"] for p in parts] == list(range(10))
    assert [p["final"] for p in parts] == [False] * 9 + [True]
    assert "summary" in parts[-1] and "summary" not in parts[0]
    assert parts[-1]["queue"] == [{"id": "q1", "status": "completed"}]
    assert sum(len(p["rows"]) for p in parts) == 5000


def test_an_empty_run_still_sends_one_final_chunk_so_the_run_completes():
    push = load_push()
    parts = push.build_payloads([], {}, {"runId": "r1"})
    assert len(parts) == 1 and parts[0]["final"] is True and parts[0]["rows"] == []


def test_a_crm_outage_fails_the_step_and_prints_no_address(capsys, monkeypatch):
    import urllib.error
    push = load_push()
    monkeypatch.setenv("CRM_URL", "https://secret-crm.example.com")
    monkeypatch.setenv("CRM_INGEST_TOKEN", "tok-123456")

    def boom(req, timeout=0):
        raise urllib.error.URLError("down")

    with pytest.raises(SystemExit) as e:
        push.post({"runId": "r"}, opener=boom, sleep=lambda s: None)
    out = capsys.readouterr()
    assert "unreachable" in str(e.value)
    assert "secret-crm" not in out.out + out.err + str(e.value) and "tok-123456" not in out.out + out.err + str(e.value)
