# Demo media (course §3)

§3 requires demo screenshots and/or a short demo video/GIF in the README. Put them
here and embed them in README §8.

## What to capture
1. `dashboard_overview.png` — the running dashboard after a full run (recommendation,
   algorithm comparison, trace, metrics, correction card).
2. `correction.png` — the safety-net moment (e.g. MLFQ judged FAIL → corrected to RR,
   turnaround improved) — this is the strongest single screenshot.
3. `demo.gif` *(optional)* — a short capture of a RUN.

## How to produce
```bash
# 1) generate live data (offline path needs no API key)
python3 scripts/orchestrator.py --backend simulator --offline-fixture
# 2) run the dashboard and screenshot it in the browser
cd dashboard_live && npm run dev      # open the shown localhost URL, then screenshot
```
Then reference them in README §8, e.g. `![dashboard](docs/images/dashboard_overview.png)`.
