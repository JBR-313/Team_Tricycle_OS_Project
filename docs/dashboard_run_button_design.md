# Dashboard "Run Experiment" Button — Design

> **Scope:** Design only — no implementation in this PR. The goal is a
> button on `dashboard_live` that triggers a fresh orchestrator run and
> updates the dashboard in place. Reason for design-first: the dashboard
> is a static Vite app today and cannot start QEMU on its own; introducing
> a backend HTTP service is a non-trivial security/process boundary that
> must be agreed before code lands.

---

## 1. Problem

Today the only way to refresh the dashboard with new data is:

1. Run `python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload <profile> --run-all` in a terminal.
2. Wait for it to publish `dashboard_live/public/live-data/`.
3. The dashboard's live-poll picks up the new `manifest.json` within ~1 s.

This is fine for engineering but invisible to a demo audience — the
“pipeline runs here” claim has no on-screen evidence. A **Run Experiment**
button makes the loop visible.

## 2. Why React can't do this alone

- `dashboard_live` is a Vite SPA; the browser cannot fork QEMU, run Python,
  or write files outside the sandbox.
- The orchestrator is a Python CLI that needs subprocess control of `make`,
  `qemu-system-riscv64`, and the host filesystem (`outputs/`,
  `dashboard_live/public/live-data/`).
- We therefore need a thin **backend service** running on the same host as
  the dashboard, which the React app calls over `fetch`.

## 3. State machine

Single global run state, owned by the backend:

```
            POST /api/run                         on success
   IDLE  ──────────────►  RUNNING ────► PARSING ──────► EVALUATING ──► DONE
     ▲                       │             │                │             │
     │                       │ (any step throws / non-zero) │             │
     │                       ▼             ▼                ▼             │
     │                            ERROR  ◄┴────────────────┘             │
     │                                                                    │
     └─── client polls /api/status; backend resets to IDLE on next /run ──┘
```

| State | Backend behaviour | Dashboard hint |
|---|---|---|
| `IDLE` | Run button enabled. | “Ready.” |
| `RUNNING` | xv6 backend: `make qemu` + `schedtest` per algorithm. Simulator backend: `scheduler_simulator.run_all_algorithms`. Streams progress lines to a ring buffer for `/api/status`. | Disable button, spin. Show current algorithm. |
| `PARSING` | `trace_parser.py` on each `xv6_raw_*` (xv6 path); simulator path is already JSONL so this is a no-op. | “Parsing trace…”. |
| `EVALUATING` | `metrics.py` + `trace_explainer.py` (LLM) + `event_detector.py` + `validate_dashboard_contract.py`. | “Evaluating…”. |
| `DONE` | live-data published, manifest version bumped. Auto-transitions to `IDLE` after the dashboard pulls one full reload. | “Run complete — N events parsed.” |
| `ERROR` | Last error message + which stage failed (`run`/`parse`/`evaluate`/`publish`). | Red banner + “Reset.” |

Implementation primitive: a single `RunState` dataclass + `asyncio.Lock` or
`threading.Lock`. Only one run at a time; second `POST /api/run` returns
HTTP 409 with the current state in the body.

## 4. HTTP surface

Minimum surface (matches the user's spec):

### 4.1 `POST /api/run`

Request body:
```json
{
  "backend":  "xv6" | "simulator",
  "profile":  "interactive" | "cpu_bound" | "mixed" | "priority_sensitive",
  "seed":     42,
  "run_all":  true,
  "offline_fixture": false
}
```

Validation:
- `profile ∈ XV6_PROFILES` from `scripts/orchestrator.py:76`.
- `seed` is `int` (≥ 0).
- `backend = xv6` requires `qemu-system-riscv64` on `PATH` (server-side
  probe at startup; refuse with 503 if missing).

Response:
- `202 Accepted` + `{ "run_id": "...", "state": "RUNNING" }` on success.
- `409 Conflict` + current state if another run is in progress.
- `400 Bad Request` for schema violations.

Side effect: spawns a worker thread that invokes the equivalent of the
existing CLI (`scripts/orchestrator.py`) — we deliberately call the
existing entry point rather than reimplementing it, so the CLI and the
button stay in lockstep.

### 4.2 `GET /api/status`

```json
{
  "state":    "RUNNING",
  "run_id":   "2026-05-28T11:42:03Z-7e",
  "stage":    "schedtest mlfq",
  "started_at": "2026-05-28T11:42:03Z",
  "progress": { "completed_algos": 3, "total_algos": 6 },
  "log_tail": ["[orchestrator] running mlfq…", "..."]
}
```

`log_tail` is the last N (e.g. 20) lines of the run's combined stdout/stderr.
This is what the dashboard renders into the “current run” panel.

### 4.3 `GET /api/live-data/<file>`

Plain static file proxy that maps to
`dashboard_live/public/live-data/<file>`. Today Vite's dev server already
serves these; in production (`npm run build`) the backend would need to
serve them. The endpoint exists so the dashboard can resolve **one** base
URL whether running under `vite dev` or `python -m http.server`.

### 4.4 (Optional) `POST /api/cancel`

Hard-kill the current run (SIGTERM the orchestrator subprocess, mark state
`ERROR` with reason `cancelled`). Out of scope for the first iteration.

## 5. Server skeleton (sketch — not implemented in this PR)

Stack: stdlib `http.server` + `threading`. Zero new dependencies (matches
`requirements.txt`'s "stdlib only at runtime" rule).

```
scripts/run_server.py            (~150 lines, sketch)
   ├── parse_args()              host=127.0.0.1, port=8765
   ├── class RunState:
   │     state, run_id, started_at, stage, log_tail
   │     lock = threading.Lock()
   ├── class RunWorker(threading.Thread):
   │     run():
   │       state -> RUNNING
   │       subprocess.run(["python3", "scripts/orchestrator.py", ...], stream)
   │       state -> PARSING / EVALUATING based on log markers
   │       state -> DONE
   │
   ├── class Handler(BaseHTTPRequestHandler):
   │     POST /api/run     → spawn worker, return 202
   │     GET  /api/status  → JSON snapshot of RunState
   │     GET  /api/live-data/<file> → serve from dashboard_live/public/live-data/
   │     anything else     → 404
   │
   └── if __name__ == "__main__": ThreadingHTTPServer((host, port), Handler).serve_forever()
```

Frontend hook (sketch):

```js
// dashboard_live/src/data/runClient.js
const RUN_API = "http://localhost:8765"
export async function startRun(args) {
  const r = await fetch(`${RUN_API}/api/run`, { method: "POST",
    headers: {"content-type":"application/json"}, body: JSON.stringify(args) })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
export async function getRunStatus() {
  const r = await fetch(`${RUN_API}/api/status`); return r.json()
}
```

A new `<RunControls/>` component sits in the dashboard header next to the
snapshot selector; it owns a `useEffect` poll on `/api/status` every 750 ms
while `state !== IDLE` and triggers `loadAll()` (existing) once
`state === DONE`.

## 6. Security / safety

This is a process-spawn endpoint; it must never face the public internet.

- **Bind 127.0.0.1 only.** Configurable but default-localhost.
- **No shell interpolation.** Pass orchestrator args as a list to
  `subprocess.run` — never a shell string.
- **Profile/backend allow-list.** Validate against the constants already in
  `orchestrator.py`; reject anything else with 400.
- **No new env injection.** The server inherits the user's environment for
  `UPSTAGE_API_KEY` and friends; the request body cannot set env vars.
- **CORS.** Only allow the dashboard's origin (`http://localhost:5174` by
  default).
- **Rate limit.** One run at a time. Second `POST /run` → 409.
- **Logs** redact `Authorization` / `UPSTAGE_API_KEY` if they ever appear.

## 7. Non-goals

- **Multi-user / queue.** A single run-in-flight is sufficient for a demo.
- **Persistent run history.** The CLI/orchestrator already produces
  `outputs/build_*.log` and `outputs/check_xv6_scheduler_*.log`; reuse those
  instead of inventing a new store.
- **Cancellation UI** — `POST /api/cancel` is optional, off in v1.
- **Running multiple profiles in parallel.** xv6+QEMU is single-CPU
  (`-smp 1` in `orchestrator.py:71`); parallel runs would race for the
  output directory.
- **Web-driven build.** Building the kernel is part of the orchestrator's
  xv6 path; we expose the same path, no separate “build” button.

## 8. Sequencing

Three steps, each independently shippable:

1. **Backend service** (`scripts/run_server.py`) — pure stdlib, no UI
   changes. Smoke-test with `curl`.
2. **Frontend client + state hook** (`runClient.js`, `RunControls.jsx`) —
   wired against a running `run_server.py`, gated by `VITE_RUN_API` env
   var. When the env var is absent the controls hide → existing snapshot
   demo is unchanged.
3. **End-to-end** — orchestrator log markers (`[orchestrator] stage=…`)
   that the worker thread parses into `RunState.stage`, so the dashboard
   knows whether we're at `parse` vs `evaluate`.

Effort estimate: ~½ day each, ≤ 400 lines total.

## 9. Demo decision

For the final demo this is **deferred to post-demo work**. The reasons:

- The snapshot selector + four xv6 profiles already gives the audience a
  visible state change without needing a live QEMU run.
- A live run during the demo introduces failure surface (QEMU timing, LLM
  latency, network) that is not worth the upside given we already have
  green snapshots.
- The design is captured here so we can land it cleanly after the demo
  without a second design round.

