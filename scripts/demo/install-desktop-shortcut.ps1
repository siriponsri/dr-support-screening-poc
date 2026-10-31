# Creates (or replaces) one desktop shortcut "DR Screening Demo" with the app logo.
# It points at start-dr-train-demo.bat in this checkout. Nothing else is changed.
Set-StrictMode -Version Latest
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Resolve-Path (Join-Path $here '..\..')
$desktop = [Environment]::GetFolderPath('Desktop')
$link = Join-Path $desktop 'DR Screening Demo.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = Join-Path $here 'start-dr-train-demo.bat'
$shortcut.WorkingDirectory = $repo.Path
$shortcut.IconLocation = (Join-Path $here 'dr-screening.ico') + ',0'
$shortcut.Description = 'Start the DR Screening demo (dr-train AI server and web app)'
$shortcut.Save()
Write-Output "Shortcut ready: $link"
