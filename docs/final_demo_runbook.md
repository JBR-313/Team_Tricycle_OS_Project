# Final Demo Runbook

Step-by-step to run the demo, plus troubleshooting. Commands are run from the
repo root unless noted.

## 1. Setup

```bash
# Python deps (pipeline)
python3 -m pip install -r requirements.txt
# Dev deps (tests) — optional, offline
python3 -m pip install -r requirements-dev.txt

# Dashboard deps
cd dashboard_live && npm ci && cd ..
```

Toolchain for the xv6 primary path:
- `qemu-system-riscv64`
- `riscv64-unknown-elf-gcc` (or `riscv64-linux-gnu-gcc`)

Check quickly:
```bash
python3 scripts/final_demo_check.py        # PASS/FAIL summary (skips xv6 if no toolchain)
```

## 2. API key setup

```bash
cp .env.example .env          # then edit .env and set UPSTAGE_API_KEY=...
```
- `.env` is gitignored; never commit it.
- Without a key, use `--offline-fixture` (recommendation comes from committed
  fixtures; manifest stamped `metadata_source=demo_fallback`).

## 3. xv6 primary demo (the core claim)

```bash
python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all
```
This builds the kernel, boots QEMU, runs `schedtest` for each algorithm
(LLM-selected first), parses the **real serial console**, aggregates metrics,
exports to `dashboard_live/public/live-data/`, runs the correction apply loop,
the trace explainer [8], and the FAIL-only feedback step [9].

Or via Make:
```bash
make demo-xv6
```

## 4. Simulator fallback (no QEMU / no key)

```bash
python3 scripts/orchestrator.py --backend simulator --seed 42 \
  --workload interactive --run-all --offline-fixture
# or
make demo-sim
```
The dashboard badge will read `SIMULATOR` (and `·fixture` when offline).

## 5. Dashboard + run-server

```bash
# Terminal A — run-server (the dashboard RUN button calls this)
python3 scripts/run_server.py            # serves on :8765

# Terminal B — dashboard dev server
cd dashboard_live && npm run dev          # http://localhost:5174
```

## 6. Expected UI flow

```
Initial (IDLE)  → press RUN ANALYSIS
  → LLM reveal (analyzing → recommendation → guard → explanation)
  → READY TO VISUALIZE → press RUN VISUALIZATION
  → replay (ms clock, Super Slow / Slow / Real Time)
  → REPLAY DONE → press VIEW EVALUATION
      → Evaluation Result + Algorithm Comparison + Metric Visualization
      → LLM Explanation (post-run) card (trace_explanation.json)
```
- Default RUN = **xv6 primary**. The data-source badge confirms `XV6 TRACE`.
- Pre-analysis screen has no recommendation leak and no execution preview.

## 7. Pre-demo one-shot check

```bash
python3 scripts/final_demo_check.py            # fast (skips xv6 if no toolchain)
python3 scripts/final_demo_check.py --with-xv6 # force-require the xv6 smoke
make final-demo-check
```

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `LLM advisor failed … UPSTAGE_API_KEY` | no/invalid key, strict mode | set `.env`, or add `--offline-fixture` |
| RUN errors with "xv6 primary demo could not run" | QEMU / RISC-V gcc missing | install toolchain, or pick the SIMULATOR fallback |
| `no RUN_END captured` | QEMU boot slow / schedtest timeout | re-run; increase `QEMU_RUN_TIMEOUT` in `orchestrator.py` |
| Dashboard shows `NO DATA` / `FALLBACK` | no live-data, run-server offline | run the orchestrator, or start `run_server.py` |
| Trace Explanation = NOT AVAILABLE | LLM unavailable for step [8] | set a key, or accept the honest placeholder |
| contract validator WARN/ERROR | stale/missing live-data field | re-run the orchestrator to regenerate |

## 9. Reset / clean

```bash
make clean                                  # python caches
git checkout -- dashboard_live/public/live-data  # restore committed demo data
```
