# Build verification

Build-time checks performed in a Linux Python 3.13 environment with installed dependencies:
- Demo data generation and model training: successful (2,160 synthetic hourly records; 1,296 training, 432 validation and 432 test records).
- `python -m pytest -q`: 9 passed.
- Local Uvicorn smoke test: health endpoint, dashboard HTML and 48-row forecast returned successfully.
- Live Open-Meteo request: blocked by DNS/network restrictions in the build environment. HTTP adapter was tested using a mocked response. Run the fetch commands on your network to verify the actual Pretoria feed.
- No actual device data, Raspberry Pi hardware, Windows environment or full browser interaction testing was available in this build. The supplied Windows instructions target Python 3.12; the scientific dependencies must be installed on your target platform.

`demo_evaluation.json` contains the generated example metrics. Solar linear regression was selected using validation data; the physical load baseline narrowly won validation. These are simulated component-level metrics, not evidence of real device or day-ahead battery accuracy.
