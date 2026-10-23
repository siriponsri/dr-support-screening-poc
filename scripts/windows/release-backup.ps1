param(
    [string]$ImageRoot,
    [string]$Destination,
    [string]$Release,
    [string]$HospitalSourceMap,
    [string]$ExpectedHospitalSourceMapSha256,
    [string]$HospitalRestoreMap,
    [string]$ExpectedHospitalRestoreMapSha256,
    [string]$ExpectedManifestSha256,
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
        if ($ExpectedManifestSha256) { $recoveryArguments += @("--expected-manifest-sha256", $ExpectedManifestSha256) }
        if ($HospitalRestoreMap) { $recoveryArguments += @("--hospital-restore-map", $HospitalRestoreMap) }
        if ($ExpectedHospitalRestoreMapSha256) { $recoveryArguments += @("--expected-hospital-restore-map-sha256", $ExpectedHospitalRestoreMapSha256) }
    } else {
        if (([bool]$ImageRoot -eq [bool]$HospitalSourceMap) -or -not $Destination -or -not $Release -or $HospitalRestoreMap -or $ExpectedHospitalRestoreMapSha256 -or $ExpectedManifestSha256) {
            throw "Supply either -ImageRoot or the independently pinned -HospitalSourceMap, a new -Destination, and -Release. Default is plan only."
        }
        Read-ReleaseDotEnv
        if (-not ([string]$env:DR_SUPPORT_DATABASE_URL).Trim()) {
            $local = Import-ReleaseLocalDatabaseConfig
            if (-not $local) { throw "Configure the approved database privately or start the existing workstation first." }
        }
        $recoveryArguments = @("-m", "dr_support.persistence.recovery", "backup",
            "--destination", $Destination, "--release", $Release)
        if ($ImageRoot) { $recoveryArguments += @("--image-root", $ImageRoot) }
        if ($Apply) { $recoveryArguments += "--apply" }
    }
    if ($HospitalSourceMap) { $recoveryArguments += @("--hospital-source-map", $HospitalSourceMap) }
    if ($ExpectedHospitalSourceMapSha256) { $recoveryArguments += @("--expected-hospital-source-map-sha256", $ExpectedHospitalSourceMapSha256) }
    & $python @recoveryArguments
    exit $LASTEXITCODE
} catch {
    Write-Host "[BLOCKED] Recovery launcher could not continue. Supply the required absolute paths/release, verify the existing private database configuration and project Python, and consult docs/operations/BACKUP_RESTORE.md. No service was started or stopped."
    exit 2
}
