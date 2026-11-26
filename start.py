#!/usr/bin/env python3
"""
Quick launcher for smart-energy-ai: just starts the API.
No installing, no training. Run start.py (the installer) first.

Usage:
    python start_ai.py
    python start_ai.py --open     # also open the browser
"""
import argparse
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
MODEL = ROOT / "artifacts" / "synthetic_demo.joblib"
URL = "http://127.0.0.1:8000"


def fail(msg):
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Start the smart-energy-ai API.")
    parser.add_argument("--open", action="store_true", help="open the browser")
    args = parser.parse_args()

    if not VENV_PY.exists():
        fail("No .venv found. Run the installer first:  python start.py")
    if not MODEL.exists():
        fail("No trained model found. Run the installer first:  python start.py")

    print(f"Starting API at {URL}  (Ctrl+C to stop)\n", flush=True)
    if args.open:
        webbrowser.open(URL)
    try:
        subprocess.run([str(VENV_PY), "-m", "energy_ai", "serve"], cwd=ROOT)
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()