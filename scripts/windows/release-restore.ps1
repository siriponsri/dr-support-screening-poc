param(
    [string]$Bundle,
    [string]$ExpectedTargetDatabase,
    [string]$ImageDestination,
    [string]$OutputDestination,
    [switch]$Apply,
    [switch]$TargetQuiesced
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "release-common.ps1")

try {
    if (-not $Bundle -or -not $ExpectedTargetDatabase -or -not $ImageDestination -or -not $OutputDestination) {
        throw "Supply -Bundle, -ExpectedTargetDatabase, and new -ImageDestination/-OutputDestination directories. Default is plan only."
    }
    Read-ReleaseDotEnv
    if (-not ([string]$env:DR_SUPPORT_RESTORE_DATABASE_URL).Trim()) {
        throw "An operator must provision the separate test database and privately set DR_SUPPORT_RESTORE_DATABASE_URL."
    }
    $python = Get-ReleasePythonPath
    $recoveryArguments = @("-m", "dr_support.persistence.recovery", "restore",
        "--bundle", $Bundle, "--expected-target-database", $ExpectedTargetDatabase,
        "--image-destination", $ImageDestination, "--output-destination", $OutputDestination)
    if ($Apply) { $recoveryArguments += "--apply" }
    if ($TargetQuiesced) { $recoveryArguments += "--target-quiesced" }
    & $python @recoveryArguments
    exit $LASTEXITCODE
} catch {
    Write-Host "[BLOCKED] Restore launcher could not continue. Check the approved isolated test database configuration, exact target name and required new directories; consult docs/operations/BACKUP_RESTORE.md. No service was started or stopped."
    exit 2
}
