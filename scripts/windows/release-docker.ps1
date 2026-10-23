# Called only by the managed-local PostgreSQL startup path. Dot-sourcing is inert.
# This helper never installs, elevates, changes Docker context or stops Docker.
Set-StrictMode -Version Latest

function Invoke-ReleaseDockerProbe {
    param(
        [string]$Docker,
        [ValidateSet("Context", "Engine")][string]$Operation,
        [string]$Endpoint = "",
        [int]$TimeoutMilliseconds = 2000
    )
    $process = $null
    $startedChild = $false
    $probeWatch = [Diagnostics.Stopwatch]::StartNew()
    try {
        $arguments = 'context inspect --format "{{.Endpoints.docker.Host}}"'
        if ($Operation -eq "Engine") {
            if ($Endpoint -notin @("npipe:////./pipe/docker_engine", "npipe:////./pipe/dockerDesktopLinuxEngine")) {
                return [pscustomobject]@{ Succeeded=$false; Output=""; TimedOut=$false }
            }
            $arguments = '--host "' + $Endpoint + '" info --format "{{.OSType}}"'
        }
        $start = New-Object System.Diagnostics.ProcessStartInfo
        $start.FileName = $Docker
        $start.Arguments = $arguments
        $start.UseShellExecute = $false
        $start.CreateNoWindow = $true
        $start.RedirectStandardOutput = $true
        $start.RedirectStandardError = $true
        $start.RedirectStandardInput = $true
        # A probe must not inherit a remote endpoint override. This affects only
        # this short-lived CLI child, never persistent Docker/user configuration.
        foreach ($name in @("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")) {
            if ($Operation -eq "Engine") { $start.EnvironmentVariables.Remove($name) }
        }
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $start
        if (-not $process.Start()) {
            return [pscustomobject]@{ Succeeded=$false; Output=""; TimedOut=$false }
        }
        $startedChild = $true
        $process.StandardInput.Close()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $remaining = [Math]::Max(1, $TimeoutMilliseconds - $probeWatch.ElapsedMilliseconds)
        if (-not $process.WaitForExit([int]$remaining)) {
            # Terminate only this owned readiness CLI child; never the daemon.
            try { $process.Kill() } catch { }
            return [pscustomobject]@{ Succeeded=$false; Output=""; TimedOut=$true }
        }
        $output = ""
        $remaining = [Math]::Max(0, $TimeoutMilliseconds - $probeWatch.ElapsedMilliseconds)
        if ($stdout.Wait([int]$remaining) -and -not $stdout.IsFaulted) { $output = $stdout.Result.Trim() }
        # stderr is drained asynchronously but is never emitted or waited on
        # beyond the probe deadline because it can contain private diagnostics.
        return [pscustomobject]@{ Succeeded=($process.ExitCode -eq 0); Output=$output; TimedOut=$false }
    } catch {
        return [pscustomobject]@{ Succeeded=$false; Output=""; TimedOut=$false }
    } finally {
        if ($null -ne $process) {
            if ($startedChild) {
                try { if (-not $process.HasExited) { $process.Kill() } } catch { }
            }
            $process.Dispose()
        }
    }
}

function Get-ReleaseDockerDesktopPath {
    $desktopProgramFiles = [Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles)
    if (-not $desktopProgramFiles) { return $null }
    return Join-Path $desktopProgramFiles "Docker\Docker\Docker Desktop.exe"
}

function Test-ReleaseDockerDesktopRunning {
    return [bool](Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Get-ReleaseDockerElapsedMilliseconds([object]$Watch) {
    return [long]$Watch.ElapsedMilliseconds
}

function New-ReleaseDockerStatus([bool]$Ready, [string]$Status, [bool]$Started, [string]$Detail, [string]$Endpoint = "") {
    return [pscustomobject]@{ Ready=$Ready; Required=$true; Status=$Status; Started=$Started; Detail=$Detail; Endpoint=$Endpoint }
}

function ConvertTo-ReleaseDockerArgument([string]$Value) {
    # Windows native argv quoting, including quotes and trailing backslashes.
    $quoted = New-Object Text.StringBuilder
    $null = $quoted.Append('"')
    $slashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') { $slashes++; continue }
        if ($character -eq '"') {
            $null = $quoted.Append(('\' * (2 * $slashes + 1))).Append('"')
        } else {
            $null = $quoted.Append(('\' * $slashes)).Append($character)
        }
        $slashes = 0
    }
    return $quoted.Append(('\' * (2 * $slashes))).Append('"').ToString()
}

function Invoke-ReleaseLocalDocker {
    param([string]$Docker, [string]$Endpoint, [string[]]$Arguments,
        [ValidateRange(1, 180)][int]$TimeoutSeconds = 90)
    if ($Endpoint -notin @("npipe:////./pipe/docker_engine", "npipe:////./pipe/dockerDesktopLinuxEngine")) {
        throw "A verified local Docker endpoint is required; no Docker operation was sent."
    }
    $process = $null
    try {
        $start = New-Object Diagnostics.ProcessStartInfo
        $start.FileName = $Docker
        $start.Arguments = ((@('--host', $Endpoint) + $Arguments | ForEach-Object { ConvertTo-ReleaseDockerArgument $_ }) -join ' ')
        $start.UseShellExecute = $false
        $start.CreateNoWindow = $true
        $start.RedirectStandardInput = $true
        $start.RedirectStandardOutput = $true
        $start.RedirectStandardError = $true
        foreach ($name in @('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH')) {
            $start.EnvironmentVariables.Remove($name)
        }
        $process = New-Object Diagnostics.Process
        $process.StartInfo = $start
        if (-not $process.Start()) { return $false }
        $process.StandardInput.Close()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) { return $false }
        return $process.ExitCode -eq 0
    } catch {
        return $false
    } finally {
        if ($null -ne $process) {
            try { if (-not $process.HasExited) { $process.Kill() } } catch { }
            $process.Dispose()
        }
    }
}

function Ensure-ReleaseDockerEngine {
    param(
        [string]$Docker,
        [bool]$ManagedLocal = $true,
        [ValidateRange(1, 180)][int]$TimeoutSeconds = 90,
        [ValidateRange(50, 5000)][int]$PollMilliseconds = 1000
    )
    if (-not $ManagedLocal) {
        return [pscustomobject]@{ Ready=$true; Required=$false; Status="NOT_REQUIRED"; Started=$false;
            Detail="External PostgreSQL is selected; Docker was not inspected or started." }
    }
    if (-not $Docker) {
        return New-ReleaseDockerStatus $false "CLIENT_MISSING" $false "Docker CLI is missing. Ask IT to provision the approved Docker Desktop installation or configure an approved external PostgreSQL server."
    }
    $allowed = @("npipe:////./pipe/docker_engine", "npipe:////./pipe/dockerDesktopLinuxEngine")
    if ($env:DOCKER_HOST -and $env:DOCKER_HOST -notin $allowed) {
        return New-ReleaseDockerStatus $false "LOCAL_ENDPOINT_REQUIRED" $false "Docker is configured for an unapproved endpoint. Ask IT to select the approved local Docker Desktop engine; no endpoint configuration was changed."
    }
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $budget = [long]$TimeoutSeconds * 1000
    $remaining = $budget - (Get-ReleaseDockerElapsedMilliseconds $watch)
    if ($remaining -le 0) {
        return New-ReleaseDockerStatus $false "STARTUP_TIMEOUT" $false "Docker readiness deadline expired before probing. Retry after checking the local installation with IT."
    }
    $context = Invoke-ReleaseDockerProbe -Docker $Docker -Operation Context -TimeoutMilliseconds ([Math]::Min(2000, $remaining))
    if (-not $context.Succeeded -or $context.Output -notin $allowed) {
        return New-ReleaseDockerStatus $false "LOCAL_ENDPOINT_REQUIRED" $false "The approved local Docker Desktop endpoint could not be verified. Check the installed CLI and local context with IT; no remote engine was contacted."
    }
    $endpoint = $context.Output
    $started = $false
    $desktopChecked = $false
    while (($remaining = $budget - (Get-ReleaseDockerElapsedMilliseconds $watch)) -gt 0) {
        $probe = Invoke-ReleaseDockerProbe -Docker $Docker -Operation Engine -Endpoint $endpoint -TimeoutMilliseconds ([Math]::Min(2000, $remaining))
        if ($probe.Succeeded -and $probe.Output -eq "linux") {
            return New-ReleaseDockerStatus $true "READY" $started "The approved local Linux Docker engine is ready for project-owned PostgreSQL." $endpoint
        }
        if ($probe.Succeeded -and $probe.Output -eq "windows") {
            return New-ReleaseDockerStatus $false "LINUX_ENGINE_REQUIRED" $started "The local Docker engine is in Windows-container mode. Ask IT to select the approved Linux-container mode; no engine mode was changed."
        }
        if (($budget - (Get-ReleaseDockerElapsedMilliseconds $watch)) -le 0) { break }
        if (-not $desktopChecked) {
            $desktopChecked = $true
            if (-not (Test-ReleaseDockerDesktopRunning)) {
                $desktop = Get-ReleaseDockerDesktopPath
                if (-not $desktop -or -not (Test-Path -LiteralPath $desktop -PathType Leaf)) {
                    return New-ReleaseDockerStatus $false "DESKTOP_NOT_INSTALLED" $false "Docker Desktop was not found at its approved Program Files location. Ask IT to install/configure it; no installation was attempted."
                }
                try {
                    $null = Start-Process -FilePath $desktop -WindowStyle Hidden -PassThru -ErrorAction Stop
                    $started = $true
                } catch {
                    return New-ReleaseDockerStatus $false "DESKTOP_START_DENIED" $false "Docker Desktop could not be started under the current account. Ask IT to resolve access or first-run setup; no elevation or access change was attempted."
                }
            }
        }
        $remaining = $budget - (Get-ReleaseDockerElapsedMilliseconds $watch)
        if ($remaining -gt 0) { Start-Sleep -Milliseconds ([Math]::Min($PollMilliseconds, $remaining)) }
    }
    return New-ReleaseDockerStatus $false "STARTUP_TIMEOUT" $started "The local Docker engine did not become ready within the startup deadline. Check Docker Desktop first-run setup, Linux engine/virtualization and account access with IT. Existing services and volumes were not stopped or removed."
}
