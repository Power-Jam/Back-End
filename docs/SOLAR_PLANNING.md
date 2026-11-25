# Solar outlook and charging opportunity

This is an additive update to the original Smart Energy AI project. Existing trained models, configuration, dashboard controls and `GET /api/forecast` are retained. No new dependencies or retraining are required when applying the patch to a working installation.

## Calculation

For each remaining forecast interval, use the existing predicted solar power and estimated load. Multiply solar power by interval duration to estimate solar energy in Wh. The existing battery simulation applies charging efficiency and caps stored energy at battery capacity. Rank intervals in each covered local day by the positive increase in stored battery energy (Wh); choose the earliest in a tie. If none has a positive increase, return no useful window. The first interval can be shorter than one hour. Daily totals cover only the intervals in the requested forecast, not past hours or an uncovered part of a day. The reference location is Pretoria; its local time is UTC+02:00.

The recommended window is an estimated solar charging opportunity under the selected usage plan, not an instruction to delay charging. Existing charge-by and reserve warnings remain authoritative within this advisory prototype. The solar window is not an external-charger schedule and does not control hardware.

## API

`GET /api/forecast` now also returns `solar_daily`, an array with local date, coverage start/end and hours, predicted solar energy (Wh), incoming sunlight energy (Wh/m²), peak sunlight (W/m²), peak solar output (W), and `best_charging_window` (start/end local, solar/load/net power in W and battery gain in Wh; null if unavailable). `charging_opportunity` explains why no window exists. `warning_before_or_at_best_window` flags a warning threshold reached before or at the start of the opportunity. Existing hourly rows also include `interval_start_local`, `duration_hours`, `solar_energy_wh`, `net_power_w`, and `battery_gain_wh`.

## Dashboard

The new section shows daily cards, a sunlight intensity chart, and a solar generation versus consumption chart. Shaded bands mark the best charging intervals. Weather provenance remains visible above the dashboard. All charts use local SVG and JavaScript, without external libraries.

## Test

From the project root, with the existing virtual environment active:

```powershell
python -m pytest -q
python -m energy_ai serve
```

Open http://127.0.0.1:8000/energy and select Simulated / Sunny, then Cloudy. Change battery to 10% and confirm that the immediate low-battery warning remains. Live weather still requires a valid cache (`python -m energy_ai fetch-weather`).

Validation performed: 13 automated tests passed; dashboard rendering and scenario/low-battery interactions checked in headless Chromium with API responses supplied through FastAPI TestClient. No real hardware or live weather validation was performed.
