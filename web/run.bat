@echo off
REM Double-click this to start the HVAC Toolkit dev server.
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Could not find .venv in this folder.
    echo Run: python -m venv .venv  then  pip install -r requirements.txt
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
flask --app wsgi run --debug

echo.
echo Server stopped.
pause
