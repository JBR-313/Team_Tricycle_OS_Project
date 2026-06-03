# Demo Rehearsal Notes

Log of final-demo rehearsals. Each entry records the date, the exact commands,
the outcome, any failure + its cause, the recovery method, and presentation
notes. Rehearsals 1 and 2 here are the **mechanical** parts (commands +
verification) that can be automated; the **visual confirmation** (watching the
rendered dashboard) and **Rehearsal 3** (spoken English walkthrough) are done by
the presenter.

Mechanical environment for the entries below: `main`, real xv6 + QEMU available,
`UPSTAGE_API_KEY` present in `.env`.

---

## Rehearsal 1 — Normal xv6 demo (mechanical) · 2026-06-03

**Goal:** the on-stage path generates real xv6 data and the dashboard serves it.

**Commands**
```bash
git pull --ff-only origin main
python3 scripts/final_demo_check.py            # xv6, seed 42, interactive
cd dashboard_live && npm run dev               # serves http://localhost:5174
```

**Result: PASS**
- `final_demo_check.py` → **exit 0** in ~43 s (build xv6 CPUS=1, boot QEMU per
  algorithm, strict contract **13 OK / 0 WARN / 0 ERROR**,
  recommendation/guard/manifest agree on **MLFQ**).
- Dev server: **Vite ready in ~174 ms**; `GET /` → **HTTP 200**;
  `GET /live-data/manifest.json` → **HTTP 200** (`backend=xv6`, MLFQ);
  `GET /live-data/metrics.json` → **HTTP 200**.
- Badge basis: `manifest.backend=xv6`, `metadata_source=None` ⇒ **`XV6 TRACE`**.

**Failure / cause:** none.

**Recovery method:** dev server stopped with `pkill -f "vite --port 5174"`
(the `npm run dev` wrapper spawns a child `vite` process that outlives a kill of
the wrapper PID — kill the child explicitly). `final_demo_check.py` regenerates
`dashboard_live/public/live-data/`; restored the committed snapshot afterwards
with `git checkout -- dashboard_live/public/live-data`.

**Presenter visual checklist (to confirm on screen):**
- [ ] Header badge reads **`XV6 TRACE`** (not SIMULATOR / FALLBACK).
- [ ] LLM Recommendation + Algorithm Guard card shows **MLFQ / accepted**.
- [ ] Gantt / process lanes render for each algorithm.
- [ ] Algorithm Comparison + Metric Visualization shows the judgment.
- [ ] Profile snapshot selector lists 4 profiles.
- [ ] LLM Explanation text renders.

---

## Rehearsal 2 — API-key-absent fallback (mechanical) · 2026-06-03

**Goal:** confirm the system behaves honestly with no API key — it must NOT
silently fake a recommendation, and the documented fallback must badge `FALLBACK`
without breaking the dashboard.

**Commands**
```bash
mv .env .env.backup                                   # simulate "no API key"

# (2a) strict default — expected to REFUSE:
python3 scripts/final_demo_check.py

# (2b) opt-in offline fixtures — expected graceful fallback:
python3 scripts/final_demo_check.py --offline-fixture

mv .env.backup .env                                   # ALWAYS restore the key
```

**Result: PASS (both sub-cases behave as designed)**
- **(2a) strict, no key → exit 1 (honest refusal), in <1 s.** Message:
  *"The orchestrator will not silently substitute a fake Solar Pro 3 response …
  Re-run with `--offline-fixture` …"*. This is the correct, honest behavior — no
  silent guessing.
- **(2b) `--offline-fixture`, no key → exit 0 in ~39 s.** Uses the committed
  `outputs/_demo_fixtures/` recommendation, runs the real xv6 backend, strict
  contract **13 OK**, `manifest.metadata_source=demo_fallback` ⇒ **`FALLBACK`**
  badge. Dashboard data validates (does not break).

**Failure / cause:** none (the exit 1 in 2a is the *intended* refusal, not a
bug).

**Recovery method (critical):** `.env` was restored immediately
(`mv .env.backup .env`) and the move was additionally guarded by a shell
`trap '... ' EXIT` so the key is restored even on interruption. Verified after:
`.env` present (113 B, `UPSTAGE_API_KEY` set), `.env.backup` gone. The
fallback run rewrites live-data with `metadata_source=demo_fallback`; restored
the committed honest xv6 snapshot with
`git checkout -- dashboard_live/public/live-data` (manifest back to
`backend=xv6`, `metadata_source=None`, `XV6 TRACE`).

**What to say on stage if this happens for real:**
- "The badge says `FALLBACK`, which means the live LLM call was unavailable
  (e.g. no API key / network), so we are showing the committed demo fixtures —
  not a live recommendation, and not a fake one. The system refuses to invent a
  Solar Pro 3 response." Then, with the key present, re-run
  `python3 scripts/final_demo_check.py` to return to `XV6 TRACE`.

---

## Rehearsal 3 — Spoken English walkthrough · _TODO (presenter)_

**Goal:** deliver the talk end-to-end in English following
`docs/final_presentation_outline.md`, in the order:
Problem → Architecture → LLM recommendation → Algorithm Guard → xv6 execution →
`XV6 TRACE` / `FALLBACK` badge → Gantt chart → Metrics comparison → Limitations.

**Checklist (fill after rehearsing):**
- [ ] Date / who presented:
- [ ] Could explain "LLM is not the scheduler; xv6 is the execution authority":
- [ ] Could explain the `XV6 TRACE` vs `FALLBACK` badge meaning:
- [ ] Could explain why SJF/SRTF do not see future bursts (EMA only):
- [ ] Stayed honest about limitations (no websocket, runtime correction not
      closed-loop, sparse traces, predictor MAE = future work):
- [ ] Total time:
- [ ] Notes / things to tighten:

---

## Standing pre-demo gate (run before the talk / before freeze)

```bash
python3 scripts/final_demo_check.py
python3 scripts/multi_profile_demo_check.py
python3 tools/validate_dashboard_contract.py --strict --dir dashboard_live/public/live-data
python3 tools/validate_dashboard_contract.py --strict --dir dashboard_live/public/live-data \
    --snapshots dashboard_live/public/live-data/snapshots
cd dashboard_live && npm ci && npm run build
```

> Reminder: `multi_profile_demo_check.py` overwrites
> `dashboard_live/public/live-data/` with the LAST profile — restore the
> committed snapshot afterwards with
> `git checkout -- dashboard_live/public/live-data` (and remove any leftover
> `correction_*.json`).
