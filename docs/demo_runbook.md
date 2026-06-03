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

> **Validation scope at a glance.** The final demo path is
> `--backend xv6 --seed 42 --workload interactive`. That is what
> `scripts/final_demo_check.py` (and §"Demo command sequence" below)
> exercises end-to-end on the demo machine. `scripts/multi_profile_demo_check.py`
> reruns the same xv6 + strict-validator chain across every curated
> profile (`interactive`, `cpu_bound`, `mixed`, `priority_sensitive`)
> for broader confidence — all four currently pass on xv6 per
> `docs/xv6_profile_support.md`; it is **not** a substitute for the
> demo check. GitHub Actions CI (`.github/workflows/ci.yml`) is
> lightweight only (py_compile + strict validator on committed
> live-data + the two dashboard builds); **it does not run QEMU/xv6**
> and a green CI badge does not replace the local demo check. See
> `docs/final_demo_acceptance.md` §0 for the authoritative breakdown.

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
  `outputs/_demo_fixtures/recommendation.json`, stamps `metadata_source=demo_fallback`
  in `manifest.json`, and the dashboard downgrades the badge to `FALLBACK`.
- xv6 traces are short and sparse (5 children per curated profile, typically
  30–80 events per algorithm). The simulator typically produces richer traces.
  The starvation rule in `tools/metrics.py` is hardened for short traces (it
  requires the relative 3× rule, an absolute ≥5-tick floor, a wait ≥50% of
  makespan, and a minimum completed-process count; an explicit
  `STARVATION_WARNING` event stays authoritative), so tiny waits no longer
  false-trigger a starvation `FAIL`. The remaining xv6 `FAIL` judgments are
  regret-driven (the LLM picked a non-optimal algorithm on a small workload),
  not starvation.

---

## Demo command sequence (presenter checklist)

Follow this in order during the live demo. Every step is copy-pasteable.

### 0. (Optional) Pull latest main

```bash
git checkout main
git pull --ff-only origin main
```

### 1. One command — sanity-check + generate live data

The presenter's single demo-prep command:

```bash
python3 scripts/final_demo_check.py
```

Three fail-fast stages — the script bails on the first non-zero stage,
so you only see the green path:

1. `py_compile tools/*.py scripts/*.py` (catch import / syntax errors)
2. `python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all`
   — the real xv6 backend (Builds xv6 CPUS=1, boots QEMU per algorithm,
   types `schedtest <algo> 42 interactive`, captures the serial console,
   windows the run, parses to `trace_<algo>.jsonl`, aggregates
   `metrics.json`, and publishes to `dashboard_live/public/live-data/`).
3. `python3 tools/validate_dashboard_contract.py --strict ...` — refuses
   to greenlight a broken demo. Empty traces, missing manifest fields,
   recommendation/guard/manifest algorithm disagreement, etc. all fail
   the script.

On success you'll see `[OK] All pre-demo checks passed.` and the one
next-step line printed below. The script does NOT auto-open a browser
— start the dashboard manually so you control the terminal.

Useful flags:

- `--backend simulator` — use the simulator instead of xv6 (see
  step 4 below for when to use this).
- `--skip-orchestrator` — fast re-check (compile + validate only) when
  the live-data is already fresh.
- `--no-strict-validator` — make the validator non-blocking.

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
    `outputs/_demo_fixtures/`. Should NOT appear in a real demo.
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
times out, switch backends with the same check script:

```bash
python3 scripts/final_demo_check.py --backend simulator
# refresh dashboard_live; the badge will switch to SIMULATOR FALLBACK
```

The dashboard will visibly downgrade to `Backend: SIMULATOR FALLBACK` so the
audience can see that the data is from the host model, not real xv6.

### 5. Honest limitations to acknowledge during the demo

- **No websocket streaming.** The dashboard polls `manifest.json`
  periodically; there is no push channel.
- **Runtime correction loop is partial.** `tools/event_detector.py` exists,
  but the proposer → LLM call → guard re-check → apply step → trace
  `CORRECTION_APPLIED` event are not wired. Don't claim closed-loop.
- **Solar Pro 3 API key.** Without `.env`, the orchestrator falls back to
  `outputs/_demo_fixtures/recommendation.json` and stamps
  `metadata_source=demo_fallback`; the dashboard then shows
  `Backend: FALLBACK`. Should not occur in a real demo.
- **xv6 traces are short educational traces.** 5 children per curated
  profile, ~30–80 events per algorithm. Simulator traces are typically
  richer. The starvation rule applies multiple conjunctive gates (relative
  3×, absolute ≥5-tick floor, ≥50%-of-makespan share, and a minimum
  completed-process count; explicit `STARVATION_WARNING` stays authoritative
  — see `tools/metrics.py` and `tools/test_metrics_starvation.py`) so
  sub-tick noise on these short workloads is no longer flagged as starvation.
