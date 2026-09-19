@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo OWNER ACTION REQUIRED: create the existing .venv and install the project dependencies first.
  exit /b 1
)

if not defined DR_DEMO_FOLDER set "DR_DEMO_FOLDER=%USERPROFILE%\Desktop\DR-DEMO"
if not exist "%DR_DEMO_FOLDER%\" (
  echo OWNER ACTION REQUIRED: demo folder was not found: %DR_DEMO_FOLDER%
  exit /b 1
)
for %%F in (IMG_01.jpg IMG_02.jpg IMG_03.jpg) do (
  if not exist "%DR_DEMO_FOLDER%\%%F" (
    echo OWNER ACTION REQUIRED: missing demo image %DR_DEMO_FOLDER%\%%F
    exit /b 1
  )
)

if not defined REMOTE_MODEL_URL (
  echo OWNER ACTION REQUIRED: set REMOTE_MODEL_URL to the externally configured Lightning model API URL.
  exit /b 1
)

if not exist "frontend\dist\index.html" (
  where npm >nul 2>&1
  if errorlevel 1 (
    echo OWNER ACTION REQUIRED: npm is required to build the React demo app.
    exit /b 1
  )
  if not exist "frontend\node_modules" (
    echo Installing frontend dependencies...
    pushd frontend
    call npm ci
    if errorlevel 1 (
      popd
      exit /b 1
    )
    popd
  )
  echo Building the React demo app...
  pushd frontend
  call npm run build
  if errorlevel 1 (
    popd
    exit /b 1
  )
  popd
)

set "APP_PROFILE=review"
set "MODEL_RUNTIME=remote"
echo Starting clinician review workstation at http://127.0.0.1:8000/app/
echo Demo folder: %DR_DEMO_FOLDER%
.venv\Scripts\python.exe -m dr_support.run
set "EXIT_CODE=%ERRORLEVEL%"
pause
exit /b %EXIT_CODE%
