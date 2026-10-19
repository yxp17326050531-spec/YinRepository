@echo off
setlocal
cd /d "%~dp0"
where git >nul 2>nul
if errorlevel 1 goto missing
if exist "checkout" goto exists
git clone --branch etheria-desktop --single-branch https://github.com/yxp17326050531-spec/YinRepository.git checkout
if errorlevel 1 goto failed
cd checkout\etheria_assistant
call install_windows.cmd
exit /b %errorlevel%
:missing
echo Install Git for Windows first, then run this file again.
goto failed
:exists
echo checkout already exists. Use checkout\etheria_assistant\update.cmd.
:failed
pause
exit /b 1
