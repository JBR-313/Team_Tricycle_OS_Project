# Presentation Defense Notes

Concise, honest answers to the questions the demo audience is most
likely to ask. Use these as a prompt — every claim here is backed by
the docs and code linked next to it.

> **One-line elevator pitch:**
> LLM suggests. Algorithm Guard checks. xv6 executes. Metrics verify.
> GUI explains.

---

## 1. What actually runs in xv6 vs what is simulator fallback?

**xv6 backend = final demo / experiment path.** When you see
`Backend: XV6 TRACE` in the dashboard header, every Gantt chart, every
metric, every per-process trace event came from a real xv6 kernel
running under QEMU. Concretely:

1. `scripts/orchestrator.py --backend xv6` builds the xv6 kernel
   (`make CPUS=1`).
2. For each scheduling algorithm (LLM-selected first), it boots QEMU,
   types `schedtest <algo> 42 interactive`, captures the serial
   console, windows the run on `RUN_BEGIN`/`RUN_END`, parses the
   `[SCHED]`/`[SCHEDTEST]` lines into `trace_<algo>.jsonl`, and
   aggregates `metrics.json`.
3. `xv6-riscv/kernel/proc.c` is the **scheduler that picks the next
   process**, not the orchestrator or the LLM.

**Simulator backend = dev / fallback only.** `tools/scheduler_simulator.py`
is a Python model of the same algorithms; it is fast, deterministic,
and good for UI development. When the dashboard header shows
`Backend: SIMULATOR FALLBACK` the data came from this Python model —
**say so explicitly** if you have to fall back to it during the demo.
Never present simulator output as real xv6.

Code paths: `xv6-riscv/kernel/proc.c`, `xv6-riscv/user/schedtest.c`,
`scripts/orchestrator.py`, `tools/scheduler_simulator.py`.

---

## 2. Why is the LLM an advisor, not the scheduler?

The LLM is too slow, too non-deterministic, and too unsafe to be on the
hot path of a kernel scheduler:

- A scheduler decision must happen at every timer tick (~10 ms in
  xv6). A network round-trip to Solar Pro 3 is orders of magnitude
  slower.
- An LLM is non-deterministic. The same workload could get different
  schedules on different days — the comparison story would collapse.
- An LLM hallucinates. An unchecked recommendation could pick an
  unsupported algorithm or violate kernel invariants.

So the LLM is **before** and **after** the scheduling run:

- **Before:** interpret the workload summary, recommend a Scheduling
  Algorithm + parameters (`tools/llm_advisor.py` → `recommendation.json`).
- **After:** explain the trace and metrics in natural language
  (`tools/trace_explainer.py` → `trace_explanation.json`).

The kernel picks the next process at every tick. The LLM never does.

Source: `README.md` §3 "System Principle"; `tools/llm_advisor.py`;
`docs/orchestrator_design.md` §"Why the simulator is not the final
backend".

---

## 3. How does the Algorithm Guard protect recommendations?

Every LLM output passes through `tools/algorithm_guard.py` before xv6
sees it. The Guard checks:

- The recommended algorithm is actually implemented in xv6 (`RR`,
  `FCFS`, `Priority+Aging`, `MLFQ`, `SJF`, `SRTF`).
- Parameters fall inside known-safe ranges (quantums positive, aging
  threshold reasonable, etc).
- The output matches the required JSON schema.
- For burst-prediction-dependent algorithms (`SJF`, `SRTF`), the Guard
  also checks that no actual future-burst values were leaked into the
  LLM input (the "burst prediction rule" from `CLAUDE.md`).

If anything fails, the Guard rejects the recommendation and falls back
to a safe algorithm (RR). The decision is written to
`guard_decision.json`, the dashboard surfaces it on the Algorithm Guard
card.

Source: `tools/algorithm_guard.py`; `README.md` §6 "Algorithm Guard".

---

## 4. How are the algorithms compared fairly?

`scripts/orchestrator.py` enforces the fairness rule documented in
`docs/orchestrator_design.md`:

- **Same deterministic workload** for every algorithm — same `seed`
  and `profile`, mapped to the same `workloads/*.json` file.
- **Algorithms run sequentially, never simultaneously.** Each run is a
  fresh QEMU boot.
- **LLM-selected algorithm runs first**, then the rest in the canonical
  order `RR, FCFS, Priority, MLFQ, SJF, SRTF` (minus the selected one).
- After all runs finish, the orchestrator aggregates `metrics.json` with
  a per-algorithm `comparison` block and a single judgment.

This is why `manifest.algorithms_executed` is a list, not a set: the
order is part of the experimental claim.

Source: `scripts/orchestrator.py:compute_run_order`, `:run_xv6_backend`;
`docs/orchestrator_design.md` §"Why algorithms run sequentially on the
same seed/profile".

---

## 5. Why is the runtime correction loop only partial?

The closed-loop design is:

```
trace event → event_detector → proposer → LLM → guard re-check →
applied at next scheduling point → CORRECTION_APPLIED trace event →
dashboard
```

What exists today: **only `event_detector.py`**. It can spot starvation,
poor response time, or excessive preemption from the trace, and it
writes a candidate event JSON.

What does **not** exist today: the proposer, the LLM call for a
correction, the guard re-check on the correction, the actual apply step
inside xv6, and the `CORRECTION_APPLIED` trace event the dashboard
would render.

This is honestly marked `Partial / Future Work` in:
- `README.md` §12.1 status table
- `docs/implementation_status.md`
- `docs/demo_runbook.md` §"Limitations"

Do not claim closed-loop runtime correction during the demo. It is the
single biggest piece of intentional future work.

Source: `tools/event_detector.py`; `docs/implementation_status.md`.

---

## 6. Known limitations to acknowledge (audience may ask)

- **No websocket / push streaming.** The dashboard polls
  `manifest.json` periodically. Live mode reflects the most recent
  orchestrator publish, not a real-time event stream.
- **xv6 traces are short, educational traces.** 5 children per curated
  workload profile, typically 30–80 events per algorithm. Real OS
  schedulers produce orders of magnitude more events. The metrics
  starvation rule (`tools/metrics.py`) and the regret-based judgment
  (`scripts/orchestrator.py`, `dashboard_live/src/data/schemaCompat.js`)
  both apply an absolute tick floor so sub-tick noise on these short
  traces does not falsely flag starvation or FAIL — see PR #14 and #15.
- **Solar Pro 3 API fallback.** Without a key in `.env`, the
  orchestrator falls back to `outputs/demo/recommendation.json` and
  stamps `metadata_source=demo_fallback`. The dashboard then shows
  `Backend: FALLBACK` instead of `XV6 TRACE`. If this happens during
  the demo, announce it.
- **Kernel/user printf interleave on xv6.** The serial console
  occasionally splits a `[SCHEDTEST] event=RUN_BEGIN ...` line mid-
  print. The orchestrator's windowing matches both `RUN_BEGIN` and a
  per-algorithm `algo=<TARGET>` anchor so the run is recovered (see PR
  #17). Empty traces are caught by the strict contract validator (see
  PR #16).

---

## 7. Quick mapping of "audience question" → "where to point"

| Question | Where to point |
|----------|----------------|
| "Did the LLM actually run xv6?" | Header backend badge → `XV6 TRACE` |
| "How do you stop the LLM picking a bad algorithm?" | Algorithm Guard card |
| "What if the LLM is wrong?" | Comparison table — same workload, every algorithm, target-metric judgment |
| "Can the LLM change strategy mid-run?" | Runtime correction is Partial / Future Work (be honest) |
| "Is this real-time?" | No — `manifest.json` polling; final result is replayable per tick |
| "What if the API is down?" | Demo fallback (`Backend: FALLBACK`); recommendation/guard come from `outputs/demo/` |

---

## 8. Things to say with confidence

- "xv6 is the execution authority. The LLM is a decision support layer."
- "Every algorithm in the comparison ran on the **same** deterministic
  workload — same seed, same profile, same workload file."
- "The Algorithm Guard never lets an unverified LLM recommendation
  reach xv6."
- "The dashboard's backend badge is the honesty signal — if it doesn't
  say `XV6 TRACE`, the data is not from real xv6."
- "Runtime correction is the one piece we are honest about as Future
  Work. Event detection exists; the close-the-loop steps don't yet."

## 9. Things to NOT claim

- That the LLM runs inside xv6 (it doesn't, by design).
- That the LLM makes per-tick scheduling decisions (it doesn't).
- That runtime correction is closed loop today (it isn't).
- That the simulator output is real xv6 execution (it isn't —
  `SIMULATOR FALLBACK` is a separate badge for that reason).
- That trace streaming is real-time (it's polling).
