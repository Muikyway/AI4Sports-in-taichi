"""Small local character tokenizer backed by a plain vocab.json file."""
from __future__ import annotations

import json
from pathlib import Path


class LocalTokenizer:
    SPECIALS = ["<pad>", "<bos>", "<eos>", "<unk>"]

    def __init__(self, vocab):
        self.vocab = vocab
        self.id_to_token = {value: key for key, value in vocab.items()}
        self.pad_id = vocab["<pad>"]
        self.bos_id = vocab["<bos>"]
        self.eos_id = vocab["<eos>"]
        self.unk_id = vocab["<unk>"]

    @classmethod
    def build(cls, texts):
        chars = sorted({char for text in texts for char in text})
        vocab = {token: index for index, token in enumerate(cls.SPECIALS)}
        vocab.update({char: index for index, char in enumerate(chars, len(vocab)) if char not in vocab})
        return cls(vocab)

    def encode(self, text, add_bos=True, add_eos=True):
        ids = ([self.bos_id] if add_bos else []) + [self.vocab.get(char, self.unk_id) for char in text]
        if add_eos:
            ids.append(self.eos_id)
        return ids

    def decode(self, ids):
        ignored = {self.pad_id, self.bos_id, self.eos_id}
        return "".join(self.id_to_token.get(int(index), "") for index in ids if int(index) not in ignored)

    def save(self, path):
        with Path(path).open("w", encoding="utf-8") as handle:
            json.dump(self.vocab, handle, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path):
        with Path(path).open("r", encoding="utf-8") as handle:
            return cls(json.load(handle))
