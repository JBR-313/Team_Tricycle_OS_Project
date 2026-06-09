# LLM Sched Copilot — Architecture

Three host-side phases wrap **xv6 (the sole execution authority)**. The LLM only
emits `recommendation.json` / `correction.json`; the Algorithm Guard validates
every LLM output before it is applied; xv6 runs the algorithm and the metrics
verify it.

```mermaid
flowchart TD
  subgraph BEFORE["Before running"]
    B0[workloads/*.json] --> B1[workload_analyzer.py]
    B1 -->|workload_summary.json| B2[llm_advisor.py · Solar Pro 3]
    B2 -->|recommendation.json| B3[algorithm_guard.py]
  end
  subgraph RUNNING["Running (xv6 under QEMU)"]
    R0[xv6 schedtest · RR/FCFS/Priority/MLFQ/SJF/SRTF]
    R0 -->|trace.jsonl| R2[trace_parser.py] --> R3[metrics.py]
    R3 --> R4[event_detector.py] --> R5[correction_proposer.py]
    R5 -->|correction.json → guard → host-side re-run| R0
  end
  subgraph AFTER["After running"]
    A1[trace_explainer.py]
    A2[feedback rules · FAIL-only]
    A3[dashboard_live]
  end
  B3 -->|guard_decision.json ✓| R0
  R3 --> A1 --> A3
  R3 --> A2 -.->|feedback_rules.md · next run, opt-in| B2
  R3 --> A3
```

## Data interfaces (all JSON / JSONL — no CSV)
| file | producer → consumer |
|---|---|
| `workload_summary.json` | analyzer → advisor |
| `recommendation.json` | advisor → guard, dashboard |
| `guard_decision.json` | guard → xv6 |
| `trace_<algo>.jsonl` | xv6 → parser, explainer, dashboard |
| `metrics.json` | metrics → explainer, advisor(feedback), dashboard |
| `runtime_events.json` → `correction_applied.json` | event_detector → correction loop → dashboard |
| `trace_explanation.json` | explainer → dashboard |
| `feedback_rules.md` | advisor(FAIL) → advisor(next run, opt-in) |

## Metrics
```
response_time   = first_run_time − arrival_time
turnaround_time = finish_time − arrival_time
waiting_time    = turnaround_time − total_cpu_burst_time
throughput      = completed_process_count / total_execution_time
```

## Design rules
- LLM is **not** the scheduler; xv6 is the execution authority.
- The Algorithm Guard validates every LLM output before it is applied.
- Runtime correction is a **host-side post-evaluation re-run** (a second xv6 run),
  not mid-run kernel injection; the LLM is never on the kernel hot path.
- Future CPU bursts are never given to the LLM. RR baseline is always kept.
- API key lives in `.env` only (git-ignored).

> **LLM suggests · Algorithm Guard checks · xv6 executes · metrics verify · GUI explains.**

See `docs/orchestrator_design.md` (control plane), `docs/trace_format.md` and
`docs/dashboard_data_contract.md` (formats), `docs/system_limitations.md` (limits).
