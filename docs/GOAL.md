# GOAL — xv6 as the sole execution authority, with reproducible measurement

## Why
The project's thesis is *"the LLM advises; xv6 executes."* Today a Python
**scheduler simulator** is a second execution engine whose fidelity to xv6 is
unverified, and the real-xv6 path is **non-deterministic** (FCFS varied ~24% run
to run) because `schedtest`'s `run_burst()` spins on the wall-clock tick counter
and the QEMU guest timer is driven by host wall-clock. We want one execution
authority (xv6) that produces **reproducible** numbers we can honestly cite.

## What
1. **Determinize execution** (do FIRST):
   - `run_burst()` → fixed, calibrated iteration count (no `uptime()` spin).
     A CPU burst is an amount of *computation*, not wall-clock; the old code also
     wrongly counted descheduled time (global `uptime()`).
   - QEMU `-icount` → guest timer on a deterministic virtual clock, so preemption
     points reproduce.
2. **VERIFY** with `experiments/xv6_determinism_probe.py` (the gate).
3. **Remove the simulator** (only if the gate passes): delete the simulator, its
   tests, and the simulator-only experiment/A-B tools; make the orchestrator
   xv6-only.

## Order matters
Determinize → **verify gate** → remove simulator. Removing the simulator before
xv6 is proven reproducible would delete the fallback *and* the clean A/B with
nothing reliable to replace it.

## Done when
- The determinism probe reports DETERMINISTIC (or residual noise << the gap
  between algorithms), AND
- `scripts/orchestrator.py` runs the full pipeline on xv6 only, with no simulator
  code or dangling imports remaining, AND
- the remaining test suite passes.

## Honesty notes
- Removing the simulator makes prior **simulator-based** conclusions (ODA negative
  result, burst-prediction +30%) non-reproducible; their RESULTS.md get a
  provenance note. Deterministic xv6 is the path to re-measuring them *cleanly*.
- `-icount` makes runs host-independent in *virtual* time; absolute tick counts
  may shift from the old wall-clock numbers (a re-baseline, expected).
