# Smart Energy AI — consolidated release 3.2

## Start in VS Code (Windows)
Extract the ZIP into a new folder. Open the inner `Smart-Energy-AI` folder. Run in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

This installs runtime dependencies, trains all three model pipelines (hourly research, daily prototype and daily team) on this computer and starts FastAPI. Open http://127.0.0.1:8000/. If preferred, use the manual commands:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m energy_ai train-all
python -m pytest -q
python -m energy_ai serve
```

If an earlier server is using port 8000, stop it with Ctrl+C first. The release includes training CSVs and source code; model binaries are generated locally to avoid cross-version joblib incompatibility. Python 3.12 is recommended. Keep the first terminal running.

## Demonstration
Select **Stored TTN reading**, device `scb-5000`, weather scenario Mixed, and **Prototype model**. Generate advice. Included is the previously exported TTN reading (3%, 25 Nov 2026 09:48:34 UTC); its physical measurement accuracy is not established. The timestamp is rounded upward to 12:00 Pretoria time. Generated weather is not an archived observation or current live forecast. This is a historical replay, not current advice. The 3% reading permits zero lessons based on the input energy. The future recommendation uses a separate, engineering-limited charging estimate. Check actual battery and device state before learning.

Manual scenario is suitable for a sunny/cloudy comparison. Live forecast cache uses Open-Meteo for Pretoria and the supported morning forecast window. Outside that window, use the actual-battery calculator, which is a battery-only estimate, not permission to learn now; it does not track elapsed time or completed lessons. The old research page uses a different hardware profile and must not be used as current suitcase advice.

## Team dataset — included and ready for training
The complete original `data/device_sessions_hourly_mock_long.csv` is included unchanged (8,760 hourly records; 365 dates, 23 Nov 2025–22 Nov 2026; no missing values or duplicate rows). The importer produces 2,080 windows on 260 eligible charging days. The prepared dataset is included as `data/daily_team_training.csv`. The team dataset is generated prototype data, not verified hardware measurements.

`train-all` and `start.ps1` now train the team model automatically. To retrain only the team model:

```powershell
python -m energy_ai train-daily-team --csv data/device_sessions_hourly_mock_long.csv
```

After training, both **Prototype model** and **Team prototype dataset** are available. The measured model remains unavailable until sufficient real charging data has been collected. The team test results are recorded in `docs/team_evaluation.json` and `docs/RELEASE_VERIFICATION.md`. Compare different training sources on a common independent dataset before claiming one is superior in real use.

## Connect TTN (second terminal)
If upgrading from an earlier folder, stop its collector and copy your actual `data/battery_telemetry.sqlite3` and `data/ttn_historical.json` into the new project, preserving backups. Copy the database while the old collector is stopped. Do not copy API keys into project files. Revoke any previously exposed keys and use a dedicated application key with read application traffic permission.

```powershell
.\.venv\Scripts\Activate.ps1
$env:TTN_HOST = 'eu1.cloud.thethings.network'
$env:TTN_USERNAME = 'scb-5000@ttn'
$env:TTN_DEVICE_ID = 'scb-5000'
$env:TTN_BATTERY_FIELD = 'battery_percent'
$env:TTN_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'TTN API key' -AsSecureString)).Password.Trim()
python -m energy_ai fetch-ttn-history
python -m energy_ai listen-ttn
```

The history command downloads valid decoded uplinks and merges them into the historical JSON without replacing older saved records. New MQTT uplinks are stored separately in SQLite. A fresh measurement must arrive while the collector is running. The UI refreshes the live reading every 20 seconds and rejects stale data. The device determines the transmission interval. No fresh uplink was received by the Python collector in the documented user demonstration; MQTT authentication and the historical HTTP retrieval were successful. Do not treat history as a current battery reading.

## Final policy and architecture
- One main dashboard at `/`, `/daily`, `/energy`. Original hourly research archived at `/research` and `/api/forecast`.
- 180 Wh battery, 25 W solar panel, 80% assumed derating; 10 percentage points per 20-minute session, four 5-minute lessons per session, 2.5 points per lesson, 10% end reserve. Hardware values require confirmation. The reported 11 h charge and 3 h runtime are reference observations, not a charging law.
- Charging before 14:00, learning 14:00–17:00; at most 8 sessions/32 lessons/160 minutes. No simultaneous charging and use.
- Python backend: weather features, grouped chronological model training, baseline/linear regression/random forest, parameter selection and independent calibration, MAE, prediction range and session recommendation evaluation. Runtime planning caps the raw prediction with a conservative weather-based energy estimate. Reliability figures describe the raw model before the engineering guard; they are not a field guarantee or probability for an individual forecast.
- Frontend: source labels, live monitoring, solar graphs, battery-only capacity, future recommendation, session track and technical details. Untrained options disabled. JSON API available to the educational app.

## Real-data validation
`python -m energy_ai export-ttn` exports the SQLite log. Verify the actual battery level, charging/usage state, location and charging window, and save the forecast made before the outcome. Compare it with the actual 14:00 reading over multiple days. Use matching weather/location; do not pair Belgian device measurements with Pretoria weather. See `DAILY_QUICKSTART.md` and `docs/DAILY_LEARNING_PLAN.md` for the real-data preparation and training workflow; their earlier route descriptions are superseded by this file. A real battery model cannot be trained on one historical reading. The final measured model and external learning-app integration remain pending. This software is advisory, not a battery protection controller.

## API
- `/docs`: interactive API reference
- `/api/daily/models`: model availability
- `POST /advice`: daily forecast and recommendation
- `/api/daily/reliability`: raw model reliability
- `/api/daily/metrics`: evaluation
- `/api/lessons/actual?battery_pct=30`: battery-only calculation
- `/api/battery/latest?device_id=scb-5000`: fresh MQTT reading
- `/api/battery/historical?device_id=scb-5000`: stored history

See `docs/RELEASE_VERIFICATION.md` for the latest test evidence. Earlier reports describe earlier versions, not current test counts.
