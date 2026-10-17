"""A compact causal Transformer checkpoint format implemented with PyTorch."""
from __future__ import annotations

import json
from pathlib import Path

import torch
from torch import nn


class TinyCausalLM(nn.Module):
    def __init__(self, vocab_size, max_length=512, hidden_size=256, layers=4, heads=8, dropout=0.1):
        super().__init__()
        self.max_length = max_length
        self.token_embedding = nn.Embedding(vocab_size, hidden_size)
        self.position_embedding = nn.Embedding(max_length, hidden_size)
        layer = nn.TransformerEncoderLayer(hidden_size, heads, hidden_size * 4, dropout, activation="gelu", batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, layers)
        self.norm = nn.LayerNorm(hidden_size)
        self.lm_head = nn.Linear(hidden_size, vocab_size, bias=False)
        self.lm_head.weight = self.token_embedding.weight

    def forward(self, input_ids, attention_mask=None, labels=None):
        _, length = input_ids.shape
        if length > self.max_length:
            raise ValueError(f"sequence length {length} exceeds model max_length {self.max_length}")
        positions = torch.arange(length, device=input_ids.device).unsqueeze(0)
        hidden = self.token_embedding(input_ids) + self.position_embedding(positions)
        causal_mask = torch.triu(torch.ones(length, length, device=input_ids.device, dtype=torch.bool), diagonal=1)
        padding_mask = attention_mask.eq(0) if attention_mask is not None else None
        hidden = self.encoder(hidden, mask=causal_mask, src_key_padding_mask=padding_mask)
        logits = self.lm_head(self.norm(hidden))
        result = {"logits": logits}
        if labels is not None:
            result["loss"] = nn.functional.cross_entropy(logits.reshape(-1, logits.size(-1)), labels.reshape(-1), ignore_index=-100)
        return result

    @torch.no_grad()
    def generate(self, input_ids, max_new_tokens, eos_id):
        self.eval()
        for _ in range(max_new_tokens):
            context = input_ids[:, -self.max_length:]
            logits = self(input_ids=context)["logits"][:, -1]
            next_token = logits.argmax(dim=-1, keepdim=True)
            input_ids = torch.cat([input_ids, next_token], dim=1)
            if bool((next_token == eos_id).all()):
                break
        return input_ids


def load_local_model(model_dir: Path, device):
    with (model_dir / "config.json").open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    model = TinyCausalLM(**config)
    state = torch.load(model_dir / "model.pt", map_location=device, weights_only=True)
    model.load_state_dict(state)
    return model.to(device), config
