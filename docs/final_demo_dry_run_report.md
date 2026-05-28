# Final Demo Dry-Run Report

A point-in-time record of one clean-main rehearsal of the demo. Use
this as evidence that the release candidate is green; rerun the same
commands on the actual demo machine before walking on stage.

> See `docs/final_demo_acceptance.md` for the per-check contract,
> `docs/demo_checklist.md` for the on-stage cheat sheet, and
> `docs/presentation_defense_notes.md` for audience Q&A.

---

## Run metadata

| Field | Value |
|-------|-------|
| Date / time (UTC) | 2026-05-26 06:34:50Z |
| Branch | `main` (origin/main fast-forwarded) |
| Head | `8a1eeae` — `chore(hygiene): defensive .gitignore patterns for the demo release (#23)` |
| Host | WSL2 (Linux 6.6.87.2), `qemu-system-riscv64`, `riscv64-unknown-elf-gcc` |
| Backend used | xv6 (final demo path) |

---

## Commands run

In order, each from the repository root:

```bash
git fetch origin
git checkout main
git pull origin main

# Three fail-fast stages in one wrapper:
python3 scripts/final_demo_check.py
#   stage 1: py_compile tools/*.py scripts/*.py
#   stage 2: scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all
#   stage 3: tools/validate_dashboard_contract.py --strict --dir dashboard_live/public/live-data

cd dashboard_live && npm run build
cd ../dashboard_test && npm run build
```

---

## Pass / fail table

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | `python3 -m py_compile tools/*.py scripts/*.py` | **PASS** | exit 0 |
| 2 | `python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all` | **PASS** | `[DONE] Orchestrator pipeline complete.` |
| 3 | `python3 tools/validate_dashboard_contract.py --strict --dir dashboard_live/public/live-data` | **PASS** | 13 OK, 0 WARN, 0 ERROR; manifest cross-check on MLFQ |
| 4 | `cd dashboard_live && npm run build` | **PASS** | 175.36 KB JS / 55.48 KB gzip |
| 5 | `cd dashboard_test && npm run build` | **PASS** | 224.43 KB JS / 63.46 KB gzip |

`scripts/final_demo_check.py` exited 0 and printed:

```
[OK] All pre-demo checks passed.
  Dashboard data is from the xv6 backend (final demo path).
Next step (run in another terminal — the script will NOT auto-open):
  cd dashboard_live && npm run dev
```

---

## Published live-data snapshot

`dashboard_live/public/live-data/`:

- `manifest.json`
  - `backend: "xv6"`
  - `mode: "xv6-log"`
  - `version: 16`
  - `seed: 42`
  - `workload_type: "interactive"` (`workload: "interactive_heavy"`)
  - `llm_selected_algorithm: "MLFQ"`
  - `algorithms_executed: ["MLFQ", "RR", "FCFS", "Priority", "SJF", "SRTF"]`
  - `generated_at: 2026-05-26T06:35:29Z`
- `recommendation.json` → `MLFQ`
- `guard_decision.json` → `MLFQ`, `guard_result: accepted`
- `metrics.json` top-level: `scheduling_algorithm: "MLFQ"`, `judgment: "SUCCESS"`, `regret_score: 0.0`, `starvation_occurred: False`
- All six `trace_<algo>.jsonl` non-empty, each with 5 `EXIT` events

Comparison block (target metric `avg_response_time`, lower is better):

| Algo     | avg_resp | avg_wait | avg_turn | starvation | Judge   |
|----------|----------|----------|----------|------------|---------|
| MLFQ     | 0.0      | 0.2      | 2.4      | False      | SUCCESS (selected, regret 0.0) |
| Priority | 0.2      | 0.2      | 2.4      | False      | SUCCESS |
| RR       | 0.25     | 0.25     | 2.25     | False      | SUCCESS |
| FCFS     | 0.4      | 0.4      | 2.8      | False      | SUCCESS |
| SJF      | 0.4      | 0.4      | 2.8      | False      | SUCCESS |
| SRTF     | 0.4      | 0.4      | 2.8      | False      | SUCCESS |

All six rows pass the absolute-floor regret rule (`JUDGMENT_ABS_FLOOR =
0.5`) because every gap from the best (MLFQ=0.0) sits inside one tick.
This is the expected behaviour on the short interactive workload —
see `docs/final_demo_acceptance.md` §3.

---

## Limitations to mention on stage (honest)

- **No websocket streaming.** The dashboard polls `manifest.json`.
- **Runtime correction loop is partial.** Only `tools/event_detector.py`
  exists today; the propose / LLM / guard re-check / apply /
  `CORRECTION_APPLIED` steps are intentional **Future Work**. Do not
  claim closed-loop runtime correction.
- **Solar Pro 3 API fallback.** Without `.env`, the orchestrator falls
  back to `outputs/_demo_fixtures/recommendation.json` and stamps
  `metadata_source=demo_fallback`. The dashboard then shows
  `Backend: FALLBACK`. This dry-run did not exhibit fallback; the LLM
  picked MLFQ on its own.
- **xv6 traces are short educational traces.** ~30–80 events per
  algorithm, 5 children per profile. The starvation rule
  (`MIN_STARVATION_WAIT_TICKS = 5` in `tools/metrics.py`) and the
  judgment regret rule (`JUDGMENT_ABS_FLOOR = 0.5` in both
  `scripts/orchestrator.py` and
  `dashboard_live/src/data/schemaCompat.js`) apply an absolute tick
  floor so sub-tick noise does not falsely flag starvation or `FAIL`.
- **Kernel/user printf interleave.** Recovered by the orchestrator's
  lenient `RUN_BEGIN` windowing (substring + `algo=<TARGET>` fallback).
  An empty trace would be caught by the strict contract validator.

---

## Exact command to start the dashboard on demo day

After `scripts/final_demo_check.py` passes:

```bash
cd dashboard_live
npm install        # first time only on a fresh clone
npm run dev        # opens http://localhost:5174
```

Then walk the dashboard per `docs/demo_checklist.md` §C and answer
audience questions using `docs/presentation_defense_notes.md`.

---

## Verdict

The release candidate is **GREEN** for the demo as of the timestamp
above. Repeat this dry run on the actual demo machine immediately
before the show.
