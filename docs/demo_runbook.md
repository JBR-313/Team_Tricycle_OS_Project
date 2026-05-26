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
| `dashboard_live` | **Primary** generated-data dashboard  | 5174  | `public/live-data/` (written by `scripts/orchestrator.py`) |
| `dashboard_test` | **Static UI lab** — fixture data only | 5173  | hardcoded fixtures in `src/data/`                          |
| `dashboard/`     | Streamlit fallback (legacy)           | n/a   | local files                                               |

---

## Final demo flow

### Step 1 — generate data with the Orchestrator (fixed seed)

Use a fixed seed so the demo is reproducible and every algorithm is compared on
the identical workload.

```bash
# xv6 backend (final demo / experiment path)
python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all

# Simulator backend (fast dev / fallback path)
python3 scripts/orchestrator.py --backend simulator --seed 42 --workload interactive --run-all
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

- The simulator backend is a host-side model, not proof of real xv6 execution —
  keep it for fast UI development and as a fallback; the **xv6 backend is the
  final demo / experiment path**.
- Live mode polls `manifest.json` periodically (no websocket streaming).
- The runtime correction loop is not closed end to end — `event_detector.py`
  exists, but the proposer / LLM call / guard re-check / apply step are not
  wired (Future Work).
- Solar Pro 3 API key in `.env` is required for a real LLM recommendation;
  without it, the orchestrator falls back to a baked
  `outputs/demo/recommendation.json`, stamps `metadata_source=demo_fallback`
  in `manifest.json`, and the dashboard downgrades the badge to `FALLBACK`.
- xv6 traces are short and sparse (5 children per curated profile, typically
  30–80 events per algorithm). The simulator typically produces richer traces.
  The multiplier-based starvation rule in `tools/metrics.py` (3× avg waiting)
  may flag tiny waits as starvation on these short runs and force a `FAIL`
  judgment — this is a metric-rule limitation on small workloads, not a
  scheduler bug.

---

## Demo command sequence (presenter checklist)

Follow this in order during the live demo. Every step is copy-pasteable.

### 0. (Optional) Pull latest main

```bash
git checkout main
git pull --ff-only origin main
```

### 1. Generate live data on the real xv6 backend

```bash
python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all
```

What this does, in order:

1. `workload_analyzer.py` → `workload_summary.json`
2. `llm_advisor.py` → `recommendation.json` (Solar Pro 3; demo fallback if no key)
3. `algorithm_guard.py` → `guard_decision.json`
4. **Build xv6 (CPUS=1)**, then for each algorithm (LLM-selected first):
   boot QEMU → type `schedtest <algo> 42 interactive` → capture serial console
   to `outputs/xv6_raw_<algo>_seed42.log` → window on `RUN_BEGIN`/`RUN_END` →
   parse to `outputs/live/trace_<algo>.jsonl` → rebase ticks to 0
5. Aggregate `metrics.json` (per-algorithm `comparison` block + judgment)
6. Copy everything to `dashboard_live/public/live-data/` + write fresh
   `manifest.json` (with `backend=xv6`, incremented `version`)

If everything succeeds you should see `[DONE] Orchestrator pipeline complete.`

### 2. Start the live dashboard

```bash
cd dashboard_live
npm install        # first time only
npm run dev        # opens http://localhost:5174
```

### 3. What to show on screen

In the header bar, point to (left → right):

- **Brand** "LLM Sched Copilot · LIVE"
- **Data status** with manifest version (`v10`, …), last-updated timestamp,
  and the live polling dot (green = polling, ■ = replay mode).
- **Backend badge** (the honesty signal):
  - `Backend: XV6 TRACE` — real xv6 console log was loaded.
  - `Backend: SIMULATOR FALLBACK` — host-side simulator output.
  - `Backend: FALLBACK` — even the recommendation/guard came from
    `outputs/demo/`. Should NOT appear in a real demo.
- **Manifest meta**: workload, llm-selected algo, executed count, seed, total
  trace events.
- **Algorithm selector** — switch between the algorithms (LLM-selected first).
- **Replay / Live** toggle and tick slider.

Then walk the page top → bottom:

1. **Workload Summary** — the synthetic profile interpretation.
2. **LLM Recommendation** + **Algorithm Guard** — accepted/rejected, params.
3. **Main Gantt / Process Lanes / Trace Stack** — per-algorithm timeline.
4. **Algorithm Comparison + Metric Visualization** — same workload, every
   algorithm, target-metric judgment.
5. **LLM Explanation / Evaluation Result** — natural-language summary.

### 4. Fallback command — if xv6/QEMU does not work on the demo machine

If the kernel fails to build, QEMU is missing, or a serial-console capture
times out, switch backends without changing anything else:

```bash
python3 scripts/orchestrator.py --backend simulator --seed 42 --workload interactive --run-all
# refresh dashboard_live; the badge will switch to SIMULATOR FALLBACK
```

The dashboard will visibly downgrade to `Backend: SIMULATOR FALLBACK` so the
audience can see that the data is from the host model, not real xv6.
