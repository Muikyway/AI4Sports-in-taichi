"""Run a local PyTorch rule-conversion checkpoint."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from local_model import load_local_model
from tokenizer import LocalTokenizer
from train_sft import prompt_text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    args = parser.parse_args()
    device = torch.device("cuda" if args.device == "auto" and torch.cuda.is_available() else args.device if args.device != "auto" else "cpu")
    model, _ = load_local_model(Path(args.model_dir), device)
    tokenizer = LocalTokenizer.load(Path(args.model_dir) / "vocab.json")
    record = json.loads(Path(args.input).read_text(encoding="utf-8"))
    input_ids = torch.tensor([tokenizer.encode(prompt_text(record), add_bos=True, add_eos=False)], device=device)
    generated = model.generate(input_ids, args.max_new_tokens, tokenizer.eos_id)[0].tolist()
    output = tokenizer.decode(generated[input_ids.shape[1]:])
    print(output)


if __name__ == "__main__":
    main()
