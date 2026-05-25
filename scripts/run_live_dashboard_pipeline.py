#!/usr/bin/env python3
"""DEPRECATED shim — use scripts/orchestrator.py instead."""
import os
import sys
from pathlib import Path

print("[deprecated] run_live_dashboard_pipeline.py is now scripts/orchestrator.py; "
      "forwarding...", file=sys.stderr)
target = str(Path(__file__).with_name("orchestrator.py"))
os.execv(sys.executable, [sys.executable, target, *sys.argv[1:]])
