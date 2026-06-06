# xv6 Workload Profile Support — Audit

Post-RC audit of which schedtest profiles are actually runnable on the
xv6 backend, recorded against `main` at the time of this document.

> The broader validation scope spans the local final demo check, the
> broader multi-profile check, and lightweight CI.

---

## 1. Where profile support lives

Two places have to agree for a profile to be "truly supported":

1. **xv6 schedtest** — `xv6-riscv/user/schedtest.c` carries a fixed
   curated workload table per profile (no JSON parsing inside the
   guest by design). The `WORKLOADS[]` array at the top of the file
   is the source of truth on the kernel side. Each entry is a list
   of `{arrival, cpu_burst, priority, label}` for the children that
   `schedtest` will fork.
2. **Orchestrator** — `scripts/orchestrator.py` exposes the matching
   profile names in `XV6_PROFILES` (used to refuse silently falling
   back to a different profile) and in `PROFILE_MAP` (used to point
   the host-side `workload_analyzer.py` at the corresponding
   `workloads/*.json` file).

Both sets must contain the same profile name; otherwise the orchestrator
either refuses the profile (`XV6_PROFILES` miss → fallback to `mixed`,
which would silently substitute) or the analyzer can't find a JSON
workload to interpret.

## 2. Profiles available today

| Profile | In `schedtest.c` `WORKLOADS[]`? | In `scripts/orchestrator.py` `XV6_PROFILES`? | In `PROFILE_MAP` → `workloads/*.json`? |
|---------|---------------------------------|---------------------------------------------|-----------------------------------------|
| `interactive`        | ✓ (5 procs) | ✓ | ✓ `workloads/interactive_heavy.json` |
| `cpu_bound`          | ✓ (4 procs) | ✓ | ✓ `workloads/long_cpu_bound_first.json` |
| `mixed`              | ✓ (5 procs) | ✓ | ✓ `workloads/mixed_workload.json` |
| `priority_sensitive` | ✓ (5 procs) | ✓ | ✓ `workloads/priority_sensitive.json` |
| `interactive_storm`  | ✓ (8 procs) | ✓ | ✓ `workloads/xv6_interactive_storm.json` |
| `batch_convoy`       | ✓ (8 procs) | ✓ | ✓ `workloads/xv6_batch_convoy.json` |

The two 8-proc profiles (`interactive_storm`, `batch_convoy`) were added to
raise xv6 workload scale and variety beyond ~5 procs. Their mirror JSONs are
their own canonical file (analyzed == forked), and
`tests/test_xv6_mirror_alignment.py` parses `WORKLOADS[]` and asserts the
mirror matches the C table process-for-process. `schedtest.c` compiles clean
(`-Wall -Werror`) and `fs.img` builds with `_schedtest`; an end-to-end QEMU
snapshot run for the two new profiles is not yet recorded below (the empirical
table in §3 predates them).

Additional `PROFILE_MAP` entries that are **not** in `XV6_PROFILES`
(simulator-only / dev-only profiles):

| Profile | Status on xv6 |
|---------|---------------|
| `short_jobs`      | **Not curated for xv6.** Orchestrator would substitute `mixed` if invoked; not in `XV6_PROFILES`. |
| `starvation_risk` | **Not curated for xv6.** Same behaviour as above. |

## 3. Empirical run (xv6 backend, seed=42)

`python3 scripts/export_profile_snapshots.py --backend xv6` exercises
every `XV6_PROFILES` entry end-to-end (orchestrator → strict contract
validator). Result on `main` at audit time:

```
profile                 orch   val judgement       regret starv sel       ver   sec
-----------------------------------------------------------------------------------
interactive                0     0 SUCCESS            0.0 False MLFQ       16  38.9
cpu_bound                  0     0 SUCCESS            0.0 False MLFQ       17  42.4
mixed                      0     0 SUCCESS            0.0 False MLFQ       18  39.3
priority_sensitive         0     0 SUCCESS            0.0 False MLFQ       19  40.8

  passed : 4/4 — ['interactive', 'cpu_bound', 'mixed', 'priority_sensitive']
```

Per profile: `orchestrator_rc=0`, `validator_rc=0` (`--strict`), LLM
picked `MLFQ` on all four, top-level metrics `judgment=SUCCESS` with
`regret_score=0.0` and `starvation_occurred=False`. Each profile takes
roughly 40 seconds end-to-end (xv6 build + 6 QEMU boots + parse +
metrics + publish + validate).

## 4. Practical conclusion

- **All four original curated profiles are empirically verified on the xv6
  backend** (table §3). Two larger 8-proc profiles (`interactive_storm`,
  `batch_convoy`) have since been added and statically verified (compile +
  `fs.img` build + mirror-alignment test); a fresh QEMU snapshot run would
  extend the §3 table to 6/6.
- The on-stage demo path remains `--seed 42 --workload interactive`
  — this audit is broader confidence, not a replacement for the demo check.
- The two simulator-only profiles (`short_jobs`, `starvation_risk`)
  are intentionally **not** part of the xv6 path. If a future demo
  needs them on xv6, a new `WORKLOADS[]` entry would have to be added
  in `schedtest.c` and the profile listed in `XV6_PROFILES`. Until
  then, they are reported as SKIPPED rather than silently
  substituting `mixed`.

## 5. Out of scope for this audit

- No new profiles added; no schedtest table changes.
- No runtime-correction changes here. (Runtime correction itself is
  **implemented** as a host-side post-evaluation apply loop — see
  `docs/implementation_status.md`; it is simply out of scope for this
  profile-support audit.)
- No UI changes.
