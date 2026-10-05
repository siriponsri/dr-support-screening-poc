param([switch]$NoBrowser)

Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "release-common.ps1")

try {
    Set-ReleaseReviewEnvironment
    Ensure-ReleaseDirectories
    Test-ReleaseFrontend
    $postgres = Ensure-ReleasePostgres
    $postgresStatus = Test-ReleasePostgres
    if (-not $postgresStatus.Ready) {
        throw $postgresStatus.Detail
    }
    $record = Get-ReleaseRecord
    if ($record -and (Test-ReleaseManagedProcess ([int]$record.pid)) -and (Test-ReleaseHealth)) {
        Write-Host "Retinal Review Workbench is already running at $($record.url)."
        if (-not $NoBrowser) { Start-Process $record.url }
        exit 0
    }
    if ($record) { Remove-ReleaseRecord }
    $python = Get-ReleasePythonPath
    $portProcess = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($portProcess) {
        $details = Get-ReleaseProcessDetails ([int]$portProcess.OwningProcess)
        $processName = if ($details -and $details.Name) { [string]$details.Name } else { "unknown executable" }
        Stop-ReleaseLocalPostgres $postgres
        throw "Port 8000 is already in use by PID $($portProcess.OwningProcess) ($processName). No process was stopped."
    }
    $stdout = Join-Path $script:ReleaseLogRoot "workstation.stdout.log"
    $stderr = Join-Path $script:ReleaseLogRoot "workstation.stderr.log"
    $process = Start-Process -FilePath $python -ArgumentList @("-m", "dr_support.run") -WorkingDirectory $script:ReleaseRepoRoot -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
    Write-ReleaseRecord ([int]$process.Id) $postgres
    $healthy = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (-not (Test-ReleaseManagedProcess ([int]$process.Id))) { break }
        if (Test-ReleaseHealth) { $healthy = $true; break }
    }
    if (-not $healthy) {
        if (Test-ReleaseManagedProcess ([int]$process.Id)) { Stop-Process -Id $process.Id -Force }
        Stop-ReleaseLocalPostgres $postgres
        Remove-ReleaseRecord
        throw "The workstation did not become healthy at http://127.0.0.1:8000/health. Review the credential-safe logs under local-state/logs/ and retry after correcting the reported startup issue."
    }
    Write-Host "Retinal Review Workbench is running at http://127.0.0.1:8000/app/"
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:8000/app/" }
    exit 0
} catch {
    Write-Error $_
    exit 1
}
