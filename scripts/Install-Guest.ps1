# Run inside the Windows guest as the intended interactive (non-admin) AIWS user.
# Third-party downloads are explicitly opt-in; never bypass policy or collect credentials.
[CmdletBinding()]
param(
    [switch]$InstallTools,
    [switch]$InstallT3,
    [switch]$CreateWorkspace
)
$ErrorActionPreference = 'Stop'
$workspace = Join-Path $env:USERPROFILE 'AI-Workstation'
function Install-WingetPackage([string]$Id) {
    Write-Host "Installing $Id using official WinGet manifest..."
    & winget install --id $Id -e --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget failed: $Id ($LASTEXITCODE)" }
}
if ($CreateWorkspace) {
    foreach($name in @('projects','tasks','logs','artifacts','knowledge','config')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $workspace $name) | Out-Null
    }
    Write-Host "Workspace created: $workspace"
}
if ($InstallTools) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'WinGet is required; install App Installer first.' }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Install-WingetPackage 'Git.Git' }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Install-WingetPackage 'OpenJS.NodeJS.LTS' }
    if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) { Install-WingetPackage 'Python.Python.3.13' }
    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { Install-WingetPackage 'Anthropic.ClaudeCode' }
    # WinGet may update PATH only in newly opened terminals.
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
            & npm install -g '@openai/codex@latest'
            if ($LASTEXITCODE -ne 0) { throw 'Codex npm install failed.' }
        }
    } else {
        Write-Warning 'Node/npm PATH not active yet. Open a NEW PowerShell and run: npm install -g @openai/codex@latest'
    }
}
if ($InstallT3) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'WinGet not found.' }
    Install-WingetPackage 'T3Tools.T3Code'
}
Write-Host 'No accounts logged in automatically. Open a NEW terminal and run claude then codex login.'
Write-Host 'For this project, install dependencies only from official repositories.'
