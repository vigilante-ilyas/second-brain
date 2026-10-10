$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Create the project virtual environment first. See SETUP.md.' }
& $projectPython bootstrap.py
if ($LASTEXITCODE -ne 0) { throw 'Storage initialization failed.' }
& $projectPython -m streamlit run "$PSScriptRoot\dashboard.py" --server.address=127.0.0.1 --server.port=8503 --server.enableCORS=true --server.enableXsrfProtection=true --server.enableStaticServing=false --server.maxUploadSize=50 --browser.gatherUsageStats=false
