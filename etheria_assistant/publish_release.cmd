@echo off
setlocal
cd /d "%~dp0"
if not exist ".build-venv\Scripts\python.exe" goto missing
".build-venv\Scripts\python.exe" release_tools.py publish
if errorlevel 1 goto failed
echo Release published.
pause
exit /b 0
:missing
echo Run build_windows.cmd first.
:failed
echo Publication did not finish. Read the error above.
pause
exit /b 1
