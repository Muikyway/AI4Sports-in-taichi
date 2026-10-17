#!/usr/bin/env bash
set -euo pipefail

# AlphaPose Halpe-26 JSON -> MotionBERT H36M-17 3D pose.
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
POSE_JSON="${POSE_JSON:-$ROOT_DIR/outputs/yema_fenzong/alphapose-results.json}"
VIDEO="${VIDEO:-}"
MOTIONBERT_DIR="${MOTIONBERT_DIR:-$ROOT_DIR/MotionBERT}"
CONFIG="${CONFIG:-$MOTIONBERT_DIR/configs/pose3d/MB_ft_h36m_global_lite.yaml}"
CHECKPOINT="${CHECKPOINT:-$MOTIONBERT_DIR/checkpoint/pose3d/FT_MB_lite_MB_ft_h36m_global_lite/best_epoch.bin}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/outputs/motionbert_3d}"
FOCUS="${FOCUS:-}"
CLIP_LEN="${CLIP_LEN:-243}"
PIXEL=0
RENDER=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/run_motionbert_3d.sh --video VIDEO [options]

Options:
  --pose-json PATH       AlphaPose Halpe-26 JSON
  --video PATH           Original video (required)
  --motionbert-dir PATH MotionBERT checkout
  --config PATH          3D pose config
  --checkpoint PATH      3D pose checkpoint
  --output-dir PATH      Output directory (default: outputs/motionbert_3d)
  --focus ID             AlphaPose idx for one person
  --clip-len N           MotionBERT clip length (default: 243)
  --pixel                Keep pixel-aligned x/y output
  --render               Write X3D.mp4
  -h, --help             Show this help

Environment equivalents: PYTHON_BIN, POSE_JSON, VIDEO, MOTIONBERT_DIR,
CONFIG, CHECKPOINT, OUTPUT_DIR, FOCUS, CLIP_LEN.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pose-json) POSE_JSON="$2"; shift 2 ;;
    --video) VIDEO="$2"; shift 2 ;;
    --motionbert-dir) MOTIONBERT_DIR="$2"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    --checkpoint) CHECKPOINT="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --focus) FOCUS="$2"; shift 2 ;;
    --clip-len) CLIP_LEN="$2"; shift 2 ;;
    --pixel) PIXEL=1; shift ;;
    --render) RENDER=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$VIDEO" ]]; then
  echo "--video is required (or set VIDEO=/path/to/video.mp4)" >&2
  usage >&2
  exit 2
fi

ARGS=(
  "$ROOT_DIR/scripts/run_motionbert_3d.py"
  --pose-json "$POSE_JSON"
  --video "$VIDEO"
  --motionbert-dir "$MOTIONBERT_DIR"
  --config "$CONFIG"
  --checkpoint "$CHECKPOINT"
  --output-dir "$OUTPUT_DIR"
  --clip-len "$CLIP_LEN"
)
[[ -n "$FOCUS" ]] && ARGS+=(--focus "$FOCUS")
[[ "$PIXEL" -eq 1 ]] && ARGS+=(--pixel)
[[ "$RENDER" -eq 1 ]] && ARGS+=(--render)

exec "$PYTHON_BIN" "${ARGS[@]}"
