# Presenter Script — 3-minute Demo

A tight, spoken-aloud script for the live demo. Six beats, ~30 seconds
each. Honest about what is real and what is intentional future work.

> Pair with `docs/demo_checklist.md` (terminal commands), `docs/
> final_demo_acceptance.md` (release contract), and `docs/
> presentation_defense_notes.md` (deeper Q&A).

> One-line message: **LLM suggests. Algorithm Guard checks. xv6
> executes. Metrics verify. GUI explains.**

---

## Beat 1 — The problem (≈30s)

> CPU scheduling decisions are usually visible only as terminal logs.
> Choosing the right algorithm — and tuning its parameters — for a
> given workload is a judgment call, and the consequences only show
> up after you run it.
>
> Our project asks: can an LLM act as a **decision-support layer** for
> the xv6 scheduler? Not the scheduler itself — that stays in the
> kernel — but the advisor that picks the algorithm, the guard that
> validates the pick, and the explainer that turns the trace into
> something a human can understand.

→ Show the dashboard header. Backend badge must read `XV6 TRACE`.
The top-left **Demo flow** card lists the 5 steps you'll walk
through — click any numbered chip during the demo to flash the
matching element on screen (no slide change needed).

---

## Beat 2 — LLM recommendation (≈30s)

> Before the run, the workload summary goes to Solar Pro 3. The LLM
> answers with a recommended algorithm, parameters, target metric,
> and a one-line reason — all as JSON.
>
> For this interactive workload, the LLM picked **MLFQ** with three
> queues. The dashboard shows the full recommendation card on the
> right; it is exactly what the LLM returned, no post-editing.

→ Point at the **LLM Recommendation** card for the algorithm + target
+ params, then the **"Why this algorithm?"** evidence card right below.
The evidence card consolidates the workload traits the LLM keyed off
(interactive ratio, avg burst, avg priority) next to the LLM's full
reason and the LLM confidence — that one card answers the "why" in
about five seconds. Read the LLM reason aloud directly from it.

The provenance pill in that card tells the audience whether they're
looking at a real LLM call (`LLM: solar-pro3`) or the committed demo
fallback (`demo fallback (no LLM call)` — warning-tinted). On stage,
this should read `LLM: solar-pro3`.

---

## Beat 3 — Algorithm Guard (≈30s)

> An LLM can hallucinate. So every recommendation passes through the
> Algorithm Guard before xv6 sees it. The Guard checks four things:
> the algorithm is actually implemented in the kernel, parameters
> are in safe ranges, the JSON schema is correct, and the burst
> prediction rule isn't violated.
>
> If anything fails, the Guard rejects the recommendation and falls
> back to RR. Today's run shows the decision was **accepted** — the
> recommendation reached xv6 intact.

→ Point at the **Algorithm Guard** card showing `accepted`.

---

## Beat 4 — xv6 execution (≈30s)

> Now the important part: the data on screen is from a **real xv6
> kernel** running under QEMU. The orchestrator built the kernel
> with `make CPUS=1`, booted QEMU, and typed `schedtest mlfq 42
> interactive` into the shell. The kernel printed `[SCHED]` and
> `[SCHEDTEST]` lines to the console, and we parsed them into the
> Gantt chart you see.
>
> Every algorithm in the comparison ran the **same** workload — same
> seed, same profile, same workload file — so the comparison isn't
> confounded by different random inputs.

→ Show the **Main Gantt / Process Lanes** for MLFQ, then cycle the
algorithm selector through one or two others. Mention "same workload
across every algorithm".

If the header shows the **Snapshot selector**, end this beat by
switching to one other profile (e.g. `cpu_bound`) and pointing out
that the recommendation, the trace, and the Judge all re-derive for
a completely different xv6 workload — same Advisor → Guard → xv6 →
Metrics loop, four different curated workloads. The backend badge
stays `XV6 TRACE` because every snapshot is real xv6. Return to
`Default (current run)` before moving on.

---

## Beat 5 — Metric comparison (≈30s)

> The Metrics Evaluator turns the trace into hard numbers: average
> waiting time, response time, turnaround time, throughput,
> preemptions, starvation. Then the dashboard's Judge column re-
> derives `SUCCESS`, `NEAR-SUCCESS`, or `FAIL` for whichever metric
> you select in the dropdown, against the best algorithm on the same
> workload.
>
> For this run the LLM-picked MLFQ matches the best response time,
> regret score 0.0 — the LLM made the right call. Switch the metric
> dropdown to see the Judge re-derive on a different objective.

→ Open the **Algorithm Comparison + Metric Visualization** card.
Show the Judge column under `avg_response_time`, then flip the
metric dropdown to e.g. `avg_waiting_time`, point out that the Judge
re-derives.

If anyone asks "why does the LLM always pick MLFQ?", point at the
**Metric trade-off** card in the left column. It shows the best
algorithm per metric on this workload — the response-time row is
highlighted because that's the current target. On
`priority_sensitive` you'll see RR winning waiting / turnaround /
max-waiting; on `interactive` Priority wins turnaround. The LLM is
honestly best on the metric it was asked to optimise, and the card
makes the trade-off visible without changing any scheduler
behaviour.

---

## Beat 6 — Honest limitations (≈30s)

> Three things we are deliberately honest about:
>
> 1. **Runtime correction is partial.** Today's pipeline does the
>    *before* and *after* — it recommends and explains. The closed
>    loop where the LLM proposes a mid-run correction, the Guard
>    re-checks it, and xv6 applies it at the next scheduling point
>    is `event_detector.py` only. The rest is intentional Future
>    Work.
> 2. **The dashboard polls.** There is no websocket; the GUI updates
>    on the next `manifest.json` poll. Live mode reflects the most
>    recent orchestrator publish, not a real-time stream.
> 3. **xv6 traces are short educational traces.** Five children per
>    profile, tens of events per algorithm. The metrics and Judge
>    rules apply absolute tick floors so sub-tick noise doesn't
>    falsely flag starvation or `FAIL`.
>
> Everything else on the dashboard — the workload, the
> recommendation, the guard decision, the trace, the metrics, the
> explanation — was actually produced by the pipeline you see.

→ Wrap on the one-liner: "LLM suggests. Guard checks. xv6 executes.
Metrics verify. GUI explains."

---

## Things to NOT say

- "The LLM is making scheduling decisions every tick." (It is not —
  the kernel does. The LLM advises before, explains after.)
- "Runtime correction is closed-loop." (It is **Partial / Future
  Work**.)
- "The trace updates in real time." (Polling, not streaming.)
- "The simulator output is real xv6 execution." (When the badge
  reads `SIMULATOR FALLBACK` or `FALLBACK`, announce it.)

## If the API is down (`Backend: FALLBACK`)

State it plainly:

> "The Solar API isn't reachable on this machine, so the
> recommendation came from our committed demo fallback — the
> dashboard badge says `FALLBACK`, which is the project's honesty
> signal. The xv6 execution, parsing, and metrics are still real.
> The recommendation isn't from the live LLM right now."

Then continue with beats 3–6 as usual.
