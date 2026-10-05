Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "release-common.ps1")

try {
    $record = Get-ReleaseRecord
    if (-not $record) {
        Write-Host "No release-managed workstation process is recorded. No process was stopped."
        exit 0
    }
    $processId = [int]$record.pid
    if (-not (Test-ReleaseManagedProcess $processId)) {
        Stop-ReleaseLocalPostgres $record.database
        Remove-ReleaseRecord
        Write-Host "The recorded release workstation process is no longer running. No unrelated process was stopped."
        exit 0
    }
    Stop-Process -Id $processId -Force
    for ($attempt = 0; $attempt -lt 20 -and (Get-Process -Id $processId -ErrorAction SilentlyContinue); $attempt++) {
        Start-Sleep -Milliseconds 250
    }
    Stop-ReleaseLocalPostgres $record.database
    Remove-ReleaseRecord
    Write-Host "Stopped the release-managed workstation process (PID $processId)."
    exit 0
} catch {
    Write-Error $_
    exit 1
}
