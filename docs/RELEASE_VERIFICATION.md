# Release 3.2 — complete team-data edition

## Included and verified
- The complete team CSV is included byte-for-byte: 8,760 rows, 15 columns, 365 dates, zero missing values and duplicate rows. The importer retains 2,080 prediction windows on 260 eligible charging days. The prepared CSV is included. The team data is prototype data, not physical battery measurements.
- `python -m energy_ai train-all` trained all three pipelines (hourly research, daily prototype, daily team) successfully. `start.ps1` invokes this command automatically.
- `python -m pytest -q --disable-warnings`: 35 passed in 10.83 seconds. Includes a test of the supplied full CSV. Warnings suppressed in the summary only.
- FastAPI TestClient with actual trained models: HTTP 200 for /, /energy, /research, model availability, team metrics, team reliability, historical battery and /advice. Both daily model sources available; measured model unavailable as expected.
- For 41% and the sunny 08:00 scenario, both models allocated 28 lessons. For the stored 3% mixed-weather replay, the original daily model planned 14.59%, team model 11.93%, both zero lessons. For 100% and sunny 08:00, both allocated 32 lessons / 8 sessions. All are scenario checks, not real charging validation.

## Model evaluation (08:00)
| Metric | Daily prototype | Team prototype |
|---|---:|---:|
| Test days | 73 | 52 |
| Selected model | Random Forest direct | Random Forest gain |
| MAE (percentage points) | 2.55 | 1.50 |
| Observed interval coverage | 91.8% | 84.6% |
| Exact full-session count | 58.9% | 86.5% |
| Too many full sessions | 1.4% | 7.7% |
| Too many lessons | 1.4% | 17.3% |

These scores use different held-out prototype datasets and the raw-model recommendation rule, before the engineering constraint. They do not establish real-world superiority. The team model misses the 90% nominal coverage target and exceeds the 5% validation over-advice target on test days. The final guarded advice requires separate evaluation. No claims of actual battery safety or hardware accuracy are made.

## Environment and limitations
Executed with Python 3.13.5, scikit-learn 1.8.0, pandas 2.2.3, numpy 2.3.5. Model binaries are deliberately generated locally by the startup script for compatibility with the user's Python environment. Evaluation JSONs are included in docs. Windows startup and interactive browser operation not retested here. No new live TTN or Open-Meteo request was made. Historical TTN input is a previously reported battery value; its measurement accuracy is unverified. Fresh MQTT receipt, verified charging days, measured-data training, real consumption and external educational-app integration remain pending. Preserve live telemetry from previous installations. Do not embed API keys.
