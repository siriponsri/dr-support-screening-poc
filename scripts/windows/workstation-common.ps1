Set-StrictMode -Version Latest

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:StateRoot = Join-Path $script:RepoRoot "local-state"
$script:LogRoot = Join-Path $script:StateRoot "logs"
$script:RunRoot = Join-Path $script:StateRoot "run"
$script:SetupRoot = Join-Path $script:StateRoot "setup"
$script:PidFile = Join-Path $script:RunRoot "workstation.json"
$script:FrontendSignatureFile = Join-Path $script:SetupRoot "frontend-source.sha256"
$script:FrontendDependenciesFile = Join-Path $script:SetupRoot "frontend-dependencies.sha256"
$script:PortableNodeVersion = "20.18.1"

function Ensure-LauncherDirectories {
    foreach ($path in @($script:LogRoot, $script:RunRoot, $script:SetupRoot, (Join-Path $script:StateRoot "tools"))) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
    }
}

function Read-DotEnv {
    $envPath = Join-Path $script:RepoRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
        return
    }
    foreach ($line in Get-Content -LiteralPath $envPath) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }
        if ($trimmed -notmatch "^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$") {
            continue
        }
        $name = $Matches[1]
        $value = $Matches[2].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Set-SafeWorkstationEnvironment {
    Read-DotEnv
    $env:APP_PROFILE = "review"
    $env:MODEL_RUNTIME = "remote"
    $env:HOST = "127.0.0.1"
    $env:PORT = "8000"
    $env:WORKERS = "1"
}

function Get-UvPath {
    $command = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $candidates = @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "uv\uv.exe"),
        (Join-Path $script:StateRoot "tools\uv.exe")
    )
    return $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}

function Get-PythonPath {
    $python = Join-Path $script:RepoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Project Python is missing. Run SETUP.cmd first."
    }
    return $python
}

function Get-SystemNodeTools {
    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npmCommand) {
        $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
    }
    if (-not $nodeCommand -or -not $npmCommand) {
        return $null
    }
    try {
        $version = (& $nodeCommand.Source --version 2>$null).Trim()
        $major = [int]($version -replace '^v([0-9]+).*$', '$1')
    } catch {
        return $null
    }
    if ($major -lt 18) {
        return $null
    }
    return [pscustomobject]@{ Node = $nodeCommand.Source; Npm = $npmCommand.Source; Version = $version; Source = "system" }
}

function Get-PortableNodeTools {
    $folder = Join-Path $script:StateRoot ("tools\node-v{0}-win-x64" -f $script:PortableNodeVersion)
    $node = Join-Path $folder "node.exe"
    $npm = Join-Path $folder "npm.cmd"
    if ((Test-Path -LiteralPath $node -PathType Leaf) -and (Test-Path -LiteralPath $npm -PathType Leaf)) {
        return [pscustomobject]@{ Node = $node; Npm = $npm; Version = "v$($script:PortableNodeVersion)"; Source = "portable" }
    }
    return $null
}

function Get-NodeTools {
    $system = Get-SystemNodeTools
    if ($system) {
        return $system
    }
    return Get-PortableNodeTools
}

function Install-PortableNode {
    $existing = Get-PortableNodeTools
    if ($existing) {
        return $existing
    }
    Ensure-LauncherDirectories
    $toolsRoot = Join-Path $script:StateRoot "tools"
    $archive = Join-Path $toolsRoot ("node-v{0}-win-x64.zip" -f $script:PortableNodeVersion)
    $url = "https://nodejs.org/dist/v$($script:PortableNodeVersion)/node-v$($script:PortableNodeVersion)-win-x64.zip"
    Write-Host "System Node.js 18+ was not found; downloading official Node.js $($script:PortableNodeVersion) to local-state/tools..."
    Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing
    $expectedFolder = Join-Path $toolsRoot ("node-v{0}-win-x64" -f $script:PortableNodeVersion)
    if (Test-Path -LiteralPath $expectedFolder) {
        [System.IO.Directory]::Delete($expectedFolder, $true)
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $toolsRoot -Force
    Remove-Item -LiteralPath $archive -Force
    $installed = Get-PortableNodeTools
    if (-not $installed) {
        throw "The official Node.js archive did not contain the expected npm.cmd."
    }
    return $installed
}

function Get-FrontendFiles {
    $frontend = Join-Path $script:RepoRoot "frontend"
    $fixed = @("package.json", "package-lock.json", "vite.config.ts", "tsconfig.json")
    $files = foreach ($name in $fixed) {
        $path = Join-Path $frontend $name
        if (Test-Path -LiteralPath $path -PathType Leaf) { Get-Item -LiteralPath $path }
    }
    $src = Join-Path $frontend "src"
    if (Test-Path -LiteralPath $src -PathType Container) {
        $files += Get-ChildItem -LiteralPath $src -Recurse -File | Sort-Object FullName
    }
    return $files
}

function Get-FileSignature([System.IO.FileInfo[]] $files) {
    $lines = foreach ($file in $files) {
        $relative = $file.FullName.Substring($script:RepoRoot.Length + 1).Replace('\', '/')
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$relative|$hash"
    }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes(($lines -join "`n"))
    $digest = [System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
    return ([System.BitConverter]::ToString($digest) -replace '-', '').ToLowerInvariant()
}

function Get-FrontendSourceSignature {
    return Get-FileSignature (Get-FrontendFiles)
}

function Get-FrontendDependencySignature {
    $lock = Join-Path $script:RepoRoot "frontend\package-lock.json"
    if (-not (Test-Path -LiteralPath $lock -PathType Leaf)) { return "missing" }
    return (Get-FileHash -LiteralPath $lock -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Invoke-Npm([object[]] $Arguments, [string] $WorkingDirectory) {
    $tools = Get-NodeTools
    if (-not $tools) {
        throw "Node.js 18+ and npm are required. Run SETUP.cmd to install the no-admin portable fallback."
    }
    Push-Location $WorkingDirectory
    try {
        & $tools.Npm @Arguments
        if ($LASTEXITCODE -ne 0) { throw "npm $($Arguments -join ' ') failed with exit code $LASTEXITCODE." }
    } finally {
        Pop-Location
    }
}

function Ensure-FrontendBuild([switch] $AllowInstall) {
    $frontend = Join-Path $script:RepoRoot "frontend"
    $distIndex = Join-Path $frontend "dist\index.html"
    $sourceSignature = Get-FrontendSourceSignature
    $savedSource = if (Test-Path -LiteralPath $script:FrontendSignatureFile) { (Get-Content -LiteralPath $script:FrontendSignatureFile -Raw).Trim() } else { "" }
    $dependencySignature = Get-FrontendDependencySignature
    $savedDependency = if (Test-Path -LiteralPath $script:FrontendDependenciesFile) { (Get-Content -LiteralPath $script:FrontendDependenciesFile -Raw).Trim() } else { "" }
    $nodeModules = Join-Path $frontend "node_modules"
    if (-not (Test-Path -LiteralPath $nodeModules -PathType Container)) {
        if (-not $AllowInstall) { throw "Frontend dependencies are missing. Run SETUP.cmd." }
        Invoke-Npm @("ci") $frontend
    } elseif ($savedDependency -ne $dependencySignature) {
        if (-not $AllowInstall) { throw "Frontend dependency state is stale. Run SETUP.cmd." }
        Write-Host "Frontend lockfile changed; installing dependencies once with npm ci..."
        Invoke-Npm @("ci") $frontend
    }
    $needsBuild = -not (Test-Path -LiteralPath $distIndex -PathType Leaf) -or ($savedSource -ne $sourceSignature)
    if ($needsBuild) {
        Write-Host "Building the clinician workstation UI..."
        Invoke-Npm @("run", "build") $frontend
        Set-Content -LiteralPath $script:FrontendSignatureFile -Value $sourceSignature -NoNewline
    }
    Set-Content -LiteralPath $script:FrontendDependenciesFile -Value $dependencySignature -NoNewline
    return $needsBuild
}

function Get-ManagedRecord {
    if (-not (Test-Path -LiteralPath $script:PidFile -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $script:PidFile -Raw | ConvertFrom-Json } catch { return $null }
}

function Get-ProcessDetails([int] $ProcessId) {
    return Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}

function Test-ManagedProcess([int] $ProcessId) {
    $details = Get-ProcessDetails $ProcessId
    if (-not $details) { return $false }
    $command = [string]$details.CommandLine
    $python = (Join-Path $script:RepoRoot ".venv\Scripts\python.exe").ToLowerInvariant()
    return $command.ToLowerInvariant().Contains("dr_support.run") -and $command.ToLowerInvariant().Contains($python)
}

function Get-ListeningProcess([int] $Port) {
    $connection = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $connection) { return $null }
    $details = Get-ProcessDetails ([int]$connection.OwningProcess)
    return [pscustomobject]@{ Pid = [int]$connection.OwningProcess; Details = $details }
}

function Test-AppHealth {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch { return $false }
}

function Write-ManagedRecord([int] $ProcessId) {
    Ensure-LauncherDirectories
    [pscustomobject]@{
        pid = $ProcessId
        repo = $script:RepoRoot
        url = "http://127.0.0.1:8000/app/"
        started_at = (Get-Date).ToUniversalTime().ToString("o")
        stdout_log = (Join-Path $script:LogRoot "workstation.stdout.log")
        stderr_log = (Join-Path $script:LogRoot "workstation.stderr.log")
    } | ConvertTo-Json | Set-Content -LiteralPath $script:PidFile
}

function Remove-ManagedRecord {
    if (Test-Path -LiteralPath $script:PidFile) { Remove-Item -LiteralPath $script:PidFile -Force }
}
