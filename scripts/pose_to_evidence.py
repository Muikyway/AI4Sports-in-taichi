"""Convert AlphaPose COCO/Halpe JSON into rule-matching kinematic evidence."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rule_scoring.engine import rule_violation, signed_margin


# The first 17 Halpe-26 points use the COCO body ordering.
KP = {
    "LShoulder": 5, "RShoulder": 6, "LElbow": 7, "RElbow": 8,
    "LWrist": 9, "RWrist": 10, "LHip": 11, "RHip": 12,
    "LKnee": 13, "Right_Knee": 14, "LAnkle": 15, "RAnkle": 16,
}


def natural_key(value: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def midpoint(a, b):
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def angle(a, b, c):
    """Angle ABC in degrees."""
    ba = (a[0] - b[0], a[1] - b[1])
    bc = (c[0] - b[0], c[1] - b[1])
    denom = math.hypot(*ba) * math.hypot(*bc)
    if denom <= 1e-9:
        return None
    cosine = max(-1.0, min(1.0, (ba[0] * bc[0] + ba[1] * bc[1]) / denom))
    return math.degrees(math.acos(cosine))


def parse_pose(result: dict[str, Any]) -> dict[int, tuple[float, float, float]]:
    values = result.get("keypoints", [])
    if len(values) % 3:
        raise ValueError("AlphaPose keypoints length must be divisible by 3")
    return {index: (float(values[index * 3]), float(values[index * 3 + 1]), float(values[index * 3 + 2]))
            for index in range(len(values) // 3)}


def point(pose, name, min_conf):
    index = KP[name]
    value = pose.get(index)
    if value is None or value[2] < min_conf:
        return None
    return value[0], value[1]


def body_metrics(result, min_conf):
    pose = parse_pose(result)
    points = {name: point(pose, name, min_conf) for name in KP if name in {"LShoulder", "RShoulder", "LHip", "RHip", "Right_Knee", "LAnkle", "RAnkle", "RWrist"}}
    required = [points.get(name) for name in ("LShoulder", "RShoulder", "LHip", "RHip")]
    if any(value is None for value in required):
        body_height = float(result.get("box", [0, 0, 0, 1])[3] or 1.0)
    else:
        body_height = distance(midpoint(points["LShoulder"], points["RShoulder"]), midpoint(points["LHip"], points["RHip"]))
        if points.get("LAnkle") and points.get("RAnkle"):
            body_height += distance(midpoint(points["LHip"], points["RHip"]), midpoint(points["LAnkle"], points["RAnkle"]))
    body_height = max(body_height, 1e-6)
    metrics = {}
    if all(points.get(name) for name in ("RHip", "Right_Knee", "RAnkle")):
        metrics[("Right_Knee", "joint_angle")] = (angle(points["RHip"], points["Right_Knee"], points["RAnkle"]), min(pose[KP[name]][2] for name in ("RHip", "Right_Knee", "RAnkle")))
    if all(points.get(name) for name in ("LShoulder", "RShoulder", "LHip", "RHip")):
        shoulders = midpoint(points["LShoulder"], points["RShoulder"])
        hips = midpoint(points["LHip"], points["RHip"])
        metrics[("Torso", "torso_tilt")] = (math.degrees(math.atan2(abs(shoulders[0] - hips[0]), abs(shoulders[1] - hips[1]))), min(pose[KP[name]][2] for name in ("LShoulder", "RShoulder", "LHip", "RHip")))
    if points.get("LAnkle") and points.get("RAnkle"):
        metrics[("Feet", "foot_distance_ratio")] = (distance(points["LAnkle"], points["RAnkle"]) / body_height, min(pose[KP[name]][2] for name in ("LAnkle", "RAnkle")))
    if points.get("RWrist") and points.get("LHip") and points.get("RHip"):
        hip_y = midpoint(points["LHip"], points["RHip"])[1]
        metrics[("Right_Wrist", "wrist_height_ratio")] = ((hip_y - points["RWrist"][1]) / body_height, pose[KP["RWrist"]][2])
    return metrics


def select_people(results, track_id=None):
    frames = {}
    for result in results:
        image_id = str(result.get("image_id", ""))
        frames.setdefault(image_id, []).append(result)
    ordered = sorted(frames, key=natural_key)
    selected = []
    for frame_index, image_id in enumerate(ordered):
        people = frames[image_id]
        if track_id is not None:
            tracked = [p for p in people if p.get("idx") == track_id]
            if tracked:
                people = tracked
        selected.append((frame_index, image_id, max(people, key=lambda p: float(p.get("score", 0.0)))))
    return selected


def group_samples(samples):
    groups = []
    for sample in samples:
        if not groups or sample[0] != groups[-1][-1][0] + 1 or sample[3] != groups[-1][-1][3]:
            groups.append([sample])
        else:
            groups[-1].append(sample)
    return groups


def convert(rules_doc, pose_json, action, phase, phase_start, phase_end, min_conf, track_id):
    results = json.loads(Path(pose_json).read_text(encoding="utf-8"))
    if not isinstance(results, list):
        raise ValueError("AlphaPose JSON must be a list in COCO format")
    selected = select_people(results, track_id)
    requested = {(rule["predicate"].get("body_part"), rule["predicate"].get("metric")): rule
                 for rule in rules_doc.get("rules", []) if rule.get("enabled", True)}
    samples = {key: [] for key in requested}
    for frame_index, _image_id, result in selected:
        if phase_start is not None and frame_index < phase_start:
            continue
        if phase_end is not None and frame_index > phase_end:
            continue
        confidence = float(result.get("score", 1.0))
        for key, value_conf in body_metrics(result, min_conf).items():
            if value_conf[0] is not None and key in samples:
                value, kp_conf = value_conf
                rule = requested[key]
                violating = rule_violation(float(value), rule["predicate"])
                samples[key].append((frame_index, float(value), min(confidence, float(kp_conf)), violating))
    facts = []
    for key, values in samples.items():
        rule = requested[key]
        for group in group_samples(values):
            # Choose the most severe frame within this contiguous segment.
            chosen = max(group, key=lambda item: signed_margin(item[1], rule["predicate"]))
            facts.append({
                "frame_range": [group[0][0], group[-1][0]], "duration_frames": len(group),
                "phase": phase or rule.get("phase"), "body_part": key[0], "metric": key[1],
                "value": chosen[1], "unit": rule["predicate"].get("unit"),
                "confidence": round(sum(item[2] for item in group) / len(group), 6),
                "source": "alphapose-json",
            })
    duration = (phase_end - phase_start + 1) if phase_start is not None and phase_end is not None else None
    if duration is not None:
        facts.append({"frame_range": [phase_start, phase_end], "duration_frames": duration, "phase": phase, "body_part": "Phase", "metric": "phase_duration", "value": duration, "unit": "frame", "confidence": 1.0, "source": "phase-boundary-cli"})
    return {"performance_id": Path(pose_json).stem, "action": action, "facts": facts, "metadata": {"pose_json": str(pose_json), "frame_count": len(selected), "phase": phase, "phase_range": [phase_start, phase_end]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pose-json", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--action", default="野马分鬃")
    parser.add_argument("--phase", default="第二阶段")
    parser.add_argument("--phase-start", type=int)
    parser.add_argument("--phase-end", type=int)
    parser.add_argument("--min-keypoint-confidence", type=float, default=0.20)
    parser.add_argument("--track-id", type=int)
    args = parser.parse_args()
    rules_doc = yaml.safe_load(Path(args.rules).read_text(encoding="utf-8"))
    evidence = convert(rules_doc, args.pose_json, args.action, args.phase, args.phase_start, args.phase_end, args.min_keypoint_confidence, args.track_id)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(evidence['facts'])} evidence facts -> {args.output}")


if __name__ == "__main__":
    main()
