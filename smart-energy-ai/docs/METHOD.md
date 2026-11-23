# Technical methodology

## Objective
Predict energy availability and provide actionable charge/conserve/stop recommendations for an educational device in Pretoria. The core operational forecast horizon is up to 48 hourly interval ends. The design deliberately separates prediction from decision rules.

## Flow
```
Historical weather + paired solar/load measurements + activity minutes
                 -> clean + chronological split -> model training
Current battery + future weather + planned activity minutes
                 -> solar/load models -> hourly energy balance
                 -> charge/stop timing -> FastAPI -> dashboard
```

## Models
Solar: shortwave radiation, air temperature, cloud cover → average electrical solar W. Load: activity minutes, cyclic local hour (sin/cos), weekend indicator → average load W. Compare linear regression and random forest against a physical baseline. Baseline solar = rated W × GHI/1000 × derate, clamped to rated power; load = idle W + (active W − idle W) × active fraction. Solar output is zero at zero irradiance. These are approximate, especially with panel orientation and controller losses. The demo dataset was generated from similar equations with noise; a strong baseline is expected, not proof of AI superiority. The load predictor uses a supplied future plan, not a separate autonomous usage predictor.

## Battery
For an interval of length Δt hours, net energy = (solar W − load W) × Δt. If net positive, multiply by charging efficiency; if negative divide by discharge efficiency. Add this to available Wh and clamp to [0, usable capacity]. Percentage = stored Wh / usable capacity × 100. Calculate the first predicted reserve and warning crossings with interpolation within the interval. Recommendations: above warning, continue; at/below warning, charge or reduce use; at/below reserve, save/stop if no charging; also alert if reserve is forecast within four hours. This is a simplified DC-bus model, not electrochemical battery simulation. It ignores temperature-dependent battery capacity, charge current limits, inverter losses beyond configured derates, battery aging, and supplemental charging; it assumes solar/load power constant within the interval and allows solar recovery after depletion if predicted supply permits. The reported unserved quantity is battery-equivalent Wh, not exact unmet device energy.

## Evaluation
Training/validation/test are chronological 60%/20%/20%; select by validation MAE, refit on train + validation, report MAE/RMSE for all candidates on untouched held-out data. No random shuffle. Solar and load are evaluated independently in W. In operational testing, save forecast issue timestamps and evaluate 1/6/24-hour ahead predictions against real future readings, including battery MAE in percentage points, warning lead time, false-low and missed-low warnings, and forecast coverage. Historical reanalysis is not the same as a historical forecast at the time of decision; use Open-Meteo previous runs or archived forecast snapshots to avoid hindsight. Real battery forecasting accuracy and usability are not established by simulated results. Compare to physical baseline and persistence, then validate on independent device deployments and stakeholder-approved thresholds.

## User-centered design
Users see remaining time until reserve, simple recommendations and optionally a detailed chart. Show estimates and assumptions; avoid presenting a precise prediction as a guarantee. Prototype colors are accompanied by words. Test comprehension with students and the person of trust. Localize language/time formats as appropriate. On real deployment, stale battery telemetry or stale weather should produce an explicit degraded mode, not guessed values. Hardware protections remain independent.
