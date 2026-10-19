@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto install
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
exit /b
:install
echo First run: install dependencies using install_windows.cmd, then run start.cmd.
pause
