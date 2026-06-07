"""Workload JSON regression tests — schema and the no-future-burst honesty rule.

Every workload under workloads/ must be parseable, carry the required fields,
and — critically — the workload analyzer must NOT leak `actual_bursts` (true
future bursts) into the features handed to the LLM. Offline; no API key.
"""
import json

import pytest

from conftest import WORKLOADS_DIR

WORKLOAD_FILES = sorted(WORKLOADS_DIR.glob("*.json"))
REQUIRED_TOP = {"id", "description", "target_metric", "schema_version", "processes"}
REQUIRED_PROC = {"pid", "arrival_time", "cpu_bursts"}


def test_there_are_workloads():
    assert WORKLOAD_FILES, "no workload JSON files found"


@pytest.mark.parametrize("path", WORKLOAD_FILES, ids=lambda p: p.name)
def test_workload_parses_and_has_required_fields(path):
    doc = json.loads(path.read_text())
    missing = REQUIRED_TOP - set(doc)
    assert not missing, f"{path.name} missing top-level fields: {missing}"
    assert isinstance(doc["processes"], list) and doc["processes"], \
        f"{path.name} has no processes"
    for p in doc["processes"]:
        pmissing = REQUIRED_PROC - set(p)
        assert not pmissing, f"{path.name} pid={p.get('pid')} missing {pmissing}"
        assert isinstance(p["cpu_bursts"], list) and p["cpu_bursts"], \
            f"{path.name} pid={p.get('pid')} has empty cpu_bursts"


@pytest.mark.parametrize("path", WORKLOAD_FILES, ids=lambda p: p.name)
def test_pids_unique(path):
    doc = json.loads(path.read_text())
    pids = [p["pid"] for p in doc["processes"]]
    assert len(pids) == len(set(pids)), f"{path.name} has duplicate pids"


def test_analyzer_does_not_leak_actual_bursts(tmp_path):
    """The visible features the LLM sees must never include actual_bursts.

    This is the central honesty rule (CLAUDE.md Burst Prediction Rule):
    future CPU bursts must not be given to the LLM as input.
    """
    import subprocess
    import sys
    from conftest import ROOT

    # Pick a workload that actually carries actual_bursts.
    target = None
    for path in WORKLOAD_FILES:
        doc = json.loads(path.read_text())
        if any("actual_bursts" in p for p in doc["processes"]):
            target = path
            break
    if target is None:
        pytest.skip("no workload carries actual_bursts")

    # Write the summary to a tmp path (2nd arg) so the test never clobbers the
    # tracked outputs/workload_summary.json.
    summary_path = tmp_path / "workload_summary.json"
    rc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "workload_analyzer.py"),
         str(target), str(summary_path)],
        capture_output=True, text=True,
    )
    assert summary_path.is_file(), f"analyzer produced no summary (rc={rc.returncode})"
    summary = json.loads(summary_path.read_text())

    visible = (summary.get("visible_processes")
               or summary.get("processes")
               or [])
    assert visible, "analyzer summary has no visible process list"
    for p in visible:
        assert "actual_bursts" not in p, \
            "actual_bursts leaked into LLM-visible features"
        assert "cpu_bursts" not in p or "burst_count" in p, \
            "raw cpu_bursts should be summarized, not handed through verbatim"
