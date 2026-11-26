#!/usr/bin/env python3
"""
One-file starter for smart-energy-ai.

Usage (run from anywhere, the script switches to its own folder):
    python start.py                 # setup + checks + train (if needed) + serve
    python start.py --retrain       # force re-training of the demo model
    python start.py --skip-install  # never run pip install
    python start.py --force-install # run pip install even if packages are present
    python start.py --test          # also install pytest and run the tests
    python start.py --no-serve      # do everything except starting the API

Place this file in the smart-energy-ai folder (next to requirements.txt).
"""
import argparse
import importlib.util
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
MODEL = ROOT / "artifacts" / "synthetic_demo.joblib"
MIN_PYTHON = (3, 10)

# import name -> pip package name
REQUIRED_MODULES = {
    "numpy": "numpy",
    "pandas": "pandas",
    "sklearn": "scikit-learn",
    "requests": "requests",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "joblib": "joblib",
}


def step(msg):
    print(f"\n=== {msg} ===", flush=True)


def fail(msg):
    print(f"\n[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def venv_python():
    sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return VENV / sub


def run(cmd, check=True):
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    result = subprocess.run([str(c) for c in cmd], cwd=ROOT)
    if check and result.returncode != 0:
        fail(f"Command failed with exit code {result.returncode}.")
    return result.returncode


def ensure_venv():
    step("1/5 Virtual environment")
    if sys.version_info < MIN_PYTHON:
        fail(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required, found {sys.version.split()[0]}.")
    if not venv_python().exists():
        print("  Creating .venv ...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    else:
        print("  .venv already exists.")
    if not venv_python().exists():
        fail("Could not create the virtual environment.")


def install_requirements():
    if not REQUIREMENTS.exists():
        fail(f"requirements.txt not found in {ROOT}. Put start.py in the smart-energy-ai folder.")
    py = venv_python()
    run([py, "-m", "pip", "install", "--upgrade", "pip", "--quiet"], check=False)
    run([py, "-m", "pip", "install", "-r", REQUIREMENTS])


def find_missing():
    py = venv_python()
    code = (
        "import importlib.util, sys\n"
        f"mods = {list(REQUIRED_MODULES)!r}\n"
        "missing = [m for m in mods if importlib.util.find_spec(m) is None]\n"
        "print(','.join(missing))\n"
    )
    out = subprocess.run([str(py), "-c", code], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        fail(f"Package check crashed:\n{out.stderr}")
    return [m for m in out.stdout.strip().split(",") if m]


def report_installs():
    py = venv_python()
    for mod, pkg in REQUIRED_MODULES.items():
        ver = subprocess.run(
            [str(py), "-c", f"import {mod}; print(getattr({mod}, '__version__', '?'))"],
            cwd=ROOT, capture_output=True, text=True,
        ).stdout.strip()
        print(f"  OK  {pkg:<14} {ver}")
    if not (ROOT / "energy_ai").is_dir():
        fail("The 'energy_ai' package folder was not found next to start.py.")
    print("  OK  energy_ai package found")


def ensure_packages(force, skip):
    step("2/5 Checking packages")
    missing = find_missing()
    if missing:
        names = ", ".join(REQUIRED_MODULES[m] for m in missing)
        print(f"  Missing: {names}")
    else:
        print("  All required packages are already installed.")

    if skip:
        print("  Skipping install (--skip-install).")
    elif missing or force:
        print("  Installing requirements ...")
        install_requirements()
        missing = find_missing()
    else:
        print("  Nothing to install.")

    if missing:
        pkgs = ", ".join(REQUIRED_MODULES[m] for m in missing)
        fail(f"Still missing in .venv: {pkgs}. Re-run without --skip-install.")
    report_installs()


def run_tests():
    step("Running tests (pytest)")
    py = venv_python()
    run([py, "-m", "pip", "install", "pytest", "--quiet"])
    run([py, "-m", "pytest", "-v"], check=False)


def prepare_data_and_model(retrain):
    step("4/5 Weather data + model")
    py = venv_python()
    # Weather fetch needs internet; the demo model does not depend on it, so don't abort.
    if run([py, "-m", "energy_ai", "fetch-weather"], check=False) != 0:
        print("  [warn] fetch-weather failed (offline?). Continuing with demo data.")
    if retrain or not MODEL.exists():
        run([py, "-m", "energy_ai", "train-demo"])
    else:
        print(f"  Model already trained ({MODEL.relative_to(ROOT)}). Use --retrain to rebuild.")


def serve():
    step("5/5 Starting API")
    print("  Open http://127.0.0.1:8000  (Ctrl+C to stop)\n", flush=True)
    py = venv_python()
    try:
        subprocess.run([str(py), "-m", "energy_ai", "serve"], cwd=ROOT)
    except KeyboardInterrupt:
        print("\nServer stopped.")


def main():
    parser = argparse.ArgumentParser(description="Set up and start smart-energy-ai.")
    parser.add_argument("--skip-install", action="store_true", help="never run pip install")
    parser.add_argument("--force-install", action="store_true", help="run pip install even if everything is present")
    parser.add_argument("--retrain", action="store_true", help="force model re-training")
    parser.add_argument("--test", action="store_true", help="install pytest and run tests")
    parser.add_argument("--no-serve", action="store_true", help="do not start the API")
    args = parser.parse_args()

    os.chdir(ROOT)
    ensure_venv()
    ensure_packages(args.force_install, args.skip_install)
    if args.test:
        run_tests()
    prepare_data_and_model(args.retrain)
    if args.no_serve:
        print("\nDone (API not started because of --no-serve).")
    else:
        serve()


if __name__ == "__main__":
    main()