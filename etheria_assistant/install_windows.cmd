@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto missing
py -3 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Ready. Run start.cmd to open Etheria Assistant.
pause
exit /b 0
:missing
echo Install 64-bit Python 3.10 or newer with the py launcher first.
pause
exit /b 1
:failed
echo Installation failed. Read the error above.
pause
exit /b 1
