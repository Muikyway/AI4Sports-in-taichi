"""Run MotionBERT 2D-to-3D lifting on an AlphaPose Halpe-26 JSON file."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pose-json", required=True, help="AlphaPose Halpe-26 JSON")
    parser.add_argument("--video", required=True, help="Original video, used for FPS/size")
    parser.add_argument("--motionbert-dir", default="MotionBERT")
    parser.add_argument(
        "--config",
        default="MotionBERT/configs/pose3d/MB_ft_h36m_global_lite.yaml",
    )
    parser.add_argument(
        "--checkpoint",
        default="MotionBERT/checkpoint/pose3d/FT_MB_lite_MB_ft_h36m_global_lite/best_epoch.bin",
    )
    parser.add_argument("--output-dir", default="outputs/motionbert_3d")
    parser.add_argument("--focus", type=int, default=None, help="AlphaPose idx for target person")
    parser.add_argument(
        "--primary-person",
        action="store_true",
        help="For a single-performer video, retain the highest-score detection in each frame",
    )
    parser.add_argument("--clip-len", type=int, default=243)
    parser.add_argument("--pixel", action="store_true", help="Keep pixel-aligned 3D x/y output")
    parser.add_argument("--render", action="store_true", help="Render X3D.mp4")
    return parser.parse_args()


def absolute(path: str | Path, root: Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def idx_matches(value: Any, focus: int) -> bool:
    if isinstance(value, (list, tuple)):
        return any(float(item) == float(focus) for item in value)
    return value is not None and float(value) == float(focus)


def validate_pose_json(path: Path, focus: int | None) -> tuple[int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("AlphaPose JSON must be a non-empty list")
    frame_ids = [str(item.get("image_id", "")) if isinstance(item, dict) else "" for item in data]
    invalid = [
        index
        for index, item in enumerate(data)
        if not isinstance(item, dict)
        or len(item.get("keypoints", [])) != 78
        or "image_id" not in item
    ]
    if invalid:
        raise ValueError(
            "Each Halpe-26 record must contain image_id and exactly 78 keypoint values; "
            f"invalid records start at {invalid[:5]}"
        )
    if focus is not None and not any(idx_matches(item.get("idx"), focus) for item in data):
        raise ValueError(f"--focus {focus} was not found in AlphaPose idx values")
    if focus is None and len(frame_ids) != len(set(frame_ids)):
        raise ValueError(
            "Multiple people were detected in at least one frame. "
            "Pass --focus <AlphaPose idx> to select one person."
        )
    return len(data), len(set(frame_ids))


def select_primary_person(path: Path, output_dir: Path) -> tuple[Path, int]:
    """Keep the highest-confidence AlphaPose record in every video frame."""
    data = json.loads(path.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in data:
        grouped.setdefault(str(item["image_id"]), []).append(item)

    selected: list[dict[str, Any]] = []
    ambiguous_frames = 0
    for candidates in grouped.values():
        if len(candidates) > 1:
            ambiguous_frames += 1

        def confidence(candidate: dict[str, Any]) -> float:
            if candidate.get("score") is not None:
                return float(candidate["score"])
            keypoints = candidate["keypoints"]
            return sum(float(keypoints[index]) for index in range(2, len(keypoints), 3)) / 26.0

        selected.append(max(candidates, key=confidence))

    output_dir.mkdir(parents=True, exist_ok=True)
    selected_path = output_dir / "alphapose-primary-person.json"
    selected_path.write_text(json.dumps(selected, ensure_ascii=False), encoding="utf-8")
    return selected_path, ambiguous_frames


def main() -> None:
    opts = parse_args()
    # Keep --help and argument validation usable outside the MotionBERT environment.
    import imageio.v2 as imageio
    import numpy as np
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader

    root = Path(__file__).resolve().parents[1]
    pose_json = absolute(opts.pose_json, root)
    video = absolute(opts.video, root)
    motionbert_dir = absolute(opts.motionbert_dir, root)
    config = absolute(opts.config, root)
    checkpoint_path = absolute(opts.checkpoint, root)
    output_dir = absolute(opts.output_dir, root)

    for name, path in (
        ("pose JSON", pose_json),
        ("video", video),
        ("MotionBERT directory", motionbert_dir),
        ("config", config),
        ("checkpoint", checkpoint_path),
    ):
        if not path.exists():
            raise FileNotFoundError(f"{name} not found: {path}")

    source_pose_json = pose_json
    primary_selection_frames = 0
    if opts.primary_person:
        pose_json, primary_selection_frames = select_primary_person(pose_json, output_dir)
    pose_count, frame_count = validate_pose_json(pose_json, opts.focus)
    dataset_focus: Any = opts.focus
    if opts.focus is not None:
        records = json.loads(pose_json.read_text(encoding="utf-8"))
        if any(isinstance(item.get("idx"), (list, tuple)) for item in records):
            dataset_focus = [float(opts.focus)]
    sys.path.insert(0, str(motionbert_dir))
    from lib.data.dataset_wild import WildDetDataset
    from lib.utils.learning import load_backbone
    from lib.utils.tools import get_config
    from lib.utils.utils_data import flip_data
    from lib.utils.vismo import render_and_save

    config_args = get_config(str(config))
    maxlen = getattr(config_args, "maxlen", None)
    if maxlen is not None and opts.clip_len > int(maxlen):
        raise ValueError(f"--clip-len {opts.clip_len} exceeds model maxlen {maxlen}")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_backbone(config_args)
    checkpoint = torch.load(str(checkpoint_path), map_location="cpu")
    state_dict = checkpoint.get("model_pos", checkpoint) if isinstance(checkpoint, dict) else checkpoint
    if not isinstance(state_dict, dict):
        raise ValueError("MotionBERT checkpoint does not contain a state dictionary")
    # Training with DataParallel stores keys as ``module.<name>`` while the
    # inference model is unwrapped on CPU. Normalize that wrapper prefix.
    if state_dict and all(str(key).startswith("module.") for key in state_dict):
        state_dict = {str(key)[len("module."):]: value for key, value in state_dict.items()}
    model.load_state_dict(state_dict, strict=True)
    model = model.to(device)
    if torch.cuda.is_available():
        model = nn.DataParallel(model)
    model.eval()

    reader = imageio.get_reader(str(video), "ffmpeg")
    meta = reader.get_meta_data()
    fps = float(meta.get("fps") or 25.0)
    video_size = meta.get("size")
    reader.close()
    if opts.pixel and not video_size:
        raise RuntimeError("Could not read video dimensions required by --pixel")

    dataset = WildDetDataset(
        str(pose_json),
        clip_len=opts.clip_len,
        vid_size=video_size if opts.pixel else None,
        scale_range=None if opts.pixel else [1, 1],
        focus=dataset_focus,
    )
    loader = DataLoader(
        dataset,
        batch_size=1,
        shuffle=False,
        num_workers=0,
        pin_memory=torch.cuda.is_available(),
        drop_last=False,
    )

    predictions: list[Any] = []
    with torch.no_grad():
        for batch_input in loader:
            batch_input = batch_input.to(device)
            if getattr(config_args, "no_conf", False):
                batch_input = batch_input[:, :, :, :2]
            if getattr(config_args, "flip", False):
                prediction = model(batch_input)
                prediction_flip = model(flip_data(batch_input))
                prediction = (prediction + flip_data(prediction_flip)) / 2.0
            else:
                prediction = model(batch_input)
            if getattr(config_args, "rootrel", False):
                prediction[:, :, 0, :] = 0
            elif not getattr(config_args, "gt_2d", False):
                prediction[:, 0, 0, 2] = 0
            if getattr(config_args, "gt_2d", False):
                prediction[..., :2] = batch_input[..., :2]
            predictions.append(prediction.detach().cpu().numpy())

    if not predictions:
        raise RuntimeError("MotionBERT produced no prediction")
    pose_3d = np.concatenate(predictions, axis=1)[0]
    render_pose_3d = pose_3d
    if opts.pixel:
        scale = min(video_size) / 2.0
        pose_3d = pose_3d * scale
        pose_3d[:, :, :2] = pose_3d[:, :, :2] + np.asarray(video_size, dtype=np.float32) / 2.0
    output_dir.mkdir(parents=True, exist_ok=True)
    np.save(output_dir / "X3D.npy", pose_3d)
    metadata: dict[str, Any] = {
        "source_pose_json": str(source_pose_json),
        "model_input_pose_json": str(pose_json),
        "source_video": str(video),
        "motionbert_config": str(config),
        "motionbert_checkpoint": str(checkpoint_path),
        "focus": opts.focus,
        "primary_person": opts.primary_person,
        "primary_selection_frames": primary_selection_frames,
        "input_records": pose_count,
        "input_frames": frame_count,
        "output_shape": list(pose_3d.shape),
        "fps": fps,
        "video_size": list(video_size) if video_size else None,
        "input_skeleton": "halpe-26",
        "output_skeleton": "h36m-17",
        "coordinate_system": "pixel-aligned x/y with model-scaled z" if opts.pixel else "MotionBERT normalized coordinates",
        "pixel_mode": opts.pixel,
    }
    (output_dir / "X3D.metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if opts.render:
        render_and_save(render_pose_3d, str(output_dir / "X3D.mp4"), keep_imgs=False, fps=fps)
    print(f"MotionBERT 3D pose: {pose_3d.shape} -> {output_dir / 'X3D.npy'}")
    print(f"Metadata: {output_dir / 'X3D.metadata.json'}")
    if opts.render:
        print(f"Render: {output_dir / 'X3D.mp4'}")


if __name__ == "__main__":
    main()
