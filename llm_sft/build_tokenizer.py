"""Build the local character vocabulary from SFT JSONL files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from train_sft import prompt_text, target_text
from tokenizer import LocalTokenizer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    texts = []
    for filename in args.files:
        with Path(filename).open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    texts.extend([prompt_text(record), target_text(record)])
    tokenizer = LocalTokenizer.build(texts)
    tokenizer.save(args.output)
    print(f"saved {len(tokenizer.vocab)} tokens -> {args.output}")


if __name__ == "__main__":
    main()
