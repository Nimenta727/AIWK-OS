# Run inside the Windows guest interactively. No admin rights required.
[CmdletBinding()]
param([int]$Port=8765, [switch]$EnableCodexReadonly)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$workspace = Join-Path $env:USERPROFILE 'AI-Workstation'
if (Get-Command py -ErrorAction SilentlyContinue) { $python='py'; $prefix=@('-3') }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $python='python'; $prefix=@() }
else { throw 'Python 3.10+ is required. Use scripts/Install-Guest.ps1 -InstallTools.' }
Set-Location $repoRoot
$cmd = @($prefix) + @('app.py','--workspace',$workspace,'--port',"$Port")
if ($EnableCodexReadonly) { $cmd += '--enable-codex-readonly' }
& $python @cmd
