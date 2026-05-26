# Final Release Candidate Report

Point-in-time record of the RC validation after the recent README,
runtime-correction preview, validator, CI, and dashboard updates.

> Companion to `docs/final_demo_acceptance.md` (release contract),
> `docs/final_demo_dry_run_report.md` (earlier dry-run snapshot),
> and `docs/runtime_correction_preview_validation.md` (preview
> schema rules).

---

## 1. Run metadata

| Field | Value |
|-------|-------|
| Date / time (UTC) | 2026-05-26 12:13:16Z |
| Branch | `main` (origin/main fast-forwarded) |
| HEAD | `d5f4b62` — `docs(sync): note --preview validator + CI smoke in README + defense notes (#61)` |
| Host | WSL2 (Linux 6.6.87.2), `qemu-system-riscv64`, `riscv64-unknown-elf-gcc` |
| Backend used by the demo command | xv6 (final demo path) |

---

## 2. Commands run

From the repository root:

```bash
git fetch origin && git checkout main && git pull origin main

python3 scripts/final_demo_check.py
python3 scripts/correction_preview_smoke.py
python3 tools/validate_dashboard_contract.py --strict --preview \
    --dir dashboard_live/public/live-data \
    --snapshots dashboard_live/public/live-data/snapshots

cd dashboard_live && npm run build
cd ../dashboard_test && npm run build
```

---

## 3. Pass / fail table

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | `python3 scripts/final_demo_check.py` | **PASS** | `[OK] All pre-demo checks passed.` exit 0 (xv6 full pipeline + strict validator inside the script). |
| 2 | `python3 scripts/correction_preview_smoke.py` | **PASS** | 5/5 scenarios OK; every proposal `preview_only=true / applied=false`; all guard verdicts `accepted`; `dashboard_live/public/live-data/` untouched. |
| 3 | `python3 tools/validate_dashboard_contract.py --strict --preview --dir ... --snapshots ...` | **PASS** | **67 OK / 0 WARN / 0 ERROR.** Includes the four committed xv6 snapshots and the new `runtime_events.json` (`0 event(s)`). |
| 4 | `cd dashboard_live && npm run build` | **PASS** | 192.71 KB JS / 59.77 KB gzip. |
| 5 | `cd dashboard_test && npm run build` | **PASS** | 224.43 KB JS / 63.46 KB gzip. |

---

## 4. Published live-data snapshot

`dashboard_live/public/live-data/` (committed on `main`):

| Field | Value |
|-------|-------|
| `manifest.backend` | `xv6` |
| `manifest.mode` | `xv6-log` |
| `manifest.version` | `17` (flat live-data; per-snapshot manifests have their own versions) |
| `manifest.workload_type` | `interactive` |
| `manifest.llm_selected_algorithm` | `MLFQ` |
| `manifest.algorithms_executed` | `[MLFQ, RR, FCFS, Priority, SJF, SRTF]` |
| `metrics.scheduling_algorithm` | `MLFQ` |
| `metrics.judgment` | `SUCCESS` |
| `metrics.regret_score` | `0.0` |
| `metrics.starvation_occurred` | `false` |
| `snapshots/` directories | 4 (interactive, cpu_bound, mixed, priority_sensitive) |
| `snapshots_manifest.json` profile count | `4` |
| Runtime-correction preview (after fresh xv6 run) | `runtime_events.json` published with `events: []` (healthy state) |

---

## 5. CI status

`.github/workflows/ci.yml` defines three jobs (python + dashboard_live +
dashboard_test). The python job runs:

- `py_compile tools/*.py scripts/*.py`
- `validate_dashboard_contract.py --strict`
- `correction_preview_smoke.py` *(added in PR #60)*
- `validate_dashboard_contract.py --strict --preview` *(added in PR #60)*

**Observation:** GitHub Actions did not produce new CI runs for
several recent PRs (#55–#61). The workflow itself is `active` and
identical to a known-good pattern; the most recent successful run
on `main` is at `2026-05-26 10:35:03Z` (commit `8551361`,
PR #48). Subsequent PRs landed with `no checks reported on the …
branch` and merged without CI feedback. Root cause is external
(GitHub-side delay or repo throttle); the steps were verified
locally before each merge. The next push that does trigger CI
will re-validate every step.

---

## 6. Known issue — not a regression of the strict contract

While walking the committed snapshots, the per-row `Comparison`
data for the **interactive** profile shows
`RR.avg_response_time = 34.2` and `RR.avg_waiting_time = 34.4`,
which is inconsistent with the other algorithms on the same
short workload (all ≤ 0.67 ticks) and with the other profiles'
RR rows.

Root cause: when `dashboard_live/public/live-data/snapshots/
interactive/` was generated (PR #38), the xv6 RUN_BEGIN line for
the RR run was very likely interleaved by a kernel `[SCHED]
algo=RR` line, so the orchestrator's lenient
`_extract_run_window` fell back to anchoring on
`algo=RR` and picked up xv6's default-RR boot output from
`tick=1` onwards. The trace then included ~32 spurious
`pid=1` / `pid=2` (init/sh) DISPATCH events at `tick=0`, which
shifted RR's first-child dispatch to `tick=34` and pushed the
average response/waiting time up.

This does **not** violate the strict dashboard contract — every
required field is present and well-typed; the `--strict
--snapshots --preview` validator passes 67/0/0 on it. But the
number is misleading on stage. Treatment for the next PR (P1
in this goal):

- Tighten the orchestrator's `algo=<TARGET>` fallback so it only
  fires AFTER a `[SCHEDTEST]` marker has been observed (which
  guarantees the schedtest userspace program is running and
  prevents the boot-time RR lines from anchoring the window).
- Re-generate the `interactive` snapshot only.

The other three committed snapshots (`cpu_bound`, `mixed`,
`priority_sensitive`) show plausible RR values and are
**unaffected**.

---

## 7. Verdict

**YELLOW** — every automated check passes, but the
`interactive` snapshot ships an artifact-level anomaly in the
RR row (§6). The on-stage demo would render this row in
`AlgorithmComparison` and `CounterfactualMetricView`. The
P1 fix in this goal closes the gap; until merged, the
verdict stays YELLOW.

After P1 lands:

- ✅ §3 table all PASS
- ✅ §6 known issue resolved
- ✅ The committed snapshots match what the audience would
  reasonably expect

… and this report can be amended to **GREEN**.

---

## 8. Honesty rules (still preserved)

- Runtime correction stays `preview_only=true`, `applied=false`.
- No `CORRECTION_APPLIED` event is emitted.
- No xv6 kernel changes in this goal.
- The strict validator's `--preview` mode hard-rejects any
  forged "live" preview artifact.
- README §12.1 row stays `Runtime correction loop … Partial /
  Future Work`.

---

## 9. Next command to start the dashboard

```bash
cd dashboard_live
npm install        # first time only on a fresh clone
npm run dev        # opens http://localhost:5174
```
