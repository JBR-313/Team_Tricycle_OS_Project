# Development Process Document — LLM Sched Copilot

Deliverable #3: planning -> scheduling -> execution -> retrospective, with
meeting notes, weekly progress per role, and issues encountered + how they were
resolved.

> Sections marked **[TEAM TODO]** need team-specific information (names, dates,
> who-did-what) that only the team can fill in. The technical issue log (section 5) is
> reconstructed from the actual commit history and is accurate.

## 1. Team & roles  [TEAM TODO]

| Role | Member | Responsibility |
|---|---|---|
| Team lead / integration | _name (ID)_ | orchestrator, repo, submissions |
| Kernel / xv6 | _name (ID)_ | scheduling algorithms, syscalls, schedtest |
| LLM / evaluation | _name (ID)_ | advisor, guard, ablations, metrics |
| Dashboard / docs | _name (ID)_ | React dashboard, report, slides |

Team name: **[TEAM TODO]** · Repo: this repository (public).

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

## 4. Execution — weekly progress per role  [TEAM TODO for dates/owners]

Reconstructable highlights (fill owners/dates):
- Kernel: implemented RR/FCFS/Priority+Aging/MLFQ/SJF/SRTF in `kernel/proc.c`;
  added `setscheduler`/`setpriority`/`setpredictor`/`setrrquantum`/`setmlfqparams`/
  `setbursthint` syscalls; built `user/schedtest.c` curated-workload harness.
- LLM/eval: `llm_advisor` + `algorithm_guard` + `correction_proposer`; honesty rule
  (no future bursts); ablations (burst prediction, retrieval learning, adaptive).
- Dashboard/host: `orchestrator.py` control plane; React dashboard with live data
  contract + validator; trace explainer + FAIL-only feedback.

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
measurement-driven evaluation (191 pytest + 28 vitest passing); a safety architecture
that guarantees the LLM cannot degrade execution.

**What we would change:** define the evaluation baselines (always-MLFQ, kNN,
stock-RR) *before* claiming a performance benefit; make `schedtest` bursts
deterministic (fixed iteration counts) before attempting real-xv6 A/B; scope the
LLM's role to where it is irreplaceable (explanation, zero-shot hints) rather than
raw selection.

**Key lesson:** "add an LLM to make it faster" is not automatically true — it depends
on whether the deciding information is available to the LLM and whether exhaustive
search is cheap. We measured the boundary instead of assuming the win.

## 7. Meeting notes  [TEAM TODO]

| Date | Attendees | Decisions | Action items |
|---|---|---|---|
| _wk9_  | _all_ | Direction B; topic = LLM hint oracle for xv6 scheduling | repo, roles |
| _wk10_ | _all_ | block diagram; OS concepts | … |
| … | | | |
