"""Validate and normalize JSONL records used by the rule-conversion SFT."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_INPUT = {"action", "rule_text", "available_metrics", "available_body_parts", "available_phases"}


def validate_record(record: dict[str, Any], line_no: int) -> None:
    for field in ("instruction", "input", "output"):
        if field not in record:
            raise ValueError(f"line {line_no}: missing {field}")
    if not isinstance(record["instruction"], str) or not record["instruction"].strip():
        raise ValueError(f"line {line_no}: instruction must be non-empty")
    input_obj = record["input"]
    if not isinstance(input_obj, dict) or not REQUIRED_INPUT.issubset(input_obj):
        missing = REQUIRED_INPUT - set(input_obj or {})
        raise ValueError(f"line {line_no}: missing input fields {sorted(missing)}")
    if not isinstance(record["output"], dict):
        raise ValueError(f"line {line_no}: output must be an object")
    output = record["output"]
    if output.get("status") != "unsupported":
        predicate = output.get("predicate", {})
        required = {"phase", "predicate", "penalty", "evidence"}
        missing = required - set(output)
        if missing or not {"metric", "body_part", "operator", "threshold", "unit"}.issubset(predicate):
            raise ValueError(f"line {line_no}: invalid DSL output; missing {sorted(missing)}")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            validate_record(record, line_no)
            records.append(record)
    if not records:
        raise ValueError(f"no records found in {path}")
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="source JSONL")
    parser.add_argument("--output", required=True, help="normalized JSONL")
    args = parser.parse_args()
    records = read_jsonl(Path(args.input))
    write_jsonl(Path(args.output), records)
    print(f"validated {len(records)} records -> {args.output}")


if __name__ == "__main__":
    main()
