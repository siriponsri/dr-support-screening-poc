param([switch]$NoBrowser)

. (Join-Path $PSScriptRoot "workstation-common.ps1")

try {
    Set-SafeWorkstationEnvironment
    Ensure-LauncherDirectories
    $record = Get-ManagedRecord
    if ($record -and (Test-ManagedProcess ([int]$record.pid)) -and (Test-AppHealth)) {
        Write-Host "Retinal Review Workbench is already running at $($record.url)."
        if (-not $NoBrowser) { Start-Process $record.url }
        exit 0
    }
    if ($record) { Remove-ManagedRecord }
    $portProcess = Get-ListeningProcess 8000
    if ($portProcess) {
        $details = $portProcess.Details
        $command = if ($details) { [string]$details.CommandLine } else { "command line unavailable" }
        Write-Error "Port 8000 is already in use by PID $($portProcess.Pid): $command"
        Write-Host "No process was stopped. Stop that process deliberately or choose another approved deployment boundary."
        exit 1
    }
    $python = Get-PythonPath
    Ensure-FrontendBuild | Out-Null
    $stdout = Join-Path $script:LogRoot "workstation.stdout.log"
    $stderr = Join-Path $script:LogRoot "workstation.stderr.log"
    $process = Start-Process -FilePath $python -ArgumentList @("-m", "dr_support.run") -WorkingDirectory $script:RepoRoot -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
    Write-ManagedRecord ([int]$process.Id)
    $healthy = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (-not (Test-ManagedProcess ([int]$process.Id))) { break }
        if (Test-AppHealth) { $healthy = $true; break }
    }
    if (-not $healthy) {
        $tail = if (Test-Path -LiteralPath $stderr) { (Get-Content -LiteralPath $stderr -Tail 8) -join "`n" } else { "" }
        if (Test-ManagedProcess ([int]$process.Id)) { Stop-Process -Id $process.Id -Force }
        Remove-ManagedRecord
        throw "The workstation did not become healthy at http://127.0.0.1:8000/health.`n$tail"
    }
    Write-Host "Retinal Review Workbench is running at http://127.0.0.1:8000/app/"
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:8000/app/" }
    exit 0
} catch {
    Write-Error $_
    exit 1
}
