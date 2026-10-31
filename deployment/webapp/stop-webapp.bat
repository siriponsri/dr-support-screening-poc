@echo off
rem Stop the web app package. Data (database and folders) is kept.
set "ENVFILE=%LOCALAPPDATA%\DRScreening\webapp.env"
docker compose --env-file "%ENVFILE%" -f "%~dp0compose.yml" stop
echo Stopped. Data is kept.
timeout /t 3 >nul
