"""Adapter contract for a locally implemented Qwen3-8B model.

This file deliberately does not import transformers, model hubs, GGUF runtimes,
or any Qwen checkpoint loader. A native Qwen3 implementation must be supplied
locally and expose the two functions imported below.
"""
from __future__ import annotations

from pathlib import Path


def load(model_dir: Path, device):
    """Return ``(model, tokenizer, config)`` for a local Qwen3 checkpoint.

    ``model`` must be a torch.nn.Module with
    ``forward(input_ids, attention_mask=None, labels=None)`` returning a dict
    with ``loss`` and ``logits``. ``tokenizer`` must expose ``encode(text,
    add_bos=True, add_eos=True)``, ``pad_id`` and optionally ``save(path)``.

    Replace the imports below with your local Qwen3 implementation. GGUF and
    Ollama files are inference formats and are not accepted by this trainer.
    """
    try:
        from qwen3_native import load_model, load_tokenizer
    except ImportError as exc:
        raise RuntimeError(
            "No local qwen3_native adapter found. Provide a local Qwen3 implementation "
            "with load_model(model_dir, device) and load_tokenizer(model_dir)."
        ) from exc
    model = load_model(model_dir, device)
    tokenizer = load_tokenizer(model_dir)
    config = {"architecture": "Qwen3-8B", "source": str(model_dir)}
    return model, tokenizer, config
