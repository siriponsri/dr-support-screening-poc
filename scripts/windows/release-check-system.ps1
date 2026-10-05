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
    try {
        Test-ReleaseFrontend
        Report "Frontend build identity/readiness" $true "Retinal Review Workbench SPA and referenced assets are present"
    } catch {
        Report "Frontend build identity/readiness" $false $_.Exception.Message
    }
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
    if ($postgres.Source -eq "local") {
        $docker = Get-ReleaseDockerPath
        Report "Docker Desktop for project-owned PostgreSQL" ([bool]$docker) "Docker CLI is required only for the private local PostgreSQL path"
    } elseif ($postgres.Source -eq "external") {
        Write-Host "[INFO] External PostgreSQL is selected; Docker is not required or started."
    } else {
        Write-Host "[INFO] No PostgreSQL source is ready yet; START_DR_SCREENING.bat will provision the project-owned local path when Docker Desktop is available."
    }
    $uv = Get-ReleaseUvPath
    Report "uv" ([bool]$uv) "optional after first run; used for provisioning"
    $record = Get-ReleaseRecord
    $processStatus = Get-ReleaseProcessStatus $record
    if ($processStatus.State -eq "STOPPED") {
        Write-Host "[STOPPED] Workstation process: not running (this is safe; START_DR_SCREENING.bat starts it)."
    } else {
        Report "Workstation process" $processStatus.Ready $processStatus.Detail
    }
    if ($processStatus.State -eq "RUNNING" -and $processStatus.Ready) {
        try {
            $workspaceResponse = Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/workspaces/active" -UseBasicParsing -TimeoutSec 2
            Report "Workspace API readiness" ($workspaceResponse.StatusCode -eq 200) "active workspace endpoint responded"
        } catch {
            Report "Workspace API readiness" $false "The running workstation did not return its active workspace state."
        }
    } else {
        Write-Host "[NOT_RUN] Workspace API readiness: start the workstation to verify the active workspace endpoint."
    }
    $modelUrl = ($env:REMOTE_MODEL_URL | ForEach-Object { $_.Trim() })
    if (-not $modelUrl) {
        Write-Host "[PASS] Model API / manual mode: no remote URL is configured; manual review remains available."
    } else {
        try {
            $headers = @{}
            if ($env:REMOTE_MODEL_TOKEN) { $headers.Authorization = "Bearer $env:REMOTE_MODEL_TOKEN" }
            $modelHealth = Invoke-WebRequest -Uri "$modelUrl/health" -Headers $headers -UseBasicParsing -TimeoutSec 5
            $healthBody = $modelHealth.Content | ConvertFrom-Json
            $healthStatus = ([string]$healthBody.status).Trim().ToUpperInvariant()
            if ($modelHealth.StatusCode -ne 200 -or -not (Test-ReleaseModelHealth $healthBody)) {
                Write-Host "[WARN] Model API connection: remote health/assets are not verified; manual review remains available."
            } else {
                $modelList = Invoke-WebRequest -Uri "$modelUrl/v1/models" -Headers $headers -UseBasicParsing -TimeoutSec 5
                $capabilityStatus = if ($modelList.StatusCode -eq 200) {
                    Get-ReleaseModelCapabilityStatus $modelList.Content
                } else {
                    [pscustomobject]@{ Valid = $false; Ready = $false }
                }
                if (-not $capabilityStatus.Valid) {
                    Write-Host "[WARN] Model API connection: capability discovery could not be verified; manual review remains available."
                } else {
                    if ($capabilityStatus.Ready -and $healthStatus -eq "PASS") {
                        Write-Host "[PASS] Model API connection: health and capability discovery verified; manual review remains available."
                    } else {
                        Write-Host "[WARN] Model API connection: reachable but no ready capability was verified; manual review remains available."
                    }
                }
            }
        } catch {
            Write-Host "[WARN] Model API connection: health or capability discovery failed; manual review remains available."
        }
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
