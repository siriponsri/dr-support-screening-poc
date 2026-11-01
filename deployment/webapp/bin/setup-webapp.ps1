# First-time setup of the web app package on Windows with Docker Desktop. Run by setup-webapp.bat.
# Asks three plain questions, writes the private settings file with random passwords, starts the app,
# creates the first administrator, puts "DR Screening Web App" on the desktop and opens the browser.
# Safe to run again: an existing settings file and existing accounts are kept.
param(
    [string]$EnvFile = (Join-Path $env:LOCALAPPDATA 'DRScreening\webapp.env'),
    [string]$DataDir = (Join-Path $env:LOCALAPPDATA 'DRScreening\webapp-data'),
    [string]$ImagesDir = '',
    [string]$ModelUrl = '',
    [switch]$NoAi,
    [switch]$SkipAdmin,
    [switch]$NoShortcut,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$Package = Split-Path -Parent $PSScriptRoot
$Repo = Split-Path -Parent (Split-Path -Parent $Package)
$Compose = Join-Path $Package 'compose.yml'

function Say([string]$Text) { Write-Host $Text }
function Stop-Setup([string]$Text) { Write-Host ''; Write-Host "Stopped: $Text" -ForegroundColor Yellow; exit 1 }
function Slash([string]$Path) { return ($Path -replace '\\', '/') }
function New-Secret {
    $alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
    $bytes = New-Object byte[] 40
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}
function Invoke-Compose {
    & docker compose --env-file $EnvFile -f $Compose @args
    if ($LASTEXITCODE -ne 0) { Stop-Setup "docker compose $($args -join ' ') did not finish. See the lines above." }
}

Say 'DR Screening web app: first-time setup'
Say ''

# 1. Docker Desktop
& docker info *> $null
if ($LASTEXITCODE -ne 0) { Stop-Setup 'Docker Desktop is not running. Open Docker Desktop, wait until it says Running, then run setup again.' }
Say '1/5 Docker Desktop is running'

# 2. Settings file (private, outside Git)
if (Test-Path $EnvFile) {
    Say "2/5 Using your existing settings: $EnvFile"
} else {
    $commit = ''
    try { $commit = (& git -C $Repo rev-parse HEAD 2>$null) } catch { $commit = '' }
    if ($commit -notmatch '^[0-9a-f]{40}$') { Stop-Setup 'Run setup from the project folder downloaded with Git (git clone), so the build can be labelled.' }
    if (-not $ImagesDir) {
        $default = Join-Path $env:USERPROFILE 'DRScreening\images'
        Say ''
        Say 'Question 1 of 2: which folder holds the retinal images to review?'
        Say "  Press Enter for $default"
        $ImagesDir = Read-Host '  Folder'
        if (-not $ImagesDir) { $ImagesDir = $default }
    }
    New-Item -ItemType Directory -Force -Path $ImagesDir | Out-Null
    if (-not $ModelUrl -and -not $NoAi) {
        Say ''
        Say 'Question 2 of 2: address of the AI server (from your IT team), for example http://192.0.2.10:8880'
        Say '  Press Enter to start without AI (review, reports and export still work)'
        $ModelUrl = Read-Host '  AI server address'
    }
    $token = New-Secret
    if ($ModelUrl) {
        $secure = Read-Host '  AI server token (typing is hidden)' -AsSecureString
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
        if ($plain) { $token = $plain }
    } else {
        $ModelUrl = 'http://127.0.0.1:9'   # Nothing listens there: the app shows AI as not available.
    }
    $lines = @(
        '# Private settings for the DR Screening web app, written by setup-webapp. Never put this file in Git.',
        "DR_SCREENING_SOURCE_COMMIT=$commit",
        'DR_SCREENING_IMAGE_TAG=local',
        'DR_SUPPORT_POSTGRES_DB=dr_support',
        'DR_SUPPORT_POSTGRES_USER=dr_support',
        "DR_SUPPORT_POSTGRES_PASSWORD=$(New-Secret)",
        "REMOTE_MODEL_URL=$ModelUrl",
        "REMOTE_MODEL_TOKEN=$token",
        "DR_DATA_DIR=$(Slash $DataDir)",
        "DR_IMAGES_DIR=$(Slash $ImagesDir)",
        'DR_SITE_ADDRESS=localhost',
        'DR_HTTPS_BIND=127.0.0.1',
        'DR_SUPPORT_REFERRAL_HOSTS='
    )
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $EnvFile) | Out-Null
    [IO.File]::WriteAllText($EnvFile, (($lines -join "`n") + "`n"), (New-Object Text.UTF8Encoding($false)))
    & icacls $EnvFile /inheritance:r /grant:r "$($env:USERNAME):(F)" *> $null   # Only this Windows account.
    Say "2/5 Settings saved (passwords made for you): $EnvFile"
}

# 3. Start (the first start builds the app; this can take several minutes)
$dataDir = (Get-Content $EnvFile | Where-Object { $_ -match '^DR_DATA_DIR=' } | Select-Object -First 1) -replace '^DR_DATA_DIR=', ''
if (-not $dataDir) { $dataDir = Join-Path $Package 'data' }
foreach ($name in 'config', 'state', 'output') { New-Item -ItemType Directory -Force -Path (Join-Path $dataDir $name) | Out-Null }
Say '3/5 Starting the web app (the first time builds it and can take several minutes)'
Invoke-Compose up -d --build
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    & curl.exe -s -k -o NUL https://localhost/health
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 3
}
if (-not $ready) { Stop-Setup 'The web app did not answer in 3 minutes. Run setup again, or ask IT to read: docker compose logs review' }

# 4. First administrator (only when no account exists yet)
$accounts = Join-Path $dataDir 'config\pilot-users.json'
if ($SkipAdmin) {
    Say '4/5 Administrator account skipped'
} elseif (Test-Path $accounts) {
    Say '4/5 Accounts already exist (kept)'
} else {
    Say ''
    Say '4/5 Create the administrator account (you will choose a new password at the first sign-in)'
    $user = Read-Host '  Username (lowercase, for example admin)'
    if (-not $user) { $user = 'admin' }
    $secure = Read-Host '  Temporary password, at least 8 letters and numbers (typing is hidden)' -AsSecureString
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    $plain | & docker compose --env-file $EnvFile -f $Compose run --rm -T review python -m dr_support.services.pilot_auth set-user --file /data/config/pilot-users.json --username $user --role admin --must-change
    if ($LASTEXITCODE -ne 0) { Stop-Setup 'The account was not created. Run setup again and choose a longer password with letters and numbers.' }
    $plain = $null
}

# 5. Desktop button and browser
if (-not $NoShortcut) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'DR Screening Web App.lnk'))
    $link.TargetPath = Join-Path $Package 'start-webapp.bat'
    $link.WorkingDirectory = $Package
    $icon = Join-Path $Repo 'scripts\demo\dr-screening.ico'
    if (Test-Path $icon) { $link.IconLocation = $icon }
    $link.Save()
    Say '5/5 Desktop button "DR Screening Web App" is ready'
}
Say ''
Say 'Done. Open https://localhost/app/ and sign in. Next time, use the desktop button.'
Say 'The browser may warn about the certificate the first time (it is made on this computer): choose Advanced, then continue.'
if (-not $NoBrowser) { Start-Process 'https://localhost/app/' }
