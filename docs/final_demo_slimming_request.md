# Final Demo Codebase Slimming Request

## 0. How to Use This Document

This document is a task specification for slimming down the Visual Scheduler codebase before the final demo.

Use this file as the detailed context document.  
The actual Claude/Codex goal can stay short and simply reference this file.

Recommended workflow:

```text
1. Add this file to docs/final_demo_slimming_request.md
2. Give Claude the short goal at the bottom of this document
3. Let Claude use this file as the source of truth for the cleanup/refactor task
```

---

## 1. Purpose

The current Visual Scheduler project has accumulated many feature PRs.  
The codebase now feels larger than the core functionality required for the final demo.

This cleanup is not a feature-expansion task.

The goal is to make the project look like a focused:

```text
xv6-primary LLM-assisted scheduling system
```

not an overloaded toolbox.

The final repository should clearly communicate:

- xv6 is the primary OS execution backend.
- The LLM is a scheduling advisor, not the scheduler itself.
- Algorithm Guard validates LLM recommendations before execution.
- Scheduling traces and metrics evaluate whether the recommendation was useful.
- `dashboard_live/` is the final demo UI.
- Python simulator, `dashboard_test/`, legacy dashboards, and preview-only modules are not part of the final core path.

---

## 2. Current Problem

The project has many useful parts, but they are mixed together:

```text
xv6 backend
Python simulator
dashboard_live
dashboard_test
legacy Streamlit dashboard
runtime correction preview
feedback loop
snapshots
old outputs
old audit docs
multiple validator/smoke scripts
```

This makes the project feel overloaded.

The final demo should not feel like:

```text
a pile of loosely connected tools
```

It should feel like:

```text
one clear xv6-centered pipeline
```

---

## 3. Final Core Demo Path

The final demo path must be:

```text
Workload
→ Workload Analyzer
→ LLM Advisor
→ Algorithm Guard
→ xv6 + QEMU
→ Trace Parser
→ Metrics Evaluator
→ dashboard_live
```

This path should be easy to identify within 30 seconds of opening the README.

The README, architecture docs, and demo docs should all reinforce this path.

---

## 4. Core Principle

Do not add new product features in this task.

This task is about:

- codebase slimming
- final demo hardening
- documentation cleanup
- role clarification
- archive planning
- reducing confusion between core, dev, fallback, legacy, archive, and future-work modules

Prefer classification and archive planning over aggressive deletion.

The goal is not to destroy useful development history.  
The goal is to make the final demo path thin and obvious.

---

## 5. Repository Classification

Classify major files and folders into the following categories.

---

### 5.1 CORE

Files and folders directly needed for the final demo path.

Expected examples:

```text
xv6-riscv/
workloads/
tools/workload_analyzer.py
tools/llm_advisor.py
tools/solar_client.py
tools/algorithm_guard.py
tools/trace_parser.py
tools/metrics.py
scripts/orchestrator.py
scripts/final_demo_check.py
dashboard_live/
docs/demo_runbook.md
docs/architecture.md
```

CORE means:

- directly used in the final demo path
- needed to prove the xv6-primary execution flow
- should not be aggressively moved or deleted
- should remain easy to find

---

### 5.2 DEV / FALLBACK

Files useful for development, testing, smoke checks, local fallback, or debugging, but not part of the final demo path.

Expected examples:

```text
tools/scheduler_simulator.py
dashboard_test/
dashboard contract validators
algorithm winner analysis scripts
generated fixtures
smoke-test helpers
```

DEV / FALLBACK means:

- useful, but not the main product
- should not be presented as the final execution path
- may stay in the repository
- should be labeled clearly

The Python simulator can remain, but its role must be downgraded:

```text
scheduler_simulator.py = dev/test fallback only
```

---

### 5.3 LEGACY

Older implementation paths that have been replaced by the current final path.

Expected examples:

```text
dashboard/ Streamlit dashboard
old visualization prototypes
outdated execution instructions
```

LEGACY means:

- historically useful
- possibly still runnable
- not part of the final demo
- should not compete with `dashboard_live/`

---

### 5.4 ARCHIVE CANDIDATE

Files that may be useful as development history but should not clutter the main project path.

Expected examples:

```text
old generated outputs
old snapshots not used in final demo
old PR audit documents
outdated planning docs
stale logs
duplicate progress reports
```

ARCHIVE CANDIDATE means:

- do not delete immediately unless clearly safe
- move to `archive/` or `docs/archive/` if appropriate
- preserve grading-useful development history
- reduce visual clutter in the main folders

---

### 5.5 FUTURE WORK

Features that are designed, previewed, partially implemented, or documented but not fully implemented.

Expected examples:

```text
runtime correction closed-loop if xv6 runtime apply is not implemented
feedback-loop automation if it still requires manual execution
dashboard Run Experiment backend if only planned
WebSocket/SSE live streaming if not implemented
```

FUTURE WORK means:

- do not present as completed
- may be demoed as preview only if labeled honestly
- should not be part of the final core path unless fully implemented

---

## 6. Required Document: `docs/codebase_slimming_plan.md`

Create:

```text
docs/codebase_slimming_plan.md
```

It must include this table:

| Path | Category | Current Role | Keep / Move / Archive | Reason | Risk |
|---|---|---|---|---|---|

Rules:

- Do not delete aggressively.
- If moving a file may break imports, do not move it yet.
- If unsure, classify it and explain the risk.
- Keep the xv6 core protected.
- Prefer `archive plan` over risky file moves.
- The document should be useful for a future cleanup PR.

---

## 7. README Cleanup

Update README so that the final demo path is obvious near the top.

The README must clearly state:

- `dashboard_live/` is the final demo dashboard.
- `xv6 + QEMU` is the primary execution backend.
- `scheduler_simulator.py` is dev/test fallback only.
- `dashboard_test/` is UI sandbox only.
- Streamlit dashboard, if present, is legacy.
- runtime correction is preview-only unless closed-loop xv6 apply is actually implemented.

Add a section like:

```markdown
## Final Demo Path

Workload
→ Workload Analyzer
→ LLM Advisor
→ Algorithm Guard
→ xv6 + QEMU
→ Trace Parser
→ Metrics Evaluator
→ dashboard_live
```

The README should answer these questions quickly:

1. What is the main demo path?
2. Which dashboard should be opened?
3. Is xv6 the primary backend?
4. Is the simulator only a fallback?
5. Which modules are preview-only?

---

## 8. Dashboard Cleanup

Review dashboard-related folders.

Expected classification:

| Path | Expected Role |
|---|---|
| `dashboard_live/` | Final demo UI |
| `dashboard_test/` | UI sandbox / dev-only |
| `dashboard/` | Legacy Streamlit dashboard / archive candidate |

The final README must not make multiple dashboards look equally important.

Required actions:

- Make `dashboard_live/` clearly the final UI.
- Mark `dashboard_test/` as UI sandbox only.
- Mark Streamlit dashboard, if present, as legacy.
- Do not let users wonder which dashboard to run for the final demo.
- If moving dashboard files is risky, document the plan instead of moving immediately.

---

## 9. Runtime Correction Cleanup

Review:

```text
tools/event_detector.py
tools/correction_proposer.py
tools/correction_guard.py
RuntimeCorrectionPreview dashboard component
```

Check whether runtime correction is actually closed-loop.

A completed closed-loop would mean:

```text
runtime event detected
→ correction proposed
→ correction validated
→ correction applied back to xv6 at runtime
→ trace records CORRECTION_APPLIED or equivalent event
```

If the system only detects events, proposes a correction, and validates it without applying the correction back to xv6 at runtime, label it clearly as:

```text
Runtime Correction Preview Only
```

Do not present it as completed closed-loop runtime correction.

Expected action:

- Keep it as FUTURE WORK or DEV preview.
- Remove it from the final core path.
- Update README/docs/dashboard labels if needed.
- If files remain in place, make their role clear.
- If moving is safe, consider `tools/dev/` or `archive/runtime_correction_preview/`.

---

## 10. Simulator Cleanup

The Python simulator may remain in the repository, but it must not look like the primary product.

Expected role:

```text
scheduler_simulator.py = dev/test fallback only
```

The final demo path should be xv6-primary.

Do not remove simulator code if it is still useful for tests or fallback.

Required actions:

- Downgrade simulator role in README/docs.
- Do not describe simulator as the final backend.
- If simulator is still used by smoke tests, keep it but label it correctly.
- If simulator output is used only for fallback/demo safety, say so.

---

## 11. Documentation Cleanup

Review docs and classify them.

Keep main docs focused:

```text
architecture
demo runbook
evaluation criteria
final demo checklist
limitations
development process summary
```

Move or classify as archive candidates:

```text
old PR audit docs
outdated planning docs
duplicate architecture explanations
old demo notes
stale progress reports
```

Do not delete development history that may be useful for grading.

Prefer:

```text
docs/archive/
```

or an archive plan in `docs/codebase_slimming_plan.md`.

The docs folder should not feel like a dumping ground.

---

## 12. Output / Snapshot Cleanup

Review generated outputs and snapshots.

Classify:

- final demo snapshots to keep
- old generated outputs to archive
- stale logs to remove or ignore
- temporary fixtures to mark as dev-only

Do not delete anything needed by:

```text
dashboard_live
final demo checks
snapshot selector
contract validator
demo runbook
```

If unsure, classify first and avoid deletion.

---

## 13. Duplication Review

Check duplication between:

```text
dashboard_live/ and dashboard_test/
metrics/evaluator-like logic
schema compatibility logic
runtime correction preview logic
repeated docs explaining the same architecture
```

For each duplicated area, choose one:

- keep both but clarify roles
- merge later
- archive one
- leave unchanged due to import/demo risk

Document the decision in:

```text
docs/codebase_slimming_plan.md
```

---

## 14. Protected Core

Do not aggressively refactor or delete:

```text
xv6-riscv/kernel/proc.c
scheduler implementation
setscheduler / getscheduler syscalls
xv6-riscv/user/schedtest.c
trace generation logic
tools/trace_parser.py
tools/metrics.py
tools/algorithm_guard.py
dashboard_live/
```

The xv6 scheduler implementation is the OS core of this project.

Do not break it for cleanup aesthetics.

---

## 15. Smoke Check Document

Create:

```text
docs/final_slimming_smoke_check.md
```

It should include commands or check steps for:

- xv6 build check
- orchestrator xv6 backend check, if QEMU is available
- trace parser check
- metrics generation check
- dashboard_live build check
- dashboard contract validation, if available

The goal is to verify that slimming did not break the final demo path.

Suggested structure:

```markdown
# Final Slimming Smoke Check

## 1. xv6 Build Check

Command:
...

Expected:
...

## 2. xv6 Backend Orchestrator Check

Command:
...

Expected:
...

## 3. Trace Parser Check

Command:
...

Expected:
...

## 4. Metrics Generation Check

Command:
...

Expected:
...

## 5. Dashboard Live Build Check

Command:
...

Expected:
...

## 6. Dashboard Contract Validation

Command:
...

Expected:
...
```

---

## 16. Success Criteria

This task is successful if:

1. A new reader can identify the final demo path within 30 seconds.
2. README clearly presents xv6 + QEMU as the primary backend.
3. `dashboard_live/` is clearly the final UI.
4. simulator and `dashboard_test/` are clearly non-core.
5. runtime correction is honestly labeled preview-only unless fully implemented.
6. old outputs, duplicate docs, and legacy code are classified.
7. The core path still works after cleanup.
8. No unnecessary new feature is added.
9. The repository feels like a focused xv6-primary project, not an overloaded toolbox.

---

## 17. Non-Goals

Do not:

- add new product features
- implement runtime correction closed-loop
- rewrite the whole project
- delete files aggressively
- break xv6 scheduler code
- present simulator as the final execution path
- present preview-only features as completed features
- over-optimize code performance before clarifying project structure
- remove grading-useful development history without archiving

---

## 18. Recommended Final Repository Shape

The final repository should conceptually look like this:

```text
VisualScheduler/
├─ README.md
├─ xv6-riscv/
│  ├─ kernel/proc.c
│  ├─ kernel/sysproc.c
│  └─ user/schedtest.c
│
├─ workloads/
│  ├─ interactive_heavy.json
│  ├─ cpu_bound_batch.json
│  ├─ priority_sensitive.json
│  └─ short_job_sjf.json
│
├─ tools/
│  ├─ workload_analyzer.py
│  ├─ llm_advisor.py
│  ├─ solar_client.py
│  ├─ algorithm_guard.py
│  ├─ trace_parser.py
│  └─ metrics.py
│
├─ scripts/
│  ├─ orchestrator.py
│  └─ final_demo_check.py
│
├─ dashboard_live/
│  └─ ...
│
├─ docs/
│  ├─ architecture.md
│  ├─ demo_runbook.md
│  ├─ evaluation_criteria.md
│  ├─ limitations.md
│  ├─ codebase_slimming_plan.md
│  └─ final_slimming_smoke_check.md
│
└─ archive/
   ├─ dashboard_test/
   ├─ streamlit_dashboard/
   ├─ runtime_correction_preview/
   └─ old_outputs_or_docs/
```

This is a conceptual target.  
Do not force risky file moves if imports or demo scripts may break.

---

## 19. Short Claude/Codex Goal

Use the following short goal after adding this document to the repository.

```text
Goal: Final-demo codebase slimming for Visual Scheduler.

Read `docs/final_demo_slimming_request.md` first and follow it as the source of truth for this task.

Main objective:
Make the repository look like a focused xv6-primary LLM-assisted scheduling project, not an overloaded toolbox.

Required actions:
1. Classify the repository into CORE / DEV-FALLBACK / LEGACY / ARCHIVE CANDIDATE / FUTURE WORK.
2. Create `docs/codebase_slimming_plan.md`.
3. Update README so the final demo path is obvious within 30 seconds.
4. Make `dashboard_live/` the only final demo dashboard.
5. Mark `scheduler_simulator.py` as dev/test fallback only.
6. Mark `dashboard_test/` as UI sandbox only.
7. Mark Streamlit dashboard, if present, as legacy.
8. Mark runtime correction as preview-only unless closed-loop xv6 runtime apply is actually implemented.
9. Create `docs/final_slimming_smoke_check.md`.
10. Do not add new product features.

Final core path:
Workload
→ Workload Analyzer
→ LLM Advisor
→ Algorithm Guard
→ xv6 + QEMU
→ Trace Parser
→ Metrics Evaluator
→ dashboard_live

Constraints:
- Do not delete aggressively.
- Do not break xv6 scheduler code.
- Do not break `trace_parser.py`, `metrics.py`, `algorithm_guard.py`, or `dashboard_live/`.
- Prefer archive planning over risky file moves.
- Keep the final demo path thin, obvious, and xv6-primary.

After finishing, report:
- files changed
- classification summary
- actual moves performed
- moves intentionally not performed due to risk
- verification commands
- remaining cleanup recommendations
```

---

## 20. One-Sentence Summary

Core should be thin, demo should be clear, and everything else should be classified as dev, fallback, legacy, archive, or future work.

```text
Core thin.
Demo clear.
Extras classified.
```
