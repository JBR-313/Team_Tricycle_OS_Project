# Repository Cleanup Plan — Final-Demo Hardening

> **Scope:** Classify every top-level path in the repo as one of
> `KEEP-PRIMARY` / `KEEP-FALLBACK` / `KEEP-DEV` / `LEGACY` / `BUILD-OUTPUT`
> / `MOVE` for the final-demo window. **No file is deleted in this PR.**
> Only labels and (when safe) directory moves are proposed.
>
> Status: 2026-05-28, branch `feat/upstage-runtime-strict`.
> Companion docs: `docs/implementation_status.md`,
> `docs/sjf_srtf_prediction_audit.md`, `docs/workload_coverage_matrix.md`.

---

## 1. Principles

1. **xv6 + QEMU is the primary path.** Anything not on that path must be
   labelled `KEEP-FALLBACK` (still ships, audience-visible) or `KEEP-DEV`
   (ships, not audience-visible) or `LEGACY` (ships, marked deprecated).
2. **Delete nothing before the demo.** Late-stage deletions are how demos
   break. Renames and README labels are reversible; `rm` is not.
3. **Build outputs go to `outputs/` or `.gitignored`** — never into a
   tracked source path.
4. **One README sentence per major directory.** If a directory's purpose
   can't be expressed in one sentence, that's a sign it needs splitting,
   not adding to.

---

## 2. Status legend

| Label | Meaning | Audience-visible? | Deletable post-demo? |
|---|---|---|---|
| `KEEP-PRIMARY` | On the final demo execution path. | yes | no |
| `KEEP-FALLBACK` | Used when the primary path is unavailable (no QEMU / no API key). | yes (with a “fallback” badge) | no |
| `KEEP-DEV` | Used by developers; not on the demo path. | no | reconsider in 1 quarter |
| `LEGACY` | Superseded but kept for safety. | no | yes (after one PR cycle marking deprecated) |
| `BUILD-OUTPUT` | Generated artifacts. | no | yes (regeneratable) |
| `MOVE` | Should be moved to a clearer location. | depends | no |

---

## 3. Top-level inventory

| Path | Label | Final-demo necessary? | Notes |
|---|---|---|---|
| `README.md` | KEEP-PRIMARY | yes | Will be updated in this PR to make `xv6+QEMU = primary` explicit. |
| `CLAUDE.md` | KEEP-DEV | no (developer-facing) | Project rules; keep at root. |
| `architecture_diagram.md` | KEEP-PRIMARY | yes | Audience may be shown this. |
| `requirements.txt` | KEEP-PRIMARY | yes | Stdlib-only runtime; pinned dev deps. |
| `.env.example` | KEEP-PRIMARY | yes | Onboarding. |
| `.env` | KEEP-PRIMARY (local only) | yes (server-side) | Must never be committed; covered by `.gitignore`. |
| `.gitignore` | KEEP-PRIMARY | yes | |
| `.github/` | KEEP-PRIMARY | yes | CI smoke + validator. |
| `.agents/`, `.codex/`, `.claude/` | KEEP-DEV | no | IDE/agent config; harmless but invisible to demo. |
| `tools/` | KEEP-PRIMARY | yes | All host-side modules. |
| `scripts/` | KEEP-PRIMARY | yes | Orchestrator + demo checks + snapshot export. |
| `xv6-riscv/` | KEEP-PRIMARY | yes | Kernel source, `schedtest`, syscalls. |
| `workloads/` | KEEP-PRIMARY | yes | Curated JSON workloads. |
| `dashboard_live/` | KEEP-PRIMARY | yes | Final-demo UI. |
| `dashboard_test/` | KEEP-FALLBACK (UI sandbox label) | no (for the audience) | Reclassify in README to “UI prototype/sandbox.” |
| `dashboard/` (Streamlit) | LEGACY | no | Mark deprecated in §6.4; archive plan below. |
| `xv6-style-scheduler/` (simulator copy) | KEEP-DEV → MOVE | no | This is a *separate* simulator copy from `tools/scheduler_simulator.py`; should move to `xv6-style-scheduler/` → `dev/xv6-style-scheduler/` or be merged with the canonical one. See §5. |
| `outputs/` | BUILD-OUTPUT | no | `outputs/*` is gitignored, with an explicit `!outputs/_demo_fixtures/` exception for the committed offline-fallback fixture set. |
| `traces/` (root) | LEGACY | no | Pre-orchestrator-refactor trace samples (`mixed_rr.jsonl`, `starvation_sjf.jsonl`, …). Mark deprecated; the canonical traces now live in `outputs/_demo_fixtures/` and `dashboard_live/public/live-data/snapshots/`. |
| `docs/` | KEEP-PRIMARY | yes | Already organized; this PR adds 5 new audits. |
| `.venv/` | BUILD-OUTPUT | no | `.gitignore`d. |

---

## 4. Per-module file-level audit

### 4.1 `tools/` — all KEEP-PRIMARY

| File | Role | Comment |
|---|---|---|
| `workload_analyzer.py` | Stage 2 | — |
| `llm_advisor.py` | Stage 3 | — |
| `solar_client.py` | LLM client | — |
| `algorithm_guard.py` | Stage 4 | — |
| `scheduler_simulator.py` | Stage 5b (fallback) | Reclassify to `KEEP-FALLBACK`; not on the primary demo path. |
| `trace_parser.py` | Stage 6 | — |
| `metrics.py` | Stage 7 | — |
| `event_detector.py` | Stage 8 | — |
| `correction_proposer.py` | Stage 9 (PREVIEW) | Keep banner: preview-only. |
| `correction_guard.py` | Stage 10 (PREVIEW) | Keep banner: preview-only. |
| `trace_explainer.py` | Stage 11 | — |
| `schema_compat.py` | normalizer | — |
| `validate_dashboard_contract.py` | CI gate | — |

### 4.2 `scripts/` — all KEEP-PRIMARY

| File | Role |
|---|---|
| `orchestrator.py` | host control plane (primary). |
| `final_demo_check.py` | pre-demo smoke (primary). |
| `multi_profile_demo_check.py` | 4-profile sweep (primary). |
| `export_profile_snapshots.py` | snapshot publish (primary). |
| `analyze_algorithm_winners.py` | algorithm-diversity audit (KEEP-DEV). |
| `correction_preview_smoke.py` | offline preview smoke (KEEP-DEV / CI). |
| `run_live_dashboard_pipeline.py` | thin runner — 10-line shim. |
| `check_xv6_scheduler.sh` | quick smoke on xv6 build (KEEP-DEV). |

### 4.3 `xv6-riscv/`

All `KEEP-PRIMARY`. The only review item is that `xv6-riscv/kernel/` and
`xv6-riscv/user/` ship `.asm` / `.d` / `.o` / `.sym` files. These should not
be tracked: add them to `.gitignore` in a separate cleanup PR (post-demo).

| Pattern | Today | Should be |
|---|---|---|
| `xv6-riscv/**/*.o`, `*.d`, `*.asm`, `*.sym` | tracked | ignored (post-demo) |

### 4.4 `workloads/`

All `KEEP-PRIMARY`. `docs/workload_coverage_matrix.md` proposes four new
files (`pure_batch`, `short_burst_cluster`, `bursty_long_tail`,
`priority_critical`) — those should be added under `workloads/` with no
restructuring.

### 4.5 `dashboard_live/`

`KEEP-PRIMARY`. Sub-paths:

| Path | Label | Note |
|---|---|---|
| `dashboard_live/src/components/*.jsx` | KEEP-PRIMARY | 17 components — all used. |
| `dashboard_live/public/live-data/` | KEEP-PRIMARY | Demo data; snapshots ship in git. |
| `dashboard_live/dist/` | BUILD-OUTPUT | Generated by `npm run build`; should be gitignored if not already. |
| `dashboard_live/dist/live-data/` | BUILD-OUTPUT | Same. |

### 4.6 `dashboard_test/`

Reclassify to `KEEP-FALLBACK (UI prototype/sandbox)`. README + the app's
own header should make it clear this is not real scheduling output. No file
moves.

### 4.7 `dashboard/` (Streamlit)

`LEGACY` — see §6.4.

### 4.8 `xv6-style-scheduler/`

This directory contains `simulator/simulator.py` (516 lines) — **a separate
simulator** from `tools/scheduler_simulator.py` (484 lines). Two simulators
is a smell.

| Decision | Action |
|---|---|
| `xv6-style-scheduler/simulator/simulator.py` | KEEP-DEV; mark in its own README that the canonical fallback is `tools/scheduler_simulator.py`. Post-demo: choose one and remove the other. |

### 4.9 `outputs/` and `traces/`

| Path | Label | Action |
|---|---|---|
| `outputs/_demo_fixtures/*.json,*.jsonl` | KEEP-PRIMARY | Fixture set used by `--offline-fixture`. |
| `outputs/live/*` | BUILD-OUTPUT | Generated; should be in `.gitignore` (currently `outputs/` is). |
| `outputs/build_*.log`, `outputs/check_xv6_scheduler_*.log`, `outputs/xv6_raw_*_seed42.log` | BUILD-OUTPUT | gitignored; surviving copies are useful past evidence — leave them. |
| `traces/` (root) | LEGACY | Mark deprecated in `docs/data_format.md`; do not delete pre-demo. |

---

## 5. Concrete labelling table for the README

The README will gain a “**Final-Demo Path** vs **Fallback** vs **Legacy**”
table built from this plan:

| Path | Label in README | One-line |
|---|---|---|
| `xv6-riscv/` + `scripts/orchestrator.py --backend xv6` | **PRIMARY** | Real xv6 + QEMU execution via `schedtest`. |
| `tools/scheduler_simulator.py` + `scripts/orchestrator.py --backend simulator` | **FALLBACK (dev/test)** | Host-side Python model. **Not** proof of real xv6. |
| `dashboard_live/` | **PRIMARY** | Live observability dashboard. |
| `dashboard_test/` | **FALLBACK (UI prototype/sandbox)** | Static fixture data for UI iteration. |
| `dashboard/` (Streamlit) | **LEGACY** | Superseded by `dashboard_live`; kept for safety. Archive plan in `docs/repo_cleanup_plan.md`. |
| `xv6-style-scheduler/simulator/` | **DEV** | Standalone scheduler study; not on the demo path. |
| `traces/` (root) | **LEGACY** | Pre-orchestrator trace samples. Use `outputs/_demo_fixtures/` for the canonical fixtures. |

---

## 6. Post-demo cleanup queue (do NOT touch before the demo)

### 6.1 Move `.asm`/`.d`/`.o`/`.sym` out of git

`git rm --cached` the existing tracked binaries; add a `.gitignore` clause
in `xv6-riscv/`. Schedule for the **first PR after the demo**.

### 6.2 Rename `outputs/demo/` → `outputs/_demo_fixtures/` — **DONE**

“`outputs/demo/`” read as “build output of `demo`”, but it was curated
fixture data. The directory is now `outputs/_demo_fixtures/`, committed
to git via a `.gitignore` `!outputs/_demo_fixtures/` exception so the
offline fallback works from a fresh checkout. README and orchestrator
constants updated to match.

### 6.3 Pick one simulator

Either:
- merge `xv6-style-scheduler/simulator/simulator.py` into
  `tools/scheduler_simulator.py` and delete the separate directory, or
- keep `xv6-style-scheduler/` as a study sandbox and remove
  `tools/scheduler_simulator.py` (no — the host pipeline depends on the
  `tools/` one).

The former is the only realistic answer; tag the work as a one-PR cleanup.

### 6.4 Archive plan for `dashboard/` (Streamlit)

Two-step archive:

1. **Now (in this PR):** add a banner to `dashboard/dashboard.py`'s
   top-of-file docstring: `"""LEGACY — use dashboard_live/. This file is
   retained for the audit trail and the Streamlit fallback only."""`
   Plus a one-paragraph note in README §9.
2. **2 weeks post-demo:** `git mv dashboard/ legacy/dashboard/` and add
   `legacy/` to `.gitignore`'s “tracked but excluded from CI” list. Do not
   delete — the Streamlit dashboard is the only host-only fallback for an
   environment without Node.

### 6.5 Decide on `traces/` (root)

Either delete or move to `outputs/legacy_traces/`. Either choice is fine
post-demo; pre-demo, leave it alone.

---

## 7. What this PR actually changes

| Change | Scope |
|---|---|
| Add the 5 new audit/design docs (this file + the four others). | docs only |
| Update `README.md` to mark PRIMARY / FALLBACK / LEGACY paths explicitly. | docs only |
| **No file deletes, no file moves, no source edits to `tools/`, `scripts/`, `xv6-riscv/`, `dashboard_*/`.** | — |

All risky cleanup (file removals, dir renames, deprecation moves) is
deferred to post-demo, with the plan above as the queue.
