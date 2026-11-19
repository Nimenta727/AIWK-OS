# Run inside any local Git repository after an agent edits project files.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Summary, [string]$NextSteps='Needs planning')
$ErrorActionPreference='Stop'
$root=(& git rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0) { throw 'Not inside a Git repository.' }
$folder=Join-Path $root 'docs\routine'
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$stamp=Get-Date -Format 'yyyy-MM-dd_HHmmss'
$changes=(& git status --short) -join "`r`n"
$body=@"
# $stamp - $Summary

- Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')
- Summary: $Summary

## Changed files

``````text
$changes
``````

## Tests / verification

- [ ] Document actual commands and results

## Known issues

- To be completed

## Next steps

$NextSteps
"@
$path=Join-Path $folder "$stamp-change.md"
[System.IO.File]::WriteAllText($path,$body,[Text.UTF8Encoding]::new($false))
Write-Host "Created: $path"
