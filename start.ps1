[CmdletBinding()]
param(
    [Parameter(Mandatory=$true, Position=0)][string]$BlendFile,
    [Alias('h')][double]$Height = 1.5,
    [switch]$Desktop,
    [switch]$ConvertOnly,
    [switch]$Rebuild,
    [string]$Blender,
    [string]$Godot,
    [string]$Microphone,
    [int]$BenchmarkSeconds = 0
)
$ErrorActionPreference = 'Stop'
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) { throw 'Python 3.10 or later is required.' }
$launchArgs = @((Join-Path $PSScriptRoot 'tools\launch.py'), $BlendFile, '--height', $Height.ToString([Globalization.CultureInfo]::InvariantCulture))
if ($Desktop) { $launchArgs += '--desktop' }
if ($ConvertOnly) { $launchArgs += '--convert-only' }
if ($Rebuild) { $launchArgs += '--rebuild' }
if ($Blender) { $launchArgs += @('--blender', $Blender) }
if ($Godot) { $launchArgs += @('--godot', $Godot) }
if ($Microphone) { $launchArgs += @('--microphone', $Microphone) }
if ($BenchmarkSeconds -gt 0) { $launchArgs += @('--benchmark-seconds', "$BenchmarkSeconds") }
& $pythonCommand.Source @launchArgs
exit $LASTEXITCODE
