Set-StrictMode -Version Latest

$script:ReleaseRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:ReleaseStateRoot = Join-Path $script:ReleaseRepoRoot "local-state\release"
$script:ReleaseLogRoot = Join-Path $script:ReleaseRepoRoot "local-state\logs"
$script:ReleaseRunFile = Join-Path $script:ReleaseStateRoot "workstation.json"
$script:ReleaseLocalDatabaseEnvFile = Join-Path $script:ReleaseStateRoot "postgres.env"
$script:ReleaseComposeFile = Join-Path $script:ReleaseRepoRoot "deployment\docker-compose.local-postgres.yml"
$script:ReleaseComposeService = "postgres"

function Get-ReleaseCheckoutIdentity {
    $normalizedPath = [IO.Path]::GetFullPath($script:ReleaseRepoRoot).TrimEnd('\', '/').ToUpperInvariant()
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($normalizedPath))
    } finally {
        $sha.Dispose()
    }
    return (-join ($digest | ForEach-Object { $_.ToString("x2") })).Substring(0, 16)
}

$script:ReleaseCheckoutIdentity = Get-ReleaseCheckoutIdentity
$script:ReleaseComposeProject = "dr-support-workstation-$script:ReleaseCheckoutIdentity"
$script:ReleaseComposeVolume = "dr_support_workstation_postgres_data_$script:ReleaseCheckoutIdentity"

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
        if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
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

function Get-ReleaseDockerPath {
    $command = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    return $null
}

function Get-ReleaseComposeArguments([string[]] $Arguments) {
    return @(
        "compose",
        "--project-name", $script:ReleaseComposeProject,
        "--file", $script:ReleaseComposeFile,
        "--env-file", $script:ReleaseLocalDatabaseEnvFile
    ) + $Arguments
}

function Invoke-ReleaseCompose([string] $Docker, [string[]] $Arguments) {
    if (-not (Test-Path -LiteralPath $script:ReleaseComposeFile -PathType Leaf)) {
        throw "The project-owned PostgreSQL Compose definition is missing. Re-extract the complete workstation package."
    }
    $composeArguments = Get-ReleaseComposeArguments $Arguments
    $null = & $Docker @composeArguments 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose could not complete the project-owned PostgreSQL operation. Start Docker Desktop and retry; no SQLite fallback is used."
    }
}

function Import-ReleaseLocalDatabaseConfig {
    if (-not (Test-Path -LiteralPath $script:ReleaseLocalDatabaseEnvFile -PathType Leaf)) {
        return $null
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $script:ReleaseLocalDatabaseEnvFile) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        if ($trimmed -notmatch "^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$") { continue }
        $values[$Matches[1]] = $Matches[2].Trim()
    }
    $required = @(
        "DR_SUPPORT_POSTGRES_DB",
        "DR_SUPPORT_POSTGRES_USER",
        "DR_SUPPORT_POSTGRES_PASSWORD",
        "DR_SUPPORT_POSTGRES_BIND",
        "DR_SUPPORT_POSTGRES_PORT",
        "DR_SUPPORT_DATABASE_URL",
        "DR_SUPPORT_CHECKOUT_ID",
        "DR_SUPPORT_POSTGRES_VOLUME"
    )
    $missing = @($required | Where-Object { -not $values.ContainsKey($_) -or -not $values[$_] })
    if ($missing.Count -gt 0) {
        throw "Legacy project-owned PostgreSQL state detected in local-state/release/postgres.env. An owner must preserve or back up its data, then remove only that ignored env file to provision checkout-isolated state; the legacy named volume is not removed automatically."
    }
    if ($values["DR_SUPPORT_CHECKOUT_ID"] -ne $script:ReleaseCheckoutIdentity -or
        $values["DR_SUPPORT_POSTGRES_VOLUME"] -ne $script:ReleaseComposeVolume) {
        throw "Project-owned PostgreSQL state belongs to another checkout identity. An owner must preserve or back up its data before migrating this checkout; no existing volume was changed."
    }
    foreach ($name in $values.Keys) {
        [Environment]::SetEnvironmentVariable($name, $values[$name], "Process")
    }
    return [pscustomobject]@{
        Source = "local"
        Dsn = $env:DR_SUPPORT_DATABASE_URL
        Database = $env:DR_SUPPORT_POSTGRES_DB
        User = $env:DR_SUPPORT_POSTGRES_USER
        Port = $env:DR_SUPPORT_POSTGRES_PORT
        ManagedLocal = $true
        Project = $script:ReleaseComposeProject
        Service = $script:ReleaseComposeService
        ComposeFile = $script:ReleaseComposeFile
    }
}

function New-ReleaseLocalDatabaseConfig {
    Ensure-ReleaseDirectories
    $existing = Import-ReleaseLocalDatabaseConfig
    if ($existing) { return $existing }
    $password = ([Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N"))
    $database = "dr_support"
    $user = "dr_support"
    $bind = "127.0.0.1"
    $port = "54329"
    $dsn = "postgresql://$user`:$password@$bind`:$port/$database"
    @(
        "DR_SUPPORT_POSTGRES_DB=$database",
        "DR_SUPPORT_POSTGRES_USER=$user",
        "DR_SUPPORT_POSTGRES_PASSWORD=$password",
        "DR_SUPPORT_POSTGRES_BIND=$bind",
        "DR_SUPPORT_POSTGRES_PORT=$port",
        "DR_SUPPORT_DATABASE_URL=$dsn",
        "DR_SUPPORT_CHECKOUT_ID=$script:ReleaseCheckoutIdentity",
        "DR_SUPPORT_POSTGRES_VOLUME=$script:ReleaseComposeVolume"
    ) | Set-Content -LiteralPath $script:ReleaseLocalDatabaseEnvFile -Encoding ascii
    return Import-ReleaseLocalDatabaseConfig
}

function Start-ReleaseLocalPostgres([object] $Database) {
    $docker = Get-ReleaseDockerPath
    if (-not $docker) {
        throw "No Docker CLI was found. Install and start Docker Desktop, then retry; configure an external PostgreSQL URL to use an existing server."
    }
    try {
        Invoke-ReleaseCompose $docker @("up", "-d", $script:ReleaseComposeService)
    } catch {
        throw "Project-owned PostgreSQL could not start. Start Docker Desktop and confirm the loopback port $($Database.Port) is available. No SQLite fallback is used."
    }
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $composeArguments = Get-ReleaseComposeArguments @(
            "exec", "-T", $script:ReleaseComposeService,
            "pg_isready", "-U", $Database.User, "-d", $Database.Database
        )
        $null = & $docker @composeArguments 2>$null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 1
    }
    throw "Project-owned PostgreSQL did not become ready. Check Docker Desktop and retry START_DR_SCREENING.bat; existing local data remains in the named volume."
}

function Stop-ReleaseLocalPostgres([object] $Database) {
    if (-not $Database) { return }
    $managedLocal = if ($Database.PSObject.Properties.Name -contains "ManagedLocal") {
        [bool]$Database.ManagedLocal
    } elseif ($Database.PSObject.Properties.Name -contains "managed_local") {
        [bool]$Database.managed_local
    } else {
        $false
    }
    $composeFile = if ($Database.PSObject.Properties.Name -contains "ComposeFile") {
        [string]$Database.ComposeFile
    } elseif ($Database.PSObject.Properties.Name -contains "compose_file") {
        [string]$Database.compose_file
    } else {
        ""
    }
    if (-not $managedLocal) { return }
    if ([string]$Database.Project -ne $script:ReleaseComposeProject -or
        [string]$Database.Service -ne $script:ReleaseComposeService -or
        $composeFile -ne $script:ReleaseComposeFile) {
        Write-Warning "Recorded PostgreSQL ownership does not match this checkout; no container was stopped."
        return
    }
    $docker = Get-ReleaseDockerPath
    if (-not $docker) {
        Write-Warning "Docker CLI is unavailable; the recorded project-owned PostgreSQL service was not stopped."
        return
    }
    try {
        Invoke-ReleaseCompose $docker @("stop", $script:ReleaseComposeService)
    } catch {
        Write-Warning "The workstation process stopped, but the project-owned PostgreSQL service could not be stopped. Start Docker Desktop and run STOP_DR_SCREENING.bat again."
    }
}

function Test-ReleasePostgres {
    Read-ReleaseDotEnv
    $mode = ($env:DR_SUPPORT_CASE_STORE | ForEach-Object { $_.Trim().ToLowerInvariant() })
    if ($mode -eq "sqlite") {
        return [pscustomobject]@{
            Ready = $false
            Mode = "sqlite"
            Source = "legacy"
            ManagedLocal = $false
            Detail = "Explicit DR_SUPPORT_CASE_STORE=sqlite is legacy compatibility mode; normal managed PostgreSQL readiness is not available."
        }
    }
    $source = "external"
    $dsn = ($env:DR_SUPPORT_DATABASE_URL | ForEach-Object { $_.Trim() })
    if (-not $dsn) {
        $local = Import-ReleaseLocalDatabaseConfig
        if ($local) {
            $source = "local"
            $dsn = $local.Dsn
        }
    }
    if (-not $dsn) {
        return [pscustomobject]@{
            Ready = $false
            Mode = "postgres"
            Source = "none"
            ManagedLocal = $false
            Detail = "No external PostgreSQL URL or project-owned local PostgreSQL state is configured. Run START_DR_SCREENING.bat or configure DR_SUPPORT_DATABASE_URL."
        }
    }
    $env:DR_SUPPORT_CASE_STORE = "postgres"
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
                Source = $source
                ManagedLocal = $source -eq "local"
                Detail = "PostgreSQL configuration and SELECT 1 connectivity verified without exposing credentials."
            }
        }
    } catch {
        # Diagnostics intentionally remain credential-safe and concise.
    }
    return [pscustomobject]@{
        Ready = $false
        Mode = "postgres"
        Source = $source
        ManagedLocal = $source -eq "local"
        Detail = "PostgreSQL is configured but the project Python could not verify SELECT 1 connectivity."
    }
}

function Ensure-ReleasePostgres {
    Read-ReleaseDotEnv
    $mode = ($env:DR_SUPPORT_CASE_STORE | ForEach-Object { $_.Trim().ToLowerInvariant() })
    if ($mode -eq "sqlite") {
        throw "DR_SUPPORT_CASE_STORE=sqlite is legacy compatibility mode and cannot be used by the normal Windows workstation launcher."
    }
    $externalDsn = ($env:DR_SUPPORT_DATABASE_URL | ForEach-Object { $_.Trim() })
    if ($externalDsn) {
        $status = Test-ReleasePostgres
        if (-not $status.Ready) { throw $status.Detail }
        return [pscustomobject]@{
            Ready = $true
            Mode = "postgres"
            Source = "external"
            ManagedLocal = $false
            Detail = $status.Detail
        }
    }
    $local = New-ReleaseLocalDatabaseConfig
    Start-ReleaseLocalPostgres $local
    $env:DR_SUPPORT_DATABASE_URL = $local.Dsn
    $env:DR_SUPPORT_CASE_STORE = "postgres"
    $status = Test-ReleasePostgres
    if (-not $status.Ready) {
        Stop-ReleaseLocalPostgres $local
        throw "Project-owned PostgreSQL started but connectivity verification failed. Check Docker Desktop and local-state/logs, then retry."
    }
    return $local
}

function Test-ReleaseFrontend {
    $index = Join-Path $script:ReleaseRepoRoot "frontend\dist\index.html"
    if (-not (Test-Path -LiteralPath $index -PathType Leaf)) {
        throw "The prebuilt frontend is missing. Re-extract the complete workstation release package; do not run a developer build on this workstation."
    }
    $identityPath = Join-Path $script:ReleaseRepoRoot "frontend\dist\build-identity.json"
    if (-not (Test-Path -LiteralPath $identityPath -PathType Leaf)) {
        throw "The prebuilt frontend identity is missing. Rebuild frontend/dist or re-extract the complete workstation release package."
    }
    try {
        $identity = Get-Content -LiteralPath $identityPath -Raw | ConvertFrom-Json
    } catch {
        throw "The prebuilt frontend identity is invalid. Rebuild frontend/dist or re-extract the complete workstation release package."
    }
    if ($identity.schema_version -ne "frontend-build-identity.v1" -or
        [string]$identity.source_commit -notmatch "^[0-9a-f]{40}$" -or
        [string]$identity.source_digest -notmatch "^[0-9a-f]{64}$" -or
        [string]$identity.output_set_sha256 -notmatch "^[0-9a-f]{64}$") {
        throw "The prebuilt frontend identity is incomplete. Rebuild frontend/dist or re-extract the complete workstation release package."
    }
    $declaredOutputs = @($identity.output_files)
    if (-not ($declaredOutputs | Where-Object { $_.path -eq "index.html" })) {
        throw "The prebuilt frontend identity does not include index.html. Rebuild frontend/dist."
    }
    foreach ($output in $declaredOutputs) {
        $relative = [string]$output.path
        if (-not $relative -or $relative -eq "build-identity.json" -or
            [IO.Path]::IsPathRooted($relative) -or $relative.Contains("..") -or
            -not (Test-Path -LiteralPath (Join-Path $script:ReleaseRepoRoot (Join-Path "frontend/dist" $relative)) -PathType Leaf)) {
            throw "The prebuilt frontend identity references a missing or unsafe output. Rebuild frontend/dist."
        }
    }
    $html = Get-Content -LiteralPath $index -Raw
    if ($html -notmatch '<title>Retinal Review Workbench</title>') {
        throw "The prebuilt frontend identity is invalid. Re-extract the complete workstation release package."
    }
    $assetPaths = [regex]::Matches($html, '(?:src|href)="(/app/assets/[^"]+)"') |
        ForEach-Object { $_.Groups[1].Value }
    if (-not $assetPaths -or ($assetPaths | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $script:ReleaseRepoRoot ($_ -replace '^/app/', 'frontend/dist/')) -PathType Leaf)
    })) {
        throw "The prebuilt frontend assets are incomplete. Re-extract the complete workstation release package."
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

function Write-ReleaseRecord([int] $ProcessId, [object] $Database = $null) {
    Ensure-ReleaseDirectories
    [pscustomobject]@{
        pid = $ProcessId
        repo = $script:ReleaseRepoRoot
        url = "http://127.0.0.1:8000/app/"
        started_at = (Get-Date).ToUniversalTime().ToString("o")
        stdout_log = (Join-Path $script:ReleaseLogRoot "workstation.stdout.log")
        stderr_log = (Join-Path $script:ReleaseLogRoot "workstation.stderr.log")
        database = if ($Database) {
            [pscustomobject]@{
                managed_local = [bool]$Database.ManagedLocal
                project = [string]$Database.Project
                service = [string]$Database.Service
                compose_file = [string]$Database.ComposeFile
            }
        } else { $null }
    } | ConvertTo-Json | Set-Content -LiteralPath $script:ReleaseRunFile
}

function Remove-ReleaseRecord {
    if (Test-Path -LiteralPath $script:ReleaseRunFile) { Remove-Item -LiteralPath $script:ReleaseRunFile -Force }
}
