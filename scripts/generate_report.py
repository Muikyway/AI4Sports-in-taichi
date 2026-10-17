"""Generate an evidence-grounded Markdown referee report from score JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def status_text(item):
    return {"violation": "违规", "pass": "通过", "manual_review": "待人工复核", "no_evidence": "缺少证据"}.get(item.get("status"), item.get("status", "未知"))


def recommendation(item):
    if item.get("status") == "no_evidence":
        return "补充该规则要求的运动学证据后再判定。"
    if item.get("review_required"):
        return "复核对应帧、关键点可见性和测量误差，再确认是否扣分。"
    if item.get("violation"):
        return "针对该时间段的动作进行专项纠正。"
    return "当前证据满足该规则，不需要专项扣分建议。"


def generate(score):
    items = score.get("items", [])
    review_items = [item for item in items if item.get("review_required")]
    confirmed = [item for item in items if item.get("violation") and not item.get("review_required")]
    lines = [
        f"# {score.get('rubric', {}).get('name', '动作评估报告')}",
        "",
        "> 本报告由版本化白盒规则和运动学证据生成；规则名称和阈值仅适用于本次测试配置。",
        "",
        "## 1. 总结",
        "",
        f"- Performance ID：`{score.get('performance_id')}`",
        f"- 评分模式：`{score.get('mode')}`",
        f"- 基础分：{score.get('base_score'):.2f}",
        f"- 暂定扣分：{score.get('total_deduction'):.2f}",
        f"- 暂定得分：{score.get('final_score'):.2f}",
        f"- 已确认违规：{len(confirmed)} 条",
        f"- 待人工复核：{len(review_items)} 条",
        "",
        "> 若存在待复核项，暂定得分不能直接作为最终裁判成绩。",
        "",
        "## 2. 逐规则判定",
        "",
        "| 规则 | 状态 | 实际值 | 证据帧 | 扣分 | 复核 |",
        "|---|---|---:|---|---:|---|",
    ]
    for item in items:
        evidence = item.get("evidence", {})
        lines.append(
            f"| `{item.get('rule_id')}` {item.get('rule_name', '')} | {status_text(item)} | "
            f"{evidence.get('value', '—')} {evidence.get('unit', '')} | "
            f"{evidence.get('frame_range', '—')} | {float(item.get('deduction', 0.0)):.2f} | "
            f"{'是' if item.get('review_required') else '否'} |"
        )
    lines.extend(["", "## 3. 证据与建议", ""])
    for index, item in enumerate(items, 1):
        evidence = item.get("evidence", {})
        lines.extend([
            f"### {index}. `{item.get('rule_id')}` {item.get('rule_name', '')}",
            "",
            f"- 判定：{status_text(item)}；规则违规值：`{item.get('violation')}`。",
            f"- 证据：第 `{evidence.get('frame_range')}` 帧，部位 `{evidence.get('body_part')}`，指标 `{evidence.get('metric')}`，实际值 `{evidence.get('value')} {evidence.get('unit', '')}`。",
            f"- 测量置信度：`{evidence.get('confidence')}`；来源：`{evidence.get('source')}`。",
            f"- 建议：{recommendation(item)}",
            "",
        ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    score = json.loads(Path(args.score).read_text(encoding="utf-8"))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(generate(score), encoding="utf-8")
    print(f"report written to {args.output}")


if __name__ == "__main__":
    main()
