# dashboard_test — Static Fixture UI Dashboard

This is the **UI test dashboard** using static fixture data (`src/data/demoData.js`).

It is **not** the final live dashboard.
It does **not** depend on generated runtime files, polling, or any output pipeline.

## Purpose

- Layout experiments and visual polish
- Component development and inspection
- Demo fixture visualization
- No real runtime data dependency

## Run

```bash
cd dashboard_test
npm install
npm run dev    # http://localhost:5173
npm run build
```

## Data source

`src/data/demoData.js` — static fixture embedded in the source tree.
Do not replace this with live polling. That is the job of `dashboard_live/`.

## Relationship to dashboard_live

| | dashboard_test | dashboard_live |
|---|---|---|
| Data source | static demoData.js | fetched from public/live-data/ |
| Polling | none | manifest.json every 1s |
| Purpose | UI design | final project dashboard |
| Rebuild needed? | on source change | on pipeline run |
