# Demo Runbook

## Dashboard overview

| Dashboard        | Purpose                               | Port  | Data source           |
|------------------|---------------------------------------|-------|-----------------------|
| `dashboard_test` | UI design / fixture visualization     | 5173  | static demoData.js    |
| `dashboard_live` | Final project dashboard               | 5174  | public/live-data/     |

---

## Run dashboard_test (static UI fixture)

```bash
cd dashboard_test
npm install
npm run dev
# open http://localhost:5173
```

No pipeline needed. Uses hardcoded fixture data.

---

## Run dashboard_live (real generated data)

### Step 1 — generate live data

```bash
# Simulator mode (default)
python3 scripts/run_live_dashboard_pipeline.py

# With a specific workload
python3 scripts/run_live_dashboard_pipeline.py \
  --workload workloads/short_jobs.json

# xv6 log mode (when raw xv6 output is available)
python3 scripts/run_live_dashboard_pipeline.py \
  --mode xv6-log \
  --xv6-log /path/to/xv6_console.log
```

Output goes to `dashboard_live/public/live-data/`.

### Step 2 — start dashboard_live

```bash
cd dashboard_live
npm install
npm run dev
# open http://localhost:5174
```

### Step 3 — build for production

```bash
cd dashboard_live
npm run build
```

---

## Streamlit dashboard (legacy)

```bash
streamlit run dashboard/dashboard.py
```

---

## xv6 (QEMU)

```bash
cd xv6-riscv
make qemu
```

---

## Python tools

```bash
# Workload analysis
python3 tools/workload_analyzer.py --workload workloads/interactive_heavy.json

# Simulator only
python3 tools/scheduler_simulator.py \
  --workload workloads/interactive_heavy.json \
  --guard outputs/guard_decision.json \
  --out-dir outputs/live

# Metrics only
python3 tools/metrics.py \
  --traces-dir outputs/live \
  --output outputs/live/metrics.json
```

---

## Data contract

See `docs/dashboard_data_contract.md` for file schemas.

---

## Limitations

- Live dashboard currently uses host-side simulator, not real xv6 kernel.
- xv6 integration: parse raw QEMU console output via `--mode xv6-log` once `tools/trace_parser.py` is adapted.
- Live mode polls `manifest.json` every 1 second (no websocket yet).
