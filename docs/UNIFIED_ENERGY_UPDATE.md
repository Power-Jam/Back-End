> Release 3.1: read [START_HERE.md](../START_HERE.md) first. This earlier development document is retained for research history; current routes and verification are in the release guide.

# Unified energy dashboard update

Apply to the Complete A-to-Z project after the historical TTN update. Stop the FastAPI server first. Back up the files being replaced. No data, config, credentials, database or model artifacts are included or changed.

- `/`, `/daily` and `/energy` serve the same daily dashboard. Generate advice and choose Integrated energy analysis. The old 500 Wh / 100 W research page is retained at `/research`; `/api/forecast` remains the legacy API and is not suitcase advice.
- The daily planner uses 180 Wh, 25 W, 80% derating, 14:00–17:00 learning, 8 sessions / 32 lessons, no simultaneous charging and use. These are assumptions.
- The historical replay uses the original receipt date and rounded-up local hour (Pretoria), with explicitly simulated weather. Partial-hour charging is omitted. A replay outside the supported morning window is not a forecast.
- The raw ML forecast and its calibrated range are unchanged. The planning battery is the lower of the raw ML estimate and a weather-based physical energy estimate, rounded down to two decimals. The latter is a conservative model-based ceiling, not a guaranteed physical limit. The recommendation applies the original reserve and margin to this planning value. The evaluated model metrics and range refer to the original rule, not the new guard; re-evaluate the guarded policy before making performance claims.
- `battery_based_capacity_at_input` shows battery-only allowance, not permission to learn now. Check actual battery, charging state, time and lessons already completed. The existing calculator does not track completed lessons or enforce actual time remaining.
- Historical readings are not live. MQTT and historical JSON are preserved. The live monitor remains available outside the supported morning window, but live morning advice is not generated then.

Verification: 32 pytest tests passed in the build environment (including two new regression tests); JavaScript syntax checked with Node. Full 365-day simulated training and the 3% historical replay were exercised. No live MQTT or live weather test was performed for this update. Browser interactions and Windows installation are not independently verified. The actual device's location, hardware measurements and field accuracy remain pending.
