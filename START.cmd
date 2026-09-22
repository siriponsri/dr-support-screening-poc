@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating Python 3.12 environment...
  py -3.12 -m venv .venv >nul 2>&1
  if errorlevel 1 (
    where uv >nul 2>&1
    if not errorlevel 1 (
      echo Windows py launcher does not expose 3.12; using uv-managed Python 3.12.
      uv venv --python 3.12 .venv
    )
  )
  if not exist ".venv\Scripts\python.exe" (
    echo Python 3.11 or 3.12 is required. If uv is installed, run: uv venv --python 3.12 .venv
    echo See docs\INSTALLATION.md.
    pause
    exit /b 1
  )
  .venv\Scripts\python.exe -m pip install -e .
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
if not exist "frontend\dist\index.html" (
  where npm >nul 2>&1
  if errorlevel 1 (
    echo npm is required to build the clinician workstation UI.
    pause
    exit /b 1
  )
  if not exist "frontend\node_modules" (
    echo Installing frontend dependencies...
    pushd frontend
    call npm ci
    if errorlevel 1 (
      popd
      pause
      exit /b 1
    )
    popd
  )
  echo Building the clinician workstation UI...
  pushd frontend
  call npm run build
  if errorlevel 1 (
    popd
    pause
    exit /b 1
  )
  popd
)

set "APP_PROFILE=review"
set "MODEL_RUNTIME=remote"
echo Starting Retinal Review Workbench clinician workstation.
echo Open http://127.0.0.1:8000/app/
echo Create or open a Workspace from Settings after startup.
.venv\Scripts\python.exe -m dr_support.run
pause
