# Run in an elevated PowerShell on the Hyper-V HOST. Copies the ZIP without opening WinRM/network ports.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$VMName,
    [Parameter(Mandatory=$true)][string]$ZipPath,
    [string]$GuestDestination='C:\AIWS'
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $ZipPath -PathType Leaf)) { throw 'ZIP file not found.' }
$vm = Get-VM -Name $VMName -ErrorAction Stop
if ($vm.State -ne 'Running') { throw 'The guest must be running for PowerShell Direct.' }
Write-Host 'PowerShell Direct requires a valid account INSIDE the guest. Credentials are never stored.'
$cred = Get-Credential -Message 'Enter the guest Windows account credentials'
$session = New-PSSession -VMName $VMName -Credential $cred
try {
    Invoke-Command -Session $session -ScriptBlock {
        param($p)
        New-Item -ItemType Directory -Path $p -Force | Out-Null
    } -ArgumentList $GuestDestination
    $target = Join-Path $GuestDestination 'aiws-package.zip'
    Copy-Item -LiteralPath $ZipPath -Destination $target -ToSession $session -Force
    Invoke-Command -Session $session -ScriptBlock {
        param($p)
        $archive = Join-Path $p 'aiws-package.zip'
        $targetDir = Join-Path $p 'AIWS-Prototype'
        if (Test-Path -LiteralPath $targetDir) { throw 'Destination exists. Move/backup it before redeploying.' }
        Expand-Archive -LiteralPath $archive -DestinationPath $targetDir
        Write-Output "Code copied to $targetDir"
    } -ArgumentList $GuestDestination
}
finally { Remove-PSSession $session }
Write-Host "Deployment copied. Inside the VM, review and run: $GuestDestination\AIWS-Prototype\scripts\Preflight-Guest.ps1"
Write-Host 'Then use Install-Guest.ps1 and Start-AIWS.ps1 manually in the guest account session.'
