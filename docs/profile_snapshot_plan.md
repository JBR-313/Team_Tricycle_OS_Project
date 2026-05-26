# Multi-Profile xv6 Snapshots — Plan

This document plans the snapshot feature so dashboard_live can show
xv6 results for any of the four curated workload profiles without
re-running QEMU live. It is the spec for the follow-up PRs in this
goal; no code lands in this PR.

> Read alongside `docs/dashboard_data_contract.md` (the canonical
> data contract) and `docs/xv6_profile_support.md` (which profiles
> actually work on xv6 today).

---

## 1. Current shape

`dashboard_live/public/live-data/` is a **flat directory** with the
files the orchestrator publishes per run:

```
dashboard_live/public/live-data/
├── manifest.json          # backend, version, seed, workload, …
├── recommendation.json
├── guard_decision.json
├── workload_summary.json
├── metrics.json
├── trace_explanation.json
├── trace_rr.jsonl
├── trace_fcfs.jsonl
├── trace_priority.jsonl
├── trace_mlfq.jsonl
├── trace_sjf.jsonl
└── trace_srtf.jsonl
```

`dashboard_live/src/data/liveDataClient.js` loads everything from a
single `BASE = '/live-data'` prefix. The orchestrator overwrites this
directory on every run; only one workload's results live there at a
time.

`scripts/multi_profile_demo_check.py` already exercises every curated
profile on the xv6 backend (`interactive`, `cpu_bound`, `mixed`,
`priority_sensitive`) and confirms they all pass strict validation —
but it overwrites `live-data/` on each profile, so the dashboard only
ever reflects the last one.

---

## 2. Proposed layout

Add a new sub-tree alongside the existing flat files. **The existing
flat files do not move.** They remain the default live-data run that
`scripts/final_demo_check.py` and `scripts/orchestrator.py` publish.

```
dashboard_live/public/live-data/
├── … (existing flat files, unchanged) …
├── snapshots_manifest.json        # index of available snapshots
└── snapshots/
    ├── interactive/
    │   ├── manifest.json
    │   ├── recommendation.json
    │   ├── guard_decision.json
    │   ├── workload_summary.json
    │   ├── metrics.json
    │   ├── trace_explanation.json
    │   ├── trace_rr.jsonl
    │   ├── trace_fcfs.jsonl
    │   ├── trace_priority.jsonl
    │   ├── trace_mlfq.jsonl
    │   ├── trace_sjf.jsonl
    │   └── trace_srtf.jsonl
    ├── cpu_bound/        (same shape)
    ├── mixed/            (same shape)
    └── priority_sensitive/ (same shape)
```

Each `snapshots/<profile>/` directory is a **byte-for-byte copy** of
what the orchestrator would publish for that profile — same schema,
no new fields. The dashboard can therefore load a snapshot by
swapping the loader base prefix from `/live-data` to
`/live-data/snapshots/<profile>` without any other change to the
component tree.

### `snapshots_manifest.json`

Top-level index the dashboard reads to populate the selector.
Existence is the gate — if the file is missing, the snapshot
selector hides itself and the dashboard behaves exactly as today.

```jsonc
{
  "version": 1,
  "generated_at": "2026-05-26T07:00:00Z",
  "profiles": [
    {
      "profile": "interactive",
      "path": "snapshots/interactive",
      "backend": "xv6",
      "seed": 42,
      "llm_selected_algorithm": "MLFQ",
      "judgment": "SUCCESS",
      "regret_score": 0.0,
      "generated_at": "2026-05-26T06:35:29Z"
    },
    { "profile": "cpu_bound", "path": "snapshots/cpu_bound", ... },
    { "profile": "mixed", "path": "snapshots/mixed", ... },
    { "profile": "priority_sensitive", "path": "snapshots/priority_sensitive", ... }
  ]
}
```

Required keys per profile entry: `profile`, `path`, `backend`,
`llm_selected_algorithm`. Optional but recommended: `seed`,
`judgment`, `regret_score`, `generated_at`. Anything else
(`workload_type`, etc.) is allowed but not required.

---

## 3. Export script

Add a new `scripts/export_profile_snapshots.py` (preferred over
extending `multi_profile_demo_check.py` so the responsibilities stay
separate: the existing script is a green/red checker, this one is a
publisher). Behavior:

1. For each xv6-supported profile (read from orchestrator's
   `XV6_PROFILES`):
   - Run the orchestrator with `--backend xv6 --seed N --workload
     <profile> --run-all`. The orchestrator publishes to the default
     live-data dir as always.
   - Strict-validate that live-data dir; abort the snapshot for this
     profile if validation fails.
   - `cp` the validated live-data flat files into
     `dashboard_live/public/live-data/snapshots/<profile>/`.
2. After all profiles, write `snapshots_manifest.json`.
3. **Optional safety:** restore the default live-data to a chosen
   profile (default: `interactive`) at the end, so the dashboard's
   default still shows what `final_demo_check.py` would produce.
   Behind a `--restore-default` flag, default to `interactive`.

CLI sketch:

```bash
python3 scripts/export_profile_snapshots.py
python3 scripts/export_profile_snapshots.py --profiles interactive,cpu_bound
python3 scripts/export_profile_snapshots.py --seed 7 --no-restore-default
```

Exit non-zero if any profile fails validator; the snapshots dir for
that profile is left empty so the dashboard hides it from the
selector.

---

## 4. Validator extension

`tools/validate_dashboard_contract.py --snapshots <dir>` adds a
second pass:

- Discover sub-directories under `snapshots/`.
- For each, run the existing per-dir checks: manifest cross-link,
  metrics comparison, every trace non-empty with ≥1 EXIT,
  recommendation/guard/manifest cross-agreement.
- Report `OK <profile>` or `WARN/ERROR <profile> <detail>`.
- Aggregate to the same OK / WARN / ERROR / exit-code semantics the
  validator already uses.
- Default off; only runs when `--snapshots` is given. This keeps the
  CI run lightweight (CI still validates only the flat live-data).

---

## 5. Dashboard selector plan

Add a tiny selector in the existing `Header.jsx` (no new column, no
layout change). Behavior:

1. On mount, `liveDataClient.js` attempts
   `fetch('/live-data/snapshots_manifest.json')`. If the request
   fails (404 or parse error), `snapshots_manifest` is `null` and
   the selector is **hidden**.
2. If present, the selector renders a `<select>` with options:
   - `Default (current run)` — uses `BASE = '/live-data'` (today's
     behavior).
   - One option per entry in `snapshots_manifest.profiles`.
3. Selecting an entry switches the loader's base to
   `'/live-data/snapshots/<profile>'`. The existing components
   (workload, recommendation, guard, metrics, traces) re-render off
   the new files without changes.
4. The selector's current choice is reflected in a header pill so
   the audience sees which profile is being shown.

Loader changes are minimal: `liveDataClient.js` exports `setBase()`
or accepts an optional `base` argument on each load function. Either
way, the dashboard's component tree does not change — only the URLs
it fetches from.

---

## 6. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Snapshots drift from the demo's claims (stale data shown on stage). | Validator's `--snapshots` pass + CI step on each PR; export script refuses to write a snapshot dir if strict validation fails. |
| Live xv6 results during the demo overwrite the snapshot dir. | The snapshot dirs are in a separate `snapshots/` sub-tree; the orchestrator writes to the flat root only. No collision. |
| Repo bloat from committed JSONL. | A typical xv6 trace is ~30–80 events per algorithm; 6 algos × 4 profiles ≈ 1.6 K events committed. Acceptable; far smaller than `xv6-riscv/kernel/kernel.asm`. |
| Confusion between "live" and "snapshot" data on stage. | Selector pill in the header makes the active source explicit (`SNAPSHOT: cpu_bound` vs default). Backend badge continues to read `XV6 TRACE` because the snapshot itself is xv6. |
| Snapshot generated with `metadata_source=demo_fallback` accidentally committed. | Export script can check `manifest.metadata_source` after orchestrator runs and refuse to write the snapshot if the LLM call fell back to demo. Allowed when explicitly opted in via `--allow-fallback`. |
| Dashboard fetch fails for a profile whose dir doesn't exist (e.g. user manually deleted it). | The dashboard already has a yellow fallback banner; an individual snapshot fetch failure should surface the same banner with profile context, not crash. |

---

## 7. Out of scope for this goal

- No scheduler, xv6 kernel, or orchestrator changes — snapshots are
  pure copies of existing orchestrator output.
- No runtime correction implementation (still Partial / Future Work).
- No new LLM calls; the LLM advisor runs once per profile during
  export, same as today.
- No data-contract expansion: snapshot dirs use the existing schema
  byte-for-byte.

---

## 8. Sequencing of follow-up PRs

1. **P0-2** — add `scripts/export_profile_snapshots.py`. Local
   smoke-run on at least one profile; do not commit live-data churn
   from the default dir.
2. **P0-3** — add `--snapshots` to
   `tools/validate_dashboard_contract.py`.
3. **P0-4** — wire the dashboard selector in `Header.jsx` +
   `liveDataClient.js` base swap. Snapshots may or may not be
   committed yet; the selector hides cleanly when absent.
4. **P0-5 (optional, separate PR)** — generate + commit the four
   xv6 snapshots once P0-2/P0-3/P0-4 are all merged, so the demo
   ships with snapshots ready.
5. **P1** — update `docs/demo_checklist.md` and
   `docs/presenter_script.md` to mention the selector.

Each PR follows the existing one-PR-one-fix loop and keeps
`final_demo_check.py` passing throughout.
