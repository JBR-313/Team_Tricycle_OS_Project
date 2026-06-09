#!/usr/bin/env python3
"""final_demo_check.py — one command to run before the final demo.

Runs the cheap-to-verify health checks and prints a single PASS/FAIL summary:

    PASS  python compile
    PASS  unit tests
    PASS  dashboard build
    PASS  contract validation
    SKIP  xv6 smoke (qemu-system-riscv64 not found)
    PASS  trace sanity

Design rules:
  - Never requires UPSTAGE_API_KEY (uses --offline-fixture for the smoke run).
  - xv6 smoke is SKIPPED (not FAILED) when the QEMU / RISC-V toolchain is
    unavailable, and the skip reason is explicit.
  - Exit code is non-zero iff any non-skipped check FAILED.

Usage:
    python3 scripts/final_demo_check.py
    python3 scripts/final_demo_check.py --with-xv6     # force-require xv6 smoke
    python3 scripts/final_demo_check.py --skip-build   # faster (no npm build)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
LIVE = ROOT / "dashboard_live" / "public" / "live-data"
OUT_LIVE = ROOT / "outputs" / "live"

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []  # (status, name, detail)


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    line = f"  {status:4}  {name}"
    if detail:
        line += f"  — {detail}"
    print(line, flush=True)


def run(cmd: list[str], cwd: Path | None = None, timeout: float | None = None):
    """Return (rc, combined_output). rc=-1 on timeout/spawn failure."""
    try:
        p = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "timed out"
    except Exception as exc:  # noqa: BLE001
        return -1, str(exc)


def check_python_compile() -> None:
    import glob
    files = (glob.glob(str(TOOLS / "*.py"))
             + glob.glob(str(ROOT / "scripts" / "*.py"))
             + glob.glob(str(ROOT / "tests" / "*.py")))
    rc, out = run([sys.executable, "-m", "py_compile", *files])
    record(PASS if rc == 0 else FAIL, "python compile",
           "" if rc == 0 else out.strip().splitlines()[-1] if out.strip() else "error")


def check_unit_tests() -> None:
    try:
        import pytest  # noqa: F401
    except Exception:
        record(SKIP, "unit tests", "pytest not installed (pip install -r requirements-dev.txt)")
        return
    rc, out = run([sys.executable, "-m", "pytest", str(ROOT / "tests"), "-q"], timeout=300)
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    record(PASS if rc == 0 else FAIL, "unit tests", "" if rc == 0 else tail)


def check_dashboard_build(skip: bool) -> None:
    if skip:
        record(SKIP, "dashboard build", "--skip-build")
        return
    dash = ROOT / "dashboard_live"
    if not (dash / "node_modules").is_dir():
        rc, out = run(["npm", "ci"], cwd=dash, timeout=600)
        if rc != 0:
            record(FAIL, "dashboard build", "npm ci failed")
            return
    rc, out = run(["npm", "run", "build"], cwd=dash, timeout=600)
    record(PASS if rc == 0 else FAIL, "dashboard build",
           "" if rc == 0 else "vite build failed")


def check_contract() -> None:
    rc, out = run([sys.executable, str(TOOLS / "validate_dashboard_contract.py"),
                   "--strict", "--dir", str(LIVE)])
    record(PASS if rc == 0 else FAIL, "contract validation",
           "" if rc == 0 else "strict contract violations")


def xv6_tools_available() -> tuple[bool, str]:
    if not shutil.which("qemu-system-riscv64"):
        return False, "qemu-system-riscv64 not found"
    if not (shutil.which("riscv64-unknown-elf-gcc")
            or shutil.which("riscv64-linux-gnu-gcc")):
        return False, "RISC-V gcc not found"
    return True, ""


def check_xv6_smoke(force: bool) -> None:
    ok, why = xv6_tools_available()
    if not ok:
        record(FAIL if force else SKIP, "xv6 smoke", why)
        return
    # Non-destructive: throwaway dirs so the committed demo live-data is safe.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        rc, out = run([sys.executable, str(ROOT / "scripts" / "orchestrator.py"),
                       "--backend", "xv6", "--seed", "42",
                       "--workload", "interactive", "--run-all",
                       "--out-dir", str(Path(td) / "out"),
                       "--live-data-dir", str(Path(td) / "live")],
                      timeout=600)
    record(PASS if rc == 0 else FAIL, "xv6 smoke",
           "" if rc == 0 else "orchestrator (xv6) failed — see output above")


def check_trace_sanity() -> None:
    """traces exist, JSONL parseable, metrics + manifest exist, selected trace present."""
    problems: list[str] = []
    manifest_p = LIVE / "manifest.json"
    metrics_p = LIVE / "metrics.json"
    if not manifest_p.is_file():
        problems.append("manifest.json missing")
    if not metrics_p.is_file():
        problems.append("metrics.json missing")

    selected = None
    if manifest_p.is_file():
        try:
            mf = json.loads(manifest_p.read_text())
            selected = (mf.get("llm_selected_algorithm")
                        or mf.get("recommended_algorithm"))
        except Exception:
            problems.append("manifest.json not valid JSON")

    traces = sorted(LIVE.glob("trace_*.jsonl"))
    if not traces:
        problems.append("no trace_*.jsonl files")
    for tp in traces:
        n = 0
        for ln in tp.read_text().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                json.loads(ln)
                n += 1
            except Exception:
                problems.append(f"{tp.name}: bad JSONL line")
                break
        if n == 0 and "_corrected" not in tp.name:
            problems.append(f"{tp.name}: empty trace")

    if selected:
        sel_file = LIVE / f"trace_{str(selected).lower()}.jsonl"
        if not sel_file.is_file():
            problems.append(f"selected trace {sel_file.name} missing")

    record(PASS if not problems else FAIL, "trace sanity",
           "" if not problems else "; ".join(problems[:3]))


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-demo health check")
    ap.add_argument("--with-xv6", action="store_true",
                    help="require the xv6 smoke (FAIL instead of SKIP if tools missing)")
    ap.add_argument("--skip-build", action="store_true",
                    help="skip the npm dashboard build (faster)")
    ap.add_argument("--skip-xv6", action="store_true",
                    help="do not attempt the xv6 smoke at all")
    args = ap.parse_args()

    print("=" * 60)
    print("LLM Sched Copilot — final demo check")
    print("=" * 60)

    check_python_compile()
    check_unit_tests()
    check_dashboard_build(args.skip_build)
    check_contract()
    if args.skip_xv6:
        record(SKIP, "xv6 smoke", "--skip-xv6")
    else:
        check_xv6_smoke(args.with_xv6)
    check_trace_sanity()

    print("=" * 60)
    n_pass = sum(1 for s, _, _ in results if s == PASS)
    n_fail = sum(1 for s, _, _ in results if s == FAIL)
    n_skip = sum(1 for s, _, _ in results if s == SKIP)
    print(f"  {n_pass} PASS  /  {n_fail} FAIL  /  {n_skip} SKIP")
    print("=" * 60)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
