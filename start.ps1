$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or follow the manual setup in README.md.' }
}
$python = '.\.venv\Scripts\python.exe'
<<<<<<< HEAD
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $python -m energy_ai train-demo
if ($LASTEXITCODE -ne 0) { throw 'Training failed.' }
=======
& $python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $python -m energy_ai train-all
if ($LASTEXITCODE -ne 0) { throw 'Training failed.' }
Write-Host "Open http://127.0.0.1:8000/ after the server starts."
>>>>>>> origin/Final_Version
& $python -m energy_ai serve
