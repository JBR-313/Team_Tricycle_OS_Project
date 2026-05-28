# LLM Sched Copilot

**The LLM-Assisted Scheduler for xv6**

> ## Final Demo Path *(read this first — 30 s)*
>
> ```
> Workload  →  Workload Analyzer  →  LLM Advisor  →  Algorithm Guard
>           →  xv6 + QEMU  →  Trace Parser  →  Metrics Evaluator
>           →  dashboard_live
> ```
>
> | Question | Answer |
> |---|---|
> | What is the **main demo path**? | The arrow above. xv6 + QEMU runs `schedtest`; the LLM only advises. |
> | Which **dashboard** should I open? | **`dashboard_live/`** (`http://localhost:5174`). Anything else is a sandbox or legacy. The dashboard has three tabs: **LLM / Visualization / Evaluation**. The **RUN** button on the LLM tab triggers a fresh experiment when `scripts/run_server.py` is up. |
> | Is **xv6** the primary backend? | Yes. `scripts/orchestrator.py --backend xv6` is the demo path. |
> | Is the **simulator** only a fallback? | Yes. `tools/scheduler_simulator.py` + `--backend simulator` is **dev/test only**. The dashboard shows a `SIMULATOR` badge when it is in use. |
> | Does **SJF/SRTF** see future bursts? | **No**. The xv6 kernel uses an exponential-averaging (EMA) burst predictor; the simulator was refactored on 2026-05-28 to do the same (`predicted_burst` only — `actual_bursts` never leaks into the picker). LLM may **predict** bursts as hints via `recommendation.predicted_bursts[]`. See [`docs/sjf_srtf_prediction_audit.md`](docs/sjf_srtf_prediction_audit.md). |
> | What's the **judgment rule**? | Normalized regret on the workload's `target_metric`. SUCCESS ≤ 10%, NEAR-SUCCESS ≤ 25%, else FAIL; starvation forces FAIL. Output includes `selected_metric_value`, `best_metric_value`, `explanation`. See [`docs/evaluation_criteria_audit.md`](docs/evaluation_criteria_audit.md). |
> | What if I have **no API key**? | The orchestrator uses the committed `outputs/_demo_fixtures/` set and the dashboard shows a `FALLBACK` badge. No silent guessing. |
> | Which modules are **preview-only**? | The runtime-correction loop: `tools/event_detector.py`, `tools/correction_proposer.py`, `tools/correction_guard.py`, dashboard card `RuntimeCorrectionPreview`. Closed-loop xv6 apply is **Future Work**. |
> | Where is the **slimming/hardening plan**? | [`docs/codebase_slimming_plan.md`](docs/codebase_slimming_plan.md) (labels & post-demo move queue) and [`docs/final_slimming_smoke_check.md`](docs/final_slimming_smoke_check.md) (verification commands). |

LLM Sched Copilot is an **LLM-for-OS** project that uses an LLM as a high-level decision support layer for xv6 CPU scheduling.

The LLM analyzes workload summaries and Scheduling Trace Logs, recommends a suitable **Scheduling Algorithm**, suggests algorithm parameters, and explains the execution result in natural language. Closed-loop runtime correction (detect → propose → guard → apply) is **Partial / Future Work** — see §12.1.

The LLM does **not** replace the xv6 scheduler.  
xv6 remains the execution authority.  
The Metrics Evaluator verifies the LLM's judgment using concrete scheduling metrics.  
The GUI visualizes the whole process as an observability dashboard.

> **LLM suggests. Algorithm Guard checks. xv6 executes. Metrics verify. GUI explains.**

---

## 1. Project Direction

This project follows **Direction B: LLM for OS**.

The project integrates an LLM into a classical OS problem: **CPU Scheduling**.

Instead of using the LLM as a simple chatbot, this project uses the LLM as a scheduling decision support layer:

- The LLM interprets workload characteristics.
- The LLM recommends a Scheduling Algorithm and parameters.
- The LLM proposes runtime corrections when trace monitoring detects problems. *(Partial / Future Work — only event detection ships today; see §12.1.)*
- The LLM explains Scheduling Trace Logs and Scheduling Metrics.
- The LLM generates feedback rules for future recommendations. *(Partial / Future Work — no production feedback-rule generator today; see §12.1.)*

The actual Scheduling Algorithm execution is performed by xv6.

---

## 2. Core Idea

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
not proof of real xv6 execution. See `docs/orchestrator_design.md` and
`docs/implementation_status.md`.

The main question of this project is:

> Can an LLM help choose, tune, correct, and explain xv6 Scheduling Algorithms using workload summaries and Scheduling Trace Logs?

---

## 3. System Principle

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
| `dashboard_test/` | **FALLBACK (UI prototype/sandbox)** | Static fixture data for component iteration. **Not real scheduling output by design.** | no (developer-only) |
| `dashboard/` (Streamlit) | **LEGACY** | Superseded by `dashboard_live`. Kept for the host-only fallback case. Archive plan in [`docs/repo_cleanup_plan.md`](docs/repo_cleanup_plan.md). | no |
| `xv6-style-scheduler/` | **DEV** | Standalone scheduler study sandbox; not on the demo path. | no |
| `traces/` (root) | **LEGACY** | Pre-orchestrator trace samples. Canonical fixtures live in `outputs/_demo_fixtures/` and `dashboard_live/public/live-data/snapshots/`. | no |

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

## 4. Supported Scheduling Algorithms

The project targets the following Scheduling Algorithms.

### 4.1 Round Robin

Round Robin is the baseline Scheduling Algorithm.  
It gives runnable processes CPU time in turn and prevents a single process from monopolizing the CPU.

### 4.2 FCFS

FCFS executes processes in arrival order.  
It is simple, but it can suffer from the convoy effect when a long CPU-bound process arrives before short jobs.

### 4.3 Priority Scheduling + Aging

Priority Scheduling selects a process based on priority.  
It can improve the response of important processes, but low-priority processes may suffer from starvation.

Aging is used to reduce starvation by gradually increasing the effective priority of waiting processes.

### 4.4 MLFQ

MLFQ uses multiple queues with different time quantums.  
It can favor short or interactive jobs while demoting long CPU-bound jobs.

LLM Sched Copilot can suggest MLFQ parameters such as:

- number of queues
- time quantum for each queue
- aging threshold
- boost interval

### 4.5 SJF / SRTF + Burst Prediction

SJF and SRTF are powerful Scheduling Algorithms because they favor short CPU bursts.

However, a real OS cannot know the exact next CPU burst in advance.  
Therefore, this project treats burst prediction as an experimental feature.

Possible predictors:

- traditional exponential averaging
- LLM-assisted burst prediction
- LLM-assisted predictor parameter tuning

The LLM must not receive the actual future CPU burst as input.

---

## 5. LLM Roles

The LLM works in three phases.

---

### 5.1 Before Running

#### 5.1.1 Workload Interpreter

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

#### 5.1.2 Scheduling Algorithm Advisor

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

### 5.2 Running

#### 5.2.1 Runtime Correction Proposer *(Partial / Future Work)*

> This subsection describes the **planned** closed-loop runtime
> correction design — the **target**, not what ships today. On
> current main only `tools/event_detector.py` exists. The proposer,
> the LLM call, the guard re-check on a correction, the apply step
> in xv6, and the `CORRECTION_APPLIED` trace event the dashboard
> would render are all Future Work. See the §12.1 Implementation
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

In the design target, the correction would be applied at the next scheduling point, not by interrupting every timer tick with an LLM call. **Today this apply step is still Future Work** (see §12.1).

---

### 5.3 After Running

#### 5.3.1 Trace Explainer

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

#### 5.3.2 Feedback Rule Generator *(Partial / Future Work)*

> Design target, not shipped today. No production feedback-rule
> generator exists in `tools/`. The example below is the **planned**
> JSON shape, included so the design is visible to readers. See
> §12.1.

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

## 6. Algorithm Guard

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

## 7. Scheduling Trace Log

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

## 8. Metrics Evaluator

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

## 9. GUI Observability Dashboard

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
> rendered today — they are Partial / Future Work (see §12.1).

Main dashboard message:

> **LLM suggests. xv6 executes. Metrics verify. GUI explains.**

---

## 10. Example Demo Scenario

> **The shipped demo flow today** is: workload → LLM recommendation
> → Algorithm Guard → xv6 schedtest execution (per algorithm on the
> same seed + profile) → Metrics Evaluator → snapshot tour across
> the four curated xv6 profiles. See `docs/demo_runbook.md`,
> `docs/demo_checklist.md`, and `docs/presenter_script.md`.
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

## 11. Data Files

Actual layout today — what the orchestrator writes and the
dashboard reads. `docs/dashboard_data_contract.md` is canonical;
`tools/validate_dashboard_contract.py --strict --snapshots …`
enforces it.

```text
workloads/*.json                       # curated workload definitions

# Orchestrator output — primary flat live-data (what dashboard_live
# reads on first paint and what scripts/final_demo_check.py validates):
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
§12.1):

```text
outputs/runtime_events.json   # event_detector output (only event detection ships)
outputs/correction.json       # the proposer / guard re-check loop is not wired
outputs/feedback_rules.md     # no production feedback-rule generator
```

---

## 11.1 Workload Format (v2 + hidden burst rule)

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

See [`docs/workload_coverage_matrix.md`](docs/workload_coverage_matrix.md)
for the 10 curated workloads and which algorithm each one favours.

## 11.2 EMA and LLM Burst Prediction (SJF / SRTF)

- **EMA baseline (default):** `tau_next = (alpha * observed + (100-alpha) * tau_prev) / 100`. Updated when a CPU burst ends (xv6: at `sleep()`; simulator: at end-of-burst). Defaults `alpha=50%, initial=10, [min=1, max=100]`. The simulator emits `[SCHED] event=PRED_UPDATE pid=… predicted_prev=… predicted_next=…` on every refresh.
- **LLM hint (optional):** when the advisor picks SJF/SRTF it may also return `predicted_bursts: [{pid, predicted_burst|predicted_bursts, confidence, basis}]` based ONLY on visible features. The orchestrator forwards these to the simulator via `Simulator(prediction_source="llm")`. The xv6 backend currently uses EMA only; LLM hints are simulator-side until a future kernel patch.
- **Trace evidence:** dashboard's Visualization tab + `[SCHED] event=PRED_UPDATE` shows EMA drift; LLM-hinted runs land closer to the oracle baseline on first dispatch.

## 11.3 Running the End-to-End Demo (and without an API key)

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

## 12. Repository Structure

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
├── docs/                               # PRIMARY — architecture + audits
│   ├── architecture.md
│   ├── trace_format.md
│   ├── data_format.md
│   ├── evaluation_plan.md
│   ├── implementation_status.md
│   ├── orchestrator_design.md
│   ├── demo_runbook.md  · demo_checklist.md  · presenter_script.md
│   ├── final_demo_acceptance.md  · final_release_candidate_report.md
│   ├── repo_cleanup_plan.md            # NEW — labelling + post-demo queue
│   ├── sjf_srtf_prediction_audit.md    # NEW — predictor verification
│   ├── evaluation_criteria_audit.md    # NEW — judgment thresholds rationale
│   ├── workload_coverage_matrix.md     # NEW — workload × algorithm matrix
│   ├── dashboard_run_button_design.md  # NEW — Run-button API design (deferred)
│   ├── mlfq_queue_visualization_review.md # NEW — MLFQ panel proposal
│   └── …
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
│   ├── final_demo_check.py             # one-command demo prep
│   ├── multi_profile_demo_check.py     # 4-profile sweep
│   ├── export_profile_snapshots.py     # publish per-profile snapshots
│   ├── analyze_algorithm_winners.py    # diversity audit (offline)
│   ├── correction_preview_smoke.py     # offline preview smoke
│   ├── check_xv6_scheduler.sh
│   └── run_live_dashboard_pipeline.py  # DEPRECATED shim
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
├── dashboard_test/                     # FALLBACK — UI prototype/sandbox
│   └── src/                            # static fixtures only
│
├── dashboard/                          # LEGACY — Streamlit fallback
│   └── dashboard.py
│
├── xv6-style-scheduler/                # DEV — standalone simulator study
│   └── simulator/simulator.py
│
├── outputs/                            # BUILD-OUTPUT (mostly gitignored)
│   └── _demo_fixtures/                 # COMMITTED offline-demo fallback fixtures
│
└── traces/                             # LEGACY — pre-orchestrator samples
```

See [`docs/repo_cleanup_plan.md`](docs/repo_cleanup_plan.md) for the full
file-by-file labelling and the post-demo cleanup queue (no files are deleted
before the demo).

## Dashboard roles

| Dashboard        | Role                                        | Command                              |
|------------------|---------------------------------------------|--------------------------------------|
| `dashboard_live` | **PRIMARY demo** — loads real generated JSON/JSONL (xv6 trace or simulator fallback); shows backend badge | `cd dashboard_live && npm run dev` |
| `dashboard_test` | **FALLBACK (UI prototype/sandbox)** — static fixture data only; not real scheduling output by design | `cd dashboard_test && npm run dev` |
| `dashboard/`     | **LEGACY** — Streamlit; superseded by `dashboard_live`. Kept for host-only fallback. See [`docs/repo_cleanup_plan.md`](docs/repo_cleanup_plan.md) §6.4 | `streamlit run dashboard/dashboard.py` |

> `dashboard-react` has been removed. `dashboard_test` is its direct successor and fully supersedes it.

`dashboard_live` shows a backend indicator in the header: **XV6 TRACE** when the
data came from real xv6 logs, **SIMULATOR FALLBACK** when it came from the
simulator.

### Run dashboard_live (primary)

```bash
# Step 1: one-command demo prep (compile + xv6 orchestrator + strict validator).
# Runs the on-stage release contract from docs/final_demo_acceptance.md.
python3 scripts/final_demo_check.py

# Step 2: start dashboard
cd dashboard_live
npm install
npm run dev     # http://localhost:5174
```

Step 1 alternatives, if you need finer control:

```bash
# Run a specific backend / workload directly:
python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all
python3 scripts/orchestrator.py --backend simulator --seed 42 --workload interactive --run-all

# Broader pre-demo confidence — re-run xv6 + strict validate across
# all four curated profiles (interactive, cpu_bound, mixed, priority_sensitive):
python3 scripts/multi_profile_demo_check.py
```

> The old command `python3 scripts/run_live_dashboard_pipeline.py` is a
> deprecated shim. Prefer the Orchestrator command above.

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

### Run dashboard_test (UI lab)

```bash
cd dashboard_test
npm install
npm run dev     # http://localhost:5173
```

### Build

```bash
cd dashboard_test && npm run build
cd dashboard_live && npm run build
```

See `docs/demo_runbook.md` for full pipeline details.

---

## 12.1 Implementation Status

Concise current status (full evidence in `docs/implementation_status.md`):

| Component | Status | Role |
|-----------|--------|------|
| xv6 scheduler — RR / FCFS / Priority+Aging / MLFQ / SJF / SRTF | **Implemented** | execution authority |
| Orchestrator — xv6 backend (`scripts/orchestrator.py --backend xv6`) | **Implemented** | **final demo / experiment path** |
| xv6 workload profiles — `interactive`, `cpu_bound`, `mixed`, `priority_sensitive` | **Implemented** | all 4 pass `multi_profile_demo_check.py --backend xv6` end-to-end ([audit](docs/xv6_profile_support.md)) |
| Orchestrator — simulator backend (`--backend simulator`) | **Implemented** | dev / fallback only |
| `scripts/final_demo_check.py` (compile + orchestrator + strict contract validator) | **Implemented** | one-command demo-prep |
| `scripts/multi_profile_demo_check.py` (xv6 backend across all curated profiles) | **Implemented** | broader pre-demo confidence (not a substitute for the on-stage check) |
| `scripts/export_profile_snapshots.py` + committed per-profile xv6 snapshots | **Implemented** | dashboard switches across `interactive` / `cpu_bound` / `mixed` / `priority_sensitive` without re-running QEMU |
| `scripts/analyze_algorithm_winners.py` | **Implemented** | offline verifier for the algorithm-diversity audit |
| `tools/validate_dashboard_contract.py` (`--strict --snapshots --preview …`) | **Implemented** | catches empty traces, missing manifest fields, cross-file algo disagreement; `--snapshots` extends per profile snapshot; `--preview` is opt-in and validates the runtime-correction preview artifacts (`preview_only=true`, `applied=false`, no `CORRECTION_APPLIED`). Default mode is unchanged — preview files remain optional and off the strict contract. See `docs/runtime_correction_preview_validation.md`. |
| `dashboard_live` (React + `public/live-data/`) | **Implemented** | **final demo UI** — backend badge + snapshot selector + manifest meta + per-row Judge |
| `dashboard_live` Demo flow + Why this algorithm + Metric trade-off cards | **Implemented** | DemoGuide (click-to-flash), RecommendationEvidence ("Why this algorithm?"), CounterfactualMetricView ("Metric trade-off") — see PRs #32 #43 #46 #47 |
| `.github/workflows/ci.yml` (lightweight CI) | **Implemented** | py_compile + strict validator on committed live-data + dashboard builds. **No QEMU/xv6 in CI** — local `final_demo_check.py` remains authoritative |
| `dashboard_test` (React + static fixtures) | **Implemented** | UI lab only |
| `dashboard/` (Streamlit) | Legacy | fallback only, not the demo path |
| `trace_parser.py` real-log support + lenient `RUN_BEGIN` recovery | **Implemented** | survives kernel/user printf interleave |
| LLM Advisor (Solar Pro 3) + Algorithm Guard | **Implemented** | LLM may fall back to demo recommendation if no API key |
| Runtime correction loop (detect → propose → LLM → guard → apply → `CORRECTION_APPLIED`) | **Partial / Future Work** | only event detection exists today |
| Live streaming | **Polling only** | no websocket; `manifest.json` poll |

> **LLM suggests. Algorithm Guard checks. xv6 executes. Metrics verify. GUI explains.**

See `docs/implementation_status.md` for evidence files, run commands, and
remaining risks per feature; `docs/orchestrator_design.md` for the control
plane and fairness design; and `docs/demo_runbook.md` for the presenter
checklist.

---

## 13. OS Concepts Used

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

## 14. Tech Stack

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
- **UI prototype/sandbox:** React + Vite (`dashboard_test`) — static fixtures
  only; component iteration.
- **Legacy fallback:** Streamlit + pandas + Plotly (`dashboard/dashboard.py`)
  — kept for the host-only case where Node is unavailable. Marked deprecated;
  see [`docs/repo_cleanup_plan.md`](docs/repo_cleanup_plan.md) §6.4 for the
  archive plan.

### LLM Backend

- Upstage Solar Pro 3 API

API keys must not be committed to GitHub.

---

## 15. Development Roadmap

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

## 16. Limitations

- The LLM is not called at every timer tick.
- The LLM does not directly choose the next process.
- The LLM does not directly modify xv6 kernel state.
- Runtime correction is applied only after validation.
- Runtime correction takes effect from the next scheduling point.
- Future CPU bursts are not given to the LLM as answers.
- Controlled workloads may be used for reproducible experiments.

---

## 17. One-sentence Summary

**LLM Sched Copilot is an LLM-for-OS system where an LLM recommends, corrects, and explains xv6 Scheduling Algorithms, while xv6 executes them and metrics verify the result.**
