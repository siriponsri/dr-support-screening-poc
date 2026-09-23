param(
    [switch]$Dev,
    [switch]$Check
)

. (Join-Path $PSScriptRoot "workstation-common.ps1")

function Invoke-Uv([object[]] $Arguments) {
    $uv = Get-UvPath
    if (-not $uv) { throw "uv is not installed. SETUP.cmd can bootstrap it from the official uv installer." }
    & $uv @Arguments
    if ($LASTEXITCODE -ne 0) { throw "uv $($Arguments -join ' ') failed with exit code $LASTEXITCODE." }
}

function Install-UvIfMissing {
    $uv = Get-UvPath
    if ($uv) { return $uv }
    Write-Host "uv was not found; bootstrapping the official per-user uv installer..."
    $installer = Join-Path $script:StateRoot "tools\uv-install.ps1"
    Ensure-LauncherDirectories
    Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -OutFile $installer -UseBasicParsing
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer
    Remove-Item -LiteralPath $installer -Force
    $uv = Get-UvPath
    if (-not $uv) { throw "uv installation completed but uv.exe was not found in the user tool paths." }
    return $uv
}

function Ensure-ProjectVenv {
    $venv = Join-Path $script:RepoRoot ".venv"
    $python = Join-Path $venv "Scripts\python.exe"
    if (Test-Path -LiteralPath $python -PathType Leaf) {
        $version = (& $python --version 2>$null | Out-String).Trim()
        if ($version -match '^Python 3\.12\.') {
            Write-Host "Reusing project-managed $version environment."
            return
        }
        Write-Host "Existing project environment is not Python 3.12; recreating it..."
        Invoke-Uv @("venv", "--python", "3.12", "--clear", $venv)
        return
    }
    Write-Host "Creating project-managed Python 3.12 environment..."
    Invoke-Uv @("venv", "--python", "3.12", $venv)
}

function Invoke-Check {
    Ensure-LauncherDirectories
    $uv = Get-UvPath
    $python = Join-Path $script:RepoRoot ".venv\Scripts\python.exe"
    $frontendDist = Join-Path $script:RepoRoot "frontend\dist\index.html"
    $node = Get-NodeTools
    Write-Host "Repository: $script:RepoRoot"
    Write-Host ("uv: " + ($(if ($uv) { $uv } else { "MISSING (SETUP will bootstrap)" })))
    Write-Host ("Project Python: " + ($(if (Test-Path -LiteralPath $python) { $python } else { "MISSING" })))
    Write-Host ("Node/npm: " + ($(if ($node) { "$($node.Version) ($($node.Source))" } else { "MISSING (SETUP will use official portable fallback)" })))
    Write-Host ("Frontend dependencies: " + ($(if (Test-Path -LiteralPath (Join-Path $script:RepoRoot "frontend\node_modules")) { "present" } else { "MISSING" })))
    Write-Host ("Frontend build: " + ($(if (Test-Path -LiteralPath $frontendDist) { "present" } else { "MISSING" })))
    if (-not $uv -or -not (Test-Path -LiteralPath $python) -or -not $node -or
        -not (Test-Path -LiteralPath (Join-Path $script:RepoRoot "frontend\node_modules")) -or
        -not (Test-Path -LiteralPath $frontendDist)) {
        exit 1
    }
    try {
        & $python -c "import fastapi, dr_support; print('Python imports: PASS')"
        if ($LASTEXITCODE -ne 0) { exit 1 }
    } catch { exit 1 }
}

try {
    if ($Check) {
        Invoke-Check
        exit 0
    }
    $uv = Install-UvIfMissing
    Write-Host "Provisioning project-managed Python 3.12 with uv..."
    Invoke-Uv @("python", "install", "3.12")
    Ensure-ProjectVenv
    if ($Dev) {
        Invoke-Uv @("sync", "--python", "3.12", "--extra", "test", "--extra", "dicom", "--extra", "browser-test")
    } else {
        Invoke-Uv @("sync", "--python", "3.12")
    }
    $python = Get-PythonPath
    & $python -c "import fastapi, dr_support; print('Python imports: PASS')"
    if ($LASTEXITCODE -ne 0) { throw "The project-managed Python environment failed the import check." }

    $node = Get-NodeTools
    if (-not $node) { $node = Install-PortableNode }
    Write-Host "Using Node.js $($node.Version) ($($node.Source))."

    $rootPackage = $script:RepoRoot
    if (-not (Test-Path -LiteralPath (Join-Path $rootPackage "node_modules") -PathType Container)) {
        Invoke-Npm @("ci") $rootPackage
    }
    Ensure-FrontendBuild -AllowInstall | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $script:RepoRoot "frontend\dist\index.html"))) {
        throw "Frontend build did not produce frontend/dist/index.html."
    }
    Ensure-LauncherDirectories
    [pscustomobject]@{
        completed_at = (Get-Date).ToUniversalTime().ToString("o")
        python = (& $python --version 2>&1).Trim()
        node = $node.Version
        frontend_source_sha256 = (Get-Content -LiteralPath $script:FrontendSignatureFile -Raw).Trim()
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:SetupRoot "workstation.json")
    Write-Host "SETUP completed. Daily use is START.cmd; it does not reinstall dependencies."
    exit 0
} catch {
    Write-Error $_
    Write-Host "Setup did not complete. See docs/operations/INSTALLATION.md for recovery steps."
    exit 1
}
