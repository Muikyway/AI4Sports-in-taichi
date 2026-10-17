import argparse
import json

from .io import score_files


def main() -> None:
    parser = argparse.ArgumentParser(description="White-box rule scoring")
    parser.add_argument("--rules", default="rules/rules.yaml")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", default="score_result.json")
    parser.add_argument("--mode", choices=["strict", "review", "soft"], default="strict")
    args = parser.parse_args()
    result = score_files(args.rules, args.evidence, args.output, args.mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
