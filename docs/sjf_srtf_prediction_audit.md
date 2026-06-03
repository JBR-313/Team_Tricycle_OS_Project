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
| **simulator** (dev/fallback) | Integer exponential averaging on **observed** CPU usage (mirrors xv6; fixed 2026-05-28). SJF/SRTF picker uses `predicted_burst`, never `p.remaining` | **No** — `p.remaining` is used only by the simulation engine to advance time, not by the picker | **PASS** (still a host-side model — must not be presented as the final result) |

> The simulator is documented elsewhere as a “host-side model, not proof of
> real xv6 execution” (`docs/implementation_status.md`). Both backends now use
> the same EMA `predicted_burst` rule, so neither leaks future bursts; what the
> simulator still cannot prove is *real xv6 execution* — its numbers are a
> host-side model, not predictor-quality evidence. Predictor accuracy (MAE) is
> not yet measured (§3.4, Future Work).

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

## 3. Simulator SJF/SRTF — EMA prediction (oracle gap CLOSED 2026-05-28)

> **Status update.** The oracle gap described in earlier drafts of this audit
> has been fixed. As of 2026-05-28 the simulator schedules SJF/SRTF on an EMA
> `predicted_burst`, mirroring the xv6 kernel. The picker never reads the true
> remaining burst. The text below reflects the **current** code.

### 3.1 What the simulator does

`tools/scheduler_simulator.py` (`_pick_sjf` / `_pick_srtf`):

```python
def _pick_sjf(self) -> Optional[Process]:
    """Predicted SJF — uses predicted_burst, NEVER p.remaining (ground truth)."""
    r = self._runnable()
    if not r:
        return None
    return min(r, key=lambda p: (p.predicted_burst, p.ctime, p.pid))

def _pick_srtf(self) -> Optional[Process]:
    """Predicted SRTF — predicted_burst minus already-observed cur_burst_run,
    floored at predictor.min. Never reads p.remaining (ground truth)."""
    ...
    return min(r, key=lambda p: (predicted_remaining(p), p.ctime, p.pid))
```

The simulator carries a `predicted_burst` field plus an EMA `BurstPredictor`
(`alpha_percent`, `initial`, `min`, `max`), seeds it from `predictor.initial`
(or per-process LLM hints when `prediction_source == "llm"`), and refreshes it
at end-of-burst via `update_burst_prediction()` — the same shape as the xv6
kernel's `update_burst_prediction()`. `p.remaining` still exists, but it is used
**only** by the simulation engine to advance time (decrement actual remaining
each tick); it is never read by the scheduling decision.

### 3.2 Comparability with xv6

Because both backends now schedule on an EMA `predicted_burst` with the same
defaults (`alpha=50, initial=10, min=1, max=100`), the simulator vs xv6 SJF/SRTF
numbers in the `comparison` block are directly comparable, and the
Counterfactual Metric View no longer risks labelling SJF/SRTF "best on metric X"
using oracle numbers.

### 3.3 Disclosure (in place)

- `README.md`, `docs/implementation_status.md`, and `docs/demo_runbook.md` all
  state that SJF/SRTF use EMA prediction and that actual future bursts never
  reach the scheduler/LLM. The stale "simulator is oracle" caveat in
  `tools/scheduler_simulator.py`'s module docstring has been corrected.

### 3.4 Remaining future work

- **Predictor quality evaluation.** The EMA predictor is implemented, but its
  prediction *accuracy* (e.g. MAE of `predicted_burst` vs observed burst) is not
  yet measured or surfaced on the dashboard. A full predictor-MAE view is
  **Future Work**, not part of the final demo.

---

## 4. Quick reference (the four numbers that matter)

| Quantity | xv6 default | Simulator |
|---|---|---|
| `alpha_percent` (EMA smoothing) | 50 (`pred.alpha_percent = 50`) | 50 |
| `initial_predicted_burst`       | 10                              | 10 |
| `min_predicted_burst`           | 1                               | 1 |
| `max_predicted_burst`           | 100                             | 100 |
| Update trigger                  | `sleep()` (I/O block)           | end-of-burst |
| Picker key (SJF)                | `predicted_burst`               | `predicted_burst` |
| Picker key (SRTF)               | `predicted_burst − cur_burst_run` (floored) | `predicted_burst − cur_burst_run` (floored) |

---

## 5. Action items (for the demo window)

| Priority | Action | Owner | Status |
|---|---|---|---|
| ~~P1~~ | Port EMA predictor into `tools/scheduler_simulator.py` so simulator vs xv6 SJF/SRTF numbers are comparable. | sched-sim owner | **DONE (2026-05-28)** — picker now uses `predicted_burst`. |
| ~~P0~~ | Correct the "simulator SJF/SRTF is oracle" wording in code/docs. | docs | **DONE** — module docstring + this audit updated. |
| Future | Measure predictor accuracy (MAE of `predicted_burst` vs observed) and surface it on the dashboard. | sched-sim owner | Future Work (not in final demo). |
| Future | Emit a `[SCHED] event=PRED_UPDATE pid=… predicted=…` line on every EMA update in xv6 so the dashboard can show prediction drift. | xv6 lead | Future Work. |

