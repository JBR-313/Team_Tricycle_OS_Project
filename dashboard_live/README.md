# dashboard_live — observability dashboard (React/Vite)

Visualizes a real run: the LLM recommendation, the Algorithm Guard decision, each
algorithm's xv6 trace (Gantt / process lanes / state), metrics + comparison, the
runtime correction, and the natural-language explanation. It reads generated data
from `public/live-data/` (written by `scripts/orchestrator.py` step [5]); Live mode
polls `manifest.json` every 1s, and the `SourceBadge` shows provenance
(`XV6 TRACE` / `FALLBACK`).

## Run
```bash
python3 scripts/orchestrator.py --workload interactive   # 1) generate live-data on xv6
cd dashboard_live && npm install && npm run dev           # 2) http://localhost:5174
```
Data file schemas: `docs/dashboard_data_contract.md`.
