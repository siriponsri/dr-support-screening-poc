Set-StrictMode -Version Latest

$script:ReleaseRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:ReleaseStateRoot = Join-Path $script:ReleaseRepoRoot "local-state\release"
$script:ReleaseLogRoot = Join-Path $script:ReleaseRepoRoot "local-state\logs"
$script:ReleaseRunFile = Join-Path $script:ReleaseStateRoot "workstation.json"

function Ensure-ReleaseDirectories {
    foreach ($path in @($script:ReleaseStateRoot, $script:ReleaseLogRoot)) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }
}

function Get-ReleaseUvPath {
    $command = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidates = @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "uv\uv.exe"),
        (Join-Path $script:ReleaseRepoRoot "local-state\tools\uv.exe")
    )
    return $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}

function Get-ReleasePythonPath {
    $python = Join-Path $script:ReleaseRepoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Project Python is missing. Run FIRST_RUN.bat once from the extracted workstation package."
    }
    return $python
}

function Read-ReleaseDotEnv {
    $envPath = Join-Path $script:ReleaseRepoRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) { return }
    foreach ($line in Get-Content -LiteralPath $envPath) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        if ($trimmed -notmatch "^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$") { continue }
        $name = $Matches[1]
        $value = $Matches[2].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Set-ReleaseReviewEnvironment {
    Read-ReleaseDotEnv
    $env:APP_PROFILE = "review"
    $env:MODEL_RUNTIME = "remote"
    $env:HOST = "127.0.0.1"
    $env:PORT = "8000"
    $env:WORKERS = "1"
}

function Test-ReleaseFrontend {
    $index = Join-Path $script:ReleaseRepoRoot "frontend\dist\index.html"
    if (-not (Test-Path -LiteralPath $index -PathType Leaf)) {
        throw "The prebuilt frontend is missing. Re-extract the complete workstation release package; do not run a developer build on this workstation."
    }
}

function Get-ReleaseRecord {
    if (-not (Test-Path -LiteralPath $script:ReleaseRunFile -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $script:ReleaseRunFile -Raw | ConvertFrom-Json } catch { return $null }
}

function Get-ReleaseProcessDetails([int] $ProcessId) {
    return Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}

function Test-ReleaseManagedProcess([int] $ProcessId) {
    $details = Get-ReleaseProcessDetails $ProcessId
    if (-not $details) { return $false }
    $command = ([string]$details.CommandLine).ToLowerInvariant()
    $python = (Join-Path $script:ReleaseRepoRoot ".venv\Scripts\python.exe").ToLowerInvariant()
    return $command.Contains("dr_support.run") -and $command.Contains($python)
}

function Test-ReleaseHealth {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch { return $false }
}

function Write-ReleaseRecord([int] $ProcessId) {
    Ensure-ReleaseDirectories
    [pscustomobject]@{
        pid = $ProcessId
        repo = $script:ReleaseRepoRoot
        url = "http://127.0.0.1:8000/app/"
        started_at = (Get-Date).ToUniversalTime().ToString("o")
        stdout_log = (Join-Path $script:ReleaseLogRoot "workstation.stdout.log")
        stderr_log = (Join-Path $script:ReleaseLogRoot "workstation.stderr.log")
    } | ConvertTo-Json | Set-Content -LiteralPath $script:ReleaseRunFile
}

function Remove-ReleaseRecord {
    if (Test-Path -LiteralPath $script:ReleaseRunFile) { Remove-Item -LiteralPath $script:ReleaseRunFile -Force }
}
