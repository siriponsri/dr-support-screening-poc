@echo off
rem Share the running DR Screening demo with invited team members (Cloudflare Tunnel + Access). Double-click.
rem Start the demo first (desktop button "DR Screening Demo"). Keep this window open while sharing.
rem First time only: asks you to confirm the demo-data rule and to paste the tunnel token (kept private).
title DR Screening demo sharing
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tunnel.ps1" -Action Start %*
echo.
pause
