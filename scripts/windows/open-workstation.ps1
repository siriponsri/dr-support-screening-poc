. (Join-Path $PSScriptRoot "workstation-common.ps1")

try {
    Set-SafeWorkstationEnvironment
    $record = Get-ManagedRecord
    if ($record -and (Test-ManagedProcess ([int]$record.pid)) -and (Test-AppHealth)) {
        Start-Process "http://127.0.0.1:8000/app/"
        exit 0
    }
    & (Join-Path $PSScriptRoot "start-workstation.ps1")
    exit $LASTEXITCODE
} catch {
    Write-Error $_
    exit 1
}
