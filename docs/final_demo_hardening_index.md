# Final-Demo Hardening — Document Index

Bundle of audits and design docs produced in the **final-demo hardening**
pass (2026-05-28, branch `feat/upstage-runtime-strict`). Purpose: make the
project's final-demo posture readable from one page.

| # | Document | Question it answers | Status |
|---|---|---|---|
| 1 | [repo_cleanup_plan.md](repo_cleanup_plan.md) | What is PRIMARY / FALLBACK / LEGACY in the repo today, and what is the *deletion-free* cleanup queue for after the demo? | KEEP labels assigned; no deletes pre-demo. |
| 2 | [sjf_srtf_prediction_audit.md](sjf_srtf_prediction_audit.md) | Does SJF/SRTF use a real exponential-averaging predictor or an oracle on the future burst? | xv6 = predictor ✓ ; simulator = **oracle** ✗ (disclose). |
| 3 | [evaluation_criteria_audit.md](evaluation_criteria_audit.md) | Why are SUCCESS / NEAR-SUCCESS / FAIL thresholds 0.10 / 0.30, and why does starvation override regret? | Defended; constants stay. |
| 4 | [workload_coverage_matrix.md](workload_coverage_matrix.md) | Which curated workload demonstrates each algorithm's strength? What's missing? | 4 new profiles proposed; generator designed but deferred. |
| 5 | [dashboard_run_button_design.md](dashboard_run_button_design.md) | How would a “Run Experiment” button work, and why is the React app alone not enough? | Backend API + state machine designed; **deferred post-demo**. |
| 6 | [mlfq_queue_visualization_review.md](mlfq_queue_visualization_review.md) | Does the dashboard make MLFQ's Q0/Q1/Q2 and QUEUE_CHANGE visible? | New `MLFQQueuePanel` proposed; small fallback (`ProcessState` queue column + TraceStack filter) also designed. |

## Headlines (pin these in slide prep)

1. **Final-demo execution path = xv6 + QEMU + `schedtest`.** Simulator,
   `dashboard_test`, Streamlit `dashboard/` are all explicitly labelled
   FALLBACK / SANDBOX / LEGACY in the README and in this bundle.
2. **xv6 SJF/SRTF passes the burst-prediction rule.** The simulator's
   version is an oracle and must be disclosed if shown.
3. **Judgment thresholds (0.10 / 0.30) are constants with a stated
   rationale**, not learned percentiles, so they hold up to questioning.
4. **MLFQ-only recommendation diversity gap is real** — addressed at the
   workload level (4 new profiles proposed) before adding new LLM tricks.
5. **The “Run Experiment” button is a backend service**, not a frontend
   change. Designed; deferred post-demo because snapshot selector already
   gives the audience a visible state change.

## Not produced here (intentional)

- No source deletions or directory moves.
- No new feature code in `tools/`, `xv6-riscv/`, or `dashboard_live/`.
- Runtime correction is **not** promoted from preview to closed-loop.
- No new LLM call sites.

This bundle is hardening + documentation only.
