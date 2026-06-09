# experiments/ — research & evidence tools (NOT the pipeline)

Hand-run scripts that *measure* where the LLM helps; they produce the evidence in
`outputs/` and are not part of the running pipeline ([`../tools/`](../tools)).
**Honesty contract:** future CPU bursts and `expected_best_algorithm` are read only
by the offline scorer — never placed in a prompt.

| script | question it answers | output |
|---|---|---|
| `xv6_determinism_probe.py` | does the real-xv6 metric path reproduce run-to-run? | console |
| `burst_random_eval.py` | LLM vs heuristics vs blind EMA on random workloads (xv6, + negative control) | `outputs/random_eval/` |
| `workload_gen.py` | random workload generator (signal / control; leak-free) | (library) |
| `intent_eval.py` | natural-language intent → config, scored against an OS rubric | `outputs/intent_eval/` |
| `burst_ablation.py` | is the LLM's cold-start burst prediction better than EMA / a heuristic? | `outputs/ablation/` |
| `burst_xv6_confirm.py` | do burst priors improve SJF/SRTF on the real kernel? | `outputs/ablation/` |
| `outcome_store.py` · `retrieval_advisor.py` · `recommendation_eval.py` | retrieval memory + leave-one-out CV of recommendation modes | `outputs/learning/` |

Most scripts cache LLM calls, so a re-run is offline/deterministic; pass `--advise`
(or run fresh) to elicit with `UPSTAGE_API_KEY`.
