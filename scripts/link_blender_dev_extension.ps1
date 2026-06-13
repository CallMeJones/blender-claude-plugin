[CmdletBinding()]
param(
    [string]$BlenderVersion = "5.1",
    [string]$ExtensionId = "claude_blender",
    [string]$Source = "",
    [string]$ExtensionRepo = "",
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-NormalizedPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/').ToLowerInvariant()
}

if ([string]::IsNullOrWhiteSpace($Source)) {
    $repoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
    $Source = Join-Path $repoRoot "addon\$ExtensionId"
}

$sourceItem = Get-Item -LiteralPath $Source -ErrorAction Stop
$sourcePath = $sourceItem.FullName
$manifestPath = Join-Path $sourcePath "blender_manifest.toml"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Source '$sourcePath' does not look like a Blender extension root; missing blender_manifest.toml."
}

if ([string]::IsNullOrWhiteSpace($ExtensionRepo)) {
    if ([string]::IsNullOrWhiteSpace($env:APPDATA)) {
        throw "APPDATA is not set. Pass -ExtensionRepo explicitly."
    }
    $ExtensionRepo = Join-Path $env:APPDATA "Blender Foundation\Blender\$BlenderVersion\extensions\user_default"
}

New-Item -ItemType Directory -Path $ExtensionRepo -Force | Out-Null

$installPath = Join-Path $ExtensionRepo $ExtensionId
$backupRoot = Join-Path $ExtensionRepo ".dev-link-backups"
$sourceNormal = Get-NormalizedPath $sourcePath

if (Test-Path -LiteralPath $installPath) {
    $installItem = Get-Item -LiteralPath $installPath -Force
    $isLink = ($installItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0

    if ($isLink) {
        $target = $installItem.Target
        if ($target -is [array]) {
            $target = $target[0]
        }

        if ($target -and (Get-NormalizedPath $target) -eq $sourceNormal) {
            Write-Host "Already linked:"
            Write-Host "  $installPath -> $sourcePath"
            Write-Host "Restart Blender to pick up Python changes."
            exit 0
        }

        if (-not $Force) {
            throw "Install path is already a link to '$target'. Re-run with -Force to replace that link."
        }

        Remove-Item -LiteralPath $installPath
        Write-Host "Removed existing link at $installPath"
    }
    else {
        New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
        $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $backupPath = Join-Path $backupRoot "$ExtensionId-$timestamp"
        Move-Item -LiteralPath $installPath -Destination $backupPath
        Write-Host "Backed up installed extension to:"
        Write-Host "  $backupPath"
    }
}

New-Item -ItemType Junction -Path $installPath -Target $sourcePath | Out-Null

Write-Host "Linked Blender extension for development:"
Write-Host "  $installPath -> $sourcePath"
Write-Host ""
Write-Host "Next step: restart Blender, or disable/enable the extension if Blender can unregister it cleanly."
