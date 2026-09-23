. (Join-Path $PSScriptRoot "workstation-common.ps1")

try {
    $record = Get-ManagedRecord
    if (-not $record) {
        Write-Host "No repository-managed workstation process is recorded. No process was stopped."
        exit 0
    }
    $processId = [int]$record.pid
    if (-not (Test-ManagedProcess $processId)) {
        Remove-ManagedRecord
        Write-Host "The recorded workstation process is no longer running. No unrelated process was stopped."
        exit 0
    }
    Stop-Process -Id $processId -Force
    for ($attempt = 0; $attempt -lt 20 -and (Get-Process -Id $processId -ErrorAction SilentlyContinue); $attempt++) {
        Start-Sleep -Milliseconds 250
    }
    Remove-ManagedRecord
    Write-Host "Stopped the repository-managed workstation process (PID $processId)."
    exit 0
} catch {
    Write-Error $_
    exit 1
}
