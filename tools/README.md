# tools/ — host-side pipeline modules

The decision/observability layer that wraps xv6. The LLM only *advises*; every
recommendation is validated by the **Algorithm Guard** before xv6 runs it, and the
LLM never sees future CPU bursts (see `docs/system_limitations.md`).

| module | role |
|---|---|
| `workload_analyzer.py` | workload JSON → visible-feature summary |
| `llm_advisor.py` | summary → recommendation (Solar Pro 3); also FAIL-only feedback rules |
| `intent_advisor.py` | natural-language intent → scheduling config |
| `algorithm_guard.py` | validate recommendation (algorithm/metric/params/schema) → `guard_decision.json` |
| `trace_parser.py` · `metrics.py` | xv6 trace → normalized JSONL → metrics (response/turnaround/waiting/throughput, judgment, regret) |
| `event_detector.py` · `correction_proposer.py` · `correction_guard.py` | runtime-event detection → host-side post-evaluation correction loop |
| `trace_explainer.py` | finished run → natural-language explanation |
| `solar_client.py` | Upstage Solar Pro 3 API client |

Setup: `cp .env.example .env` and add `UPSTAGE_API_KEY` (`.env` is git-ignored).
Data schemas live in `docs/dashboard_data_contract.md`.
