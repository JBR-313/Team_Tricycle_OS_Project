# Demo media

Put dashboard screenshots / a short GIF here and embed them in the main README.
Best captures: the dashboard overview after a full run (recommendation + algorithm
comparison + trace + metrics) and, when shown, the runtime-correction card.

Generate data without an API key or QEMU using the offline fixtures, then
screenshot the browser:
```bash
python3 scripts/orchestrator.py --workload interactive --offline-fixture
cd dashboard_live && npm run dev
```
