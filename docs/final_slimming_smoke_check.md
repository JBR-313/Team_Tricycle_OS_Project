# Final Slimming Smoke Check

> **Purpose:** verify that the codebase slimming pass did **not** break the
> final demo path. Run top-to-bottom; every section is independent enough to
> skip when the listed prerequisite tool is unavailable (e.g. no QEMU).
>
> **Companion docs:** `docs/codebase_slimming_plan.md` (what was/wasn't
> moved), `docs/repo_cleanup_plan.md` (label conventions),
> `docs/demo_runbook.md` (full demo flow).

Status legend used in the *Expected* blocks below:

- `EXIT 0` — command returns zero.
- `EXIT N (≠0)` — non-zero, and we explain when that is OK (e.g. QEMU absent).
- `WROTE <path>` — file appears after the command, non-empty.
- `OBSERVE: …` — eyeball check; no exit code involved.

---

## 0. Prerequisites

```bash
# Sanity: you are at the repo root.
test -f README.md && test -d xv6-riscv && echo "repo root OK"

# Python 3.10+ with stdlib only (no third-party SDKs needed at runtime):
python3 --version

# Node 18+ for dashboard builds:
node --version

# Optional but recommended for the xv6 backend check:
command -v qemu-system-riscv64 && command -v riscv64-unknown-elf-gcc \
  && echo "QEMU + riscv toolchain present"

# Optional: real LLM calls (otherwise use --offline-fixture):
test -f .env && grep -q '^UPSTAGE_API_KEY=' .env && echo "Solar key present"
```

Each missing optional dependency turns its section into a “skipped + noted”
instead of a failure.

---

## 1. xv6 Build Check

**Goal:** kernel + `schedtest` still compile after the cleanup.

Command:

```bash
cd xv6-riscv
make clean
make kernel/kernel  # builds the xv6 kernel including schedtest userprog
cd ..
```

Expected:

- `EXIT 0`.
- `xv6-riscv/kernel/kernel` exists.
- `xv6-riscv/user/_schedtest` exists.
- No new warnings in `proc.c` (the protected scheduler file).

If `make` fails: **STOP**. The kernel is protected (`docs/codebase_slimming_plan.md` §2.4).
Re-check the cleanup PR didn't touch `xv6-riscv/`.

---

## 2. xv6 Backend Orchestrator Check (requires QEMU)

**Goal:** the primary demo path (`--backend xv6`) still runs end-to-end on
one profile.

Command:

```bash
python3 scripts/orchestrator.py \
    --backend xv6 --seed 42 --workload interactive --run-all
```

Expected:

- `EXIT 0`.
- Console log includes `[orchestrator] backend=xv6`, then six per-algorithm
  blocks ending in `algo=rr|fcfs|priority|mlfq|sjf|srtf`.
- `WROTE outputs/xv6_raw_<algo>_seed42.log` for each of the 6 algorithms.
- `WROTE dashboard_live/public/live-data/manifest.json` with
  `metadata_source = "xv6"` (or `metadata_source = "demo_fallback"` if
  `--offline-fixture` was used).
- `WROTE dashboard_live/public/live-data/trace_<algo>.jsonl` for each algo.
- `WROTE dashboard_live/public/live-data/metrics.json` with a non-null
  `judgment` field.

If QEMU is **not** available:

```bash
python3 scripts/orchestrator.py \
    --backend simulator --seed 42 --workload interactive --run-all
```

— `EXIT 0` and the same file set, but `manifest.metadata_source` will read
`"simulator"`. This is the documented dev/fallback path and is **not** the
final demo path.

---

## 3. Trace Parser Check

**Goal:** the parser still turns a raw xv6 console log into normalized JSONL.

Command (uses the latest xv6 raw log from §2):

```bash
LATEST=$(ls -t outputs/xv6_raw_mlfq_seed*.log 2>/dev/null | head -1)
test -n "$LATEST" || { echo "no xv6 raw log yet — run §2 first"; exit 1; }
python3 tools/trace_parser.py \
    --input "$LATEST" --algo MLFQ \
    --out outputs/_smoke/trace_mlfq.jsonl \
    --seed 42 --profile interactive
```

Expected:

- `EXIT 0`.
- `WROTE outputs/_smoke/trace_mlfq.jsonl` with one JSON object per line.
- Each line has at minimum `tick`, `algo`, `event`, `pid`.
- `event` field contains at least one of `DISPATCH`, `EXIT` and
  (for MLFQ) ideally a `QUEUE_CHANGE`.
- No “parse error” lines on stderr that are not the documented
  printf-interleave skip.

Falling back without an xv6 log: use a simulator trace
(`dashboard_live/public/live-data/trace_mlfq.jsonl` from §2's simulator
fallback) and confirm the parser is a no-op (the simulator already writes
canonical JSONL).

---

## 4. Metrics Generation Check

**Goal:** `metrics.py` still produces the judgment + regret fields the
dashboard expects.

Command:

```bash
python3 - <<'PY'
import json, subprocess, sys, pathlib
out = pathlib.Path("outputs/_smoke/metrics.json")
out.parent.mkdir(parents=True, exist_ok=True)
subprocess.check_call([
    sys.executable, "tools/metrics.py",
    "--trace-dir", "dashboard_live/public/live-data",
    "--out", str(out),
])
m = json.load(open(out))
assert "judgment" in m, "missing judgment"
assert "regret_score" in m, "missing regret_score"
assert m.get("scheduling_algorithm"), "missing scheduling_algorithm"
print("metrics OK:", {k: m.get(k) for k in
     ("scheduling_algorithm","judgment","regret_score","best_algorithm")})
PY
```

Expected:

- `EXIT 0`.
- Printed line ends with a dict containing `judgment ∈ {SUCCESS, NEAR-SUCCESS, FAIL, UNKNOWN}`,
  `regret_score` (float or null), and `best_algorithm` (string or null).
- File `outputs/_smoke/metrics.json` is non-empty and parses as JSON.

If `metrics.py`'s CLI signature differs, fall back to the orchestrator-run
`metrics.json` directly:

```bash
python3 -c "import json; m=json.load(open('dashboard_live/public/live-data/metrics.json')); print({k:m.get(k) for k in ('scheduling_algorithm','judgment','regret_score','best_algorithm')})"
```

— same expected output dict.

---

## 5. Dashboard Live Build Check

**Goal:** `dashboard_live/` still installs and builds. The build step is the
*real* slimming smoke check for the frontend (it catches missing fixtures,
broken imports, removed components).

Commands:

```bash
cd dashboard_live
npm ci || npm install            # ci preferred if a lockfile is present
npm run build                    # static build into dist/
cd ..
```

Expected:

- `EXIT 0` on both.
- `WROTE dashboard_live/dist/index.html`.
- Build log mentions all 17 components in `dashboard_live/src/components/`
  (no “unresolved import” errors).
- No new ESLint/build warnings introduced by the cleanup PR (`build` already
  shows warnings if any).

Quick dev-server sanity (optional):

```bash
cd dashboard_live && npm run dev    # then open http://localhost:5174
```

- `OBSERVE:` the header shows the backend badge (`XV6 TRACE`,
  `SIMULATOR FALLBACK`, or `FALLBACK`) — never blank.
- `OBSERVE:` the snapshot selector shows 4 entries (interactive, cpu_bound,
  mixed, priority_sensitive) when `snapshots_manifest.json` is present.

---

## 6. Dashboard Contract Validation

**Goal:** generated live-data and committed snapshots still satisfy the
contract the dashboard depends on.

Commands:

```bash
# Strict default contract over the flat live-data root:
python3 tools/validate_dashboard_contract.py --strict \
    --live-data dashboard_live/public/live-data

# All four committed xv6 profile snapshots:
python3 tools/validate_dashboard_contract.py --strict --snapshots \
    --live-data dashboard_live/public/live-data

# Optional: preview-only runtime-correction artefacts (off by default):
python3 tools/validate_dashboard_contract.py --preview \
    --live-data dashboard_live/public/live-data
```

Expected:

- All three commands `EXIT 0`.
- No `EMPTY_TRACE`, no `MISSING_MANIFEST_FIELD`, no
  `CROSS_FILE_ALGO_DISAGREEMENT` errors in the output.
- If the `--preview` command is run on a flat root that has no preview
  files, it should report "no preview artefacts found" and `EXIT 0` (it is
  opt-in, not required).

If the validator fails:

- Re-run §2 to regenerate live-data.
- If the snapshots themselves are stale, re-publish them:
  ```bash
  python3 scripts/export_profile_snapshots.py --backend xv6
  ```
  (Requires QEMU; without QEMU, leave snapshots untouched and re-validate
  only the flat live-data.)

---

## 7. Whole-flow smoke (optional but recommended)

The single one-command demo prep documented in `docs/demo_runbook.md`:

```bash
python3 scripts/final_demo_check.py
```

Expected:

- `EXIT 0`.
- Reproduces §1 + §2 + §6 with one invocation.
- Prints a final “OK — final demo ready” line. If it prints anything else,
  fix the failing sub-step before claiming slimming-safe.

Broader pre-demo confidence (still no substitute for §7 but useful):

```bash
python3 scripts/multi_profile_demo_check.py
```

— sweeps all four xv6 profiles. `EXIT 0` only when every profile passes.

---

## 8. Pass/fail summary

| # | Section | Required for slimming-safe? | Notes |
|---|---|---|---|
| 1 | xv6 build | YES | Protected kernel must still compile. |
| 2 | Orchestrator xv6 backend | **YES if QEMU available** | Otherwise use simulator backend and note the gap. |
| 3 | Trace parser | YES (via §2 output) | Skip if §2 was simulator-only. |
| 4 | Metrics generation | YES | Use the orchestrator's `metrics.json` if the CLI signature changed. |
| 5 | dashboard_live build | YES | The single most-likely place a cleanup breaks something. |
| 6 | Contract validator (strict + snapshots) | YES | Catches stale snapshots before the demo. |
| 7 | `final_demo_check.py` | recommended | One-command full path. |

A slimming PR is **only mergeable when §1, §3 (or §2's simulator path), §4,
§5, and §6 all pass** on the developer's machine. §2 with the xv6 backend
should pass on at least one teammate's machine before the demo day.

---

## 9. If something fails

Order of investigation:

1. Was a file in the protected list (`docs/codebase_slimming_plan.md` §2.4)
   touched? If so, revert that file first.
2. Was a docstring or comment edit accidentally a code edit? `git diff
   --stat` should show docs-only.
3. Is the failure on the xv6 path only, with QEMU/Toolchain warnings? Note
   the environment limitation, run §2 with `--backend simulator`, and flag
   the QEMU re-run as required on a teammate's machine.
4. Is the contract validator failing on a snapshot? Re-publish only that
   snapshot via `scripts/export_profile_snapshots.py --profile <name>` and
   re-run §6.

Never bypass the smoke check with `--no-verify` or by editing the
validator. The validator is the contract.
