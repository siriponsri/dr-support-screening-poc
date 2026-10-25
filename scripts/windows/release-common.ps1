Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "release-docker.ps1")

$script:ReleaseRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:ReleaseStateRoot = Join-Path $script:ReleaseRepoRoot "local-state\release"
$script:ReleaseLogRoot = Join-Path $script:ReleaseRepoRoot "local-state\logs"
$script:ReleaseRunFile = Join-Path $script:ReleaseStateRoot "workstation.json"
$script:ReleaseLocalDatabaseEnvFile = Join-Path $script:ReleaseStateRoot "postgres.env"
# Written once by scripts/qa/configure_local_runtime_role.py (owner-approved AC-16).
$script:ReleaseRuntimeDatabaseEnvFile = Join-Path $script:ReleaseStateRoot "postgres-runtime.env"
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
$script:ReleaseDatabaseSource = $null
$script:ReleaseDockerEndpoint = $null

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
    if ($env:DR_SUPPORT_DEPLOYMENT_PROFILE) {
        $python = Get-ReleasePythonPath
        Push-Location $script:ReleaseRepoRoot
        try {
            $null = & $python -c "from dr_support.services.deployment_profile import validate_deployment_environment; validate_deployment_environment()" 2>$null
            if ($LASTEXITCODE -ne 0) {
                throw "QA deployment configuration is invalid. Check the selected QA_SERVER/QA_LOCAL profile and its private Model API endpoint before starting PostgreSQL. No endpoint was probed."
            }
        } finally {
            Pop-Location
        }
    }
}

function Get-ReleaseDockerPath {
    $command = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    return $null
}

function Test-ReleaseLocalPostgresPort([int] $Port) {
    try {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Where-Object { [string]$_.LocalAddress -in @("127.0.0.1", "0.0.0.0", "::", "::0") } |
            Select-Object -First 1
        return -not [bool]$listener
    } catch {
        return $false
    }
}

function Get-ReleaseLocalPostgresPort {
    $seed = [Convert]::ToInt32($script:ReleaseCheckoutIdentity.Substring(0, 4), 16)
    $start = 54329 + ($seed % 1000)
    for ($offset = 0; $offset -lt 1000; $offset++) {
        $port = $start + $offset
        if (Test-ReleaseLocalPostgresPort $port) { return [string]$port }
    }
    throw "No available loopback PostgreSQL port was found for this checkout. Stop the conflicting local service or configure an external PostgreSQL URL."
}

function Get-ReleaseModelCapabilityStatus([string] $Json) {
    $empty = [pscustomobject]@{ Valid = $false; Ready = $false; Capabilities = @() }
    if (-not $Json) { return $empty }
    $trimmed = $Json.Trim()
    if (-not $trimmed.StartsWith("[") -or -not $trimmed.EndsWith("]")) { return $empty }
    try {
        $parsed = ConvertFrom-Json -InputObject $trimmed
        $capabilities = @($parsed | ForEach-Object { $_ })
    } catch {
        return $empty
    }
    if ($capabilities.Count -eq 0) { return $empty }
    $seenModelIds = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    foreach ($capability in $capabilities) {
        if (-not $seenModelIds.Add([string]$capability.model_id)) { return $empty }
    }
    $invalid = @($capabilities | Where-Object {
        $properties = $_.PSObject.Properties.Name
        $modelId = if ($properties -contains "model_id") { [string]$_.model_id } else { "" }
        $task = if ($properties -contains "task") { [string]$_.task } else { "" }
        $modalities = $null
        if ($properties -contains "modalities") { $modalities = $_.PSObject.Properties["modalities"].Value }
        $validModalities = $modalities -is [array] -and @($modalities).Count -gt 0 -and @($modalities | Where-Object {
            $_ -is [string] -and $_.Trim()
        }).Count -eq @($modalities).Count
        $unavailable = (($properties -contains "ready") -and $_.ready -eq $false) -or
            (($properties -contains "status") -and $_.status -is [string] -and
             $_.status.Trim().ToUpperInvariant() -notin @("LOADED", "SYNTHETIC_FIXTURE"))
        $invalidModalities = -not $validModalities -and -not $unavailable
        $invalidModalityValues = @($modalities | Where-Object {
            $_ -isnot [string] -or -not $_.Trim()
        }).Count -gt 0
        $invalidStatus = ($properties -contains "status") -and $null -ne $_.status -and $_.status -isnot [string]
        $invalidReady = ($properties -contains "ready") -and $_.ready -isnot [bool]
        -not $modelId.Trim() -or -not $task.Trim() -or $invalidModalities -or $invalidModalityValues -or $invalidStatus -or $invalidReady
    })
    if ($invalid.Count -gt 0) { return $empty }
    $expectedTasks = @{
        "retfound-aptos5" = "global"
        "prism-dr-5fold" = "lesion-roi"
    }
    $ready = @($capabilities | Where-Object {
        $properties = $_.PSObject.Properties.Name
        $modelId = [string]$_.model_id
        $task = [string]$_.task
        $modalities = $_.PSObject.Properties["modalities"].Value
        $knownModel = $expectedTasks.ContainsKey($modelId)
        $taskMatches = $task -in @("global", "lesion-roi") -and (-not $knownModel -or $expectedTasks[$modelId] -eq $task)
        $knownCfpOnly = $knownModel -and "CFP" -in @($modalities)
        $capabilityId = if ($properties -contains "capability_id") { [string]$_.capability_id } else { "" }
        $revision = if ($properties -contains "revision") { [string]$_.revision } elseif ($properties -contains "model_version") { [string]$_.model_version } else { "" }
        $preprocessing = if ($properties -contains "preprocessing") { [string]$_.preprocessing } elseif ($properties -contains "preprocessing_version") { [string]$_.preprocessing_version } else { "" }
        $placeholders = @("UNKNOWN", "NOT_REPORTED", "NOT_AVAILABLE", "NONE", "NULL", "N/A")
        $genericQualified = $capabilityId.Trim() -and $revision.Trim() -and $preprocessing.Trim() -and
            $capabilityId.Trim().ToUpperInvariant() -notin $placeholders -and
            $revision.Trim().ToUpperInvariant() -notin $placeholders -and
            $preprocessing.Trim().ToUpperInvariant() -notin $placeholders
        $reportedReady = ($properties -notcontains "ready") -or $_.ready
        $release = if ($properties -contains "release_status") { ([string]$_.release_status).Trim().ToUpperInvariant() } else { "" }
        $knownRelease = $release -in @("AVAILABLE", "QUALIFIED", "RESEARCH_ONLY", "COMPARATOR_ONLY", "DISABLED", "DEFERRED") -or $release.StartsWith("BLOCKED") -or $release.StartsWith("DEFERRED")
        $genericReleaseValid = $knownModel -or $knownRelease
        $blocked = $release -in @("DISABLED", "COMPARATOR_ONLY", "DEFERRED") -or $release.StartsWith("BLOCKED") -or $release.StartsWith("DEFERRED")
        $status = if ($properties -contains "status") { ([string]$_.status).Trim().ToUpperInvariant() } else { "" }
        $actionableModality = @($modalities | Where-Object { $_ -in @("CFP", "UWF") }).Count -gt 0
        ($reportedReady -and $status -eq "LOADED" -and -not $blocked -and $taskMatches -and $actionableModality -and $knownCfpOnly) -or
            ($reportedReady -and $status -eq "LOADED" -and -not $blocked -and $taskMatches -and $actionableModality -and $genericReleaseValid -and -not $knownModel -and $genericQualified)
    })
    return [pscustomobject]@{ Valid = $true; Ready = $ready.Count -gt 0; Capabilities = @($ready) }
}

function Test-ReleaseModelHealth([object] $Body) {
    if (-not $Body) { return $false }
    $properties = $Body.PSObject.Properties.Name
    return (
        ($properties -contains "status") -and
        [string]$Body.status -in @("PASS", "PASS_WITH_WARNINGS") -and
        ($properties -contains "assets_verified") -and
        $Body.assets_verified -is [bool] -and
        [bool]$Body.assets_verified
    )
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
    if (-not (Invoke-ReleaseLocalDocker -Docker $Docker -Endpoint $script:ReleaseDockerEndpoint -Arguments $composeArguments)) {
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
    $script:ReleaseDatabaseSource = "local"
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
    $port = Get-ReleaseLocalPostgresPort
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
    $engine = Ensure-ReleaseDockerEngine -Docker $docker -ManagedLocal $true
    if (-not $engine.Ready) { throw $engine.Detail }
    $script:ReleaseDockerEndpoint = $engine.Endpoint
    $Database | Add-Member -NotePropertyName DockerEndpoint -NotePropertyValue $engine.Endpoint -Force
    try {
        Invoke-ReleaseCompose $docker @("up", "-d", $script:ReleaseComposeService)
    } catch {
        throw "Project-owned PostgreSQL could not start after local Docker readiness. Check the configured loopback port and the approved PostgreSQL image availability. No SQLite fallback is used."
    }
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $composeArguments = Get-ReleaseComposeArguments @(
            "exec", "-T", $script:ReleaseComposeService,
            "pg_isready", "-U", $Database.User, "-d", $Database.Database
        )
        if (Invoke-ReleaseLocalDocker -Docker $docker -Endpoint $script:ReleaseDockerEndpoint -Arguments $composeArguments -TimeoutSeconds 5) { return }
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
    $endpoint = if ($Database.PSObject.Properties.Name -contains "DockerEndpoint") {
        [string]$Database.DockerEndpoint
    } elseif ($Database.PSObject.Properties.Name -contains "docker_endpoint") {
        [string]$Database.docker_endpoint
    } else { "" }
    if ($endpoint -notin @("npipe:////./pipe/docker_engine", "npipe:////./pipe/dockerDesktopLinuxEngine")) {
        Write-Warning "Recorded PostgreSQL state has no verified local Docker endpoint; the database was left running."
        return
    }
    $script:ReleaseDockerEndpoint = $endpoint
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
    $mode = ([string]$env:DR_SUPPORT_CASE_STORE).Trim().ToLowerInvariant()
    if ($mode -eq "sqlite") {
        return [pscustomobject]@{
            Ready = $false
            Mode = "sqlite"
            Source = "legacy"
            ManagedLocal = $false
            Detail = "Explicit DR_SUPPORT_CASE_STORE=sqlite is legacy compatibility mode; normal managed PostgreSQL readiness is not available."
        }
    }
    $source = if ($script:ReleaseDatabaseSource -eq "local") { "local" } else { "external" }
    $dsn = ([string]$env:DR_SUPPORT_DATABASE_URL).Trim()
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

function Use-ReleaseRuntimeRole {
    # AC-16: when the owner-approved runtime role exists for the project-owned
    # database, apply reviewed migrations with the owner connection, then run the
    # app as the least-privilege role in verify mode. Without the file nothing changes.
    if (-not (Test-Path -LiteralPath $script:ReleaseRuntimeDatabaseEnvFile -PathType Leaf)) { return $false }
    if ($script:ReleaseDatabaseSource -ne "local") { return $false }
    $python = Get-ReleasePythonPath
    Push-Location $script:ReleaseRepoRoot
    try {
        $migrationLog = Join-Path $script:ReleaseLogRoot "migration.log"
        & $python -c "from dr_support.persistence import PostgresDatabase, PostgresSettings, SchemaMigrator; SchemaMigrator(PostgresDatabase(PostgresSettings.from_env())).migrate()" *> $migrationLog
        if ($LASTEXITCODE -ne 0) {
            throw "Reviewed database migrations could not be applied before starting the app. Review local-state/logs/migration.log; nothing was changed by the app."
        }
    } finally {
        Pop-Location
    }
    foreach ($line in Get-Content -LiteralPath $script:ReleaseRuntimeDatabaseEnvFile) {
        if ($line.Trim() -match "^(DR_SUPPORT_DATABASE_URL|DR_SUPPORT_DATABASE_MIGRATION_MODE)=(.+)$") {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim(), "Process")
        }
    }
    # The app must not inherit the owner credential; Compose reads its own env file.
    foreach ($name in @("DR_SUPPORT_POSTGRES_PASSWORD", "DR_SUPPORT_POSTGRES_USER")) {
        [Environment]::SetEnvironmentVariable($name, $null, "Process")
    }
    return $true
}

function Ensure-ReleasePostgres {
    Read-ReleaseDotEnv
    $mode = ([string]$env:DR_SUPPORT_CASE_STORE).Trim().ToLowerInvariant()
    if ($mode -eq "sqlite") {
        throw "DR_SUPPORT_CASE_STORE=sqlite is legacy compatibility mode and cannot be used by the normal Windows workstation launcher."
    }
    $externalDsn = ([string]$env:DR_SUPPORT_DATABASE_URL).Trim()
    if ($externalDsn) {
        $script:ReleaseDatabaseSource = "external"
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
    $script:ReleaseDatabaseSource = "local"
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
    $python = Join-Path $script:ReleaseRepoRoot ".venv\Scripts\python.exe"
    $verifier = Join-Path $script:ReleaseRepoRoot "scripts\release\build_release.py"
    if ((Test-Path -LiteralPath (Join-Path $script:ReleaseRepoRoot ".git")) -and
        (Test-Path -LiteralPath $python -PathType Leaf) -and
        (Test-Path -LiteralPath $verifier -PathType Leaf)) {
        $probe = "import sys; sys.path.insert(0, sys.argv[1]); from scripts.release.build_release import verify_frontend_build; verify_frontend_build(sys.argv[2])"
        $null = & $python -c $probe $script:ReleaseRepoRoot ([string]$identity.source_commit) 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "The frontend source or output differs from its build identity. Rebuild frontend/dist in this developer checkout."
        }
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

function Test-ReleaseSelectedWorkspace([string] $Json) {
    try {
        $body = ConvertFrom-Json -InputObject $Json
        if (-not $body -or $body.PSObject.Properties.Name -notcontains "workspace") { return $false }
        $workspace = $body.workspace
        return [bool]($workspace -and $workspace.PSObject.Properties.Name -contains "id" -and ([string]$workspace.id).Trim())
    } catch { return $false }
}

function Test-ReleaseCompatibleCapability([object] $Capability, [string] $Modality, [string] $Task) {
    if ($Capability.task -ne $Task -or $Modality -notin @($Capability.modalities)) { return $false }
    # Match the clinician UI fixed model identities and PRISM experimental UWF boundary.
    $modelId = [string]$Capability.model_id
    if ($modelId -in @("retfound-aptos5", "uspec-uwf-grading")) {
        $fixed = if ($modelId -eq "retfound-aptos5") { "CFP" } else { "UWF" }
        if ($Task -ne "global" -or @($Capability.modalities | Where-Object { $_ -ne $fixed }).Count -gt 0) { return $false }
    }
    if ($modelId -eq "prism-dr-5fold") {
        $properties = $Capability.PSObject.Properties.Name
        if ($Task -ne "lesion-roi" -or $properties -notcontains "release_status" -or
            $Capability.release_status -notin @("AVAILABLE", "QUALIFIED", "RESEARCH_ONLY")) { return $false }
        if ($Modality -eq "UWF") {
            if ($properties -notcontains "uwf_use" -or $properties -notcontains "clinical_validation_status" -or
                $properties -notcontains "trained_domain") { return $false }
            if ($Capability.uwf_use -ne "EXPERIMENTAL" -or
                $Capability.clinical_validation_status -notin @("NOT_VALIDATED_FOR_UWF", "NOT_ESTABLISHED") -or
                $Capability.trained_domain -ne "CFP") { return $false }
        }
    }
    return $true
}

function Get-ReleaseShowcaseReadiness {
    # Read-only local APIs use the configured server-side connection. Never start cloud compute.
    $result = [pscustomobject]@{ Ready = $false; WorkspaceReady = $false; QueueReady = $false; ModelsReady = $false; ImageCount = 0; Detail = "Open Settings and select the intended workspace; manual review remains available." }
    try {
        $active = Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/workspaces/active" -UseBasicParsing -TimeoutSec 5
        $result.WorkspaceReady = $active.StatusCode -eq 200 -and (Test-ReleaseSelectedWorkspace $active.Content)
        if (-not $result.WorkspaceReady) { return $result }
        $result.Detail = "Open Worklist and scan the intended image folders; no review decisions were changed."
        $queue = Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/cases" -UseBasicParsing -TimeoutSec 8
        if ($queue.StatusCode -ne 200 -or -not $queue.Content.Trim().StartsWith("[")) { return $result }
        $cases = @(ConvertFrom-Json -InputObject $queue.Content | ForEach-Object { $_ })
        $result.ImageCount = $cases.Count
        $result.QueueReady = $cases.Count -gt 0
        if (-not $result.QueueReady) { return $result }
        $result.Detail = "AI is not ready. Check Settings > Model connection and the existing Lightning service. Manual review remains available; cloud compute was not started."
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/v1/models" -UseBasicParsing -TimeoutSec 12
        if ($response.StatusCode -ne 200) { return $result }
        $models = Get-ReleaseModelCapabilityStatus $response.Content
        if (-not $models.Valid -or -not $models.Ready) { return $result }
        foreach ($case in $cases) {
            $properties = $case.PSObject.Properties.Name
            if ($properties -notcontains "modality" -or $properties -notcontains "source_origin") { return $result }
            $modality = [string]$case.modality
            $origin = [string]$case.source_origin
            if ($modality -notin @("CFP", "UWF") -or $origin -notin @("PUBLIC", "SYNTHETIC", "HOSPITAL_AUTHORIZED")) {
                $result.Detail = "Some image context needs review. Use Worklist > Confirm Image; no image approval was performed by startup."
                return $result
            }
            foreach ($task in @("global", "lesion-roi")) {
                $compatible = @($models.Capabilities | Where-Object {
                    Test-ReleaseCompatibleCapability $_ $modality $task
                })
                if ($compatible.Count -eq 0) { return $result }
            }
        }
        $result.ModelsReady = $true
        $result.Ready = $true
        $result.Detail = "Selected workspace, $($result.ImageCount) images and compatible grading/lesion capabilities verified. Technical readiness only; image admission and upload authorization remain separate backend gates."
    } catch {
        # Do not print exception bodies, configured credentials, or connection URLs.
        $result.Detail = "Readiness could not be verified. Check Settings, the local queue and the existing Lightning service; manual review remains available. Cloud compute was not started."
    }
    return $result
}

function Write-ReleaseShowcaseReadiness {
    $readiness = Get-ReleaseShowcaseReadiness
    if ($readiness.Ready) {
        Write-Host "[SHOWCASE_READY] $($readiness.Detail)"
    } else {
        Write-Host "[SERVER_RUNNING / MANUAL_MODE] $($readiness.Detail)"
    }
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
            $managedLocal = if ($Database.PSObject.Properties.Name -contains "ManagedLocal") {
                [bool]$Database.ManagedLocal
            } else {
                $false
            }
            if ($managedLocal) {
                [pscustomobject]@{
                    managed_local = $true
                    project = [string]$Database.Project
                    service = [string]$Database.Service
                    compose_file = [string]$Database.ComposeFile
                    docker_endpoint = [string]$Database.DockerEndpoint
                }
            } else {
                [pscustomobject]@{ managed_local = $false }
            }
        } else { $null }
    } | ConvertTo-Json | Set-Content -LiteralPath $script:ReleaseRunFile
}

function Remove-ReleaseRecord {
    if (Test-Path -LiteralPath $script:ReleaseRunFile) { Remove-Item -LiteralPath $script:ReleaseRunFile -Force }
}
