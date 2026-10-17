"""Pure-PyTorch SFT for a local causal language model."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

import torch
from torch.nn.utils.rnn import pad_sequence

from local_model import load_local_model
from tokenizer import LocalTokenizer


def load_records(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def prompt_text(record):
    return (
        "你是一个严格的裁判规则 DSL 编译器。\n"
        f"任务：{record['instruction']}\n"
        "输入上下文：\n"
        + json.dumps(record["input"], ensure_ascii=False, indent=2)
        + "\n输出要求：只输出一个合法 JSON 对象，不要输出 Markdown 代码块或解释。\n"
        "DSL 输出：\n"
    )


def target_text(record):
    return json.dumps(record["output"], ensure_ascii=False, indent=2) + "\n"


def make_examples(records, tokenizer, max_length):
    examples = []
    for record in records:
        prompt_ids = tokenizer.encode(prompt_text(record), add_bos=True, add_eos=False)
        full_ids = tokenizer.encode(prompt_text(record) + target_text(record), add_bos=True, add_eos=True)[:max_length]
        prompt_len = min(len(prompt_ids), len(full_ids))
        labels = [-100] * prompt_len + full_ids[prompt_len:]
        if not any(value != -100 for value in labels):
            raise ValueError("A record has no target tokens; increase --max-length")
        examples.append((torch.tensor(full_ids), torch.tensor(labels)))
    return examples


def make_batch(examples, indices, pad_id, device):
    input_ids = pad_sequence([examples[i][0] for i in indices], batch_first=True, padding_value=pad_id)
    labels = pad_sequence([examples[i][1] for i in indices], batch_first=True, padding_value=-100)
    return input_ids.to(device), input_ids.ne(pad_id).long().to(device), labels.to(device)


def evaluate(model, examples, args, tokenizer):
    if not examples:
        return float("nan")
    model.eval()
    total = 0.0
    count = 0
    with torch.no_grad():
        for start in range(0, len(examples), args.eval_batch_size):
            indices = list(range(start, min(start + args.eval_batch_size, len(examples))))
            input_ids, mask, labels = make_batch(examples, indices, tokenizer.pad_id, args.device)
            total += float(model(input_ids=input_ids, attention_mask=mask, labels=labels)["loss"]) * len(indices)
            count += len(indices)
    model.train()
    return total / max(count, 1)


def save_checkpoint(model, model_dir, config, tokenizer):
    model_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), model_dir / "model.pt")
    with (model_dir / "config.json").open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
    if hasattr(tokenizer, "save"):
        tokenizer.save(model_dir / "vocab.json")


def load_backend(args):
    if args.backend == "tiny":
        model, config = load_local_model(Path(args.model_dir), args.device)
        tokenizer = LocalTokenizer.load(Path(args.model_dir) / "vocab.json")
        return model, config, tokenizer
    adapter = importlib.import_module(args.adapter_module)
    if not hasattr(adapter, "load"):
        raise SystemExit(f"adapter {args.adapter_module} must expose load(model_dir, device)")
    model, tokenizer, config = adapter.load(Path(args.model_dir), args.device)
    return model, config, tokenizer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--backend", choices=["tiny", "qwen3"], default="tiny")
    parser.add_argument("--adapter-module", default="llm_sft.qwen3_adapter")
    parser.add_argument("--train-file", required=True)
    parser.add_argument("--eval-file")
    parser.add_argument("--output-dir", default="outputs/rule-sft-local")
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--eval-batch-size", type=int, default=2)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    args = parser.parse_args()
    args.device = torch.device("cuda" if args.device == "auto" and torch.cuda.is_available() else args.device if args.device != "auto" else "cpu")
    model, config, tokenizer = load_backend(args)
    train_examples = make_examples(load_records(args.train_file), tokenizer, args.max_length)
    eval_examples = make_examples(load_records(args.eval_file), tokenizer, args.max_length) if args.eval_file else []
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    model.train()
    step = 0
    for epoch in range(args.epochs):
        order = torch.randperm(len(train_examples)).tolist()
        optimizer.zero_grad(set_to_none=True)
        for offset in range(0, len(order), args.batch_size):
            indices = order[offset:offset + args.batch_size]
            input_ids, mask, labels = make_batch(train_examples, indices, tokenizer.pad_id, args.device)
            loss = model(input_ids=input_ids, attention_mask=mask, labels=labels)["loss"]
            (loss / args.gradient_accumulation_steps).backward()
            last_batch = offset + args.batch_size >= len(order)
            if ((offset // args.batch_size) + 1) % args.gradient_accumulation_steps == 0 or last_batch:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                step += 1
                if step % 10 == 0:
                    print(f"epoch={epoch + 1} step={step} train_loss={float(loss):.4f}")
        eval_loss = evaluate(model, eval_examples, args, tokenizer)
        print(f"epoch={epoch + 1} eval_loss={eval_loss:.4f}")
        save_checkpoint(model, Path(args.output_dir), config, tokenizer)


if __name__ == "__main__":
    main()
