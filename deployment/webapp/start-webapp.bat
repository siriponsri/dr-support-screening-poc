@echo off
rem One click on Windows with Docker Desktop: start the web app package and open it.
rem Settings: %LOCALAPPDATA%\DRScreening\webapp.env (copy from webapp.env.example and fill it in).
title DR Screening web app
setlocal
set "ENVFILE=%LOCALAPPDATA%\DRScreening\webapp.env"
if not exist "%ENVFILE%" (
  echo Settings file not found: %ENVFILE%
  echo Copy webapp.env.example there and fill it in.
  pause
  exit /b 1
)
docker info >nul 2>&1 || (
  echo Docker Desktop is not running. Start Docker Desktop, then try again.
  pause
  exit /b 1
)
echo Starting the DR Screening web app...
docker compose --env-file "%ENVFILE%" -f "%~dp0compose.yml" up -d || (pause & exit /b 1)
echo Waiting for the web app to answer...
for /l %%i in (1,1,60) do (
  curl -s -k -o nul https://localhost/health && goto ready
  timeout /t 3 /nobreak >nul
)
echo The web app did not answer in 3 minutes. Run: docker compose logs review
pause
exit /b 1
:ready
start "" https://localhost/app/
echo Ready: https://localhost/app/  (stop with stop-webapp.bat; data is kept)
timeout /t 5 >nul
