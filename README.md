# LLM Sched Copilot

**The LLM-Assisted Scheduler for xv6**

---

## 1. Core Idea

Traditional xv6 scheduling behavior is usually visible only through terminal logs or source code.  
This project turns that low-level behavior into a trace-verified scheduling workflow.

A host-side **Orchestrator** (`scripts/orchestrator.py`) is the control plane. It
selects a workload, gets the LLM recommendation, validates it with the Algorithm
Guard, runs the workload through a backend (xv6 or the simulator), parses the
trace, computes metrics, and publishes the result to the dashboard. The
Orchestrator is **not** the scheduler — it only coordinates the modules and the
run order. xv6 remains the execution authority.

```text
scripts/orchestrator.py   (host-side control plane)
        ↓
workload selection  (profile → workloads/*.json)
        ↓
tools/workload_analyzer.py        → workload_summary.json
        ↓
tools/llm_advisor.py (Solar Pro 3) → recommendation.json
        ↓
tools/algorithm_guard.py          → guard_decision.json
        ↓
backend:  QEMU/xv6 boot → schedtest run → xv6 scheduler logs
          (or simulator: tools/scheduler_simulator.py)
        ↓
tools/trace_parser.py             → normalized trace_<algo>.jsonl
        ↓
tools/metrics.py                  → metrics.json
        ↓
dashboard_live/public/live-data/  → dashboard_live
```

The **final experiment path** is xv6 `schedtest` driven by the Orchestrator. The
Python simulator is used for fast UI development and fallback comparison; it is
not proof of real xv6 execution. See `docs/orchestrator_design.md`.

The main question of this project is:

> Can an LLM help choose, tune, correct, and explain xv6 Scheduling Algorithms using workload summaries and Scheduling Trace Logs?

---

## 2. System Principle

The system separates responsibility clearly.

| Component | Responsibility |
|---|---|
| Orchestrator (`scripts/orchestrator.py`) | Host-side control plane. Sequences workload selection, LLM advice, guard, backend execution, parsing, metrics, and dashboard publish. Not the scheduler. |
| LLM | Interprets workload, recommends Scheduling Algorithm, proposes correction, explains result |
| Algorithm Guard | Checks whether the LLM output is valid and safe to apply |
| xv6 (`schedtest.c` backend) | Executes the selected Scheduling Algorithm. The xv6 execution backend; runs inside QEMU and prints trace lines to the console. |
| Scheduler Simulator (`scheduler_simulator.py`) | Dev / fallback ONLY. Host-side model of the algorithms; not real xv6 execution. |
| Trace Monitor | Collects Scheduling Trace Logs and detects runtime events |
| Metrics Evaluator | Verifies the scheduling result with numerical metrics |
| GUI | Visualizes recommendation, execution, correction, metrics, and explanation |

The LLM is a **decision support layer**, not the kernel scheduler.

### Final Demo Pipeline — PRIMARY / FALLBACK / LEGACY

For the final demo, **xv6 + QEMU is the primary execution path**. Everything
else is a dev/test fallback or kept for legacy safety.

```
Workload (workloads/*.json or schedtest profile)
   → LLM Advisor (Upstage Solar Pro 3, tools/llm_advisor.py)
       → Algorithm Guard (tools/algorithm_guard.py)
           → xv6 + QEMU via scripts/orchestrator.py --backend xv6
              (kernel/proc.c · user/schedtest.c · [SCHED]/[SCHEDTEST] logs)
                  → tools/trace_parser.py → trace_<algo>.jsonl
                      → tools/metrics.py → metrics.json (judgment, regret)
                          → dashboard_live (React/Vite, port 5174)
```

| Path | Label | One-line | Audience-visible? |
|---|---|---|---|
| `xv6-riscv/` + `scripts/orchestrator.py --backend xv6` | **PRIMARY** | Real xv6 + QEMU execution via `schedtest`; the final demo path. | yes |
| `dashboard_live/` | **PRIMARY** | Live React/Vite observability dashboard. | yes |
| `tools/scheduler_simulator.py` + `--backend simulator` | **FALLBACK (dev/test)** | Host-side Python model. Not proof of real xv6 execution; used for UI iteration and when QEMU is unavailable. | yes, with badge `SIMULATOR FALLBACK` |
| `outputs/_demo_fixtures/` (offline demo fallback) | **FALLBACK (no API key / no QEMU)** | Committed fixture data so the dashboard still has something to show. Stamps `manifest.metadata_source = "demo_fallback"`. | yes, with badge `FALLBACK` |
| `outputs/_demo_fixtures/` snapshots | reference | Canonical fixtures also live in `dashboard_live/public/live-data/snapshots/`. | no |

> The dashboard header shows a backend badge — **`XV6 TRACE`** on the
> primary path, **`SIMULATOR FALLBACK`** on the dev path, **`FALLBACK`**
> when only the committed fixtures are in use. If you see anything other
> than `XV6 TRACE` during the demo, name it out loud — the badge is there
> precisely so the audience is not misled.

### Component roles in the new flow

- **Orchestrator** is the control plane. It owns the run order: it runs every
  algorithm sequentially on the same deterministic workload (same seed +
  profile), with the LLM-selected algorithm first, so the comparison is fair.
- **`schedtest.c`** is the xv6 execution backend. It is a tiny xv6 user program:
  it sets a scheduling algorithm via a system call, forks children, and prints
  `[SCHED]` / `[SCHEDTEST]` lines. It cannot open a dashboard or call the LLM.
- **`scheduler_simulator.py`** is the dev / fallback path. The Python simulator
  is used for fast UI development and fallback comparison. The final experiment
  path is xv6 `schedtest` driven by the host-side Orchestrator.

The LLM cannot:

- choose the next process at every timer tick
- directly modify kernel state
- directly perform context switches
- apply unverified recommendations automatically
- replace xv6 Scheduling Algorithms

---

## 3. Supported Scheduling Algorithms

The project targets the following Scheduling Algorithms.

### 3.1 Round Robin

Round Robin is the baseline Scheduling Algorithm.  
It gives runnable processes CPU time in turn and prevents a single process from monopolizing the CPU.

### 3.2 FCFS

FCFS executes processes in arrival order.  
It is simple, but it can suffer from the convoy effect when a long CPU-bound process arrives before short jobs.

### 3.3 Priority Scheduling + Aging

Priority Scheduling selects a process based on priority.  
It can improve the response of important processes, but low-priority processes may suffer from starvation.

Aging is used to reduce starvation by gradually increasing the effective priority of waiting processes.

### 3.4 MLFQ

MLFQ uses multiple queues with different time quantums.  
It can favor short or interactive jobs while demoting long CPU-bound jobs.

LLM Sched Copilot can suggest MLFQ parameters such as:

- number of queues
- time quantum for each queue
- aging threshold
- boost interval

### 3.5 SJF / SRTF + Burst Prediction

SJF and SRTF are powerful Scheduling Algorithms because they favor short CPU bursts.

However, a real OS cannot know the exact next CPU burst in advance.  
Therefore, this project treats burst prediction as an experimental feature.

Possible predictors:

- traditional exponential averaging
- LLM-assisted burst prediction
- LLM-assisted predictor parameter tuning

The LLM must not receive the actual future CPU burst as input.

---

## 4. LLM Roles

The LLM works in three phases.

---

### 4.1 Before Running

#### 4.1.1 Workload Interpreter

The LLM receives a workload summary generated from observable workload information.

It may infer:

- workload type
- CPU-bound tendency
- interactive tendency
- burst variance
- priority distribution
- starvation risk
- target metric

Example output:

```json
{
  "workload_type": "interactive_heavy",
  "target_metric": "avg_response_time",
  "main_risks": ["poor_response_time", "starvation"],
  "reason": "The workload contains multiple short interactive jobs mixed with long CPU-bound jobs."
}
```

The LLM does not know exact future execution results.

#### 4.1.2 Scheduling Algorithm Advisor

The LLM recommends a Scheduling Algorithm and parameters.

Example output:

```json
{
  "recommended_scheduling_algorithm": "MLFQ",
  "params": {
    "queues": 3,
    "quantum": [2, 4, 8],
    "aging_threshold": 30,
    "boost_interval": 100
  },
  "target_metric": "avg_response_time",
  "risk": ["starvation if aging is too weak"],
  "reason": "MLFQ can favor short interactive jobs while still allowing long CPU-bound jobs to make progress."
}
```

The recommendation is sent to the Algorithm Guard before execution.

---

### 4.2 Running

#### 4.2.1 Runtime Correction Proposer *(Partial / Future Work)*

> This subsection describes the **planned** closed-loop runtime
> correction design — the **target**, not what ships today. On
> current main only `tools/event_detector.py` exists. The proposer,
> the LLM call, the guard re-check on a correction, the apply step
> in xv6, and the `CORRECTION_APPLIED` trace event the dashboard
> would render are all Future Work. See the §11.1 Implementation
> Status row.

During execution, the Trace Monitor watches the Scheduling Trace Log.

If a scheduling problem is detected, the system summarizes the event and asks the LLM for a correction.

Example detected events:

- starvation warning
- poor response time
- too many preemptions
- long CPU-bound domination
- high waiting time
- burst prediction failure

Example correction output:

```json
{
  "correction_type": "parameter_update",
  "current_scheduling_algorithm": "MLFQ",
  "new_params": {
    "quantum": [2, 4, 8],
    "aging_threshold": 20,
    "boost_interval": 80
  },
  "reason": "The previous aging threshold was too high, so low-priority processes waited too long."
}
```

Possible correction types:

- parameter update
- Scheduling Algorithm change
- process hint update
- aging threshold adjustment
- time quantum adjustment

The correction would be re-checked by the Algorithm Guard.

In the design target, the correction would be applied at the next scheduling point, not by interrupting every timer tick with an LLM call. **Today this apply step is still Future Work** (see §11.1).

---

### 4.3 After Running

#### 4.3.1 Trace Explainer

After execution, the system summarizes:

- Scheduling Trace Log
- Scheduling Metrics
- detected runtime events
- comparison with other Scheduling Algorithms

Then the LLM explains the result in natural language.

Example output:

```json
{
  "summary": "FCFS performed poorly on this workload.",
  "detected_pattern": "convoy_effect",
  "main_reason": "A long CPU-bound process arrived first and delayed short interactive jobs.",
  "evidence": [
    "P1 ran from tick 0 to tick 40.",
    "P2 arrived at tick 5 but first ran at tick 41.",
    "Average response time was much higher than MLFQ."
  ],
  "suggestion": "MLFQ or Round Robin would reduce response time for short jobs."
}
```

The Trace Explainer helps users understand not only what happened, but why it happened.

#### 4.3.2 Feedback Rule Generator *(Partial / Future Work)*

> Design target, not shipped today. No production feedback-rule
> generator exists in `tools/`. The example below is the **planned**
> JSON shape, included so the design is visible to readers. See
> §11.1.

If the LLM recommendation was poor, the system asks the LLM to generate a feedback rule.

Example:

```json
{
  "failed_case": {
    "llm_selected": "FCFS",
    "actual_best": "MLFQ",
    "regret_score": 0.42
  },
  "feedback_rule": "If burst variance is high and many interactive jobs arrive after a long CPU-bound job, avoid FCFS and prefer MLFQ or Round Robin."
}
```

The feedback rule can be used in later LLM prompts.

---

## 5. Algorithm Guard

The Algorithm Guard prevents invalid or unsafe LLM output from being applied.

It checks:

- whether the recommended Scheduling Algorithm is implemented
- whether the parameters are in valid ranges
- whether required information exists
- whether burst prediction is available when SJF/SRTF is requested
- whether the correction type is supported
- whether the output follows the required JSON schema

Example decisions:

```json
{
  "guard_result": "accepted",
  "reason": "MLFQ is implemented and all parameters are valid."
}
```

```json
{
  "guard_result": "rejected",
  "reason": "SRTF requires burst prediction, but no predictor output was provided.",
  "fallback_scheduling_algorithm": "MLFQ"
}
```

---

## 6. Scheduling Trace Log

The Scheduling Trace Log records important scheduling events.

Example:

```text
[SCHED] tick=12 algo=RR event=DISPATCH pid=3 state=RUNNING queue=0
[SCHED] tick=16 algo=RR event=PREEMPT pid=3 state=RUNNABLE queue=0
[SCHED] tick=17 algo=RR event=DISPATCH pid=4 state=RUNNING queue=0
[SCHED] tick=45 algo=RR event=EXIT pid=4 state=ZOMBIE queue=0
```

Target events:

- ARRIVE
- DISPATCH
- PREEMPT
- SLEEP
- WAKEUP
- EXIT
- QUEUE_CHANGE
- CORRECTION_APPLIED

---

## 7. Metrics Evaluator

The Metrics Evaluator verifies whether the LLM recommendation was actually useful.

Metrics:

- average waiting time
- average response time
- average turnaround time
- throughput
- max waiting time
- starvation occurrence
- preemption count
- burst prediction error
- regret score

Definitions:

```text
response time = first_run_time - arrival_time
turnaround time = finish_time - arrival_time
waiting time = turnaround_time - total_cpu_burst_time
throughput = completed_process_count / total_execution_time
```

Recommendation judgment:

```text
SUCCESS      = LLM selected the best or near-best Scheduling Algorithm
NEAR-SUCCESS = LLM result is close to the best result
FAIL         = LLM result is clearly worse than the best result
```

---

## 8. GUI Observability Dashboard

The GUI is not the core scheduler.  
It is the observability dashboard that visualizes the whole LLM-assisted scheduling process.

The GUI shows (as `dashboard_live`, the primary React/Vite UI on
`http://localhost:5174`):

- **Demo flow** card (top-left): 5 numbered steps with click-to-flash
  chips to outline the matching card on screen for ~1.4 s.
- Workload Summary card.
- LLM Recommendation card + Algorithm Guard card.
- **Why this algorithm? (Recommendation Evidence)** card —
  consolidates LLM reason, workload traits, guard scores, and
  provenance.
- **Metric trade-off (Counterfactual Metric View)** card — best
  algorithm per metric; current target metric row highlighted.
- live or replayed Scheduling Trace Log (Gantt, Process Lanes,
  Trace Stack).
- Process state table.
- before/after metrics (Algorithm Comparison + Metric
  Visualization).
- Evaluation Result (judgment + regret).
- Trace Explainer result (LLM Explanation card).
- Header status bar with backend badge (**`XV6 TRACE`** /
  `SIMULATOR FALLBACK` / `FALLBACK`), snapshot selector, snapshot
  pill (e.g. `SNAPSHOT: cpu_bound`), manifest version, last
  updated timestamp.

> Runtime-correction events and Feedback Rule output are **not**
> rendered today — they are Partial / Future Work (see §11.1).

Main dashboard message:

> **LLM suggests. xv6 executes. Metrics verify. GUI explains.**

---

## 9. Example Demo Scenario

> **The shipped demo flow today** is: workload → LLM recommendation
> → Algorithm Guard → xv6 schedtest execution (per algorithm on the
> same seed + profile) → Metrics Evaluator → snapshot tour across
> the four curated xv6 profiles.
>
> The scenario below is the **target narrative for closed-loop
> runtime correction** — it is Partial / Future Work today
> (only event detection ships). Read it as the planned story, not
> as what the demo currently performs.

### Scenario: Starvation under Priority Scheduling *(Future Work)*

1. User goal:
   - interactive jobs should respond quickly
   - no process should starve

2. LLM recommendation:
   - Priority Scheduling + weak aging

3. xv6 execution:
   - low-priority process waits too long

4. Trace Monitor:
   - starvation warning detected

5. LLM correction:
   - reduce aging threshold
   - or change Scheduling Algorithm to MLFQ

6. Algorithm Guard:
   - validates the correction

7. xv6:
   - applies correction from the next scheduling point

8. Metrics Evaluator:
   - max waiting time decreases
   - starvation disappears

9. GUI:
   - shows before/after Gantt chart
   - shows metrics improvement
   - shows natural-language trace explanation

---

## 10. Data Files

Actual layout today — what the orchestrator writes and the
dashboard reads. `docs/dashboard_data_contract.md` is canonical;
`tools/validate_dashboard_contract.py --strict --snapshots …`
enforces it.

```text
workloads/*.json                       # curated workload definitions

# Orchestrator output — primary flat live-data (what dashboard_live
# reads on first paint; validated by tools/validate_dashboard_contract.py):
dashboard_live/public/live-data/manifest.json
dashboard_live/public/live-data/recommendation.json
dashboard_live/public/live-data/guard_decision.json
dashboard_live/public/live-data/workload_summary.json
dashboard_live/public/live-data/metrics.json
dashboard_live/public/live-data/trace_explanation.json
dashboard_live/public/live-data/trace_<rr|fcfs|priority|mlfq|sjf|srtf>.jsonl

# Committed per-profile xv6 snapshots (selector in the header
# switches between them; snapshots_manifest.json is the index):
dashboard_live/public/live-data/snapshots_manifest.json
dashboard_live/public/live-data/snapshots/interactive/…
dashboard_live/public/live-data/snapshots/cpu_bound/…
dashboard_live/public/live-data/snapshots/mixed/…
dashboard_live/public/live-data/snapshots/priority_sensitive/…
```

Planned but **not shipped** today (Partial / Future Work, see
§11.1):

```text
outputs/runtime_events.json   # event_detector output (only event detection ships)
outputs/correction.json       # the proposer / guard re-check loop is not wired
outputs/feedback_rules.md     # no production feedback-rule generator
```

---

## 10.1 Workload Format (v2 + hidden burst rule)

Each file in `workloads/` is a JSON object:

```jsonc
{
  "id":                      "ambiguous_mixed",       // matches the spec ID
  "description":             "...",                   // one-line for the dashboard
  "target_metric":           "avg_waiting_time",      // what we evaluate against
  "expected_best_algorithm": "SJF",                   // documented expectation
  "expected_behavior":       "On avg_waiting_time...",// teaching note
  "schema_version":          2,
  "processes": [
    {
      "pid": 1, "arrival_time": 0, "priority": 5, "label": "cpu_bound",
      "actual_bursts": [8],     // HIDDEN — execution + evaluation only
      "cpu_bursts":    [8],     // kept for backward compat (mirror of actual)
      "io_bursts":     []
    }
  ]
}
```

**Hidden actual burst rule:** the LLM advisor and the SJF/SRTF picker MUST
NOT read `actual_bursts`. They see `visible_processes` in
`workload_summary.json` (pid, arrival_time, priority, label, burst_count,
io_count) and — for SJF/SRTF — the EMA / LLM-predicted `predicted_burst`.

The `workloads/` directory holds the curated workloads and which
algorithm each one favours.

## 10.2 EMA and LLM Burst Prediction (SJF / SRTF)

- **EMA baseline (default):** `tau_next = (alpha * observed + (100-alpha) * tau_prev) / 100`. Updated when a CPU burst ends (xv6: at `sleep()`; simulator: at end-of-burst). Defaults `alpha=50%, initial=10, [min=1, max=100]`. The simulator emits `[SCHED] event=PRED_UPDATE pid=… predicted_prev=… predicted_next=…` on every refresh.
- **LLM hint (optional):** when the advisor picks SJF/SRTF it may also return `predicted_bursts: [{pid, predicted_burst|predicted_bursts, confidence, basis}]` based ONLY on visible features. The orchestrator forwards these to the simulator via `Simulator(prediction_source="llm")`. The xv6 backend currently uses EMA only; LLM hints are simulator-side until a future kernel patch.
- **Trace evidence:** the `[SCHED] event=PRED_UPDATE` line is emitted by the **simulator only** (the xv6 kernel does not emit it yet — that is Future Work), so EMA drift is visible on the simulator path; on the xv6 demo path SJF/SRTF still schedule on the EMA `predicted_burst`, just without a per-update trace line. LLM-hinted runs tend to land closer to the ideal shortest-job baseline on first dispatch.

## 10.3 Running the End-to-End Demo (and without an API key)

```bash
# 1) Real LLM (Solar Pro 3) — set up once
cp .env.example .env       # then edit: UPSTAGE_API_KEY=<your key>

# 2a) Final demo path (xv6 + QEMU)
python3 scripts/orchestrator.py --backend xv6       --seed 42 --workload interactive            --run-all

# 2b) Dev/fallback path (no QEMU needed)
python3 scripts/orchestrator.py --backend simulator --seed 42 --workload ambiguous_mixed        --run-all

# 2c) No API key? Use the committed demo recommendation
python3 scripts/orchestrator.py --backend simulator --seed 42 --workload bursty_long_tail        --run-all --offline-fixture

# 3) Start the dashboard
cd dashboard_live && npm install && npm run dev    # http://localhost:5174

# 4) Optional — RUN button server (lets the dashboard trigger 2a/2b itself)
python3 scripts/run_server.py                       # http://127.0.0.1:8765
```

When `scripts/run_server.py` is up, the dashboard's **LLM tab** shows a RUN
control: pick backend + profile + seed, hit RUN, watch the badge flip
RUNNING → PARSING → EVALUATING → DONE, and the views auto-reload. Without
the server the RUN card hides and the dashboard is read-only over
`live-data/`.

## 11. Repository Structure

Actual top-level layout today (kept honest — paths that don't exist or are
misnamed should be fixed in the README, not faked):

```text
.
├── README.md
├── CLAUDE.md
├── architecture_diagram.md
├── requirements.txt
├── .env.example
├── .github/workflows/                  # lightweight CI (no QEMU)
│
├── docs/                               # PRIMARY — execution & structure reference
│   ├── architecture.md                 # three-phase architecture + module roles
│   ├── orchestrator_design.md          # control plane, backends, fairness rule
│   ├── data_format.md                  # module-to-module JSON / JSONL interfaces
│   ├── trace_format.md                 # raw [SCHED]/[SCHEDTEST] + normalized JSONL
│   ├── dashboard_data_contract.md      # canonical files the dashboard reads
│   ├── evaluation_plan.md              # metrics, thresholds, recommendation judging
│   └── xv6_profile_support.md          # xv6 workload profile coverage audit
│
├── workloads/                          # PRIMARY — curated workload JSONs
│   ├── interactive_heavy.json  · short_jobs.json  · mixed_workload.json
│   ├── long_cpu_bound_first.json  · priority_sensitive.json
│   └── starvation_risk.json
│
├── tools/                              # PRIMARY — host pipeline modules
│   ├── workload_analyzer.py
│   ├── llm_advisor.py      · solar_client.py
│   ├── algorithm_guard.py  · schema_compat.py
│   ├── scheduler_simulator.py          # FALLBACK (dev/test)
│   ├── trace_parser.py     · metrics.py
│   ├── event_detector.py
│   ├── correction_proposer.py          # PREVIEW ONLY
│   ├── correction_guard.py             # PREVIEW ONLY
│   ├── trace_explainer.py
│   └── validate_dashboard_contract.py
│
├── scripts/                            # PRIMARY — host control plane
│   ├── orchestrator.py                 # main control plane
│   ├── export_profile_snapshots.py     # publish per-profile xv6 snapshots
│   └── run_server.py                   # RUN-button HTTP backend (optional)
│
├── xv6-riscv/                          # PRIMARY — final execution backend
│   ├── kernel/proc.c                   # 6 schedulers + predictor + traces
│   ├── kernel/sysproc.c · syscall.c    # setscheduler / getscheduler
│   └── user/schedtest.c                # curated profiles fork driver
│
├── dashboard_live/                     # PRIMARY — final demo UI (React/Vite)
│   ├── src/                            # 17 components + liveDataClient
│   └── public/live-data/               # generated by orchestrator + snapshots
│
└── outputs/                            # BUILD-OUTPUT (mostly gitignored)
    └── _demo_fixtures/                 # COMMITTED offline-demo fallback fixtures
```

## Dashboard roles

| Dashboard        | Role                                        | Command                              |
|------------------|---------------------------------------------|--------------------------------------|
| `dashboard_live` | **PRIMARY demo** — loads real generated JSON/JSONL (xv6 trace or simulator fallback); shows backend badge | `cd dashboard_live && npm run dev` |

`dashboard_live` shows a backend indicator in the header: **XV6 TRACE** when the
data came from real xv6 logs, **SIMULATOR FALLBACK** when it came from the
simulator.

### Run dashboard_live (primary)

```bash
# Step 1: generate live-data via the orchestrator (real xv6 + QEMU).
python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all

# Step 2: start dashboard
cd dashboard_live
npm install
npm run dev     # http://localhost:5174
```

Step 1 alternatives, if you need finer control:

```bash
# Dev/fallback path (no QEMU needed):
python3 scripts/orchestrator.py --backend simulator --seed 42 --workload interactive --run-all

# Re-publish all four curated xv6 profile snapshots (interactive,
# cpu_bound, mixed, priority_sensitive):
python3 scripts/export_profile_snapshots.py --backend xv6
```

`dashboard_live` shows:
- **Backend badge** (`XV6 TRACE` / `SIMULATOR FALLBACK` / `FALLBACK`) in the header status bar.
- **Snapshot selector** — visible when `snapshots_manifest.json` exists. Switch between the four committed xv6 profile snapshots (`interactive`, `cpu_bound`, `mixed`, `priority_sensitive`); a purple `SNAPSHOT: <profile>` pill appears next to the dropdown when one is active. Default is the flat live-data root.
- **Manifest version** (e.g. `v16`) to confirm data freshness.
- **Last Updated** timestamp from `manifest.json`.
- **Live Polling** indicator (blinking dot = polling active; ■ = replay mode). Polling pauses while a snapshot is selected.
- **Yellow fallback warning banner** when no live data is available — run the pipeline to dismiss it.
- **Red trace error indicator** if any JSONL trace file fails to parse.
- **Demo flow** card (top-left) — 5 numbered steps with click-to-flash chips to outline the matching card on screen for ~1.4 s.

Multi-profile snapshots are published by
`python3 scripts/export_profile_snapshots.py`. The script runs the
orchestrator + strict validator per profile and writes the result
into `dashboard_live/public/live-data/snapshots/<profile>/`.

### Build

```bash
cd dashboard_live && npm run build
```

---

## 11.1 Implementation Status

Concise current status:

| Component | Status | Role |
|-----------|--------|------|
| xv6 scheduler — RR / FCFS / Priority+Aging / MLFQ / SJF / SRTF | **Implemented** | execution authority |
| Orchestrator — xv6 backend (`scripts/orchestrator.py --backend xv6`) | **Implemented** | **final demo / experiment path** |
| xv6 workload profiles — `interactive`, `cpu_bound`, `mixed`, `priority_sensitive` | **Implemented** | all 4 run on xv6 end-to-end ([audit](docs/xv6_profile_support.md)) |
| Orchestrator — simulator backend (`--backend simulator`) | **Implemented** | dev / fallback only |
| `scripts/export_profile_snapshots.py` + committed per-profile xv6 snapshots | **Implemented** | dashboard switches across `interactive` / `cpu_bound` / `mixed` / `priority_sensitive` without re-running QEMU |
| `tools/validate_dashboard_contract.py` (`--strict --snapshots --preview …`) | **Implemented** | catches empty traces, missing manifest fields, cross-file algo disagreement; `--snapshots` extends per profile snapshot; `--preview` is opt-in and validates the runtime-correction preview artifacts (`preview_only=true`, `applied=false`, no `CORRECTION_APPLIED`). Default mode is unchanged — preview files remain optional and off the strict contract. |
| `dashboard_live` (React + `public/live-data/`) | **Implemented** | **final demo UI** — backend badge + snapshot selector + manifest meta + per-row Judge |
| `dashboard_live` Demo flow + Why this algorithm + Metric trade-off cards | **Implemented** | DemoGuide (click-to-flash), RecommendationEvidence ("Why this algorithm?"), CounterfactualMetricView ("Metric trade-off") — see PRs #32 #43 #46 #47 |
| `.github/workflows/ci.yml` (lightweight CI) | **Implemented** | py_compile + strict validator on committed live-data + dashboard_live build. **No QEMU/xv6 in CI** — local orchestrator run remains authoritative |
| `trace_parser.py` real-log support + lenient `RUN_BEGIN` recovery | **Implemented** | survives kernel/user printf interleave |
| LLM Advisor (Solar Pro 3) + Algorithm Guard | **Implemented** | Runtime backend is Upstage Solar Pro 3. The orchestrator is **strict by default**: missing/invalid `UPSTAGE_API_KEY` or any advisor failure exits with a clear error. Pass `--offline-fixture` (or `--allow-fallback`) to opt in to the committed `outputs/_demo_fixtures/` fixtures; that path stamps `manifest.metadata_source = "demo_fallback"`. |
| Runtime correction loop (detect → propose → LLM → guard → apply → `CORRECTION_APPLIED`) | **Partial / Future Work** | only event detection exists today |
| Live streaming | **Polling only** | no websocket; `manifest.json` poll |

> **LLM suggests. Algorithm Guard checks. xv6 executes. Metrics verify. GUI explains.**

See `docs/orchestrator_design.md` for the control plane and fairness design.

---

## 12. OS Concepts Used

This project directly uses the following OS concepts:

- process
- process state
- CPU scheduling
- ready queue
- preemption
- context switch
- system calls
- priority
- starvation
- aging
- Scheduling Metrics
- trace-based observability

---

## 13. Tech Stack

### OS Environment

- xv6-riscv
- QEMU
- RISC-V toolchain
- WSL or Linux

### xv6 Implementation

- C
- xv6 scheduler
- xv6 system calls
- xv6 user programs

### Host-side Tools

- Python
- JSON / JSONL
- trace parser
- Metrics Evaluator
- LLM API client

### GUI

- **Primary:** React + Vite (`dashboard_live`) — loads generated JSON/JSONL
  from `public/live-data/`. Polls `manifest.json` every 1 s in live mode.

### LLM Backend

- **Runtime LLM backend** — Upstage Solar Pro 3 API, accessed via
  `tools/solar_client.py` (stdlib `urllib` only, no vendor SDK at
  runtime).
- **Development tool** — Claude Code is used only as the coding agent
  in the editor. It is *not* a runtime project dependency.

API keys must not be committed to GitHub. The repo only ships
`.env.example` with placeholders; the real key lives in a local `.env`
that is git-ignored.

```bash
cp .env.example .env          # then edit .env to add UPSTAGE_API_KEY
```

If `UPSTAGE_API_KEY` is missing at call time, `tools/solar_client.py`
fails fast with a clear error rather than silently faking a response.

---

## 14. Development Roadmap

### Phase 1 — Basic Trace and Metrics

- implement Scheduling Trace Log
- parse trace into structured data
- calculate basic Scheduling Metrics
- visualize Gantt chart

### Phase 2 — Multiple Scheduling Algorithms

- preserve Round Robin baseline
- implement FCFS
- implement Priority Scheduling + Aging
- implement MLFQ
- add Scheduling Algorithm control interface

### Phase 3 — LLM Scheduling Algorithm Advisor

- generate workload summary
- call Solar Pro 3 API
- receive Scheduling Algorithm recommendation JSON
- validate recommendation with Algorithm Guard

### Phase 4 — Runtime Correction

- detect starvation and poor response time
- request LLM correction
- validate correction
- apply correction from the next scheduling point
- compare before/after metrics

### Phase 5 — Trace Explainer and Feedback Rule Generator

- summarize trace and metrics
- generate natural-language explanation
- generate feedback rules from failed recommendations
- display explanation in GUI

### Phase 6 — Optional Burst Prediction Experiment

- implement traditional exponential averaging
- test LLM-assisted burst prediction
- compare predicted burst and actual burst
- compare SJF/SRTF performance with different predictors

---

## 15. Limitations

- The LLM is not called at every timer tick.
- The LLM does not directly choose the next process.
- The LLM does not directly modify xv6 kernel state.
- Runtime correction is applied only after validation.
- Runtime correction takes effect from the next scheduling point.
- Future CPU bursts are not given to the LLM as answers.
- Controlled workloads may be used for reproducible experiments.

---

## 16. One-sentence Summary

**LLM Sched Copilot is an LLM-for-OS system where an LLM recommends and explains xv6 Scheduling Algorithms (and proposes runtime corrections as preview-only work), while the Algorithm Guard checks the recommendation, xv6 executes it as the authority, and metrics verify whether it was useful.**

> The LLM recommendation is a *hypothesis*: the Algorithm Guard validates it, xv6 (not the LLM) executes the chosen algorithm and remains the execution authority, and the Metrics Evaluator decides whether the hypothesis actually helped. The LLM never picks the next process at a timer tick and never modifies xv6 kernel state.
