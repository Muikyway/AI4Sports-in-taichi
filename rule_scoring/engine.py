"""Deterministic rule evaluation with optional uncertainty reporting."""
from __future__ import annotations

import math
from typing import Any


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, value))))


def rule_violation(value: float, predicate: dict[str, Any]) -> bool:
    operator = predicate["operator"]
    if operator == ">":
        return value > float(predicate["threshold"])
    if operator == ">=":
        return value >= float(predicate["threshold"])
    if operator == "<":
        return value < float(predicate["threshold"])
    if operator == "<=":
        return value <= float(predicate["threshold"])
    if operator == "between":
        lower, upper = predicate["range"]
        return not (float(lower) <= value <= float(upper))
    raise ValueError(f"Unsupported operator: {operator}")


def signed_margin(value: float, predicate: dict[str, Any]) -> float:
    operator = predicate["operator"]
    threshold = float(predicate.get("threshold", 0.0))
    if operator in (">", ">="):
        return value - threshold
    if operator in ("<", "<="):
        return threshold - value
    lower, upper = predicate["range"]
    return max(float(lower) - value, value - float(upper))


def soft_violation_score(value: float, predicate: dict[str, Any], confidence: float) -> float:
    """Return a transparent research score; it never determines strict deduction."""
    tolerance = max(float(predicate.get("tolerance", 1.0)), 1e-6)
    return max(0.0, min(1.0, sigmoid(signed_margin(value, predicate) / tolerance) * confidence))


def review_required(value: float, predicate: dict[str, Any], confidence: float) -> bool:
    uncertainty = float(predicate.get("uncertainty", predicate.get("tolerance", 0.0)))
    margin = abs(signed_margin(value, predicate))
    min_confidence = float(predicate.get("min_confidence", 0.0))
    return margin <= uncertainty or confidence < min_confidence


def _evidence_view(fact: dict[str, Any]) -> dict[str, Any]:
    return {
        "frame_range": fact["frame_range"],
        "phase": fact.get("phase"),
        "body_part": fact["body_part"],
        "metric": fact["metric"],
        "value": fact["value"],
        "unit": fact.get("unit"),
        "confidence": fact.get("confidence"),
        "source": fact.get("source"),
    }


def score_performance(rules_doc: dict[str, Any], evidence_doc: dict[str, Any], mode: str = "strict") -> dict[str, Any]:
    """Score evidence in strict, review, or soft mode.

    Strict and review modes deduct only the fixed penalty when the predicate is
    true. Soft mode still reports the strict result and adds a research score;
    it does not turn a partial score into a deduction.
    """
    if mode not in {"strict", "review", "soft"}:
        raise ValueError("mode must be strict, review, or soft")
    rubric = rules_doc["rubric"]
    action = evidence_doc.get("action")
    facts = evidence_doc.get("facts", [])
    items: list[dict[str, Any]] = []
    total_deduction = 0.0

    for rule in rules_doc.get("rules", []):
        if not rule.get("enabled", True) or rule.get("action") not in (None, action):
            continue
        predicate = rule["predicate"]
        candidates = [fact for fact in facts
                      if fact.get("phase") == rule.get("phase")
                      and fact.get("body_part") == predicate.get("body_part")
                      and fact.get("metric") == predicate.get("metric")]
        if not candidates:
            items.append({"rule_id": rule["id"], "status": "no_evidence", "deduction": 0.0})
            continue

        evaluated = []
        for fact in candidates:
            value = float(fact["value"])
            confidence = float(fact.get("confidence", 1.0))
            span = int(fact.get("duration_frames", fact["frame_range"][1] - fact["frame_range"][0] + 1))
            required_span = int(predicate.get("duration_frames", 1))
            predicate_violation = rule_violation(value, predicate) and span >= required_span
            evaluated.append({
                "fact": fact,
                "violation": predicate_violation,
                "soft_score": soft_violation_score(value, predicate, confidence),
                "review": review_required(value, predicate, confidence),
            })
        selected = max(evaluated, key=lambda result: (result["violation"], result["soft_score"]))
        fact = selected["fact"]
        violation = selected["violation"]
        deduction = float(rule["penalty"]["max_points"]) if violation else 0.0
        total_deduction += deduction
        status = "violation" if violation else "pass"
        if mode == "review" and selected["review"]:
            status = "manual_review"
        item = {
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "status": status,
            "violation": violation,
            "deduction": deduction,
            "review_required": selected["review"],
            "evidence": _evidence_view(fact),
        }
        if mode == "soft":
            item["soft_violation_score"] = round(selected["soft_score"], 6)
        items.append(item)

    base = float(rubric["base_score"])
    return {
        "performance_id": evidence_doc.get("performance_id"),
        "rubric": rubric,
        "mode": mode,
        "base_score": base,
        "total_deduction": round(total_deduction, 6),
        "final_score": round(max(0.0, base - total_deduction), 6),
        "items": items,
    }
