"""Local-path Qwen3 SFT. Downloads are disabled during training."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import torch
from torch.nn.utils.rnn import pad_sequence
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments


def load_records(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def render_prompt(tokenizer, record, template_mode):
    instruction = (
        "你是严格的裁判规则 DSL 编译器。将用户规则转换为合法 JSON。"
        "只能使用上下文给出的指标、部位和阶段；无法测量时返回 unsupported。"
    )
    user = json.dumps({"instruction": record["instruction"], "input": record["input"]}, ensure_ascii=False, indent=2)
    if template_mode == "auto" and getattr(tokenizer, "chat_template", None):
        messages = [{"role": "system", "content": instruction}, {"role": "user", "content": user}]
        try:
            return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return f"系统：{instruction}\n用户：{user}\n助手："


class RuleDataset(torch.utils.data.Dataset):
    def __init__(self, records, tokenizer, max_length, template_mode):
        self.items = []
        for record in records:
            prompt = render_prompt(tokenizer, record, template_mode)
            target = json.dumps(record["output"], ensure_ascii=False, indent=2) + "\n"
            prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
            full_ids = tokenizer(prompt + target, add_special_tokens=False)["input_ids"]
            if tokenizer.eos_token_id is not None:
                full_ids.append(tokenizer.eos_token_id)
            full_ids = full_ids[:max_length]
            prompt_len = min(len(prompt_ids), len(full_ids))
            labels = [-100] * prompt_len + full_ids[prompt_len:]
            if not any(value != -100 for value in labels):
                raise ValueError("Target was truncated; increase --max-length")
            self.items.append((torch.tensor(full_ids), torch.tensor(labels)))

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        input_ids, labels = self.items[index]
        return {"input_ids": input_ids, "labels": labels}


class Collator:
    def __init__(self, pad_id):
        self.pad_id = pad_id

    def __call__(self, features):
        input_ids = pad_sequence([x["input_ids"] for x in features], batch_first=True, padding_value=self.pad_id)
        labels = pad_sequence([x["labels"] for x in features], batch_first=True, padding_value=-100)
        return {"input_ids": input_ids, "labels": labels, "attention_mask": input_ids.ne(self.pad_id).long()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, help="local ModelScope snapshot directory")
    parser.add_argument("--train-file", required=True)
    parser.add_argument("--eval-file")
    parser.add_argument("--output-dir", default="outputs/qwen3-rule-sft")
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--eval-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--template-mode", choices=["auto", "plain"], default="auto")
    parser.add_argument("--bf16", action="store_true")
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--full-finetune", action="store_true")
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--local-files-only", action="store_true", default=True)
    args = parser.parse_args()
    if args.bf16 and args.fp16:
        raise SystemExit("Use only one of --bf16 and --fp16")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    model_dir = str(Path(args.model_dir).resolve())
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True, trust_remote_code=True, use_fast=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    dtype = torch.bfloat16 if args.bf16 else torch.float16 if args.fp16 else torch.float32
    model = AutoModelForCausalLM.from_pretrained(model_dir, local_files_only=True, trust_remote_code=True, torch_dtype=dtype)
    if not args.full_finetune:
        try:
            from peft import LoraConfig, TaskType, get_peft_model
        except ImportError as exc:
            raise SystemExit("LoRA requires peft; use --full-finetune or install requirements-qwen3.txt") from exc
        model = get_peft_model(model, LoraConfig(r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=args.lora_dropout, target_modules=["q_proj", "k_proj", "v_proj", "o_proj"], task_type=TaskType.CAUSAL_LM))
        model.print_trainable_parameters()
    train_set = RuleDataset(load_records(args.train_file), tokenizer, args.max_length, args.template_mode)
    eval_set = RuleDataset(load_records(args.eval_file), tokenizer, args.max_length, args.template_mode) if args.eval_file else None
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.eval_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        logging_steps=5,
        save_strategy="epoch",
        eval_strategy="epoch" if eval_set else "no",
        bf16=args.bf16,
        fp16=args.fp16,
        report_to="none",
        remove_unused_columns=False,
        load_best_model_at_end=bool(eval_set),
    )
    trainer = Trainer(model=model, args=training_args, train_dataset=train_set, eval_dataset=eval_set, data_collator=Collator(tokenizer.pad_token_id))
    trainer.train()
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)


if __name__ == "__main__":
    main()
