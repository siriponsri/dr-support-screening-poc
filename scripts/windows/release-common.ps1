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

function Test-ReleasePostgres {
    Read-ReleaseDotEnv
    $mode = ($env:DR_SUPPORT_CASE_STORE | ForEach-Object { $_.Trim().ToLowerInvariant() })
    if ($mode -eq "sqlite") {
        return [pscustomobject]@{
            Ready = $false
            Mode = "sqlite"
            Detail = "Explicit DR_SUPPORT_CASE_STORE=sqlite is legacy compatibility mode; normal managed PostgreSQL readiness is not available."
        }
    }
    $dsn = ($env:DR_SUPPORT_DATABASE_URL | ForEach-Object { $_.Trim() })
    if (-not $dsn) {
        return [pscustomobject]@{
            Ready = $false
            Mode = "postgres"
            Detail = "DR_SUPPORT_DATABASE_URL is not configured in the private server environment."
        }
    }
    try {
        $python = Get-ReleasePythonPath
        $probe = @"
from dr_support.persistence import PostgresDatabase, PostgresSettings
PostgresDatabase(PostgresSettings.from_env()).verify_available()
print('READY')
"@
        $output = & $python -c $probe 2>$null
        if ($LASTEXITCODE -eq 0 -and ($output -join "`n") -match "READY") {
            return [pscustomobject]@{
                Ready = $true
                Mode = "postgres"
                Detail = "PostgreSQL configuration and SELECT 1 connectivity verified without exposing credentials."
            }
        }
    } catch {
        # Diagnostics intentionally remain credential-safe and concise.
    }
    return [pscustomobject]@{
        Ready = $false
        Mode = "postgres"
        Detail = "PostgreSQL is configured but the project Python could not verify SELECT 1 connectivity."
    }
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

function Get-ReleaseProcessStatus([object] $Record) {
    if (-not $Record) {
        return [pscustomobject]@{
            State = "STOPPED"
            Ready = $true
            Detail = "not running"
        }
    }
    $processId = [int]$Record.pid
    if (-not (Test-ReleaseManagedProcess $processId)) {
        return [pscustomobject]@{
            State = "STOPPED"
            Ready = $true
            Detail = "recorded process is not running"
        }
    }
    $healthy = [bool](Test-ReleaseHealth)
    return [pscustomobject]@{
        State = if ($healthy) { "RUNNING" } else { "UNHEALTHY" }
        Ready = $healthy
        Detail = "managed PID $processId; health=$($healthy.ToString().ToUpperInvariant())"
    }
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
