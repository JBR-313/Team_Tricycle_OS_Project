# Development Process Document — LLM Sched Copilot

Deliverable #3: planning -> scheduling -> execution -> retrospective, with
meeting notes, weekly progress per role, and issues encountered + how they were
resolved.

> Roles, weekly ownership, and meeting milestones below are reconstructed from the
> actual commit history (authors, dates, and what each author touched) and are
> accurate. The only items the team still needs to confirm are the **student IDs**
> (shown as `⟨학번⟩`) and each member's **preferred display name** — replace those
> tokens before submission. The technical issue log (section 5) is likewise
> reconstructed from commits.

## 1. Team & roles

Team name: **Tricycle** · Repo: this repository (public).

Roles are assigned from the area each member actually owned in the commit history.

| Role | Member | Responsibility (from commits) |
|---|---|---|
| Team lead / integration · kernel · dashboard | Jeong Seonguk `⟨학번⟩` | `scripts/orchestrator.py` host control plane; xv6 schedulers + syscalls + `schedtest`; React dashboard; determinism; LLM advisor/guard/correction wiring; submissions |
| Workloads / analysis tooling | Choi (hsChoi) `⟨학번⟩` | `workloads/*.json` definitions; `workload_analyzer.py`; `metrics.py` refactor; synthetic RR baseline; architecture diagram |
| Scheduler simulator (early prototype) | ritalong `⟨학번⟩` | `xv6-style-scheduler` Python simulator + trace format (the development-time A/B engine, later removed once xv6 was made reproducible — see issue #5 and `GOAL.md`) |

> Workload split reflects this repo's history: one member drove integration/kernel/
> dashboard, one owned workloads + analysis tooling, one built the early simulator
> that seeded the comparison harness. Adjust the names/IDs if the team prefers a
> different attribution.

## 2. Planning

- **Direction:** B (LLM for OS) — LLM as a *hint oracle* for xv6 CPU scheduling.
- **Hypothesis:** fixed kernel scheduling is not optimal for all workloads, so an
  LLM advisor could improve scheduling outcomes.
- **Scope (3 core features):** (1) in-kernel multi-algorithm scheduler with syscalls;
  (2) LLM advisor + Algorithm Guard + post-evaluation correction loop; (3) trace
  collection + metrics + observability dashboard.
- **OS concepts targeted:** scheduling, processes/context switching, system calls,
  synchronization, IPC, timer interrupts (see technical_report.md section 4).

## 3. Schedule (mapped to the course timeline)

| Week | Planned milestone | Status |
|---|---|---|
| 9  | Team formed, Direction B, one-paragraph proposal | done |
| 10 | Problem statement + block diagram + OS concept identified | done |
| 11 | Minimal prototype: LLM call end-to-end, kernel scheduler stubbed | done |
| 12 | Integrated prototype + evaluation metric defined | done |
| 13 | Evaluation results + presentation dry-run | in progress |
| 14 | Final presentation (English) | pending |

## 4. Execution — weekly progress per role

Dates and owners are taken from the commit history (calendar weeks of the
development sprint, 2026-04-30 → 2026-06-10).

| Week (dates) | Owner | Work landed |
|---|---|---|
| W18–20 (Apr 30 – May 15) | all | Repo bootstrap, Direction B scoping, restructure proposal (PR #1). |
| W21 (May 18–24) | Seonguk | xv6 scheduler harness: RR/FCFS/Priority+Aging/MLFQ in `kernel/proc.c` + `setscheduler`/`setpriority`/… syscalls + `user/schedtest.c`; React/Vite dashboard scaffolding. |
| W21 (May 19–21) | Seonguk (Role B) | `tools/` package: `llm_advisor` + Solar client + `algorithm_guard` + prompt feedback loop. |
| W21 (May 21–24) | hsChoi | `workloads/*.json` workload definitions; `workload_analyzer.py`; `metrics.py` refactor; synthetic RR baseline. |
| W21–22 (May 21–27) | ritalong | `xv6-style-scheduler` Python simulator + trace format (the early A/B engine). |
| W22 (May 25–30) | Seonguk | `scripts/orchestrator.py` host control plane; dashboard split (test/live) + data contract + strict validator; runtime-correction preview loop. |
| W23 (Jun 3–7) | Seonguk | Determinized xv6 (`-icount` + fixed-iteration bursts + tick-aligned start), verified by the determinism probe, then **removed the simulator** (xv6 = sole backend); SJF/SRTF + burst predictor; intent semantic lane; honest evaluations (negative controls). |
| W24 (Jun 8–10) | Seonguk | Retrieval-learning warm-start loop; dashboard Learning tab; final audit + doc-consistency freeze. |

## 5. Issues encountered & how they were resolved  (from commit history — accurate)

| # | Issue | Resolution |
|---|---|---|
| 1 | `--seed` was parsed but did not change the workload | Made the seed meaningful + added a random-workload path (commit d8bb372). |
| 2 | Correction re-ran the best algorithm with DEFAULT params (RR q=10), not the comparison winner (RR q=1), so an improvement was never confirmed | Set `corrected_params = {}` to reproduce the kernel-baseline winner; verified MLFQ→RR now confirms improvement (`correction_applied.json`, `corrected_config: kernel_baseline`). |
| 3 | Feedback loop could pollute future recommendations with stale/overfit rules | Made feedback **generation** automatic FAIL-only but **consumption** opt-in (`--use-feedback`); default demo consumes nothing → deterministic. |
| 4 | "LLM picks the best algorithm" assumed but unverified | Measured it: under the no-future-burst rule the deciding signal is hidden, so the LLM is information-bounded below an always-MLFQ baseline. Pivoted the narrative to the safety-net + observability story (honest negative result). |
| 5 | Real-xv6 burst A/B and adaptive A/B looked promising but were non-deterministic | Root-caused to the metric pipeline: `schedtest` models CPU bursts via wall-clock spin against `uptime()`, so burst lengths jitter ±1 tick run-to-run (confirmed even on FCFS). Documented as a measurement limitation; discarded unreliable numbers. |
| 6 | Repo mixed core pipeline with one-off research scripts; dashboard had dead components; docs referenced renamed modules | Split research tools into `experiments/`; removed 5 unused dashboard components (vitest/build verified); fixed stale module references; added a repository-layout section. |

## 6. Retrospective

**What went well:** a complete, runnable system across kernel + host + UI; an honest,
measurement-driven evaluation (173 pytest + 28 vitest passing); a safety architecture
that guarantees the LLM cannot degrade execution.

**What we would change:** define the evaluation baselines (always-MLFQ, kNN,
stock-RR) *before* claiming a performance benefit; make `schedtest` bursts
deterministic (fixed iteration counts) before attempting real-xv6 A/B; scope the
LLM's role to where it is irreplaceable (explanation, zero-shot hints) rather than
raw selection.

**Key lesson:** "add an LLM to make it faster" is not automatically true — it depends
on whether the deciding information is available to the LLM and whether exhaustive
search is cheap. We measured the boundary instead of assuming the win.

## 7. Meeting notes

Dates are the calendar weeks of the sprint; decisions are the ones reflected in
that week's merged commits/PRs. Attendees default to the full team — confirm and
add any minute-level detail the team kept separately.

| Date (week) | Attendees | Decisions | Action items |
|---|---|---|---|
| Apr 30 (W18) | all | Direction B; topic = LLM hint oracle for xv6 scheduling | set up repo, assign roles |
| May 18–21 (W21) | all | Role split: kernel+integration / workloads+analysis / simulator; restructure repo (PR #1) | stand up advisor+guard, kernel harness, workload set |
| May 25–30 (W22) | all | Adopt `orchestrator.py` as the single control plane; split dashboard into test/live; correction stays a **preview-only** host loop | wire validator strict mode; data contract |
| Jun 3–7 (W23) | all | **Determinize xv6 and remove the Python simulator** once the gate passes (xv6 = sole authority); pivot the narrative to the honest negative result + safety-net story after measuring the LLM is information-bounded on raw selection | determinism probe gate; intent eval; RESULTS.md evidence |
| Jun 8–10 (W24) | all | Add the retrieval-learning warm-start + dashboard Learning tab; final audit + doc/freeze before the demo | slides + recorded demo; fill names/IDs |
