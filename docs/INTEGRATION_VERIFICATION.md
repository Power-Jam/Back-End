# Complete A–Z integration verification

## Changes
- All 26 files from the original project are retained or updated in the consolidated tree. Original models, configuration, data generation, weather adapter and battery module are preserved.
- Primary dashboard at `/` and `/daily`; legacy hourly research at `/energy`. Original API endpoints retained. The legacy dashboard accepts battery/weather scenario from the integrated page.
- `integration.py` reuses original physics, battery balance and solar planner with the daily model's shared weather and battery input. Charging and learning are mutually exclusive. No blending of incompatible model profiles.
- `train-all` and `start.ps1` provide a single setup path for both models. Model binaries are generated locally.

## Tests performed
- Both full demo training pipelines completed using `python -m energy_ai train-all`.
- 30 automated tests passed (26 existing tests plus four integration cases). Tests cover input validation, shared weather, battery bounds, charging/learning separation, session/lesson caps, both dashboards and unified API.
- Local Uvicorn HTTP smoke test: primary and legacy dashboards, forecast, reliability, actual battery calculator and unified POST advice.
- JavaScript syntax checks passed. Chromium rendered the integrated graph and tested sunny/cloudy changes, the actual-battery cap, and legacy-link query parameters. Browser navigation was restricted in the environment, so API calls were bridged to FastAPI TestClient and the legacy query was injected for its rendering test. No browser JavaScript errors in those tests.
- `integrated_energy_preview.png` shows the actual integrated dashboard section. `example_advice.json` and evaluation JSON files were regenerated from the current model.

## Pending
Windows startup script was not executed on a Windows machine. The team CSV, real battery measurements, live TTN, live weather, actual lesson drain and external educational application remain unverified. All default model evaluation uses simulated data. The physical reference assumes 180 Wh / 25 W, 80% derate, zero charging-mode load and 54 W battery-side learning load. The old research profile remains separate and is not suitcase advice.
