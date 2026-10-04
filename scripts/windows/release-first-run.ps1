Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "release-common.ps1")

function Install-ReleaseUv {
    $uv = Get-ReleaseUvPath
    if ($uv) { return $uv }
    Ensure-ReleaseDirectories
    $installer = Join-Path $script:ReleaseRepoRoot "local-state\release\uv-install.ps1"
    try {
        Write-Host "uv is not installed; downloading the official per-user installer..."
        Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -OutFile $installer -UseBasicParsing
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer
    } finally {
        if (Test-Path -LiteralPath $installer) { Remove-Item -LiteralPath $installer -Force }
    }
    $uv = Get-ReleaseUvPath
    if (-not $uv) { throw "uv installation completed but uv.exe was not found in the supported user tool paths." }
    return $uv
}

function Invoke-ReleaseUv([string] $Uv, [object[]] $Arguments) {
    & $Uv @Arguments
    if ($LASTEXITCODE -ne 0) { throw "uv $($Arguments -join ' ') failed with exit code $LASTEXITCODE." }
}

try {
    Test-ReleaseFrontend
    Ensure-ReleaseDirectories
    $uv = Install-ReleaseUv
    Write-Host "Provisioning project-managed Python 3.12..."
    Invoke-ReleaseUv $uv @("python", "install", "3.12")
    $venv = Join-Path $script:ReleaseRepoRoot ".venv"
    $python = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        Invoke-ReleaseUv $uv @("venv", "--python", "3.12", $venv)
    }
    Write-Host "Installing locked workstation dependencies (the prebuilt frontend is reused)..."
    Invoke-ReleaseUv $uv @("sync", "--frozen", "--python", "3.12", "--no-dev")
    $python = Get-ReleasePythonPath
    & $python -c "import fastapi, dr_support; print('Python imports: PASS')"
    if ($LASTEXITCODE -ne 0) { throw "The project-managed Python environment failed the import check." }
    [pscustomobject]@{
        completed_at = (Get-Date).ToUniversalTime().ToString("o")
        python = (& $python --version 2>&1).Trim()
        frontend = "prebuilt"
        npm_required = $false
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $script:ReleaseStateRoot "first-run.json")
    Write-Host "FIRST RUN completed. Use START_DR_SCREENING.bat each day; no developer commands are required."
    exit 0
} catch {
    Write-Error $_
    Write-Host "First run did not complete. Use CHECK_SYSTEM.bat and see README_START_HERE.md for recovery."
    exit 1
}
