<<<<<<< HEAD
=======
> Release 3.2: complete team CSV included. `train-all` trains all three model pipelines. See [START_HERE.md](START_HERE.md) for current instructions.

> Release 3.1: read [START_HERE.md](START_HERE.md) first. This earlier development document is retained for research history; current routes and verification are in the release guide.

# Smart Energy AI — Complete A–Z workspace

**One project, one server, one primary dashboard.** Open [START_HERE.md](START_HERE.md) for the complete installation and integration guide. The original hourly dashboard is preserved at `/research`; `/energy` uses the unified planner. The integrated `/` and `/daily` dashboard now reuses the original energy-balance and solar-planning code on the team profile and shares exactly the daily model weather window and battery input. The existing `/api/forecast` remains a legacy research endpoint.


**Start with [DAILY_QUICKSTART.md](DAILY_QUICKSTART.md).** The new primary learning planner is `/daily`; the original hourly research dashboard below is retained with its original assumptions, not operational suitcase advice. See [daily method and results](docs/DAILY_LEARNING_PLAN.md) and [teacher demonstration guide](docs/DEMO_GUIDE.md). **Latest teacher policy: 8 sessions, 32 lessons, 160 minutes maximum.**

---

>>>>>>> origin/Final_Version
# PPS Smart Energy Assistant
**Python prototype | Global Acting in IT | Pretoria, South Africa**

This is an end-to-end, locally runnable prototype of the team's battery forecasting and energy advice idea. It estimates solar power and device consumption, forecasts the battery's available energy, and tells a user when to plan charging, conserve energy or save work and stop. It is an advisory application, not a charge controller or electrical safety system.

## 1. Run in VS Code (Windows)

1. Extract the ZIP into a new folder, e.g. `C:\Users\raedm\Downloads\Smart-Energy-AI`. Open the **Smart-Energy-AI** folder itself in VS Code (File → Open Folder). Open a PowerShell terminal. Use Python 3.12, which you already used for your forecasting assignment; create a separate environment for this project.
2. Run these commands from the folder containing `config.json`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m energy_ai train-demo
<<<<<<< HEAD
.\.venv\Scripts\python.exe -m energy_ai serve
```

3. Open **http://127.0.0.1:8000** in your browser. Leave the terminal running. Press Ctrl+C to stop. The API docs are at http://127.0.0.1:8000/docs.
=======
.\.venv\Scripts\python.exe -m energy_ai train-daily-demo
.\.venv\Scripts\python.exe -m energy_ai serve
```

3. Open **http://127.0.0.1:8000/daily** in your browser (the original hourly research dashboard is at `/energy`). Leave the terminal running. Press Ctrl+C to stop. The API docs are at http://127.0.0.1:8000/docs.
>>>>>>> origin/Final_Version

If `py -3.12` is unavailable, check `py -0p` or `python --version` and use an installed Python 3.11/3.12 interpreter. No activation is needed with the explicit interpreter commands. Alternatively `start.ps1` performs setup, demo training and server launch; the manual commands avoid PowerShell script execution-policy issues. If port 8000 is occupied use `-m energy_ai serve --port 8001` and visit port 8001.

The first pip install needs internet. After that, training and the dashboard in **Simulated (offline)** mode require no network or API key. Retraining generates local serialized models; the ZIP does not distribute executable binary model files.

## 2. Connect real Pretoria weather

Keep the server running. Open a second terminal in the project folder:

```powershell
.\.venv\Scripts\python.exe -m energy_ai fetch-weather
.\.venv\Scripts\python.exe -m energy_ai fetch-history --start 2024-01-01 --end 2025-12-31
```

- `fetch-weather`: retrieves seven days of hourly forecast data and saves `data/cache/pretoria_forecast.csv` and fetch metadata. On the dashboard select **Open-Meteo cache**, then Forecast energy. Refresh this cache whenever new forecasts are needed (currently rejects caches older than 12 hours). If unavailable or incomplete, the live forecast returns an explicit error; select simulated mode intentionally if you only want a demonstration.
- `fetch-history`: downloads 2024–2025 hourly historical reanalysis to `data/pretoria_historical_weather.csv` (17,544 expected hourly records before missing-value checks). For real training, request dates matching actual sensor measurements. No key required for eligible non-commercial use; consult current terms before PPS deployment.
- Public API data is meteorological information, not battery measurements or measured solar electricity. Real weather + synthetic training + manual battery input is still a simulation of device behavior, not a validated field forecast.
- Coordinates are general Pretoria reference coordinates, not the exact community. Replace latitude/longitude and location in `config.json` once PPS confirms them. Refresh weather and retrain after changing configuration.
- Timestamps are UTC in files. The dashboard presents Africa/Johannesburg (UTC+2). Open-Meteo radiation is the mean over the preceding hour; sunshine duration is in seconds for the preceding hour. Hourly values are matched to interval-end timestamps. The first forecast interval is shortened to the remaining part of the current hour and uses the hourly forecast as an approximation.

Official references: [Weather Forecast API](https://open-meteo.com/en/docs), [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), [Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api), [Terms](https://open-meteo.com/en/terms).

## 3. Demonstration

Set current battery charge (manual), planned active minutes per lesson hour, and a forecast horizon. Compare sunny and cloudy scenarios. Select 48 hourly points to cover the next full local calendar day. The energy outlook and charge/stop planning times update when you click Forecast energy. Null or “Not reached” means the threshold is not crossed during the requested window, not unlimited runtime. The assumed daily lesson schedule is 08:00–17:00 local time; the device has idle consumption outside those hours. The model assumes the user follows the planned usage and does not receive additional external charging. Solar charging is included.

`config.json` is deliberately a **demo hardware profile**: 500 Wh battery, 100 W panel, 5 W idle, 65 W active, 90% charge efficiency, 95% discharge efficiency, 35% charging recommendation and 20% minimum reserve. These are not confirmed PPS hardware specs or safety limits. The system does not switch off or control hardware. Replace these values with approved specifications and retrain before field evaluation.

## 4. Real data integration (later)

The provided `data/sensor_template.csv` contains the required headers, not fabricated real measurements. Retrieve the values from your BMS/ESP32, solar controller, existing database or TTN payload adapter. See `docs/DATA_CONTRACT.md`. We intentionally do not guess your database schema, MQTT topic, API credentials, or BMS protocol. Use an export from the existing dashboard database to start. Aggregate into hourly averages and minute counts, ending at the UTC timestamp. Store battery percentage at that interval end.

Once you have matched real weather and actual sensor records, run:

```powershell
.\.venv\Scripts\python.exe -m energy_ai train-real --sensors data/sensor_actual.csv --weather data/pretoria_historical_weather.csv
.\.venv\Scripts\python.exe -m energy_ai serve --model measured
```

The real training command pairs records on exact timestamps, checks duplicate records and invalid values, and rejects insufficient data (minimum 240 valid hours as a prototype guardrail, not a guarantee of model quality). Prefer months covering multiple weather and device-use conditions. The current UI still accepts manual battery and planned usage even with a real model; wiring those to your trusted live data feed is a separate integration step.

## 5. Model design and evaluation

See `docs/METHOD.md`. Linear regression and random forest regression are compared to a transparent physical baseline. The model learns solar production from weather and load from planned usage and time features. Models are selected by validation MAE on a chronological 60/20/20 split and refitted on train+validation. The untouched test split is used for final MAE and RMSE in watts. The chosen model can be the baseline if it outperforms ML in validation. Battery level comes from a bounded hourly energy balance, not an independent black-box AI prediction. The recommendation uses transparent configurable thresholds. Evaluation reports are generated in `artifacts/` and `/api/metrics`. Synthetic metrics demonstrate the pipeline, not real accuracy. Actual day-ahead evaluation needs archived forecasts available at the original prediction time and planned usage known then, and a battery trajectory test with real data.

## 6. REST API

| Endpoint | Description |
|---|---|
<<<<<<< HEAD
| `GET /` | Local browser dashboard |
=======
| `GET /` or `/daily` | Integrated workspace |
| `GET /energy` | Original hourly research dashboard |
>>>>>>> origin/Final_Version
| `GET /api/health` | Service and model health |
| `GET /api/config` | Device/location profile |
| `GET /api/metrics` | Chronological holdout metrics and provenance |
| `GET /api/forecast` | Forecast and recommendations |
| `GET /docs` | Interactive FastAPI docs (may load Swagger assets online) |

Example in a browser: `http://127.0.0.1:8000/api/forecast?battery_pct=65&active_minutes=45&hours=48&weather_source=demo&scenario=cloudy`

Integration with the existing dashboard: have its backend call `/api/forecast` with battery percentage, planned minutes, weather source, and horizon. The response includes UTC and local timestamps, predicted battery/solar/load, status, planning times, provenance, and limitations. Use server-side integration or a same-origin reverse proxy; arbitrary cross-origin browser access is not enabled. Do not expose this development API to the internet.

## 7. Raspberry Pi deployment

See `deploy/README.md`. Use a 64-bit Raspberry Pi OS, Python 3.11/3.12 if possible, a dedicated virtual environment, and network access when updating weather. Retrain on the Pi or on a compatible environment rather than copying joblib models across versions. Keep a local cache, do not silently substitute demo data when live data fails, and integrate using LAN-only or local reverse proxy with authentication. No actual Raspberry Pi deployment has been performed or verified.

## 8. Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Tests cover bounded battery calculations, low battery recommendations, hourly timestamps, model splitting, data validation, FastAPI responses and mocked weather requests. See `docs/TEST_RESULTS.md` for the build-time test outcome. The external weather host could not be reached from the build environment; you already verified API access on your own laptop, and the new Pretoria request still needs to be run on your network.
