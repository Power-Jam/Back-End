> Release 3.2: read [START_HERE.md](START_HERE.md) first. This earlier development document is retained for research history; current routes and verification are in the release guide.

# Smart Energy AI — final integrated edition

This is a full project copy. Keep your old folder as a backup. The new daily planner is the primary demonstration; the previous dashboard remains available at `/energy`.

## Run in VS Code (Windows PowerShell)
Open the extracted `Smart-Energy-AI` folder (the one containing `config.json`). Python 3.12 is recommended.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m energy_ai train-all
python -m pytest -q
python -m energy_ai serve
```

The daily training may take a few minutes. Model files are generated locally to avoid scikit-learn version incompatibility. If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` instead of `python` for each command. If you already have a working virtual environment, reuse it with the updated requirements.

Open **http://127.0.0.1:8000/daily**. Keep the server terminal running. Do not open the HTML file directly. Original research dashboard: http://127.0.0.1:8000/research. Swagger: http://127.0.0.1:8000/docs.

## API example (second terminal)
```powershell
$body = @{battery_pct=41;weather_source='demo';scenario='sunny';prediction_hour=8;location='Pretoria'} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/advice' -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 20
```
Use `weather_source='live'` for current weather; it uses the current local time (rounded up to next full hour), only in the supported morning/afternoon charging window. A stale/missing cache is refreshed automatically. The original weather refresh command also works. No silent demo fallback.

## TTN when the hardware is ready
In TTN/TTS Console, open the application → Integrations → MQTT. Copy the exact host (without protocol/port), username (often application ID with tenant suffix), and create an API key with application traffic read permission. Agree on the device ID and decoded battery field. Use TLS port 8883.

In a separate PowerShell terminal (with venv activated):
```powershell
$env:TTN_HOST = 'YOUR_MQTT_HOST'
$env:TTN_USERNAME = 'YOUR_MQTT_USERNAME'
$env:TTN_DEVICE_ID = 'YOUR_DEVICE_ID'
$env:TTN_BATTERY_FIELD = 'battery_pct'
$secret = Read-Host 'TTN API key' -AsSecureString
$env:TTN_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
python -m energy_ai listen-ttn
```

Keep the listener running. After a real uplink, use `GET /api/battery/latest?device_id=YOUR_DEVICE_ID` or select Latest TTN reading in the daily dashboard. The API refuses readings older than 15 minutes. Actual advice needs the device to be in a charging-only window; outside it use the actual-battery recheck. Use `python -m energy_ai export-ttn` to export logs. Clear the API key from your shell when done (`Remove-Item Env:TTN_API_KEY`). Do not share keys or screenshots containing keys.

See `docs/DAILY_LEARNING_PLAN.md` for the method, results, limitations, and real-data training steps. `docs/daily_evaluation.json` is the actual simulated evaluation from this build. `data/daily_demo_training.csv` is generated mock data. `docs/TEST_RESULTS_DAILY.md` records verification.

## Prediction reliability and final teacher policy
The daily planner uses 180 Wh / 25 W, 14:00–17:00, 20-minute sessions and five-minute lessons (four per session), maximum 8 sessions / 32 lessons / 160 minutes, 10 pp/session and a conservative 10% end reserve. These are team assumptions, not verified specifications. The original hourly dashboard is labelled legacy. Retrain the daily model after upgrading; old artifacts are rejected.

The separate reliability JSON is available at http://127.0.0.1:8000/api/daily/reliability?prediction_hour=8. The `POST /advice` response includes a `prediction_reliability` object and both lesson and session counts. A 90% nominal interval is calibrated on separate days, with observed coverage on test days. It is not a guaranteed accuracy score.

The complete team CSV is bundled and trained automatically by `train-all`. To retrain just the team model, run:
```powershell
python -m energy_ai train-daily-team --csv data/device_sessions_hourly_mock_long.csv
```
Select **Team prototype dataset** on the daily dashboard. The complete team CSV is included; default prototype data is generated separately. The import keeps complete charging-only weekday windows. See the updated method document for the evaluation and limitations.

## Demonstration
See [DEMO_GUIDE.md](docs/DEMO_GUIDE.md) for a short teacher-ready walkthrough and the exact model results. The daily policy is available at `/api/daily/config`. A fully charged battery cannot produce more than eight sessions or 32 lessons. The 14:00–17:00 window retains 20 minutes outside the maximum learning allocation.
