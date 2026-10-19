@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" update.py
if errorlevel 1 goto failed
echo Update finished. Run start.cmd.
pause
exit /b 0
:missing
echo Run install_windows.cmd first.
:failed
pause
exit /b 1
