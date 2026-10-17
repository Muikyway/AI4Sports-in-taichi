"""Run AlphaPose on a video, convert skeletons to evidence, score rules, and report."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pose_to_evidence import convert
from rule_scoring.io import write_json
from rule_scoring.engine import score_performance
from generate_report import generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True)
    parser.add_argument("--rules", default="rules/yema_fenzong_test.yaml")
    parser.add_argument("--workdir", default="outputs/video-eval")
    parser.add_argument("--action", default="野马分鬃")
    parser.add_argument("--phase", default="第二阶段")
    parser.add_argument("--phase-start", type=int)
    parser.add_argument("--phase-end", type=int)
    parser.add_argument("--mode", choices=["strict", "review", "soft"], default="strict")
    parser.add_argument("--track-id", type=int)
    parser.add_argument("--min-keypoint-confidence", type=float, default=0.20)
    parser.add_argument("--alphapose-dir", default="AlphaPose")
    parser.add_argument("--checkpoint", default="AlphaPose/pretrained_models/halpe26_fast_res50_256x192.pth")
    parser.add_argument("--config", default="AlphaPose/configs/halpe_26/resnet/256x192_res50_lr1e-3_1x.yaml")
    parser.add_argument("--skip-pose", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    workdir = Path(args.workdir)
    if not workdir.is_absolute():
        workdir = root / workdir
    workdir.mkdir(parents=True, exist_ok=True)
    pose_json = workdir / "alphapose-results.json"
    if not args.skip_pose:
        alpha_dir = Path(args.alphapose_dir)
        if not alpha_dir.is_absolute():
            alpha_dir = root / alpha_dir
        cmd = [sys.executable, "scripts/demo_inference.py", "--sp", "--gpus", "-1", "--cfg", str(Path(args.config).resolve()), "--checkpoint", str(Path(args.checkpoint).resolve()), "--video", str(Path(args.video).resolve()), "--outdir", str(workdir), "--detector", "yolo"]
        print("Running AlphaPose:", " ".join(cmd))
        subprocess.run(cmd, cwd=alpha_dir, check=True)
        produced = workdir / "alphapose-results.json"
        if not produced.exists():
            raise FileNotFoundError(f"AlphaPose did not produce {produced}")
    if not pose_json.exists():
        raise FileNotFoundError(f"Pose JSON not found: {pose_json}; remove --skip-pose")
    rules_doc = yaml.safe_load(Path(args.rules).read_text(encoding="utf-8"))
    evidence = convert(rules_doc, pose_json, args.action, args.phase, args.phase_start, args.phase_end, args.min_keypoint_confidence, args.track_id)
    evidence_path = workdir / "evidence.json"
    write_json(evidence_path, evidence)
    score = score_performance(rules_doc, evidence, mode=args.mode)
    score_path = workdir / "score.json"
    write_json(score_path, score)
    report_path = workdir / "report.md"
    report_path.write_text(generate(score), encoding="utf-8")
    print(f"Evidence: {evidence_path}")
    print(f"Score: {score_path} (final_score={score['final_score']:.3f})")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
