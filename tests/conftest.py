"""Shared pytest fixtures / path setup.

Adds <repo>/tools to sys.path so the test modules can import the pipeline
modules (algorithm_guard, metrics, trace_parser) directly, exactly as the
orchestrator does, and <repo>/experiments for the research/evidence tools
(burst ablation, retrieval learning). Tests are fully offline — no
UPSTAGE_API_KEY required.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
EXPERIMENTS = ROOT / "experiments"  # research/evidence tools (ablation, retrieval)
for p in (str(TOOLS), str(EXPERIMENTS), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

WORKLOADS_DIR = ROOT / "workloads"
