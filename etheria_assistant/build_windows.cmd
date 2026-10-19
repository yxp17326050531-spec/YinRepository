@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto missingpython
py -3 -m venv .build-venv
if errorlevel 1 goto failed
".build-venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".build-venv\Scripts\python.exe" -m PyInstaller --noconfirm EtheriaAssistant.spec
if errorlevel 1 goto failed
echo.
echo Build finished: dist\EtheriaAssistant\EtheriaAssistant.exe
echo Share the WHOLE dist\EtheriaAssistant folder, including _internal.
echo Capture components are separate. Read SHARING_AND_UI.md before sharing.
pause
exit /b 0
:missingpython
echo Install 64-bit Python 3.10 or newer with the Windows py launcher first.
pause
exit /b 1
:failed
echo Build failed. Read the output above; no Windows binary was verified here.
pause
exit /b 1
