# Demo Day Checklist

Single, ordered checklist to paste into the terminal on demo day. Keep
this on one screen.

> Companion docs: `docs/final_demo_acceptance.md` (release contract),
> `docs/demo_runbook.md` (extended runbook), `docs/presentation_defense_notes.md`
> (audience Q&A).

---

## A. Run-the-pipeline (terminal 1)

```bash
# 1. Refresh main
git checkout main
git pull --ff-only origin main

# 2. Run the xv6 backend end-to-end (build + 6 algorithms + metrics + publish)
python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all

# 3. Strict-validate the published live-data (must exit 0)
python3 tools/validate_dashboard_contract.py --strict --dir dashboard_live/public/live-data
```

Steps 2 + 3 are also wrapped by one command:

```bash
python3 scripts/final_demo_check.py
```

It runs `py_compile`, the orchestrator, and the strict validator in
order, and bails on the first failure. On success it prints the
exact next step (the dashboard launch line below).

---

## B. Start the dashboard (terminal 2)

```bash
cd dashboard_live
npm install        # first time only
npm run dev        # opens http://localhost:5174
```

Do not auto-open a browser from the script — keep this terminal
visible so the audience sees the dev-server log.

---

## C. What to click / show in `dashboard_live`

Read these in order. Each step should take 30–60 seconds.

1. **Header bar (left → right).**
   - Brand `LLM Sched Copilot · LIVE`.
   - **Data status** — manifest version (e.g. `v15`), last-updated
     timestamp, live polling dot.
   - **Backend badge** — must read `Backend: XV6 TRACE` for a real run.
     If it says `SIMULATOR FALLBACK` or `FALLBACK`, announce it.
   - **Manifest meta** — `workload`, `llm`, `algos`, `seed`, `events`.
   - **Algorithm selector** — switch through each algorithm; the
     LLM-selected one is first.
   - **Replay / Live** toggle and tick slider.

2. **Workload Summary card** — the synthesized profile interpretation
   the LLM was given.

3. **LLM Recommendation + Algorithm Guard cards** — the chosen
   algorithm, parameters, and the Guard's accepted/rejected decision.

4. **Main Gantt / Process Lanes / Trace Stack** — the per-algorithm
   timeline. Demonstrates that this is real xv6 trace data — the
   `[SCHED]` events are time-stamped per tick.

5. **Algorithm Comparison + Metric Visualization** — same workload,
   every algorithm, the target-metric `Judge` column. Switch the
   metric dropdown to show the Judge re-derives.

6. **LLM Explanation / Evaluation Result** — natural-language summary
   of the trace, regret score, and overall judgment.

---

## D. Fallback — if xv6/QEMU breaks on the demo machine

If the kernel won't build, QEMU is missing, or a serial-console
capture times out:

```bash
python3 scripts/final_demo_check.py --backend simulator
# refresh the dashboard; the badge will switch to SIMULATOR FALLBACK
```

Announce the fallback to the audience — the dashboard already
downgrades the badge to `Backend: SIMULATOR FALLBACK` to make it
visible.

---

## E. Acknowledged limitations (be honest if asked)

- No websocket — `manifest.json` is polled.
- Runtime correction loop is partial: event detection only;
  propose / LLM / guard re-check / apply / `CORRECTION_APPLIED` not
  wired. Marked `Partial / Future Work`.
- Solar Pro 3 fallback: missing `.env` ⇒ demo recommendation,
  manifest stamps `metadata_source=demo_fallback`, badge becomes
  `FALLBACK`.
- xv6 traces are short educational traces (~30–80 events per algo,
  5 children per profile). Starvation and Judge rules apply an
  absolute tick floor so sub-tick noise does not flag — see PR #14
  and PR #15.

---

## F. Sign-off (tick on demo day)

- [ ] `python3 scripts/final_demo_check.py` exits 0.
- [ ] Dashboard header reads `Backend: XV6 TRACE`.
- [ ] All six algorithm tabs render a Gantt and the comparison row.
- [ ] LLM Recommendation card shows a real recommendation (not
      `FALLBACK`).
- [ ] Algorithm Guard card shows `accepted`.

If any row is unchecked, debug before going on stage — do not
work around it locally.
