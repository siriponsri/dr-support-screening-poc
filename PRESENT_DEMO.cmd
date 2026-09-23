@echo off
rem Opens the offline product presentation. No server, npm, GPU, model weights,
rem or Administrator rights are needed: the HTML file is self-contained.
setlocal
set "DECK=%~dp0docs\demo\RETINAL_REVIEW_DEMO.html"
if not exist "%DECK%" (
  echo Presentation not found: %DECK%
  echo Rebuild it with: python scripts\docs\build_docs.py demo
  pause
  exit /b 1
)
echo Opening the Retinal Review Workbench presentation...
echo   Space / Right arrow = next reveal    Left arrow = previous
echo   Home / End = first / last scene      F = full screen
echo Speaker script: docs\demo\PRESENTATION_SCRIPT_TH.md
start "" "%DECK%"
endlocal
