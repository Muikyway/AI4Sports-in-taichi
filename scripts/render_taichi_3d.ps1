param(
    [string]$OutputDir = "",
    [string]$CondaEnv = "alphapose",
    [string]$CondaExe = "D:\software\miniconda\Scripts\conda.exe",
    [switch]$Overwrite
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) { $OutputDir = Join-Path $RootDir "outputs\TaiChi" }
$MotionBertDir = Join-Path $RootDir "MotionBERT"
$Renderer = Join-Path $RootDir "scripts\render_motionbert_3d.py"
foreach ($required in @($OutputDir, $CondaExe, $MotionBertDir, $Renderer)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required path not found: $required" }
}

$poses = Get-ChildItem -LiteralPath $OutputDir -Recurse -Filter "X3D.npy" | Sort-Object FullName
if (-not $poses) { throw "No X3D.npy files found in $OutputDir" }

foreach ($pose in $poses) {
    $render = Join-Path $pose.DirectoryName "X3D.mp4"
    if (-not $Overwrite -and (Test-Path -LiteralPath $render) -and (Get-Item -LiteralPath $render).Length -gt 0) {
        Write-Output "[Render] skip existing $render"
        continue
    }
    $metadata = Join-Path $pose.DirectoryName "X3D.metadata.json"
    Write-Output "[Render] start $($pose.FullName)"
    $previousPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = $MotionBertDir
    try {
        & $CondaExe run -n $CondaEnv python $Renderer `
            --pose-3d $pose.FullName --metadata $metadata `
            --output $render --motionbert-dir $MotionBertDir
        if ($LASTEXITCODE -ne 0) { throw "Rendering failed with exit code $LASTEXITCODE" }
    }
    finally {
        $env:PYTHONPATH = $previousPythonPath
    }
    Write-Output "[Render] done $render"
}
