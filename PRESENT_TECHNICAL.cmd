@echo off
rem Opens the offline technical briefing. No server, npm, GPU, model weights,
rem or Administrator rights are needed: the HTML file is self-contained.
setlocal
set "DECK=%~dp0docs\demo\TECHNICAL_BRIEFING.html"
if not exist "%DECK%" (
  echo Technical briefing not found: %DECK%
  echo Rebuild it with: python scripts\docs\build_docs.py briefing
  pause
  exit /b 1
)
echo Opening the Retinal Review Workbench technical briefing...
echo   Space / Right arrow = next reveal    Left arrow = previous
echo   Home / End = first / last scene      F = full screen
echo Speaker script: docs\demo\TECHNICAL_PRESENTATION_SCRIPT_TH.md
start "" "%DECK%"
endlocal
