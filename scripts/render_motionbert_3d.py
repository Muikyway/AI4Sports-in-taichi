"""Render a saved MotionBERT X3D.npy skeleton sequence as an MP4 video."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pose-3d", required=True, help="MotionBERT X3D.npy, shape [T, 17, 3]")
    parser.add_argument("--output", default="", help="Output MP4 path; defaults beside X3D.npy")
    parser.add_argument("--metadata", default="", help="Optional X3D.metadata.json for FPS")
    parser.add_argument("--fps", type=float, default=0.0, help="Override FPS; default reads metadata or 25")
    parser.add_argument("--motionbert-dir", default="MotionBERT")
    return parser.parse_args()


def absolute(path: str | Path, root: Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def main() -> None:
    opts = parse_args()
    import matplotlib
    import numpy as np

    matplotlib.use("Agg")
    root = Path(__file__).resolve().parents[1]
    pose_path = absolute(opts.pose_3d, root)
    motionbert_dir = absolute(opts.motionbert_dir, root)
    output_path = absolute(opts.output, root) if opts.output else pose_path.with_name("X3D.mp4")
    metadata_path = absolute(opts.metadata, root) if opts.metadata else pose_path.with_name("X3D.metadata.json")
    if not pose_path.is_file():
        raise FileNotFoundError(f"3D pose file not found: {pose_path}")
    if not motionbert_dir.is_dir():
        raise FileNotFoundError(f"MotionBERT directory not found: {motionbert_dir}")

    pose_3d = np.load(pose_path)
    if pose_3d.ndim != 3 or pose_3d.shape[1:] != (17, 3):
        raise ValueError(f"Expected X3D shape [T, 17, 3], received {tuple(pose_3d.shape)}")
    if not np.isfinite(pose_3d).all():
        raise ValueError("X3D contains NaN or infinite coordinates")

    fps = opts.fps or 25.0
    if metadata_path.is_file() and not opts.fps:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        fps = float(metadata.get("fps") or fps)

    sys.path.insert(0, str(motionbert_dir))
    from lib.utils.vismo import render_and_save

    output_path.parent.mkdir(parents=True, exist_ok=True)
    render_and_save(pose_3d, str(output_path), keep_imgs=False, fps=fps)
    print(f"Rendered {tuple(pose_3d.shape)} at {fps:g} FPS -> {output_path}")


if __name__ == "__main__":
    main()
