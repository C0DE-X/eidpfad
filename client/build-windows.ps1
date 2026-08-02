param(
    [string]$Godot = "godot",
    [ValidateSet("release", "debug")]
    [string]$Configuration = "release"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DistDirectory = Join-Path $ProjectRoot "dist\client"
$Executable = Join-Path $DistDirectory "eidpfad-windows-x86_64.exe"
$Archive = Join-Path $DistDirectory "eidpfad-windows-x86_64.zip"

New-Item -ItemType Directory -Force -Path $DistDirectory | Out-Null

$ExportFlag = if ($Configuration -eq "release") { "--export-release" } else { "--export-debug" }
& $Godot --headless --path $PSScriptRoot $ExportFlag "Windows 11" $Executable
if ($LASTEXITCODE -ne 0) {
    throw "Godot export failed with exit code $LASTEXITCODE"
}

Compress-Archive -Path $Executable -DestinationPath $Archive -Force
Write-Host "Windows client created: $Archive"
