# Workload Coverage Matrix

> **Scope:** Whether the curated workloads in `workloads/*.json` and
> `xv6-riscv/user/schedtest.c` exercise the strengths of every supported
> Scheduling Algorithm. Status: 2026-05-28.

---

## 1. What we have today

### 1.1 Host-side JSON workloads (`workloads/`)

| File | n | Labels | Priority range | Burst range | Sum burst | Notes |
|---|---:|---|---|---|---:|---|
| `interactive_heavy.json` | 25 | interactive | [1,1] | [1,2] | 38 | All interactive, all priority 1 — pure RR/MLFQ target. |
| `short_jobs.json` | 25 | interactive | [1,3] | [1,3] | 48 | Short bursts, mild priority spread — SJF/SRTF target. |
| `mixed_workload.json` | 6 | interactive, cpu_bound | [1,3] | [1,30] | 80 | Classic mixed — MLFQ target. |
| `long_cpu_bound_first.json` | 5 | interactive, cpu_bound | [1,3] | [2,60] | 119 | Convoy-effect demonstrator — anti-FCFS target. |
| `priority_sensitive.json` | 5 | cpu_bound, interactive | [1,5] | [3,20] | 46 | Wide priority spread — Priority+Aging target. |
| `starvation_risk.json` | 5 | cpu_bound, interactive | [1,10] | [2,100] | 110 | Extreme priority spread — starvation demonstrator. |

### 1.2 xv6 `schedtest` curated profiles

`xv6-riscv/user/schedtest.c:30-65` — only **4** profiles, no JSON parsing
inside xv6. The seed argument is logged but does **not** alter the workload
yet (no random generation).

| Profile | n | First process | Mix | LLM (current) picks | Best on response_time |
|---|---:|---|---|---|---|
| `interactive` | 5 | (0, 3, prio 5, interactive) | 4 interactive + 1 cpu late | MLFQ | MLFQ |
| `cpu_bound`   | 4 | (0, 8, prio 5, cpu) | all cpu_bound | MLFQ | MLFQ |
| `mixed`       | 5 | (0, 5, prio 4, cpu) | 3 cpu + 2 interactive | MLFQ | MLFQ |
| `priority_sensitive` | 5 | (0, 6, prio 8, cpu) | wide prio (1..9), 3 cpu + 2 int | MLFQ | MLFQ |

Snapshot data: `dashboard_live/public/live-data/snapshots_manifest.json`
shows `llm_selected_algorithm = "MLFQ"` and `judgment = "SUCCESS"`
(`regret_score: 0.0`) for **all four** xv6 profiles.

---

## 2. Coverage matrix — which algorithm does each workload showcase?

Legend: ✔ = workload is genuinely the strong case for the algorithm; ◦ =
workload runs but does not differentiate; ✗ = workload should not pick this
algorithm (anti-pattern).

### 2.1 Host-side JSON workloads

| Workload | RR | FCFS | PRIORITY | MLFQ | SJF | SRTF | Comment |
|---|---|---|---|---|---|---|---|
| `interactive_heavy` | ✔ | ✗ | ◦ | ✔ | ◦ | ◦ | All-equal priority means PRIORITY ≡ FCFS; no preemption wins for SRTF. |
| `short_jobs` | ◦ | ◦ | ◦ | ◦ | ✔ | ✔ | Tightly clustered short bursts — SJF/SRTF should beat RR/MLFQ by ~2-3×. |
| `mixed_workload` | ◦ | ✗ | ◦ | ✔ | ◦ | ✔ | Bursty mix — MLFQ wins on response, SRTF on turnaround. |
| `long_cpu_bound_first` | ◦ | ✗ | ◦ | ✔ | ✔ | ✔ | Demonstrates convoy effect; anything preemptive or burst-aware wins. |
| `priority_sensitive` | ◦ | ✗ | ✔ | ◦ | ✗ | ✗ | Only Priority+Aging answers “important job first.” |
| `starvation_risk` | ◦ | ✗ | ✗ | ✔ | ✗ | ✗ | Naive Priority must starve; MLFQ aging is the right answer. Designed to FAIL Priority. |

### 2.2 xv6 schedtest profiles

| Profile | RR | FCFS | PRIORITY | MLFQ | SJF | SRTF | Comment |
|---|---|---|---|---|---|---|---|
| `interactive` | ✔ | ✗ | ◦ | ✔ | ◦ | ◦ | OK — but priorities 2..7 are mild; aging rarely fires. |
| `cpu_bound`   | ◦ | ✔ | ◦ | ◦ | ✔ | ✔ | All-cpu workload should favor FCFS / SJF. Today snapshot still says MLFQ — **diversity gap**. |
| `mixed`       | ◦ | ✗ | ◦ | ✔ | ◦ | ✔ | OK. |
| `priority_sensitive` | ◦ | ✗ | ✔ | ◦ | ✗ | ✗ | Priority must dominate, but current MLFQ snapshot wins because aging hides the difference on a 5-proc trace. |

**The xv6 profiles have a recommendation-diversity gap.** All four profiles
make the LLM (and the regret evaluator) pick MLFQ. `docs/algorithm_decision_diversity_audit.md`
and the dashboard `CounterfactualMetricView` already surface this, but the
workloads themselves are the root cause: every profile is small enough that
MLFQ's aging makes it the “safe” answer.

---

## 3. Gaps and proposed curated workloads

We need workloads that *force* the LLM to pick something other than MLFQ to
be SUCCESS. The four proposals below mirror the structure of the existing
`schedtest` profiles (5–8 procs, tick budget ≤ 200) so they can be added
without changing the trace pipeline.

### 3.1 `pure_batch` — FCFS sweet spot

```text
n=5, all priority 5, all "cpu":
  (0, 12), (1, 10), (2, 14), (3, 11), (4, 13)
```

- No I/O, no interactive jobs, priorities all equal → MLFQ aging adds no
  signal; FCFS minimizes context-switch cost, RR is wasted preemption.
- Expected SUCCESS algorithm: **FCFS** on `avg_turnaround_time`.

### 3.2 `short_burst_cluster` — SJF sweet spot

```text
n=6, priority 5, "interactive":
  (0,1) (0,2) (0,1) (0,3) (0,2) (0,1)
```

- All-zero arrival, tightly clustered short bursts → classic SJF setup.
- Expected SUCCESS algorithm: **SJF** on `avg_waiting_time`.

### 3.3 `bursty_long_tail` — SRTF sweet spot

```text
n=5:
  (0, 20, prio 5, cpu)     ← long job arrives first
  (2, 2,  prio 5, interactive)
  (4, 1,  prio 5, interactive)
  (6, 3,  prio 5, interactive)
  (8, 2,  prio 5, interactive)
```

- A long job is half-done when shorter jobs arrive — only SRTF preempts to
  the shorter one.
- Expected SUCCESS algorithm: **SRTF** on `avg_response_time`.

### 3.4 `priority_critical` — Priority sweet spot (without starving)

```text
n=5:
  (0, 8,  prio 7, cpu)     ← background CPU work
  (1, 2,  prio 1, interactive) ← top-priority
  (3, 3,  prio 2, interactive)
  (5, 2,  prio 1, interactive)
  (8, 4,  prio 3, mixed)
```

- Clear priority hierarchy, but the low-priority job is short enough that
  aging never has to rescue it → Priority+Aging wins cleanly.
- Expected SUCCESS algorithm: **PRIORITY** on `avg_response_time`.

### 3.5 (Already present, keep) — `starvation_risk` / `interactive_heavy`

- `starvation_risk.json` already forces FAIL on naive Priority — keep as the
  **FAIL/feedback demonstrator**.
- `interactive_heavy.json` already favors RR/MLFQ — keep as the **RR
  baseline demonstrator**.

### 3.6 Resulting coverage

| Algorithm | Workload that should make the LLM pick it |
|---|---|
| RR | `interactive_heavy` |
| FCFS | `pure_batch` (NEW) |
| PRIORITY | `priority_critical` (NEW) |
| MLFQ | `mixed_workload` |
| SJF | `short_burst_cluster` (NEW) |
| SRTF | `bursty_long_tail` (NEW) |
| (FAIL/feedback) | `starvation_risk` |

After adding the four new profiles, every algorithm has at least one
workload that proves the LLM can find it.

---

## 4. Seed-based random workload generator (design only)

The goal is **reproducible variation**: same seed → same workload; different
seed → statistically similar workload that still hits the algorithmic
target. This protects the demo from cherry-picking and gives the
multi-seed evaluator (see `evaluation_criteria_audit.md` §7) something
non-trivial to chew on.

### 4.1 CLI

```bash
python3 tools/workload_generator.py \
    --profile short_burst_cluster \
    --seed 42 \
    --out workloads/generated/short_burst_cluster_seed42.json
```

### 4.2 Profile-parameterized PRNG

Each profile is a *distribution*, not a fixed table. Example for
`short_burst_cluster`:

```python
{
  "n":              {"choice": [5, 6, 7, 8]},
  "arrival_lambda": 0.0,                      # Poisson, λ=0 → all arrive at t=0
  "burst":          {"truncnorm": {"mean": 2, "std": 1, "low": 1, "high": 5}},
  "priority":       {"const": 5},
  "label":          {"const": "interactive"},
}
```

The generator seeds `random.Random(seed)` and `numpy.random.default_rng(seed)`
explicitly so results are reproducible across hosts.

### 4.3 Mirroring for `schedtest`

Because `xv6-riscv/user/schedtest.c` cannot parse JSON, the generator also
emits a small C header (`workloads/generated/seed42.h`) with a
`struct procdef[]` literal:

```c
static struct workload SEED42 = { "short_burst_cluster", 6, {
   {0, 2, 5, "interactive"},
   {0, 1, 5, "interactive"},
   ...
}};
```

The `schedtest` build picks up the latest header so the *same* generated
workload runs in both xv6 and the simulator. (Compile-time only — runtime
JSON parsing in xv6 is explicitly out of scope.)

### 4.4 Acceptance check

A new `scripts/generator_check.py` would, for each (profile, seed) pair:

1. Generate the workload.
2. Run all six algorithms (simulator backend for speed).
3. Assert the “expected SUCCESS algorithm” for that profile is in
   `metrics.json:best_algorithm` for the target metric.

This is the property test the curated workloads currently lack.

### 4.5 Status

**Design only.** Implementation is intentionally **out of scope for the
final demo**; the four new curated profiles in §3 fix the diversity gap
without introducing a new code module.

---

## 5. Recommendation

For the final demo window:

| Priority | Action | Why |
|---|---|---|
| **P0** | Add the four new JSON profiles in §3 (FCFS / PRIORITY / SJF / SRTF sweet spots) to `workloads/`. Do **not** rebuild snapshots yet — the existing 4 xv6 snapshots are GREEN. | Lets the live simulator pipeline demonstrate algorithm diversity without changing the xv6 snapshot story. |
| **P0** | Cross-link this matrix from the README §4 (algorithms) so an audience member can ask “which workload proves SRTF wins?” and get an answer. | Closes the “LLM only picks MLFQ” objection. |
| P1 | Add a 5th xv6 `schedtest` profile (`bursty_long_tail`) so at least one xv6 snapshot lands on **SRTF** as the SUCCESS pick. | Closes the diversity gap inside the xv6 path. |
| P2 | Build the generator described in §4. | Post-demo; supports the multi-seed evaluator. |

