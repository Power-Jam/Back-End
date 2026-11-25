# Verification — final integrated edition

- Both demo training commands completed successfully in Python 3.13.5 / scikit-learn 1.8.0. Python 3.12 recommended on Windows; regenerate serialized models locally.
- `python -m pytest -q`: 26 passed. Includes exhaustive cap checks across 1,001 battery levels and six margins, API cap checks for sunny/cloudy/mixed scenarios, separate calibration, team CSV import with constructed rows, telemetry ingestion, and original hourly tests.
- Selected model: forest_direct (80 trees, max_depth=None, min_samples_leaf=3), 5 pp margin; 365 simulated days, 73 held-out test days. At 08:00 MAE 2.5453 pp; 67/73 interval coverage; 43/73 exact session counts, 1/73 excessive session counts.
- Chromium dashboard tested with real FastAPI TestClient responses bridged into the page in memory. Sunny/cloudy forecasts, reliability, eight session slots, full battery cap (8 sessions / 32 lessons), and actual-battery calculator verified; no JavaScript errors. Separately, a running Uvicorn server was verified over localhost HTTP: GET /api/daily/config and POST /advice both returned 200 with the expected caps.
- No real TTN connection, real battery training, live weather request or physical hardware validation performed. Team CSV not supplied; importer tested with constructed rows. Simulated results are not field accuracy.
