# Optional Windows EXE creation. NOT needed for portable Python distribution.
# This downloads PyInstaller only after the operator explicitly executes it.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
if (Get-Command py -ErrorAction SilentlyContinue) { $py='py'; $pyArgs=@('-3') }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $py='python'; $pyArgs=@() }
else { throw 'Python is required' }
& $py @pyArgs -m pip install 'pyinstaller>=6,<7'
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller install failed.' }
& $py @pyArgs -m PyInstaller --noconfirm --onefile --name AIWS --add-data 'web;web' --collect-submodules aiws app.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Write-Host 'Check dist\AIWS.exe. Build output is UNSIGNED and has NOT been independently audited.'
