Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "release-common.ps1")

$failures = 0
function Report([string]$Name, [bool]$Pass, [string]$Detail) {
    $state = if ($Pass) { "PASS" } else { "NOT_READY" }
    Write-Host ("[{0}] {1}: {2}" -f $state, $Name, $Detail)
    if (-not $Pass) { $script:failures++ }
}

try {
    Write-Host "Release workstation: $script:ReleaseRepoRoot"
    $index = Join-Path $script:ReleaseRepoRoot "frontend\dist\index.html"
    Report "Prebuilt frontend" (Test-Path -LiteralPath $index -PathType Leaf) "frontend/dist/index.html"
    $python = Join-Path $script:ReleaseRepoRoot ".venv\Scripts\python.exe"
    Report "Project Python" (Test-Path -LiteralPath $python -PathType Leaf) ".venv/Scripts/python.exe; run FIRST_RUN.bat if missing"
    if (Test-Path -LiteralPath $python -PathType Leaf) {
        & $python -c "import fastapi, dr_support; print('  imports: PASS')"
        Report "Python imports" ($LASTEXITCODE -eq 0) "FastAPI and dr_support"
    } else {
        Report "Python imports" $false "unavailable until FIRST_RUN.bat completes"
    }
    $postgres = Test-ReleasePostgres
    Report "Managed PostgreSQL readiness" $postgres.Ready $postgres.Detail
    $uv = Get-ReleaseUvPath
    Report "uv" ([bool]$uv) "optional after first run; used for provisioning"
    $record = Get-ReleaseRecord
    if ($record -and (Test-ReleaseManagedProcess ([int]$record.pid))) {
        Report "Workstation process" $true "managed PID $($record.pid); health=$((Test-ReleaseHealth).ToString().ToUpperInvariant())"
    } else {
        Write-Host "[STOPPED] Workstation process: not running (this is safe; START_DR_SCREENING.bat starts it)."
    }
    if ($failures -gt 0) {
        Write-Host "System check is not ready. Fix the reported items, then run CHECK_SYSTEM.bat again."
        exit 1
    }
    Write-Host "System check passed. The workstation can be started without npm commands."
    exit 0
} catch {
    Write-Error $_
    exit 1
}
