@echo off
REM install and run pyinstaller within venv
IF NOT DEFINED VIRTUAL_ENV (
    echo must be in a virtual env!
    exit /b
)

pyinstaller --noconfirm --onefile --windowed --icon "static/app.ico"^
 --name "recon" --add-data "static;static" "main.py"