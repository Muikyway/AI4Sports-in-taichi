"""Initialize a local TinyCausalLM checkpoint without any model hub API."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from local_model import TinyCausalLM


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vocab", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--hidden-size", type=int, default=256)
    parser.add_argument("--layers", type=int, default=4)
    parser.add_argument("--heads", type=int, default=8)
    parser.add_argument("--dropout", type=float, default=0.1)
    args = parser.parse_args()
    with Path(args.vocab).open("r", encoding="utf-8") as handle:
        vocab_size = len(json.load(handle))
    config = {"vocab_size": vocab_size, "max_length": args.max_length, "hidden_size": args.hidden_size, "layers": args.layers, "heads": args.heads, "dropout": args.dropout}
    model = TinyCausalLM(**config)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), output / "model.pt")
    with (output / "config.json").open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
    (output / "vocab.json").write_text(Path(args.vocab).read_text(encoding="utf-8"), encoding="utf-8")
    print(f"initialized local model -> {output}")


if __name__ == "__main__":
    main()
