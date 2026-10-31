@echo off
title DR Screening demo
"C:\Program Files\Git\bin\bash.exe" "%~dp0start-dr-train-demo.sh"
rem Whatever happened above, leave no web app or SSH tunnel running behind this window.
"C:\Program Files\Git\bin\bash.exe" "%~dp0stop-dr-train-demo.sh" >nul 2>&1
echo.
pause
