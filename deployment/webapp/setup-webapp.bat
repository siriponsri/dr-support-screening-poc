@echo off
rem First-time setup of the DR Screening web app (Windows with Docker Desktop). Double-click this file.
title DR Screening web app setup
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bin\setup-webapp.ps1" %*
echo.
pause
