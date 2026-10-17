param(
    [string]$InputDir = "",
    [string]$OutputDir = "",
    [string]$CondaEnv = "alphapose",
    [string]$CondaExe = "D:\\software\\miniconda\\Scripts\\conda.exe",
    [string]$MotionBertCheckpoint = "",
    [int]$Focus = -1,
    [switch]$Render,
    [switch]$Only3D,
    [switch]$PrimaryPerson
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
if (-not $InputDir) { $InputDir = Join-Path $RootDir "TaiChi" }
if (-not $OutputDir) { $OutputDir = Join-Path $RootDir "outputs\\TaiChi" }
if (-not $MotionBertCheckpoint) {
    $nestedCheckpoint = Join-Path $RootDir "MotionBERT\\checkpoint\\pose3d\\FT_MB_lite_MB_ft_h36m_global_lite\\best_epoch.bin"
    $flatCheckpoint = Join-Path $RootDir "MotionBERT\\checkpoint\\best_epoch.bin"
    if (Test-Path -LiteralPath $nestedCheckpoint) {
        $MotionBertCheckpoint = $nestedCheckpoint
    } elseif (Test-Path -LiteralPath $flatCheckpoint) {
        $MotionBertCheckpoint = $flatCheckpoint
    } else {
        $MotionBertCheckpoint = $nestedCheckpoint
    }
}

$AlphaPoseDir = Join-Path $RootDir "AlphaPose"
$AlphaPoseConfig = Join-Path $AlphaPoseDir "configs\\halpe_26\\resnet\\256x192_res50_lr1e-3_1x.yaml"
$AlphaPoseCheckpoint = Join-Path $AlphaPoseDir "pretrained_models\\halpe26_fast_res50_256x192.pth"
$MotionBertDir = Join-Path $RootDir "MotionBERT"
$MotionBertConfig = Join-Path $MotionBertDir "configs\\pose3d\\MB_ft_h36m_global_lite.yaml"
$LogFile = Join-Path $OutputDir "batch_taichi_3d.log"

foreach ($required in @($InputDir, $CondaExe, $AlphaPoseDir, $AlphaPoseConfig, $AlphaPoseCheckpoint, $MotionBertDir, $MotionBertConfig)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required path not found: $required" }
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
function Write-Log([string]$Message) {
    $line = "$(Get-Date -Format s) $Message"
    $line | Tee-Object -FilePath $LogFile -Append
}

$videos = Get-ChildItem -LiteralPath $InputDir -File |
    Where-Object { $_.Extension -in ".avi", ".mp4", ".mov" } |
    Sort-Object Name
if (-not $videos) { throw "No .avi/.mp4/.mov videos found in $InputDir" }

$hasMotionBert = Test-Path -LiteralPath $MotionBertCheckpoint
if (-not $hasMotionBert) {
    Write-Log "[MotionBERT] checkpoint not found; batch will generate only AlphaPose Halpe-26 JSON."
}

foreach ($video in $videos) {
    $videoOutput = Join-Path $OutputDir $video.BaseName
    $poseJson = Join-Path $videoOutput "alphapose-results.json"
    New-Item -ItemType Directory -Force -Path $videoOutput | Out-Null

    if ($Only3D -and (-not (Test-Path -LiteralPath $poseJson) -or (Get-Item -LiteralPath $poseJson).Length -eq 0)) {
        Write-Log "[MotionBERT] skip missing AlphaPose JSON $($video.Name)"
        continue
    }

    if (-not $Only3D -and (-not (Test-Path -LiteralPath $poseJson) -or (Get-Item -LiteralPath $poseJson).Length -eq 0)) {
        Write-Log "[AlphaPose] start $($video.Name)"
        $previousPythonPath = $env:PYTHONPATH
        $env:PYTHONPATH = $AlphaPoseDir
        Push-Location $AlphaPoseDir
        try {
            & $CondaExe run -n $CondaEnv python scripts\demo_inference.py `
                --sp --gpus 0 --cfg $AlphaPoseConfig --checkpoint $AlphaPoseCheckpoint `
                --video $video.FullName --outdir $videoOutput
            if ($LASTEXITCODE -ne 0) { throw "AlphaPose failed with exit code $LASTEXITCODE" }
        }
        finally {
            Pop-Location
            $env:PYTHONPATH = $previousPythonPath
        }
        if (-not (Test-Path -LiteralPath $poseJson) -or (Get-Item -LiteralPath $poseJson).Length -eq 0) {
            throw "AlphaPose did not create a non-empty result: $poseJson"
        }
        Write-Log "[AlphaPose] done $($video.Name)"
    }
    elseif (-not $Only3D) {
        Write-Log "[AlphaPose] skip existing $($video.Name)"
    }

    if ($hasMotionBert) {
        $motionOutput = Join-Path $videoOutput "motionbert_3d"
        $x3dPath = Join-Path $motionOutput "X3D.npy"
        if (Test-Path -LiteralPath $x3dPath) {
            Write-Log "[MotionBERT] skip existing $($video.Name)"
            continue
        }
        Write-Log "[MotionBERT] start $($video.Name)"
        $motionArgs = @(
            (Join-Path $RootDir "scripts\\run_motionbert_3d.py"),
            "--pose-json", $poseJson,
            "--video", $video.FullName,
            "--motionbert-dir", $MotionBertDir,
            "--config", $MotionBertConfig,
            "--checkpoint", $MotionBertCheckpoint,
            "--output-dir", $motionOutput
        )
        if ($Focus -ge 0) { $motionArgs += @("--focus", "$Focus") }
        if ($PrimaryPerson) { $motionArgs += "--primary-person" }
        if ($Render) { $motionArgs += "--render" }
        $previousPythonPath = $env:PYTHONPATH
        $env:PYTHONPATH = $MotionBertDir
        try {
            & $CondaExe run -n $CondaEnv python @motionArgs
            if ($LASTEXITCODE -ne 0) { throw "MotionBERT failed with exit code $LASTEXITCODE" }
        }
        finally {
            $env:PYTHONPATH = $previousPythonPath
        }
        Write-Log "[MotionBERT] done $($video.Name)"
    }
}

Write-Log "Completed $($videos.Count) TaiChi videos."
