# Documentation Map

One-stop index for every document in this repository. Start at the
[root README](../README.md) for the project overview; come here to go deeper.

## Deliverables

| Doc | What it is |
|---|---|
| [technical_report.md](technical_report.md) | **Deliverable #2** — canonical technical overview: architecture, LLM integration, key implementation details, honest findings |
| [development_process.md](development_process.md) | **Deliverable #3** — team/roles, schedule, weekly execution, issue log, retrospective, meeting notes |
| [presentation/](presentation/) | Final presentation assets (5-min slides) |

## Design references

| Doc | What it is |
|---|---|
| [architecture_diagram.md](architecture_diagram.md) | Block diagram of the three-phase pipeline (Before / Running / After) |
| [orchestrator_design.md](orchestrator_design.md) | Host-side control plane design (`scripts/orchestrator.py`) |
| [trace_format.md](trace_format.md) | Scheduling Trace Log spec: raw xv6 `[SCHED]`/`[SCHEDTEST]` lines → normalized JSONL |
| [dashboard_data_contract.md](dashboard_data_contract.md) | Schema contract for every file under `dashboard_live/public/live-data/` (mirrored by `tools/validate_dashboard_contract.py`) |
| [evaluation_plan.md](evaluation_plan.md) | Metrics, regret-based SUCCESS / NEAR-SUCCESS / FAIL judgment, feedback rules |
| [workload_coverage_matrix.md](workload_coverage_matrix.md) | Which workload exercises which scheduling behavior |
| [system_limitations.md](system_limitations.md) | Honest, explicit limits (CPUS=1, curated xv6 tables, cold-start SJF/SRTF, …) |

## Phase goal memos (historical)

| Doc | What it drove |
|---|---|
| [GOAL.md](GOAL.md) | Determinize xv6 → verify → remove the Python simulator (xv6 = sole backend) |
| [GOAL_burst_eval.md](GOAL_burst_eval.md) | Leak-free burst-prediction A/B on random workloads, with negative control |
| [GOAL_semantic.md](GOAL_semantic.md) | Natural-language intent → Guard-valid scheduling config (semantic lane) |

## Measured evidence (`outputs/`)

Every headline claim traces to a committed RESULTS doc, reproducible via
`experiments/`:

| Evidence | Claim it backs |
|---|---|
| [outputs/learning_curve/RESULTS.md](../outputs/learning_curve/RESULTS.md) · [FINDINGS.md](../outputs/learning_curve/FINDINGS.md) | **Recurring workloads → retrieval warm-start drops regret to ≈0** (dashboard Learning tab, Result slide) |
| [outputs/learning/RESULTS.md](../outputs/learning/RESULTS.md) | Standalone algorithm selection is information-bounded (always-MLFQ not beaten) |
| [outputs/random_eval/RESULTS.md](../outputs/random_eval/RESULTS.md) | Burst prediction: LLM ≈ heuristic on signal, fails fused signal; control passes |
| [outputs/adaptive/RESULTS.md](../outputs/adaptive/RESULTS.md) | Mid-run algorithm switching has no robust headroom |
| [outputs/intent_eval/RESULTS.md](../outputs/intent_eval/RESULTS.md) | Intent → config scores 8/8 (the LLM's measured win) |
| [outputs/ablation/burst_ablation.md](../outputs/ablation/burst_ablation.md) | LLM burst-*ordering* prior beats naive baselines (0.90 vs 0.50) |

## Media

`images/` — dashboard screenshots and the presentation Result chart
(`result_learning_regret.png`).
