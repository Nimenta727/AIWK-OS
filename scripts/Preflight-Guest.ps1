# Read-only diagnostics, run inside the Windows Hyper-V guest.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Continue'
Write-Host 'AIWS Guest Preflight (read only)' -ForegroundColor Cyan
Write-Host "Computer: $env:COMPUTERNAME / User: $env:USERNAME"
Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,OSArchitecture,TotalVisibleMemorySize | Format-List
Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model,NumberOfLogicalProcessors,TotalPhysicalMemory | Format-List
Get-PSDrive -PSProvider FileSystem | Select-Object Name,Free,Used | Format-Table
foreach ($name in @('py','python','git','node','npm','winget','claude','codex','t3','openclaw')) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { Write-Host ("[OK] {0} => {1}" -f $name,$cmd.Source) -ForegroundColor Green }
    else { Write-Host ("[--] {0} missing" -f $name) -ForegroundColor Yellow }
}
Write-Host 'WSL status is optional; no nested virtualization changes are made.'
if (Get-Command wsl -ErrorAction SilentlyContinue) { wsl --status }
