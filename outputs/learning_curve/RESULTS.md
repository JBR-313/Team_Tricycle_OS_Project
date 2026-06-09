# Adaptive-learning replay — regret over a workload sequence

- bank: **20 instances**, families: interactive, cpu_batch, convoy, priority
- k=3, drift z=2.0, regret = normalised gap from the measured-best on each instance's target metric (0 = best).


## sequence: `stable_blocks`  (n=20)
families in order: int int int int int cpu cpu cpu cpu cpu con con con con con pri pri pri pri pri

| arm | mean regret | series (low→high) |
|---|---|---|
| fixed_rr | 0.38 | `▂▃▁▃▁▅▅▄▄▄▁▁▁▂▁▇▆▆█▄` |
| fixed_mlfq | 0.215 | `▁▁▁▁▁▄▃▃▃▃▁▁▁▁▁▇▅▇█▅` |
| knn | 0.059 | `▃▁▁▁▁▄▁▁▁▁▁▁▁▁▁█▁▁▁▁` |
| knn_drift | 0.059 | `▃▁▁▁▁▄▁▁▁▁▁▁▁▁▁█▁▁▁▁` |

**knn regret vs # same-family precedents already seen** (the intuition test):

| same-family precedents | n | mean regret |
|---|---|---|
| 0 | 4 | 0.283 |
| 1 | 4 | 0.0 |
| 2 | 4 | 0.0 |
| 3 | 4 | 0.0 |
| 4 | 4 | 0.009 |

## sequence: `round_robin`  (n=20)
families in order: int cpu con pri int cpu con pri int cpu con pri int cpu con pri int cpu con pri

| arm | mean regret | series (low→high) |
|---|---|---|
| fixed_rr | 0.38 | `▂▅▁▇▃▅▁▆▁▄▁▆▃▄▂█▁▄▁▄` |
| fixed_mlfq | 0.215 | `▁▄▁▇▁▃▁▅▁▃▁▇▁▃▁█▁▃▁▅` |
| knn | 0.083 | `▃▄▁█▁▁▁▆▁▁▁▁▁▁▁▁▁▁▁▁` |
| knn_drift | 0.118 | `▂▄▁▇▁▁▁▅▁▁▁▁▁▁▁█▁▁▁▁` |

**knn regret vs # same-family precedents already seen** (the intuition test):

| same-family precedents | n | mean regret |
|---|---|---|
| 0 | 4 | 0.283 |
| 1 | 4 | 0.12 |
| 2 | 4 | 0.0 |
| 3 | 4 | 0.0 |
| 4 | 4 | 0.009 |

## negative control — label shuffle (signal vs artifact)

| condition | knn mean regret |
|---|---|
| true labels | 0.059 |
| shuffled labels | 0.314 |
| best fixed bar | 0.215 |

**verdict:** signal real (shuffle collapses toward fixed bar)
