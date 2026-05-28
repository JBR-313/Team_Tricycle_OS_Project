# Final Demo Acceptance

This document is the **release-candidate acceptance contract** for the final
demo. If every check below is green on the machine you are about to demo
from, the demo is ready. If any check fails, fix it before walking on stage.

> See `docs/demo_runbook.md` for the on-stage cheat sheet and
> `docs/implementation_status.md` for honest per-feature status. Do not move
> this checklist; it is the authoritative pass/fail contract.

## 0. Validation scope (what counts and what doesn't)

There are three layers of validation in this repo. Read this section
once before running anything.

| Layer | Tool | What it really proves |
|-------|------|------------------------|
| **A. Local final demo check** (this document) | `python3 scripts/final_demo_check.py` | **Authoritative on-stage release contract.** Runs the real xv6 backend with `--seed 42 --workload interactive --run-all`, then strict-validates the live-data. Green here ⇔ the on-stage demo is ready. |
| **B. Local multi-profile check** | `python3 scripts/multi_profile_demo_check.py` | Broader pre-demo confidence. Re-runs the xv6 orchestrator + strict validator across every curated `XV6_PROFILES` workload (`interactive`, `cpu_bound`, `mixed`, `priority_sensitive`). **Not a substitute for layer A** — the on-stage path stays `interactive` / seed=42. Use this to catch profile-specific regressions before demo day. |
| **C. GitHub Actions CI** (`.github/workflows/ci.yml`) | runs on every PR / push to `main` | **Lightweight only.** `py_compile`, the strict contract validator against the committed live-data, and the two `npm run build`s. **Does not run QEMU or xv6** — GitHub-hosted runners have no riscv64 toolchain and a real boot per algorithm is too brittle/expensive for CI. Green CI does not mean a real demo will run; the local layer A is still required. |

On demo day, only layer A is on the critical path. Layers B and C are
defense in depth.

**xv6 profile coverage** — as of the last audit (`docs/xv6_profile_support.md`),
all four curated xv6 profiles (`interactive`, `cpu_bound`, `mixed`,
`priority_sensitive`) pass layer B end-to-end. `short_jobs` and
`starvation_risk` are simulator-only by design and are SKIPPED, not
substituted, by the multi-profile checker.

---

## 1. Pre-demo sanity script (one command)

The single command that runs every acceptance check below in order and
bails on the first failure:

```bash
python3 scripts/final_demo_check.py
```

Expected last lines on success:

```
[OK] All pre-demo checks passed.

  Dashboard data is from the xv6 backend (final demo path).

Next step (run in another terminal — the script will NOT auto-open):
  cd dashboard_live && npm run dev
```

The rest of this document spells out each stage of that script plus the
two frontend builds the script does not run (`npm run build`).

---

## 2. Acceptance checks (exact commands)

Run from the repository root. Each command must exit 0.

| # | Command | Purpose |
|---|---------|---------|
| 1 | `python3 -m py_compile tools/*.py scripts/*.py` | catch syntax / import errors in every Python module |
| 2 | `python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all` | run the **real xv6 backend** end to end (kernel build + QEMU + 6 algorithms + metrics + publish) |
| 3 | `python3 tools/validate_dashboard_contract.py --strict --dir dashboard_live/public/live-data` | refuse to ship live-data missing required fields, with cross-file algo disagreement, or with any empty trace |
| 4 | `cd dashboard_live && npm run build` | production build of the primary generated-data dashboard |
| 5 | `cd dashboard_test && npm run build` | production build of the static UI lab |

A green run of `scripts/final_demo_check.py` covers checks 1–3
automatically and prints the next-step line for the dashboard.

---

## 3. Expected live-data state after check 2

After the orchestrator finishes, `dashboard_live/public/live-data/`
must contain:

- `manifest.json` with at least:
  - `backend == "xv6"` (the **honesty** signal)
  - `mode == "xv6-log"`
  - `seed == 42`
  - `workload == "interactive_heavy"` (the resolved file stem)
  - `workload_type == "interactive"`
  - `llm_selected_algorithm` and `recommended_algorithm` set (typically
    `MLFQ` for the interactive workload; depends on the Solar Pro 3
    recommendation — the demo fallback also selects MLFQ)
  - `algorithms_executed` listing all six canonical algorithms in run
    order (LLM-selected first, then `RR, FCFS, Priority, MLFQ, SJF, SRTF`
    minus the selected one)
  - `version` strictly greater than the previous run's `version`
  - `generated_at` is an ISO-8601 UTC timestamp
  - `orchestrator_version` present
- `metrics.json` with:
  - `scheduling_algorithm` == the LLM-selected algorithm
  - `judgment` ∈ {`SUCCESS`, `NEAR-SUCCESS`, `FAIL`, `UNKNOWN`} — the
    expected value for the **interactive / seed=42** demo is `SUCCESS`
    with `regret_score == 0.0` when the LLM picks MLFQ (currently the
    case; verify it matches your actual run)
  - `comparison` — a dict with all six canonical algorithms; every row
    carries `avg_waiting_time, avg_response_time, avg_turnaround_time,
    throughput, max_waiting_time, preemption_count, starvation_occurred,
    judgment`
- `recommendation.json` and `guard_decision.json` agreeing on the same
  algorithm as `manifest.llm_selected_algorithm` (the validator cross-
  checks this)
- Six `trace_<algo>.jsonl` files, every one non-empty and carrying at
  least one `EXIT` event (the validator flags empty traces)

Reference output from a representative run (interactive / seed=42)
recorded on 2026-05-26 against main `edc392f`:

| Algo     | avg_response_time | Judge   |
|----------|-------------------|---------|
| MLFQ     | 0.0 – 0.2         | SUCCESS (selected, regret 0.0) |
| RR       | 0.2 – 0.33        | SUCCESS |
| FCFS     | 0.2 – 0.4         | SUCCESS |
| SJF      | 0.4               | SUCCESS |
| SRTF     | 0.5               | SUCCESS |
| Priority | 0.5 – 0.67        | SUCCESS or FAIL (depends on whether the gap exceeds the 0.5-tick judgment floor) |

Sub-tick variation across runs is expected — xv6 traces are tick-
granular and ~30–80 events per algorithm. The judgment is stable
because the absolute floor (`JUDGMENT_ABS_FLOOR = 0.5` in both
`scripts/orchestrator.py` and `dashboard_live/src/data/schemaCompat.js`)
treats sub-tick differences as `SUCCESS`.

---

## 4. Things this acceptance does NOT cover

These are intentionally **not** part of the green-light contract. They
are documented limitations, not regressions:

- **Runtime correction loop** (`event_detector.py` → proposer → LLM →
  guard re-check → apply → `CORRECTION_APPLIED`) — Partial / Future
  Work. Only event detection exists today.
- **Live streaming** — the dashboard polls `manifest.json`; there is no
  websocket push channel.
- **Solar Pro 3 API key** — if `.env` is missing or the API call fails,
  the orchestrator falls back to `outputs/_demo_fixtures/recommendation.json` and
  stamps `metadata_source=demo_fallback`. The dashboard then shows
  `Backend: FALLBACK` instead of `XV6 TRACE`. This is intended honesty,
  not a bug; a real on-stage demo should not show `FALLBACK`.
- **xv6 traces are short, educational traces** — 5 children per curated
  profile, ~30–80 events per algorithm. The starvation and judgment
  rules apply an absolute tick floor so sub-tick noise is not flagged.

---

## 5. If a check fails

1. Read the failure message — `final_demo_check.py` bails on the first
   non-zero stage, so you only need to fix one thing at a time.
2. Common gotchas:
   - QEMU / `riscv64-unknown-elf-gcc` not installed on the demo machine.
   - Solar API key missing → orchestrator falls back to demo
     recommendation → manifest shows `metadata_source=demo_fallback`
     and dashboard badges `FALLBACK`. Acceptable only if you announce
     it explicitly during the demo.
   - Stale `node_modules` after a fresh clone — run `npm install` in
     `dashboard_live/` and `dashboard_test/`.
3. If a real bug surfaces, fix it via the normal one-PR-one-fix loop —
   do not work around it locally on demo day.

---

## 6. Sign-off

The release is ready to demo when:

- [ ] `scripts/final_demo_check.py` exits 0.
- [ ] `cd dashboard_live && npm run build` exits 0.
- [ ] `cd dashboard_test && npm run build` exits 0.
- [ ] `dashboard_live` opens, header shows `Backend: XV6 TRACE`, all
      six algorithm tabs render a Gantt, the comparison table shows
      `Judge` values consistent with the metrics described in §3.
