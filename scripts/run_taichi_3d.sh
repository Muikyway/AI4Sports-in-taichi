#!/usr/bin/env bash
set -euo pipefail

# Batch pipeline: TaiChi videos -> AlphaPose Halpe-26 -> MotionBERT H36M-17.
# Run from Git Bash/WSL/Linux. On Windows, set CONDA_EXE to conda.bat or use
# the equivalent PowerShell commands shown in README_MOTIONBERT_3D.md.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT_DIR="${INPUT_DIR:-${ROOT_DIR}/TaiChi}"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}/outputs/TaiChi}"
ALPHAPOSE_DIR="${ALPHAPOSE_DIR:-${ROOT_DIR}/AlphaPose}"
CONDA_ENV="${CONDA_ENV:-alphapose}"
CONDA_EXE="${CONDA_EXE:-conda}"
ALPHAPOSE_CONFIG="${ALPHAPOSE_CONFIG:-${ALPHAPOSE_DIR}/configs/halpe_26/resnet/256x192_res50_lr1e-3_1x.yaml}"
ALPHAPOSE_CHECKPOINT="${ALPHAPOSE_CHECKPOINT:-${ALPHAPOSE_DIR}/pretrained_models/halpe26_fast_res50_256x192.pth}"
MOTIONBERT_DIR="${MOTIONBERT_DIR:-${ROOT_DIR}/MotionBERT}"
MOTIONBERT_CONFIG="${MOTIONBERT_CONFIG:-${MOTIONBERT_DIR}/configs/pose3d/MB_ft_h36m_global_lite.yaml}"
if [[ -z "${MOTIONBERT_CHECKPOINT:-}" ]]; then
  if [[ -f "${MOTIONBERT_DIR}/checkpoint/pose3d/FT_MB_lite_MB_ft_h36m_global_lite/best_epoch.bin" ]]; then
    MOTIONBERT_CHECKPOINT="${MOTIONBERT_DIR}/checkpoint/pose3d/FT_MB_lite_MB_ft_h36m_global_lite/best_epoch.bin"
  else
    MOTIONBERT_CHECKPOINT="${MOTIONBERT_DIR}/checkpoint/best_epoch.bin"
  fi
fi
FOCUS="${FOCUS:-}"
RENDER=0
ONLY_3D=0
PRIMARY_PERSON=0

usage() {
  cat <<'EOF'
Usage: bash scripts/run_taichi_3d.sh [options]
Options:
  --input-dir PATH       TaiChi video directory
  --output-dir PATH      Per-video output directory
  --focus ID             AlphaPose person idx for multi-person videos
  --render               Render X3D.mp4 when MotionBERT checkpoint exists
  --only-3d              Skip AlphaPose and process only existing JSON files
  --primary-person       Choose the highest-score AlphaPose detection per frame
  --help                 Show this help
Environment: CONDA_EXE, CONDA_ENV, ALPHAPOSE_DIR, ALPHAPOSE_CONFIG,
ALPHAPOSE_CHECKPOINT, MOTIONBERT_DIR, MOTIONBERT_CONFIG,
MOTIONBERT_CHECKPOINT, INPUT_DIR, OUTPUT_DIR, FOCUS.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-dir) INPUT_DIR="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --focus) FOCUS="$2"; shift 2 ;;
    --render) RENDER=1; shift ;;
    --only-3d) ONLY_3D=1; shift ;;
    --primary-person) PRIMARY_PERSON=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for required in "$INPUT_DIR" "$ALPHAPOSE_DIR" "$ALPHAPOSE_CONFIG" "$ALPHAPOSE_CHECKPOINT"; do
  [[ -e "$required" ]] || { echo "Required path not found: $required" >&2; exit 2; }
done
mkdir -p "$OUTPUT_DIR"

shopt -s nullglob
videos=("$INPUT_DIR"/*.avi "$INPUT_DIR"/*.mp4 "$INPUT_DIR"/*.mov)
[[ ${#videos[@]} -gt 0 ]] || { echo "No videos found in $INPUT_DIR" >&2; exit 2; }

for video in "${videos[@]}"; do
  name="$(basename "$video")"
  stem="${name%.*}"
  out="$OUTPUT_DIR/$stem"
  pose_json="$out/alphapose-results.json"
  mkdir -p "$out"
  if [[ "$ONLY_3D" -eq 1 && ! -s "$pose_json" ]]; then
    echo "[MotionBERT] skip missing $pose_json"
    continue
  elif [[ "$ONLY_3D" -eq 0 && ! -s "$pose_json" ]]; then
    echo "[AlphaPose] $name"
    (cd "$ALPHAPOSE_DIR" && PYTHONPATH="$ALPHAPOSE_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      "$CONDA_EXE" run -n "$CONDA_ENV" python scripts/demo_inference.py \
      --sp --gpus "${ALPHAPOSE_GPUS:-0}" --cfg "$ALPHAPOSE_CONFIG" \
      --checkpoint "$ALPHAPOSE_CHECKPOINT" --video "$video" --outdir "$out")
  elif [[ "$ONLY_3D" -eq 0 ]]; then
    echo "[AlphaPose] skip existing $pose_json"
  fi

  if [[ -f "$MOTIONBERT_CHECKPOINT" ]]; then
    if [[ -s "$out/motionbert_3d/X3D.npy" ]]; then
      echo "[MotionBERT] skip existing $name"
      continue
    fi
    args=("$ROOT_DIR/scripts/run_motionbert_3d.py" --pose-json "$pose_json" \
      --video "$video" --motionbert-dir "$MOTIONBERT_DIR" \
      --config "$MOTIONBERT_CONFIG" --checkpoint "$MOTIONBERT_CHECKPOINT" \
      --output-dir "$out/motionbert_3d")
    [[ -n "$FOCUS" ]] && args+=(--focus "$FOCUS")
    [[ "$PRIMARY_PERSON" -eq 1 ]] && args+=(--primary-person)
    [[ "$RENDER" -eq 1 ]] && args+=(--render)
    echo "[MotionBERT] $name"
    PYTHONPATH="$MOTIONBERT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      "$CONDA_EXE" run -n "$CONDA_ENV" python "${args[@]}"
  else
    echo "[MotionBERT] checkpoint missing; leaving 2D output for $name" >&2
  fi
done

echo "Completed batch processing: $OUTPUT_DIR"
