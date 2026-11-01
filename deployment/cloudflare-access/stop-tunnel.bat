@echo off
rem Stop sharing the demo with team members. The demo app itself keeps running.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tunnel.ps1" -Action Stop
timeout /t 3 >nul
