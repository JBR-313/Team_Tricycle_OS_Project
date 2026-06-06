#!/usr/bin/env python3
"""run_server.py — minimal HTTP backend for the dashboard's RUN button.

Invokes the pipeline described in docs/orchestrator_design.md.
Single-run-at-a-time, stdlib-only (no Flask/FastAPI), localhost-only by default.

Endpoints (CORS-allowed for http://localhost:5174):
  POST /api/run
      body: {"backend": "simulator"|"xv6", "profile": "<name>",
             "seed": <int>, "run_all": true, "offline_fixture": <bool>}
      -> 202 + {"run_id": "...", "state": "RUNNING"}
      -> 409 if a run is already in flight
      -> 400 on schema violation

  GET  /api/status
      -> {"state": "IDLE|RUNNING|PARSING|EVALUATING|DONE|ERROR",
          "run_id": "...", "started_at": "...", "stage": "...",
          "log_tail": [...], "error": null}

  GET  /api/live-data/<file>
      -> raw file under dashboard_live/public/live-data/
"""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
LIVE_DATA = ROOT / "dashboard_live" / "public" / "live-data"
ORCHESTRATOR = ROOT / "scripts" / "orchestrator.py"

XV6_PROFILES = {
    "interactive", "cpu_bound", "mixed", "priority_sensitive",
    "short_jobs", "starvation_risk",
}
SIM_PROFILES = XV6_PROFILES | {
    # v2 workload-ID aliases offered by the dashboard's simulator dropdown
    # (dashboard_live/.../RunControls.jsx PROFILES_SIM). These resolve in
    # orchestrator.PROFILE_MAP; keep this whitelist in sync or the RUN button
    # 400s on a profile the orchestrator would happily accept.
    "interactive_heavy", "short_jobs_clustered", "long_job_first_convoy",
    "interactive_mixed", "priority_critical_tasks",
    "cpu_bound_vs_io_bound", "ambiguous_mixed",
    "pure_batch", "bursty_long_tail",
    # Scheduling-lab coverage workloads (simulator only).
    "convoy_effect", "fairness_rr", "staggered_short_arrival",
    "starvation_priority", "burst_prediction_demo",
}

ALLOWED_ORIGINS = {
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}

LOG_TAIL_MAX = 50


class RunState:
    """Single-run-at-a-time state machine.

    States: IDLE -> RUNNING -> PARSING -> EVALUATING -> DONE | ERROR -> IDLE.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.state = "IDLE"
        self.run_id: Optional[str] = None
        self.started_at: Optional[str] = None
        self.stage: str = ""
        self.log_tail: list[str] = []
        self.error: Optional[str] = None
        self.params: dict = {}

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "state": self.state,
                "run_id": self.run_id,
                "started_at": self.started_at,
                "stage": self.stage,
                "log_tail": list(self.log_tail),
                "error": self.error,
                "params": dict(self.params),
            }

    def begin(self, params: dict) -> str:
        with self.lock:
            if self.state not in ("IDLE", "DONE", "ERROR"):
                raise RuntimeError(f"run in progress (state={self.state})")
            self.run_id = uuid.uuid4().hex[:12]
            self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self.state = "RUNNING"
            self.stage = "starting"
            self.log_tail = []
            self.error = None
            self.params = dict(params)
            return self.run_id

    def set_stage(self, state: str, stage: str) -> None:
        with self.lock:
            self.state = state
            self.stage = stage

    def append_log(self, line: str) -> None:
        with self.lock:
            self.log_tail.append(line)
            if len(self.log_tail) > LOG_TAIL_MAX:
                self.log_tail = self.log_tail[-LOG_TAIL_MAX:]

    def finish(self, ok: bool, message: str = "") -> None:
        with self.lock:
            if ok:
                self.state = "DONE"
                self.stage = message or "done"
                self.error = None
            else:
                self.state = "ERROR"
                self.stage = "error"
                self.error = message


STATE = RunState()


def _classify_stage(line: str) -> Optional[str]:
    """Map orchestrator log markers to high-level state names."""
    l = line.lower()
    if "[trace_parser]" in l or "trace_parser.py" in l:
        return "PARSING"
    if "[metrics]" in l or "evaluate" in l or "evaluat" in l:
        return "EVALUATING"
    return None


def _worker(params: dict) -> None:
    """Run orchestrator.py as a subprocess and stream stdout into the state."""
    backend = params["backend"]
    profile = params["profile"]
    seed = int(params.get("seed", 42))
    run_all = bool(params.get("run_all", True))
    offline = bool(params.get("offline_fixture", False))
    use_feedback = bool(params.get("use_feedback", False))

    cmd = [
        sys.executable, str(ORCHESTRATOR),
        "--backend", backend,
        "--workload", profile,
        "--seed", str(seed),
    ]
    if run_all:
        cmd.append("--run-all")
    if offline:
        cmd.append("--offline-fixture")
    if use_feedback:
        cmd.append("--use-feedback")

    STATE.append_log(f"$ {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd, cwd=str(ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
    except Exception as exc:
        STATE.finish(False, f"failed to spawn orchestrator: {exc}")
        return

    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        STATE.append_log(line)
        new_state = _classify_stage(line)
        if new_state:
            STATE.set_stage(new_state, line[:80])

    rc = proc.wait()
    if rc == 0:
        STATE.finish(True, "live-data published")
    else:
        STATE.finish(False, f"orchestrator exited rc={rc}")


# ── HTTP plumbing ───────────────────────────────────────────────────────────


def _validate_run_body(body: dict) -> tuple[bool, str | dict]:
    backend = body.get("backend")
    profile = body.get("profile")
    seed = body.get("seed", 42)
    if backend not in ("xv6", "simulator"):
        return False, "backend must be 'xv6' or 'simulator'"
    if not isinstance(profile, str):
        return False, "profile must be a string"
    allow = XV6_PROFILES if backend == "xv6" else SIM_PROFILES
    if profile not in allow:
        return False, f"profile '{profile}' not in allow-list for backend={backend}"
    try:
        seed = int(seed)
    except (TypeError, ValueError):
        return False, "seed must be an integer"
    return True, {
        "backend": backend,
        "profile": profile,
        "seed": seed,
        "run_all": bool(body.get("run_all", True)),
        "offline_fixture": bool(body.get("offline_fixture", False)),
        # OPT-IN feedback consumption. Defaults to False so the dashboard RUN
        # button stays deterministic; a missing field is treated as off.
        "use_feedback": bool(body.get("use_feedback", False)),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "VisualSchedulerRunServer/1.0"

    def log_message(self, fmt, *args):  # quieter logging
        sys.stderr.write(f"[run_server] {self.address_string()} - {fmt % args}\n")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, status: int, blob: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(blob)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(blob)

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/status":
            return self._send_json(200, STATE.snapshot())

        if self.path.startswith("/api/live-data/"):
            rel = self.path[len("/api/live-data/"):]
            # prevent escape
            target = (LIVE_DATA / rel).resolve()
            if not str(target).startswith(str(LIVE_DATA.resolve())):
                return self._send_json(400, {"error": "path traversal blocked"})
            if not target.is_file():
                return self._send_json(404, {"error": f"not found: {rel}"})
            ct = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return self._send_bytes(200, target.read_bytes(), ct)

        if self.path == "/api/health":
            return self._send_json(200, {"ok": True, "live_data": str(LIVE_DATA)})

        return self._send_json(404, {"error": f"no GET handler for {self.path}"})

    def do_POST(self):
        if self.path != "/api/run":
            return self._send_json(404, {"error": f"no POST handler for {self.path}"})

        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 16384:
            return self._send_json(413, {"error": "body too large"})
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            return self._send_json(400, {"error": f"invalid JSON: {exc}"})
        if not isinstance(body, dict):
            return self._send_json(400, {"error": "body must be a JSON object"})

        ok, parsed = _validate_run_body(body)
        if not ok:
            return self._send_json(400, {"error": parsed})

        try:
            run_id = STATE.begin(parsed)
        except RuntimeError as exc:
            # Spread the snapshot first, then overwrite `error` with the
            # exception message — otherwise snapshot.error=None hides it.
            body = {**STATE.snapshot(), "error": str(exc)}
            return self._send_json(409, body)

        threading.Thread(target=_worker, args=(parsed,), daemon=True).start()
        return self._send_json(202, {"run_id": run_id, "state": "RUNNING",
                                     "params": parsed})


def main() -> int:
    host = os.environ.get("RUN_SERVER_HOST", "127.0.0.1")
    port = int(os.environ.get("RUN_SERVER_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"[run_server] listening on http://{host}:{port}")
    print(f"[run_server] live-data: {LIVE_DATA}")
    print(f"[run_server] CORS origins: {sorted(ALLOWED_ORIGINS)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[run_server] shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
