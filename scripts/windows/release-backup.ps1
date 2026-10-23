param(
    [string]$ImageRoot,
    [string]$Destination,
    [string]$Release,
    [switch]$Apply,
    [switch]$Verify
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "release-common.ps1")

try {
    $python = Get-ReleasePythonPath
    if ($Verify) {
        if (-not $Destination) { throw "Supply the existing backup directory with -Destination." }
        $recoveryArguments = @("-m", "dr_support.persistence.recovery", "verify", "--bundle", $Destination)
    } else {
        if (-not $ImageRoot -or -not $Destination -or -not $Release) {
            throw "Supply -ImageRoot, a new -Destination outside the checkout, and -Release. Default is plan only; -Apply performs the backup."
        }
        Read-ReleaseDotEnv
        if (-not ([string]$env:DR_SUPPORT_DATABASE_URL).Trim()) {
            $local = Import-ReleaseLocalDatabaseConfig
            if (-not $local) { throw "Configure the approved database privately or start the existing workstation first." }
        }
        $recoveryArguments = @("-m", "dr_support.persistence.recovery", "backup",
            "--image-root", $ImageRoot, "--destination", $Destination, "--release", $Release)
        if ($Apply) { $recoveryArguments += "--apply" }
    }
    & $python @recoveryArguments
    exit $LASTEXITCODE
} catch {
    Write-Host "[BLOCKED] Recovery launcher could not continue. Supply the required absolute paths/release, verify the existing private database configuration and project Python, and consult docs/operations/BACKUP_RESTORE.md. No service was started or stopped."
    exit 2
}
