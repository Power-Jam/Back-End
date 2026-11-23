# Data contract & collection plan

## Required hourly sensor export
One row per physical device per hour. This prototype handles one device at a time. Export one device to CSV.

| Field | Units | Description |
|---|---|---|
| timestamp | ISO 8601 UTC (+00:00 or Z) | End of the observed interval |
| battery_pct | % | Actual BMS state of charge at interval end (0–100), not voltage converted using an unverified formula |
| solar_w | W | Mean usable solar power delivered to the DC bus during the preceding hour |
| load_w | W | Mean total device load over preceding hour, including idle and peripherals |
| usage_minutes | minutes | Number of minutes device was actively used in preceding hour, 0–60 |

Example format (illustrative only):
```
timestamp,battery_pct,solar_w,load_w,usage_minutes
2026-11-18T08:00:00Z,62,42,35,30
```
Do not substitute raw battery discharge power for device load when solar power is available; they are different quantities. Keep unit conversions and meter boundary consistent. Capture actual panel rating, usable battery capacity, battery chemistry, approved reserve threshold, charge/discharge efficiency, idle and active demand, and location. Log external charging events and outages separately; baseline forecast currently assumes no external charging. Optional future fields include battery voltage/current, charge status and device ID. Never invent actual sensor values.

Sampling: start with 5-minute readings (if network/device supports that rate), preserve raw records, compute time-weighted mean W and accumulated active minutes per hour. For counters in Wh, calculate interval deltas and divide by interval duration to get mean W. Mark gaps; do not forward-fill long missing periods or assume zero means offline. Align UTC hour boundaries; keep the exact same timestamp convention for reanalysis/forecasts. Reject clock problems and duplicates; training excludes invalid/missing rows without fabricating them. Monitor completeness and dropped/matched row counts.

## Weather fields
`timestamp`, `temperature_2m` (°C), `cloud_cover` (%), `shortwave_radiation` (W/m², global horizontal radiation averaged over previous hour), `direct_radiation` (W/m²) and `sunshine_duration` (s). The first three weather variables are model features. Last two are collected for research and later feature experiments. External weather cannot provide actual battery charge or actual electrical output. For non-horizontal panels, investigate tilted irradiance once orientation/tilt are known.

## Data ownership
PPS and team must confirm permission to access device telemetry; do not collect personally identifiable student usage. Aggregate activity duration by device. Use scoped credentials, store secrets outside source code, rotate them, and avoid committing CSVs containing sensitive information. Current prototype needs no TTN credentials because it uses an explicit offline CSV integration boundary.
