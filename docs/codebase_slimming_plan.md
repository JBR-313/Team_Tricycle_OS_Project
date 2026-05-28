# Codebase Slimming Plan — Visual Scheduler Final Demo

> **Source of truth:** `docs/final_demo_slimming_request.md`.
> **Companion docs:** `docs/repo_cleanup_plan.md` (label conventions),
> `docs/final_slimming_smoke_check.md` (post-cleanup verification),
> `docs/final_demo_hardening_index.md` (audit bundle).
> **Status:** 2026-05-28, branch `feat/upstage-runtime-strict`.
>
> **Operating rule for this PR:** classify and label; do not delete; only
> move files when the move is trivially safe (no Python imports, no
> dashboard fetch paths, no shipped fixture references).

---

## 0. One-page goal

```
xv6-primary LLM-assisted scheduling system
        ↑
Workload → Workload Analyzer → LLM Advisor → Algorithm Guard
        → xv6 + QEMU → Trace Parser → Metrics Evaluator → dashboard_live
```

Everything in the repo is classified against that path: **CORE** if it's
on the path, **DEV/FALLBACK** if it supports the path but isn't on it,
**LEGACY** if it has been replaced, **ARCHIVE-CANDIDATE** if it should leave
the main tree post-demo, and **FUTURE-WORK** if it's designed/previewed but
not closed-loop.

---

## 1. Categories used

| Category | Meaning | Demo-day visible? | Risk to move/delete |
|---|---|---|---|
| **CORE** | On the final demo path. | yes | high — do not touch |
| **DEV / FALLBACK** | Supports the path but not on it (UI sandbox, smoke checks, simulator fallback). | sometimes (badge says so) | medium — labels OK, moves later |
| **LEGACY** | Older path superseded by current core. | no | low — mark deprecated |
| **ARCHIVE-CANDIDATE** | Useful history; should leave main tree post-demo. | no | low — move to `archive/` post-demo |
| **FUTURE-WORK** | Designed/previewed but not closed-loop. | preview only, with banner | medium — labels critical |

---

## 2. Path classification table

> The Risk column captures *what would break* if the row were moved or
> deleted. Rows with risk ≥ medium are KEEP for this PR.

### 2.1 Repository root

| Path | Category | Current Role | Keep / Move / Archive | Reason | Risk |
|---|---|---|---|---|---|
| `README.md` | CORE | Project entry point. | KEEP | Required for demo. | high if broken. |
| `CLAUDE.md` | DEV | Project rules for the coding agent. | KEEP | Developer-facing only. | none. |
| `architecture_diagram.md` | CORE | Architecture reference. | KEEP | Audience may see this. | none. |
| `requirements.txt` | CORE | Pinned runtime + dev deps. | KEEP | Stdlib-only runtime depends on this contract. | high. |
| `.env.example` | CORE | Onboarding template. | KEEP | Required. | none. |
| `.env` | CORE (local only) | Real API key holder. | KEEP, never commit. | Pipeline depends. | n/a. |
| `.gitignore` | CORE | Credential / output guard. | KEEP. | Safety. | high. |
| `.github/workflows/` | CORE | Lightweight CI smoke. | KEEP. | Demo evidence. | medium. |
| `.agents/`, `.claude/`, `.codex/` | DEV | IDE/agent config. | KEEP. | Invisible to demo. | none. |
| `.venv/` | BUILD-OUTPUT | Local Python env. | gitignored already. | — | — |

### 2.2 `tools/`

| Path | Category | Current Role | Keep / Move / Archive | Reason | Risk |
|---|---|---|---|---|---|
| `tools/workload_analyzer.py` | CORE | Stage 2 of pipeline. | KEEP. | On demo path. | high. |
| `tools/llm_advisor.py` | CORE | Stage 3 (advisor + feedback). | KEEP. | On demo path. | high. |
| `tools/solar_client.py` | CORE | Upstage Solar Pro 3 client. | KEEP. | On demo path. | high. |
| `tools/algorithm_guard.py` | CORE (protected) | Stage 4. | KEEP. | On demo path; protected list. | high. |
| `tools/schema_compat.py` | CORE | Normalizer used by orchestrator/metrics. | KEEP. | Import-critical. | high. |
| `tools/trace_parser.py` | CORE (protected) | Stage 6. | KEEP. | On demo path. | high. |
| `tools/metrics.py` | CORE (protected) | Stage 7 + judgment. | KEEP. | On demo path. | high. |
| `tools/trace_explainer.py` | CORE | Stage 11 (Solar Pro 3 explanation). | KEEP. | Dashboard `LLMExplanation` depends. | medium. |
| `tools/scheduler_simulator.py` | DEV / FALLBACK | Host-side simulator for dev + `--backend simulator` fallback. | **KEEP (downgrade label)**. | Used by `orchestrator.py` fallback path and demo-safety. | medium — referenced by tests / orchestrator import. |
| `tools/event_detector.py` | FUTURE-WORK (used in preview path) | Detects starvation / low-throughput / high-preempt / high-RT. | KEEP. | Drives the preview-only correction loop. | medium. |
| `tools/correction_proposer.py` | FUTURE-WORK (PREVIEW ONLY) | Deterministic rule table → `correction_proposal.json` (preview). | KEEP, banner already present. | Source already labels `PREVIEW ONLY`. | medium. |
| `tools/correction_guard.py` | FUTURE-WORK (PREVIEW ONLY) | Re-validates the preview proposal. | KEEP, banner already present. | Source already labels `PREVIEW ONLY`. | medium. |
| `tools/validate_dashboard_contract.py` | DEV (gating) | CI / pre-demo contract check. | KEEP. | Demo prep depends on it. | medium. |
| `tools/__init__.py`, `tools/README.md` | CORE | Package marker + dev doc. | KEEP. | none. | none. |

### 2.3 `scripts/`

| Path | Category | Current Role | Keep / Move / Archive | Reason | Risk |
|---|---|---|---|---|---|
| `scripts/orchestrator.py` | CORE | Host control plane. | KEEP. | Demo path entry. | high. |
| `scripts/final_demo_check.py` | CORE | One-command demo prep. | KEEP. | Demo prep. | high. |
| `scripts/multi_profile_demo_check.py` | DEV / FALLBACK | 4-profile sweep. | KEEP. | Useful for pre-demo confidence. | low. |
| `scripts/export_profile_snapshots.py` | CORE | Publishes per-profile snapshots. | KEEP. | Snapshot selector depends. | medium. |
| `scripts/analyze_algorithm_winners.py` | DEV | Offline diversity verifier. | KEEP. | Not on demo path. | low. |
| `scripts/correction_preview_smoke.py` | DEV (preview) | Offline preview smoke (no xv6). | KEEP. | CI uses it. | medium. |
| `scripts/run_live_dashboard_pipeline.py` | LEGACY (shim) | Deprecated; redirects to orchestrator. | KEEP for one release; mark deprecated in header. | Some docs/links may still call it. | low. |
| `scripts/check_xv6_scheduler.sh` | DEV | Quick xv6 build smoke. | KEEP. | Useful during cleanup. | low. |

### 2.4 `xv6-riscv/` (protected)

| Path | Category | Current Role | Keep / Move / Archive | Reason | Risk |
|---|---|---|---|---|---|
| `xv6-riscv/kernel/proc.c` | CORE (protected) | 6 schedulers + predictor + traces + syscalls. | KEEP, **do not refactor for aesthetics**. | OS core. | very high. |
| `xv6-riscv/kernel/sysproc.c`, `syscall.c` | CORE | `setscheduler` / `getscheduler` wiring. | KEEP. | OS core. | very high. |
| `xv6-riscv/user/schedtest.c` | CORE | curated profile driver. | KEEP. | OS core. | very high. |
| `xv6-riscv/**/*.o`, `*.d`, `*.asm`, `*.sym` | BUILD-OUTPUT | Tracked binaries (should not be). | leave for the demo; gitignore + `git rm --cached` post-demo. | Avoid touching kernel build path right now. | medium during PR — high if mistimed. |
| `xv6-riscv/mkfs/`, `fs.img`, etc. | CORE | xv6 build system. | KEEP. | OS core. | very high. |

### 2.5 `workloads/`

| Path | Category | Current Role | Keep / Move / Archive | Reason | Risk |
|---|---|---|---|---|---|
| `workloads/*.json` (6 files) | CORE | Curated workloads. | KEEP. | Pipeline + audits depend. | high. |
| (proposed new profiles from `workload_coverage_matrix.md` §3) | CORE (when added) | Algorithm-diversity workloads. | ADD when implemented; no-op for this PR. | Coverage gap. | low. |

### 2.6 Dashboards

| Path | Category | Current Role | Keep / Move / Archive | Reason | Risk |
|---|---|---|---|---|---|
| `dashboard_live/` | CORE | Final demo UI. | KEEP. | Demo path. | very high. |
| `dashboard_live/public/live-data/` | CORE | Generated + committed snapshots. | KEEP. | Demo path. | high. |
| `dashboard_live/dist/` | BUILD-OUTPUT | `npm run build` output. | gitignore post-demo. | Regeneratable. | low. |
| `dashboard_test/` | DEV / FALLBACK (UI sandbox) | Static fixtures, no real scheduling output. | **KEEP, label as sandbox**. Move to `archive/dashboard_test/` post-demo. | Today's role is UI prototype; not on demo path. | medium — independent app, no shared imports. |
| `dashboard_test/dist/` | BUILD-OUTPUT | `npm run build`. | gitignore. | Regeneratable. | low. |
| `dashboard/` (Streamlit) | LEGACY | Superseded by `dashboard_live`. | KEEP for host-only fallback; archive post-demo per `repo_cleanup_plan.md` §6.4. | One audit cycle marks it before move. | low. |

### 2.7 `xv6-style-scheduler/` (separate simulator copy)

| Path | Category | Current Role | Keep / Move / Archive | Reason | Risk |
|---|---|---|---|---|---|
| `xv6-style-scheduler/simulator/simulator.py` | DEV (duplicate of `tools/scheduler_simulator.py`) | Standalone scheduler study (516 lines). | **KEEP, mark as DEV study sandbox**. Post-demo: merge into `tools/scheduler_simulator.py` or move to `archive/`. | Two simulators is a smell; not used by the orchestrator. | low — independent file. |

### 2.8 `outputs/`

| Path | Category | Current Role | Keep / Move / Archive | Reason | Risk |
|---|---|---|---|---|---|
| `outputs/_demo_fixtures/*.json,*.jsonl` | CORE | Committed fallback fixtures (`--offline-fixture`). | KEEP. | Demo safety net. | high. |
| `outputs/live/*` | BUILD-OUTPUT | Generated by orchestrator runs. | already gitignored; do not track. | Regeneratable. | low. |
| `outputs/*.log`, `outputs/xv6_raw_*` | BUILD-OUTPUT | Past run evidence. | already gitignored. | Reproducible. | low. |
| `outputs/workload_summary.json` (root of outputs) | BUILD-OUTPUT | Last analyzer run. | gitignored; ignore. | Reproducible. | low. |

### 2.9 `traces/` (root)

| Path | Category | Current Role | Keep / Move / Archive | Reason | Risk |
|---|---|---|---|---|---|
| `traces/*.jsonl` | LEGACY | Pre-orchestrator trace samples. | KEEP for now; mark deprecated in `docs/data_format.md`; move to `archive/traces/` post-demo. | Canonical traces now live in `outputs/_demo_fixtures/` and `live-data/snapshots/`. | low — nothing imports these. |

### 2.10 `docs/`

| Path | Category | Current Role | Keep / Move / Archive | Reason | Risk |
|---|---|---|---|---|---|
| `architecture.md`, `architecture_diagram.md` (root) | CORE | Architecture canon. | KEEP. | Demo path. | high. |
| `demo_runbook.md`, `demo_checklist.md`, `presenter_script.md` | CORE | Demo prep. | KEEP. | Demo path. | high. |
| `final_demo_acceptance.md`, `final_release_candidate_report.md` | CORE | RC contract + status. | KEEP. | Demo evidence. | medium. |
| `evaluation_plan.md`, `evaluation_criteria_audit.md`, `evaluation_judgment_bug_analysis.md` | CORE | Evaluator canon. | KEEP. | Defense material. | medium. |
| `implementation_status.md` | CORE | Honest status. | KEEP. | Defense material. | medium. |
| `orchestrator_design.md`, `dashboard_data_contract.md`, `trace_format.md`, `data_format.md` | CORE | Module contracts. | KEEP. | Defense material. | medium. |
| `presentation_defense_notes.md` | CORE | Demo defense. | KEEP. | Demo prep. | medium. |
| `repo_cleanup_plan.md`, `codebase_slimming_plan.md` (this), `final_slimming_smoke_check.md`, `final_demo_hardening_index.md` | CORE (planning) | Slimming/hardening canon. | KEEP. | Defense material. | low. |
| `sjf_srtf_prediction_audit.md`, `workload_coverage_matrix.md`, `mlfq_queue_visualization_review.md`, `dashboard_run_button_design.md`, `algorithm_decision_diversity_audit.md`, `recommendation_evidence_audit.md`, `xv6_profile_support.md` | CORE (audit) | Recent audits. | KEEP. | Defense material. | low. |
| `readme_current_state_audit.md`, `dashboard_live_demo_readability_audit.md`, `runtime_correction_preview_demo_gap.md`, `final_dashboard_manual_qa.md` | ARCHIVE-CANDIDATE | Per-PR audits; useful as history. | KEEP for now; move to `docs/archive/` post-demo. | Useful for grading; not on every demo slide. | low. |
| `runtime_correction_preview_design.md`, `runtime_correction_preview_validation.md`, `counterfactual_metric_view_plan.md`, `profile_snapshot_plan.md`, `work_status_sjf_srtf.md` | ARCHIVE-CANDIDATE (planning) | Per-feature plans. | KEEP for now; move to `docs/archive/plans/` post-demo. | History, not the path. | low. |
| `CHANGELOG_orchestrator_refactor.md` | ARCHIVE-CANDIDATE | One-off changelog. | KEEP; move to `docs/archive/` post-demo. | History. | low. |
| `final_demo_dry_run_report.md` | ARCHIVE-CANDIDATE | Per-day dry run report. | KEEP for now; rotate post-demo. | Will accumulate. | low. |
| `project_progress_report.md`, `project_progress_report.pdf` | ARCHIVE-CANDIDATE | Audit report (from earlier session). | KEEP for now; move to `docs/archive/reports/` post-demo. | Useful for grading. | low. |
| `final_demo_slimming_request.md` | CORE (planning) | This task's source-of-truth. | KEEP. | Reference. | low. |

---

## 3. Duplication review

| Area | Where | Decision (for this PR) | Post-demo |
|---|---|---|---|
| Two simulators: `tools/scheduler_simulator.py` vs `xv6-style-scheduler/simulator/simulator.py` | tools/ + xv6-style-scheduler/ | KEEP both; the `tools/` one is on the fallback path, the other is a DEV study. | Merge or archive the study copy. |
| Two dashboards rendering similar cards: `dashboard_live` vs `dashboard_test` | dashboard_live/ + dashboard_test/ | KEEP both; roles clarified (PRIMARY vs UI-SANDBOX). | Move `dashboard_test/` to `archive/dashboard_test/` if not used for 30 days. |
| Streamlit dashboard vs React dashboard | dashboard/ + dashboard_live/ | KEEP both; Streamlit marked LEGACY in docstring + README. | Move `dashboard/` to `archive/streamlit_dashboard/` per `repo_cleanup_plan.md` §6.4. |
| Schema normalization repeats: `tools/schema_compat.py` + inline normalization in metrics/orchestrator | Multiple files | KEEP. `schema_compat.py` is already the single source; inline calls go through it. | No action. |
| Per-feature audits in `docs/` overlapping with this slimming plan | docs/ | KEEP both; this plan references the per-feature ones, not replaces them. | Move per-PR audits to `docs/archive/` once their PRs land. |

---

## 4. What this PR actually changes

| Change | Path | Risk |
|---|---|---|
| Adds this file. | `docs/codebase_slimming_plan.md` | none |
| Adds smoke-check companion. | `docs/final_slimming_smoke_check.md` | none |
| Adds a prominent **Final Demo Path** block at the very top of README. | `README.md` | none (additive) |
| Adds a one-line LEGACY-shim banner to `scripts/run_live_dashboard_pipeline.py` docstring. | `scripts/run_live_dashboard_pipeline.py` | none (docstring only) |
| Tightens `tools/scheduler_simulator.py` module docstring to “DEV / FALLBACK, not the final backend.” | `tools/scheduler_simulator.py` | none (docstring only) |
| Tightens `tools/event_detector.py` module docstring to explicitly say its output feeds the **preview-only** correction loop. | `tools/event_detector.py` | none (docstring only) |
| **No file deletes. No file moves. No `tools/` / `xv6-riscv/` / `dashboard_live/` behavioral edits.** | — | — |

The plan deliberately defers every move to a post-demo PR per the request's
"prefer archive planning over risky file moves" rule.

---

## 5. Move queue (post-demo, in order)

1. **Gitignore xv6 build artefacts** (`.o`, `.d`, `.asm`, `.sym`) and
   `git rm --cached` the currently-tracked copies.
2. Move `dashboard_test/` → `archive/dashboard_test/` (independent app, no
   shared imports).
3. Move `dashboard/` (Streamlit) → `archive/streamlit_dashboard/`.
4. Move `xv6-style-scheduler/simulator/` → `archive/xv6_style_simulator/`
   *or* merge into `tools/scheduler_simulator.py`.
5. Move `traces/` (root) → `archive/traces/`.
6. Move ARCHIVE-CANDIDATE docs in §2.10 to `docs/archive/`.
7. ~~Rename `outputs/demo/` → `outputs/_demo_fixtures/`~~ **DONE** — committed via `.gitignore` `!outputs/_demo_fixtures/` exception.

Each step is a single PR; each PR runs `docs/final_slimming_smoke_check.md`
before merging. Order matters: dashboards before docs (independent apps move
first), simulator after dashboards (tooling depends on it).

---

## 6. Risk register

| Risk | Mitigation |
|---|---|
| Moving `dashboard_test/` breaks a doc link. | `grep -rn "dashboard_test"` before the move; update all hits in the same PR. |
| Moving Streamlit breaks an external developer who only has Python. | Keep the LEGACY label one full release before moving; archive, never delete. |
| Gitignoring xv6 artefacts breaks a teammate mid-rebase. | Land the `.gitignore` change after a clean `make clean`; document in the PR. |
| Cleanup PR runs before the demo and breaks the snapshot path. | Run `docs/final_slimming_smoke_check.md` end-to-end; require green. |
| “Just clean up that one thing” scope creep into kernel. | `xv6-riscv/kernel/proc.c`, `algorithm_guard.py`, `trace_parser.py`, `metrics.py`, `dashboard_live/` are listed protected in §14 of the request; reject changes touching them in any cleanup PR. |

---

## 7. Success criteria checklist (from request §16)

| # | Criterion | Status after this PR |
|---|---|---|
| 1 | New reader identifies final demo path within 30 s. | YES (new README block §0). |
| 2 | README clearly presents xv6 + QEMU as primary. | YES. |
| 3 | `dashboard_live/` clearly the final UI. | YES. |
| 4 | Simulator + `dashboard_test/` clearly non-core. | YES (label + table). |
| 5 | Runtime correction honestly labeled preview-only. | YES (source banner already present; README/docs say preview). |
| 6 | Old outputs, duplicate docs, legacy code classified. | YES (§2.10, §3, §5). |
| 7 | Core path still works after cleanup. | Verified by `docs/final_slimming_smoke_check.md`. |
| 8 | No unnecessary new feature added. | YES (docs only). |
| 9 | Repo feels like focused xv6-primary project. | YES (README top block + classification). |

---

## 8. One-paragraph defense

> Slimming for this PR is intentionally *labelling* slimming. The two
> documents added here (this plan + the smoke check), plus a top-of-README
> Final Demo Path block and three short docstring tightenings, make the
> repository read as “xv6 is the path, everything else is a fallback or a
> note” — without moving a single file the demo depends on. Every
> physically-risky move (dashboards, Streamlit, simulator duplicate,
> stale traces, archive-candidate docs, xv6 build artefacts) is recorded in
> §5 with order and risk, ready for the first post-demo PR.
