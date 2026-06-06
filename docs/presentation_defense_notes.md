# Presentation Defense Notes

Crisp answers to the questions most likely to come up. Each is honest and maps
to concrete code.

### Does the LLM control the scheduler?
**No.** The LLM *recommends* an algorithm + params before the run, *explains*
the result after, and *proposes* corrections — but xv6 is the execution
authority. The LLM never runs in the kernel and never picks the next process at
a timer tick. (`proc.c` schedulers run independently of any LLM.)

### Is this simulator-only?
**No.** The real xv6 kernel runs under QEMU and is the **default** dashboard RUN
path (`backend: 'xv6'` in `dashboard_live/src/data/useRun.js`). The simulator is
an explicit dev/fallback backend. The data-source badge shows `XV6 TRACE` vs
`SIMULATOR` so the two are never confused.

### Does SJF/SRTF know future bursts?
**No.** Future bursts (`actual_bursts`) are never given to the LLM or the
kernel. SJF/SRTF schedule on a *predicted* burst: an exponential moving average
(EMA) over already-observed CPU time (`cur_burst_run`), optionally seeded by LLM
priors derived from **visible** features only. (`proc.c` `predicted_remaining`;
the no-future-burst rule.)

### Why does SRTF sometimes not preempt?
At cold start every unseen process gets the same `initial` burst prior, while
the running job's predicted remaining only decreases. So a freshly arrived job
never looks *shorter* than the one running, and SRTF has no reason to preempt.
Once the EMA observes a few bursts (or the LLM supplies good priors), SRTF
separates jobs and preempts. **Expected behavior, not a bug** — documented in
[`system_limitations.md`](system_limitations.md).

### Is the replay real-time kernel control?
**No.** The dashboard replays a *recorded* trace (`trace_<algo>.jsonl`) with a
simulated-ms clock. The kernel already finished; replay is visualization. There
is no websocket and no live kernel control.

### What OS concepts are implemented?
Process & process state, CPU scheduling (6 algorithms), ready queue, preemption,
context switch, system calls (`setscheduler`/`getscheduler`/`setpriority`/…),
timer interrupts, aging, multi-level feedback queues, burst prediction.

### What are the limitations?
CPUS=1; curated xv6 workloads (no JSON parser in the kernel); no in-kernel LLM;
no websocket; SJF/SRTF limited by the no-future-burst rule; simulator output is
not proof of xv6; educational not production. See
[`system_limitations.md`](system_limitations.md).

### What happens if the API key is missing?
The orchestrator is **strict by default**: a missing `UPSTAGE_API_KEY` (or any
advisor/guard failure) exits with a clear message rather than faking a Solar
call. `--offline-fixture` opts in to committed fixtures and stamps
`manifest.metadata_source = demo_fallback`. The Trace Explainer falls back to a
fixture (offline mode) or an explicit `available:false` placeholder. The
Feedback step logs an honest skip — it is **never** faked.

### Does feedback change the current run?
No. Feedback rules are **generated** after evaluation (FAIL/starvation only) and
written to `outputs/live/feedback_rules.md`. They can only influence **future**
recommendations, and only when **consumption is explicitly enabled** with
`--use-feedback`. The just-finished run is never altered.

### Why is feedback consumption opt-in?
To keep the final demo **deterministic** and to prevent a stale or overfit rule
from polluting an unrelated workload's recommendation. By default the advisor
runs from the base prompt with no feedback injected; `--use-feedback` (or
`use_feedback:true` to the run-server) is a deliberate, recorded choice
(`manifest.feedback_consumed=true` + a small **Feedback: ON** dashboard chip).

### How do you prove xv6 actually executed?
- Run `python3 scripts/orchestrator.py --backend xv6 …`: it builds the kernel,
  boots QEMU, runs `schedtest` per algorithm, and captures the **real serial
  console** to `outputs/xv6_raw_<algo>_seed<seed>.log`.
- The trace is parsed from those raw kernel logs (`trace_parser.py`), and the
  manifest records `backend: xv6` → the dashboard badge reads `XV6 TRACE`.
- `python3 scripts/final_demo_check.py --with-xv6` runs the xv6 smoke and checks
  trace sanity end-to-end.
