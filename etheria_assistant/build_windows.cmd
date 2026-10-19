@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto missingpython
py -3 -m venv .build-venv
if errorlevel 1 goto failed
".build-venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".build-venv\Scripts\python.exe" release_tools.py build %*
if errorlevel 1 goto failed
echo.
echo Build and startup checks passed. ZIP and SHA256SUMS are in release\.
echo Run publish_release.cmd to upload this exact build to GitHub Releases.
pause
exit /b 0
:missingpython
echo Install 64-bit Python 3.10+ with the Windows py launcher first.
pause
exit /b 1
:failed
echo Release did not finish. Keep this window open to read the error.
pause
exit /b 1
