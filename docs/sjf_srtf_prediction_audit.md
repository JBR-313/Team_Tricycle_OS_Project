# SJF / SRTF Burst Prediction Audit

> **Status:** Audit (2026-05-28, branch `feat/upstage-runtime-strict`).
> Scope: xv6 kernel (`xv6-riscv/kernel/proc.c`) and the host Python simulator
> (`tools/scheduler_simulator.py`). Verifies the **burst prediction rule** in
> `CLAUDE.md`:
>
> > Future CPU bursts must not be given to the LLM as input. SJF/SRTF requires
> > a burst predictor (exponential averaging or LLM-assisted). Actual future
> > burst values must never be leaked to the LLM.

---

## 1. Summary verdict

| Backend | Predictor type | Oracle (uses true future burst)? | Rule compliance |
|---|---|---|---|
| **xv6** (final demo path) | Integer exponential averaging on **observed** CPU usage | **No** — only `cur_burst_run` (already-consumed) and the prior `predicted_burst` are read | **PASS** |
| **simulator** (dev/fallback) | None. SJF/SRTF picker compares `p.remaining` — which is the **actual remaining CPU burst** taken from the workload JSON | **YES — oracle** | **FAIL** (acceptable for a dev fallback, but must not be presented as the final result) |

> The simulator is documented elsewhere as a “host-side model, not proof of
> real xv6 execution” (`docs/implementation_status.md`). This audit makes the
> SJF/SRTF-specific consequence explicit so it is not mistakenly cited as
> evidence of predictor quality.

---

## 2. xv6 SJF/SRTF predictor — full walkthrough

### 2.1 State

`xv6-riscv/kernel/proc.c:34-45`

```c
// Global burst-predictor parameters for SJF/SRTF.  The LLM recommends these
// before execution; they are applied via set_predictor_params() (validated in
// the syscall layer by Algorithm Guard / sys_setpredictor).
struct predictor_params {
  int alpha_percent;            // exponential-averaging weight, 0..100
  int initial_predicted_burst;  // prediction assigned to a brand-new process
  int min_predicted_burst;      // lower clamp for predictions
  int max_predicted_burst;      // upper clamp for predictions
};
struct predictor_params pred = {50, 10, 1, 100};   // alpha=50%, init=10, [1,100]
```

Per-process fields (`struct proc`):

| Field | Meaning |
|---|---|
| `predicted_burst` | current EMA prediction for the *next* CPU burst |
| `cur_burst_run`   | CPU ticks consumed in the *current* burst so far (zeroed at each prediction update) |
| `ready_since_tick`| tick at which the process re-entered RUNNABLE (tie-break) |

### 2.2 Initialization

`proc.c:157-162`

```c
p->predicted_burst  = pred.initial_predicted_burst;
if(p->predicted_burst < pred.min_predicted_burst)
  p->predicted_burst = pred.min_predicted_burst;
if(p->predicted_burst > pred.max_predicted_burst)
  p->predicted_burst = pred.max_predicted_burst;
p->cur_burst_run    = 0;
```

A newborn process gets the `initial_predicted_burst` (default 10), clamped.
No knowledge of the “true” first burst is used.

### 2.3 Update (only at end of an observed burst)

`proc.c:560-581`

```c
// Update a process's burst prediction at the end of an observed CPU burst,
// using integer exponential averaging:
//   new = (alpha*observed + (100-alpha)*old) / 100
// Only the already-observed burst length (cur_burst_run) feeds the update; the
// true future burst is never used.  Caller must hold p->lock.
static void
update_burst_prediction(struct proc *p)
{
  int observed = p->cur_burst_run;
  if(observed <= 0)
    return;
  int a   = pred.alpha_percent;
  int lo  = pred.min_predicted_burst;
  int hi  = pred.max_predicted_burst;
  int np  = (a * observed + (100 - a) * p->predicted_burst) / 100;
  if(np < lo) np = lo;
  if(np > hi) np = hi;
  p->predicted_burst = np;
  p->cur_burst_run   = 0;
}
```

**Call site:** `sleep()` only (`proc.c:1034-1036`):

```c
// Blocking on I/O ends the current CPU burst: fold the observed burst length
// into the prediction for this process's next burst (SJF/SRTF).
update_burst_prediction(p);
```

This means the prediction is refreshed when a process blocks on I/O
(`sleep`), modeling “the previous CPU burst is finally measurable.” No update
happens on quantum expiry, EXIT, or context switch (because those are not
end-of-burst events).

### 2.4 Picker — SJF

`proc.c:809-851` — non-preemptive. Compares `p->predicted_burst` directly;
tie-break by `ready_since_tick` then `pid`. The picker **never** reads any
field that encodes the true future burst.

### 2.5 Picker — SRTF

`proc.c:853-897` — preemptive. Compares `predicted_remaining(p)`:

```c
static int
predicted_remaining(struct proc *p)
{
  int rem = p->predicted_burst - p->cur_burst_run;
  if(rem < pred.min_predicted_burst)
    rem = pred.min_predicted_burst;
  return rem;
}
```

Both inputs (`predicted_burst`, `cur_burst_run`) are predictions or observed
elapsed time — never future. SRTF preemption is implemented by `trap.c`
yielding every tick under SRTF so `sched_srtf` re-runs on every scheduling
point.

### 2.6 LLM-recommended predictor params (input)

`tools/llm_advisor.py:82-88` defines the LLM-facing schema:

```
SJF/SRTF : params = {
   "alpha_percent": <int 0-100>,
   "initial":       <int >=1>,
   "min":           <int >=1>,
   "max":           <int, >=min, <=100000>
}
```

These flow through `algorithm_guard` (`PARAM_RANGES`) and reach the kernel
via `set_predictor_params(alpha, initial, min, max)` (`proc.c:523-540`).
The LLM is **only** influencing predictor shape, never seeing real bursts.

### 2.7 Trace leakage check

`proc.c:592-611` `sched_trace()` emits `[SCHED] tick=… algo=… event=… pid=…`
plus optional `state`, `queue`, `priority`, `reason`. **No CPU-burst value is
ever printed**, so a future-burst leak via the trace is impossible. The
explicit comment on line 595 calls this out:

```c
// No CPU-burst value is ever emitted, so future bursts cannot leak via traces.
```

### 2.8 Conclusion (xv6)

- Initial prediction: `pred.initial_predicted_burst` (default **10** ticks),
  clamped to `[1, 100]`.
- Smoothing: `alpha_percent / 100`, default **0.5**.
- Update timing: at end of observed burst, i.e. when the process calls
  `sleep()` (I/O). Updated value uses only the observed `cur_burst_run` and
  the old prediction.
- Predicted remaining (SRTF): `predicted_burst − cur_burst_run`, floored at
  `min_predicted_burst`.
- LLM-facing knobs: `alpha_percent`, `initial`, `min`, `max` (validated by
  guard, applied via `set_predictor_params`).
- **No oracle.** No code path in `proc.c` reads a future burst.

**Compliance: PASS.**

---

## 3. Simulator SJF/SRTF — oracle gap

### 3.1 What the simulator does

`tools/scheduler_simulator.py:157-167`

```python
def _pick_sjf(self) -> Optional[Process]:
    r = self._runnable()
    if not r:
        return None
    return min(r, key=lambda p: (p.remaining, p.pid))

def _pick_srtf(self) -> Optional[Process]:
    r = self._runnable()
    if not r:
        return None
    return min(r, key=lambda p: (p.remaining, p.pid))
```

`p.remaining` is set from the workload JSON’s `cpu_bursts` list
(`scheduler_simulator.py:228-230`):

```python
for p in self.procs:
    p.remaining = p.bursts[0] if p.bursts else 0
```

That is the **true remaining CPU time** for the current burst — i.e. the
picker reads the future. There is no `predicted_burst` field, no
`alpha_percent`, no `update_burst_prediction`.

### 3.2 Why this still appears in the dashboard

`scheduler_simulator.run_all_algorithms()` runs SJF/SRTF over the same
workload and `metrics.json` lists their numbers in the `comparison` block.
The Counterfactual Metric View card may therefore label SJF/SRTF as the
“best on metric X” using oracle numbers — that is a misleading comparison
when shown next to the xv6 SJF/SRTF numbers (which are EMA-predicted).

### 3.3 Required disclosure (already partially in place)

- `docs/work_status_sjf_srtf.md` and `docs/implementation_status.md` mention
  the predictor; they do not currently flag the simulator as oracle. **TODO**
  in this audit: add a one-line warning to both, plus a footnote on the
  dashboard `CounterfactualMetricView` when the backend badge is
  `SIMULATOR FALLBACK`.

### 3.4 Recommendation

Two options, in priority order:

1. **Cheap fix (P1):** add an EMA `predicted_burst` to the simulator’s
   `Process` and switch `_pick_sjf` / `_pick_srtf` to use it. Use the same
   default `(alpha=50, initial=10, min=1, max=100)` so simulator and xv6
   numbers become directly comparable. This is ~30 lines.
2. **Disclosure-only fix (P0 for the demo):** add a `CAUTION: SJF/SRTF in
   simulator uses oracle remaining time` banner in the
   `CounterfactualMetricView` card whenever `manifest.metadata_source` is
   `simulator`, plus the same line to `docs/work_status_sjf_srtf.md` and the
   README `final-status` table.

For the final demo the disclosure is the minimum that prevents misleading
the audience; the cheap fix is the right long-term answer.

---

## 4. Quick reference (the four numbers that matter)

| Quantity | xv6 default | Simulator |
|---|---|---|
| `alpha_percent` (EMA smoothing) | 50 (`pred.alpha_percent = 50`) | n/a (oracle) |
| `initial_predicted_burst`       | 10                              | n/a |
| `min_predicted_burst`           | 1                               | n/a |
| `max_predicted_burst`           | 100                             | n/a |
| Update trigger                  | `sleep()` (I/O block)           | — |
| Picker key (SJF)                | `predicted_burst`               | `remaining` (oracle) |
| Picker key (SRTF)               | `predicted_burst − cur_burst_run` (floored) | `remaining` (oracle) |

---

## 5. Action items (for the demo window)

| Priority | Action | Owner | Where |
|---|---|---|---|
| **P0** | Add a “simulator SJF/SRTF is oracle” disclosure in `docs/work_status_sjf_srtf.md` and the README final-status table. | docs | this PR |
| **P0** | Show a small caveat in `CounterfactualMetricView` when `manifest.metadata_source ≠ xv6`. | frontend | future PR |
| P1     | Port EMA predictor into `tools/scheduler_simulator.py` so simulator vs xv6 SJF/SRTF numbers are comparable. | sched-sim owner | post-demo |
| P2     | Emit a `[SCHED] event=PRED_UPDATE pid=… predicted=…` line on every EMA update in xv6 so the dashboard can show prediction drift. | xv6 lead | post-demo |

