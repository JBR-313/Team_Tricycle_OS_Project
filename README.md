# LLM Sched Copilot

An **LLM-assisted scheduler for xv6** (course project, *Direction B — LLM for OS*).
An LLM (Upstage Solar Pro 3) proposes a scheduling algorithm, parameters, and
per-process burst hints from visible workload features; an **Algorithm Guard**
validates them; and **xv6 under QEMU is the sole execution authority** — the LLM
is never in the kernel hot path and never picks the next process. The team
implements six in-kernel scheduling algorithms (RR, FCFS, Priority+Aging, MLFQ,
SJF, SRTF), the syscalls, and the host-side pipeline in this repo.

We measured, on the **real, now-reproducible** kernel (deterministic QEMU
`-icount` + fixed-iteration bursts), **where an LLM helps and where it doesn't**:
as the quantitative decision-maker (algorithm choice, mid-run switching, numeric
burst prediction) it **loses** to cheap classical methods (with negative
controls); at the **human interface** (natural-language workload intent → config,
and trace explanation) it **wins** (8/8). The honest conclusion: *put the LLM at
the OS's human-facing layer, not its decision hot path.*

## Quick start
```bash
cp .env.example .env                          # add UPSTAGE_API_KEY
python3 scripts/orchestrator.py --workload interactive          # full pipeline on xv6
python3 scripts/orchestrator.py --intent "Interactive desktop; latency matters."  # NL → config
cd dashboard_live && npm install && npm run dev                 # dashboard (:5174)
cd xv6-riscv && make qemu                                       # raw kernel (Ctrl-A X to quit)
```

## Evidence (reproduce)
- `python3 experiments/burst_random_eval.py --signal multi` → `outputs/random_eval/RESULTS.md`
- `python3 experiments/intent_eval.py` → `outputs/intent_eval/RESULTS.md`
- `python3 experiments/xv6_determinism_probe.py` (confirms reproducibility)

## Layout
`xv6-riscv/` kernel (execution authority) · `scripts/orchestrator.py` host control
plane · `tools/` pipeline modules · `experiments/` evidence tools · `workloads/`
inputs · `dashboard_live/` React dashboard · `docs/` design notes & course
deliverables (`technical_report.md`, `development_process.md`, `presentation/`).
