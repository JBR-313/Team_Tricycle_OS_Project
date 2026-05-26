# README — Current-State Audit

Pre-modernization audit of `README.md` against the actual main
(`8551361`). Lists every claim that matches the code today, every
claim that overstates, and every recent feature the README still
fails to mention. Sets up the surgical edit list for the follow-up
PR — no README edits in this PR.

> Companion to `docs/implementation_status.md` (per-feature
> evidence) and `docs/algorithm_decision_diversity_audit.md` (the
> honest LLM-pick story).

---

## 1. Sections that match current code (keep)

| README section | Status | Notes |
|----------------|--------|-------|
| Title / one-line message | ✓ | "LLM suggests. Algorithm Guard checks. xv6 executes. Metrics verify. GUI explains." still accurate. |
| §1 Project Direction (bullets 1, 2, 4, 5) | ✓ | "interprets / recommends / explains" all true. **One bullet overclaims** — see §2. |
| §2 Core Idea | ✓ | Orchestrator-centric pipeline mirrors `scripts/orchestrator.py` today. |
| §3 System Principle table | ✓ | All component roles match. |
| §4 Supported Scheduling Algorithms | ✓ | xv6 ships RR / FCFS / Priority+Aging / MLFQ / SJF / SRTF. |
| §6 Algorithm Guard | ✓ | Guard exists at `tools/algorithm_guard.py`. |
| §7 Scheduling Trace Log | ✓ | `[SCHED]` / `[SCHEDTEST]` lines emitted by `xv6-riscv/kernel/proc.c` + `user/schedtest.c`. |
| §8 Metrics Evaluator (formulae) | ✓ | Matches `tools/metrics.py`. |
| §11 → §12 (planned data files & repo structure) | partial | Files are correct; the "Planned" framing is dated — they exist now (see §3 below). |
| §12 Dashboard roles + Run dashboard_live | ✓ | Recent. |
| **§12.1 Implementation Status** table | ✓ | This table is already honest and current. |
| §13 OS Concepts | ✓ | |
| §14 Tech Stack | ✓ | |

## 2. Claims that **overclaim** (must be softened)

| README spot | Current text | Honest text |
|-------------|--------------|-------------|
| **Intro lede** (line 7) | "...proposes runtime corrections when scheduling problems are detected, and explains the execution result in natural language." | The "proposes runtime corrections" half is **Partial / Future Work**. Today only `tools/event_detector.py` exists — the proposer / LLM call / guard re-check / apply / `CORRECTION_APPLIED` trace event are not wired. Soften: "...explains the execution result in natural language. (Runtime correction is partial future work — see §12.1.)" |
| **§1 third bullet** (line 28) | "The LLM proposes runtime corrections when trace monitoring detects problems." | Same. Either remove the bullet or mark it `(Partial / Future Work)`. |
| **§1 fifth bullet** (line 30) | "The LLM generates feedback rules for future recommendations." | No production feedback-rule generator exists in `tools/`. Mark as Partial / Future Work or remove. |
| **§5.2 Running → 5.2.1 Runtime Correction Proposer** (lines 229–273) | A full subsection that describes correction types, JSON shape, and "applied from the next scheduling point". | Re-label the subsection heading "Runtime Correction Proposer **(Partial / Future Work)**". Keep the narrative as the design target, but add an opening line that this is the **planned** loop, not the shipped one. Cite the §12.1 status row. |
| **§5.3.2 Feedback Rule Generator** (lines 306–324) | Same pattern — describes shipped feedback rules. | Same fix. Tag the subsection heading with `(Partial / Future Work)` and a one-line "design target, not shipped today" lead-in. |
| **§9 GUI Observability Dashboard** (line 434) | Bullet list includes "runtime correction event" and "Feedback Rule Generator result". | Remove those two bullets, or replace with what the dashboard actually shows: backend badge, snapshot selector, **DemoGuide**, **RecommendationEvidence ("Why this algorithm?")**, **CounterfactualMetricView ("Metric trade-off")**, AlgorithmComparison + MetricVisualization, EvaluationResult, LLMExplanation. |
| **§10 Example Demo Scenario** (steps 4–7, lines 459–471) | The scenario claims a closed runtime-correction loop ("Trace Monitor detects starvation → LLM correction → Guard validates → xv6 applies"). | Mark the scenario as the **target** narrative (Partial / Future Work) with an explicit caveat, OR rewrite to the actual on-stage flow: workload → recommendation → guard → xv6 schedtest → comparison + judgment → snapshot selector across profiles. |

## 3. Recent features the README **does not mention** (must be added)

These features exist on `main` today and the modernization PR
should mention them in the relevant section, not invent a new one:

| Feature | Where on main | Where to mention in README |
|---------|---------------|----------------------------|
| `scripts/final_demo_check.py` (one-command demo prep — PR #17) | already cited in §12.1 status table, but missing from §"Run Commands" and §"Run dashboard_live (primary)" | Add as Step 1 of the Quick-Start block; keep `orchestrator.py` as the explicit step-2 alternative. |
| `tools/validate_dashboard_contract.py --strict --snapshots ...` (PR #36) | already in §12.1 status table | Mention in §11 Data Files near the live-data layout. |
| Multi-profile **snapshot selector** + committed snapshots for interactive / cpu_bound / mixed / priority_sensitive (PRs #37, #38) | already in §12.1 status table | Add a one-paragraph "Multi-profile snapshots" note in the Run dashboard_live block, and add `snapshots/<profile>/` + `snapshots_manifest.json` to §11 Data Files. |
| **RecommendationEvidence** card / "Why this algorithm?" (PR #32) | not mentioned in §9 GUI bullets | Add to §9 GUI bullets. |
| **CounterfactualMetricView** card / "Metric trade-off" (PR #43) | not mentioned in §9 GUI bullets | Add to §9 GUI bullets. |
| **DemoGuide** card + click-to-flash (PRs #46, #47) | not mentioned in §9 GUI bullets | Add to §9 GUI bullets. |
| `scripts/multi_profile_demo_check.py` (PR #26) | not in §12.1 status table either | Mention alongside `final_demo_check.py` as the broader-confidence script. |
| `scripts/analyze_algorithm_winners.py` (PR #41) | not in §12.1 status table either | Mention in §11 Data Files or §"OS Concepts → Metrics" as the offline winner verifier. |
| `.github/workflows/ci.yml` lightweight CI (PR #27) | not in §12.1 status table either | Brief mention in the Implementation Status section explaining what CI validates (no xv6/QEMU on hosted runners). |
| `dashboard_live` header snapshot pill (`SNAPSHOT: <profile>`) (PR #37) | not in the README's "dashboard_live shows" bullets | Add a bullet under §12 "Run dashboard_live (primary)". |

## 4. Stale framing (cosmetic but worth fixing)

- §11 is titled "Data Files" but the body uses the word "Planned"
  with `outputs/*.json`. The shipped path is
  `dashboard_live/public/live-data/*` plus
  `dashboard_live/public/live-data/snapshots/*`. Move "Planned"
  files into a Future Work note; show the actual layout.
- §12 is titled "Planned Repository Structure" — the structure
  shown is mostly the real layout today. Drop the word "Planned"
  or move it under §10/§11 as "Actual layout".
- The Run Commands block at the top of the file (search for
  `make qemu` / `streamlit`) lists Streamlit prominently. Mark
  Streamlit as legacy in that block too, so first-time readers
  don't follow the legacy path.

## 5. Proposed surgical edits (for the modernization PR)

The follow-up PR should make the minimum set of edits below.
Every edit references a line range so the diff stays auditable.
None of them change scheduler / data-contract behavior.

1. **Intro lede** — soften runtime-correction wording (one
   sentence).
2. **§1 bullet list** — tag the two future-work bullets
   `(Partial / Future Work)`.
3. **§5.2.1 + §5.3.2 headings** — append `(Partial / Future Work)`
   and add a one-line lead-in linking to §12.1.
4. **§9 GUI bullet list** — remove the two correction/feedback
   bullets; add DemoGuide / RecommendationEvidence /
   CounterfactualMetricView / snapshot selector bullets.
5. **§10 demo scenario** — rewrite around the **shipped** flow
   (workload → recommendation → guard → xv6 → metrics →
   snapshot tour), keep the starvation/correction narrative as
   a clearly-labeled "target narrative (Future Work)" sub-block.
6. **§11 Data Files** — replace `outputs/*.json` listing with
   `dashboard_live/public/live-data/*` plus
   `live-data/snapshots/<profile>/*` and `snapshots_manifest.json`.
7. **Quick-Start block at top** — make
   `python3 scripts/final_demo_check.py` the primary Step 1.
8. **§12.1 status table** — extend with three rows for the
   three recent additions not yet listed there
   (`multi_profile_demo_check.py`, `analyze_algorithm_winners.py`,
   `RecommendationEvidence + CounterfactualMetricView + DemoGuide`
   cards).
9. **Run dashboard_live block** — mention the snapshot selector
   and the SNAPSHOT pill.

## 6. Out of scope (this audit + the modernization PR both)

- Do **not** implement runtime correction. The narrative stays
  Partial / Future Work.
- Do **not** change scheduler / xv6 / orchestrator / metrics
  behavior.
- Do **not** change `docs/dashboard_data_contract.md`.
- Do **not** redesign the dashboard UI.
- The follow-up PR is README-only; cross-link drift in other
  docs (if any) is a separate small P1.
