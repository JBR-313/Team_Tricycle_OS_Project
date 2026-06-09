# Orchestrator Design

`scripts/orchestrator.py` is the host-side **control plane**. It drives one full
experiment end to end — select a workload, get the LLM recommendation, validate it
with the Algorithm Guard, run it on **xv6 (the only backend)**, parse the trace,
compute metrics, run the after-running stages, and publish to the dashboard. It is
**not** the scheduler: it never picks the next process; xv6 is the execution
authority.

It exists because everything around execution lives on the host: `schedtest.c`
runs inside QEMU and can only set an algorithm, fork children, and print trace
lines — it cannot call the LLM, write `live-data/`, or open a browser. (The Python
simulator backend that once served as a dev fallback has been removed; xv6 is now
reproducible, so it is the single source.)

## Fair comparison
Every algorithm runs on the **same deterministic workload** (same `seed` +
profile), **sequentially**, the **LLM-selected algorithm first**, then the fixed
order RR → FCFS → Priority → MLFQ → SJF → SRTF (RR is always kept as the
reference). xv6 is deterministic-by-profile (fixed `schedtest.c` tables, no PRNG)
and the run is reproducible (deterministic `-icount` clock + fixed-iteration
bursts), so `--seed` only labels the run.

## CLI
```bash
python3 scripts/orchestrator.py --workload PROFILE [--algo NAME] [--intent "..."] [--offline-fixture] [--use-feedback]
```
- `--workload` profile (e.g. `interactive`, `cpu_bound`, `mixed`, `priority_sensitive`, `convoy_tail`, …) — which xv6 profile to execute.
- `--intent "..."` map a natural-language intent to the config (`tools/intent_advisor.py`) instead of the numeric advisor.
- `--offline-fixture` use committed fixtures when no API key / QEMU.
- `--use-feedback` opt-in: inject accumulated FAIL-only rules into the advise prompt.

## Pipeline steps
[1] analyze → [2] advise → [3] guard → [4] run on xv6 (per algorithm) →
[5] export to `live-data/` + `manifest.json` → [6] validate dashboard contract →
[7] runtime-correction apply loop (FAIL/starvation/high-severity → re-run xv6 with
a Guard-approved correction, before/after in `correction_applied.json`; host-side,
post-evaluation, never in-kernel) → [8] trace explainer (fresh
`trace_explanation.json`, or `available:false` with no key) → [9] feedback rule
generator (FAIL-only; appends to `outputs/live/feedback_rules.md`, FIFO-capped).

`manifest.json` records `backend`, `seed`, `workload_type`,
`llm_selected_algorithm`, `algorithms_executed`, `generated_at`, plus feedback
flags. Judgment/regret definitions: `docs/evaluation_plan.md`.
