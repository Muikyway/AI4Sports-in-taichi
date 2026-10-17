"""File loading and command-line support for rule scoring."""
import json
from pathlib import Path
from typing import Any

import yaml

from .engine import score_performance


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def score_files(rules_path: str | Path, evidence_path: str | Path, output_path: str | Path, mode: str = "strict") -> dict[str, Any]:
    result = score_performance(load_yaml(rules_path), load_json(evidence_path), mode=mode)
    write_json(output_path, result)
    return result
