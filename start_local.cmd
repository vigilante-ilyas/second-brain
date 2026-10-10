@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Create the project virtual environment first. See SETUP.md.
    exit /b 1
)
".venv\Scripts\python.exe" bootstrap.py
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m streamlit run "%~dp0dashboard.py" --server.address=127.0.0.1 --server.port=8503 --server.enableCORS=true --server.enableXsrfProtection=true --server.enableStaticServing=false --server.maxUploadSize=50 --browser.gatherUsageStats=false
