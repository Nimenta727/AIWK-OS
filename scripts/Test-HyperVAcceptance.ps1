# Local, non-destructive readiness check for AIWS test VMs.
# This DOES NOT launch an Agent, execute a model, change Windows settings or claim GUI validation.
param([string]$Distribution = "$(Join-Path (Get-Location) 'dist/native-desktop')")
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$folder = [System.IO.Path]::GetFullPath($Distribution)
$exe = Join-Path $folder 'WindowsAIWorkstation.exe'
$ui = Join-Path $folder 'ui-dist/index.html'
$checks = [ordered]@{
    'Windows operating system' = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
    'WindowsAIWorkstation.exe exists' = Test-Path -LiteralPath $exe -PathType Leaf
    'Offline React index.html exists' = Test-Path -LiteralPath $ui -PathType Leaf
    'Official Git CLI detected' = [bool](Get-Command git -ErrorAction SilentlyContinue)
    'Official Codex CLI detected (optional)' = [bool](Get-Command codex -ErrorAction SilentlyContinue)
    'Official Claude CLI detected (optional)' = [bool](Get-Command claude -ErrorAction SilentlyContinue)
}
$signature = if ($checks['WindowsAIWorkstation.exe exists']) { (Get-AuthenticodeSignature -FilePath $exe).Status.ToString() } else { 'missing' }
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
foreach ($key in $checks.Keys) {
    $label = if ($checks[$key]) {'PASS'} else {'NOTE'}
    Write-Host "[$label] $key"
}
Write-Host "[INFO] Authenticode signature: $signature (unsigned means NOT verified)"
Write-Host "[INFO] Elevated account: $isAdmin (recommended: false)"
Write-Host '[MANUAL] Hyper-V GUI validation required: launch, keyboard/IME, ConPTY, monitor DPI, worktree, Git diff, task restart, queued dispatch, offline startup.'
Write-Host '[MANUAL] Back up tasks.json and the project repository before trying Agent writes.'
if (-not $checks['Windows operating system'] -or -not $checks['WindowsAIWorkstation.exe exists'] -or -not $checks['Offline React index.html exists']) {
    throw 'Mandatory offline distribution preflight checks failed; no EXE was launched.'
}
