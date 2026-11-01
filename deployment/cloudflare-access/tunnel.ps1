# Share the running DR Screening demo with invited team members through a Cloudflare Tunnel.
# Run by start-tunnel.bat (-Action Start) and stop-tunnel.bat (-Action Stop). See README.md.
# The tunnel token stays in a private file of this Windows account and is never shown.
# Only public or synthetic demo images may be shared this way (hospital rule). Never patient images.
param(
    [ValidateSet('Start', 'Stop')]
    [string]$Action = 'Start',
    [switch]$NewToken
)
$ErrorActionPreference = 'Stop'
$Private = Join-Path $env:LOCALAPPDATA 'DRScreening'
$TunnelKeyFile = Join-Path $Private 'cloudflare-tunnel.token'
$RuleFile = Join-Path $Private 'cloudflare-demo-rule.accepted'
$PidFile = Join-Path $Private 'cloudflare-tunnel.pid'
$DemoConfig = Join-Path $Private 'M1PrivateConfig\demo.env'

function Say([string]$Text) { Write-Host $Text }
function Stop-Here([string]$Text) { Write-Host ''; Write-Host "Stopped: $Text" -ForegroundColor Yellow; exit 1 }
function Protect-File([string]$Path) {
    # Only this Windows account may read the file.
    & icacls $Path /inheritance:r /grant:r "$($env:USERNAME):(F)" *> $null
    if ($LASTEXITCODE -ne 0) { Stop-Here "Could not make $Path private." }
}
function Write-PrivateFile([string]$Path, [string]$Text) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
    Protect-File $Path
}
function Get-DemoSetting([string]$Name, [string]$Default) {
    if (Test-Path $DemoConfig) {
        $line = Get-Content $DemoConfig | Where-Object { $_ -match "^\s*$Name=" } | Select-Object -Last 1
        if ($line) { return ($line -replace "^\s*$Name=", '').Trim().Trim('"').Trim("'") }
    }
    return $Default
}
function Find-Cloudflared {
    $command = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($folder in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
        if ($folder) {
            $candidate = Join-Path $folder 'cloudflared\cloudflared.exe'
            if (Test-Path $candidate) { return $candidate }
        }
    }
    return $null
}
function Test-LocalPort([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $wait = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        return ($wait.AsyncWaitHandle.WaitOne(2000) -and $client.Connected)
    } catch { return $false } finally { $client.Close() }
}

if ($Action -eq 'Stop') {
    if (-not (Test-Path $PidFile)) { Say 'No shared demo is running (nothing was started by start-tunnel.bat).'; exit 0 }
    $id = [int](Get-Content $PidFile | Select-Object -First 1)
    $process = Get-Process -Id $id -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -eq 'cloudflared') {
        Stop-Process -Id $id -Force
        Say 'Sharing stopped. Team members can no longer open the demo. The demo app itself is still running.'
    } else {
        Say 'Sharing was already stopped.'
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    exit 0
}

Say 'DR Screening demo: share with invited team members (Cloudflare)'
Say ''

# 1. Hospital rule, asked once.
if (-not (Test-Path $RuleFile)) {
    Say 'Before the first share, one question (asked only once):'
    Say ''
    Say '  This puts the demo on the internet for the people you invited in Cloudflare Access.'
    Say '  Hospital rule: only PUBLIC or SYNTHETIC demo images may be used this way.'
    Say '  Never patient images, not even with consent.'
    Say ''
    Say '  Type YES if the demo you share uses public or synthetic images only.'
    Say '  Type anything else to stop.'
    $answer = Read-Host '  Answer'
    if ($answer -cne 'YES') { Stop-Here 'nothing was shared.' }
    Write-PrivateFile $RuleFile ("Demo-data rule accepted by $($env:USERNAME) on $((Get-Date).ToString('yyyy-MM-dd HH:mm'))`n")
    Say '  Saved. You will not be asked again on this computer.'
    Say ''
}

# 2. The demo must use public images and be running.
$images = Get-DemoSetting 'DR_IMAGES' 'workspace'
if ($images -ne 'public-samples' -and $images -ne 'public-folder') {
    Stop-Here ("the demo is set to use workspace images (DR_IMAGES=$images in $DemoConfig). " +
        'For sharing, set DR_IMAGES=public-samples (or public-folder with a folder of public images), ' +
        'restart the demo, then run this again.')
}
$port = [int](Get-DemoSetting 'DR_APP_PORT' '8010')
if (-not (Test-LocalPort $port)) {
    Stop-Here "the demo app is not running on http://127.0.0.1:$port. Start it first (desktop button DR Screening Demo), then run this again."
}
Say "1/3 Demo app is running on http://127.0.0.1:$port with public images ($images)"

# 3. cloudflared is installed by the owner, never downloaded here.
$cloudflared = Find-Cloudflared
if (-not $cloudflared) {
    Say ''
    Say 'cloudflared (the Cloudflare Tunnel program) is not installed. To install it:'
    Say '  1. Open PowerShell or Command Prompt.'
    Say '  2. Run:  winget install --id Cloudflare.cloudflared'
    Say '  3. Close that window, then double-click start-tunnel.bat again.'
    Stop-Here 'cloudflared is needed.'
}
Say '2/3 cloudflared is installed'

# 4. Tunnel token in a private file (pasted once, typing hidden).
if ($NewToken -or -not (Test-Path $TunnelKeyFile)) {
    Say ''
    Say 'Paste the tunnel token from the Cloudflare dashboard (Zero Trust > Networks > Tunnels > your tunnel).'
    Say 'You can paste the whole install command; only the token is kept. Typing is hidden.'
    $secure = Read-Host '  Token' -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $pasted = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    $tokenValue = (($pasted.Trim() -split '\s+') | Select-Object -Last 1)
    $pasted = $null
    if ($tokenValue -notmatch '^[A-Za-z0-9_\-+/=.]{40,}$') { Stop-Here 'that does not look like a tunnel token. Copy it again from the dashboard.' }
    Write-PrivateFile $TunnelKeyFile $tokenValue
    Say "  Saved privately (only this Windows account can read it): $TunnelKeyFile"
} else {
    Protect-File $TunnelKeyFile
    $tokenValue = (Get-Content $TunnelKeyFile -Raw).Trim()
}
if (-not $tokenValue) { Stop-Here "the token file is empty. Run start-tunnel.bat -NewToken to paste it again." }

# 5. Run the tunnel. The token goes to cloudflared through its environment, never on the command line.
Say '3/3 Sharing. Team members open the address you set in Cloudflare (for example https://dr-demo.<your-domain>/app/),'
Say '    sign in with the code Cloudflare e-mails them, then with their DR Screening account.'
Say ''
Say 'Keep this window open while the team uses the demo. Close it (or run stop-tunnel.bat) to stop sharing.'
Say ''
$env:TUNNEL_TOKEN = $tokenValue
$tokenValue = $null
try {
    $process = Start-Process -FilePath $cloudflared -ArgumentList @('tunnel', '--no-autoupdate', 'run') -NoNewWindow -PassThru
    [IO.File]::WriteAllText($PidFile, "$($process.Id)")
    $process.WaitForExit()
} finally {
    Remove-Item Env:TUNNEL_TOKEN -ErrorAction SilentlyContinue
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}
Say ''
Say 'Sharing stopped.'
