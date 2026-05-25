# Demo Runbook

The final demo is driven by the host-side Orchestrator
(`scripts/orchestrator.py`). The Orchestrator selects a workload, gets the LLM
recommendation, validates it with the Algorithm Guard, runs every algorithm on
the **same deterministic workload** (same seed + profile, sequentially, the
LLM-selected one first), collects traces and metrics, and publishes them to
`dashboard_live/public/live-data/`.

> **LLM suggests. Algorithm Guard checks. xv6 executes. Metrics verify. GUI explains.**

See `docs/orchestrator_design.md` for the full design and the fairness rule, and
`docs/implementation_status.md` for what is implemented vs in progress.

---

## Dashboard overview

| Dashboard        | Purpose                               | Port  | Data source           |
|------------------|---------------------------------------|-------|-----------------------|
| `dashboard_test` | UI design / fixture visualization     | 5173  | static fixture data   |
| `dashboard_live` | Final project dashboard               | 5174  | `public/live-data/`   |
| `dashboard/`     | Streamlit fallback (legacy)           | n/a   | local files           |

---

## Final demo flow

### Step 1 — generate data with the Orchestrator (fixed seed)

Use a fixed seed so the demo is reproducible and every algorithm is compared on
the identical workload.

```bash
# Simulator backend (works end to end today)
python3 scripts/orchestrator.py --backend simulator --seed 42 --workload interactive --run-all

# xv6 backend (in progress — QEMU automation not yet end-to-end)
python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all
```

Output goes to `dashboard_live/public/live-data/` (trace JSONL per algorithm,
`metrics.json`, `manifest.json`, and the recommendation/guard/summary files).

Workload profiles: `interactive`, `cpu_bound`, `mixed`, `priority_sensitive`
(see the mapping in `docs/orchestrator_design.md`).

> The old command `python3 scripts/run_live_dashboard_pipeline.py` is a
> deprecated shim. Prefer the Orchestrator command above.

### Step 2 — start dashboard_live

```bash
cd dashboard_live
npm install
npm run dev
# open http://localhost:5174
```

### Step 3 — walk the story: Recommend -> Execute -> Evaluate

1. **Recommend** — show the workload summary and the LLM recommendation, then
   the Algorithm Guard decision (accepted / rejected + fallback).
2. **Execute** — show the per-algorithm traces (Gantt chart, ready-queue
   timeline, process state table). The LLM-selected algorithm ran first, and
   every algorithm used the same seed + profile.
3. **Evaluate** — show the before/after metrics and the comparison across
   algorithms, then the natural-language trace explanation.

### Step 4 — point out the backend indicator

In the dashboard header, point out the backend indicator:

- **XV6 TRACE** — data came from real xv6 console logs.
- **SIMULATOR FALLBACK** — data came from the host-side simulator.

This is the honest-status signal: the simulator is for development and
comparison; the final experiment path is xv6 `schedtest` driven by the
Orchestrator.

---

## Run dashboard_test (static UI fixture)

```bash
cd dashboard_test
npm install
npm run dev
# open http://localhost:5173
```

No pipeline needed. Uses static fixture data for component design/inspection.

---

## Streamlit dashboard (legacy)

```bash
streamlit run dashboard/dashboard.py
```

---

## xv6 (QEMU) by hand

```bash
cd xv6-riscv
make qemu
# in the xv6 shell:
schedtest rr        # or fcfs | priority | mlfq | sjf | srtf
```

> `schedtest` currently takes only the algorithm name. The planned
> `schedtest <algorithm> <seed> <profile>` form is in progress.

---

## Build for production

```bash
cd dashboard_test && npm run build
cd dashboard_live && npm run build
```

---

## Data contract

See `docs/dashboard_data_contract.md` for file schemas, `docs/data_format.md`
for module interfaces, and `docs/trace_format.md` for the trace formats.

---

## Limitations

- The xv6 backend (QEMU automation + seed/profile injection + rich kernel
  traces) is in progress; the simulator backend is the one that runs end to end
  today.
- The simulator is a host-side model, not proof of real xv6 execution.
- Live mode polls `manifest.json` periodically (no websocket).
