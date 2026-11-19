# Build on a Windows 10/11 machine with .NET 10 SDK.
# Outputs an unsigned, self-contained Windows EXE in dist/native-desktop/.
[CmdletBinding()]
param([switch]$NoSelfContained)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = Join-Path $repo 'desktop/AIWorkstation.Desktop/AIWorkstation.Desktop.csproj'
$out = Join-Path $repo 'dist/native-desktop'
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw 'Missing .NET SDK: install .NET 10 SDK from Microsoft before running this script.'
}
$runtime = if ($NoSelfContained) { 'false' } else { 'true' }
& dotnet run --project (Join-Path $repo 'desktop/AIWorkstation.Core.SmokeTests/AIWorkstation.Core.SmokeTests.csproj') -c Release
if ($LASTEXITCODE -ne 0) { throw 'Core tests failed' }
& dotnet publish $project -c Release -r win-x64 --self-contained $runtime -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=true -o $out
if ($LASTEXITCODE -ne 0) { throw 'Native publish failed' }
$exe = Join-Path $out 'WindowsAIWorkstation.exe'
if (-not (Test-Path $exe)) { throw 'EXE missing after publish' }
Write-Host "Built: $exe" -ForegroundColor Green
Write-Warning 'This binary is unsigned. Verify the checksum and test in a Hyper-V snapshot before regular use.'
