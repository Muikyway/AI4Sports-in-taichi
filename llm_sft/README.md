# 本地 PyTorch SFT

本目录的 Qwen3 训练流程不通过 Hugging Face 下载模型或数据：模型先从 ModelScope 下载，训练时仅从本地路径读取。纯 PyTorch `TinyCausalLM` 后端完全不依赖 Transformers；Qwen3-8B 入口使用 Transformers 的模型实现，但通过 `local_files_only=True` 和离线环境变量阻止远程访问。

## Qwen3-8B 说明

Qwen3-8B 可以作为 SFT 基础模型。你的限制是下载阶段不使用 Hugging Face，因此推荐先从 ModelScope 下载完整快照，再在训练时通过本地路径加载。训练脚本使用 Transformers 的本地加载能力，但设置了 `local_files_only=True` 和离线环境变量，不会联网下载。

官方 ModelScope 模型：`Qwen/Qwen3-8B-Base`。如果希望保留更强的指令跟随能力，也可以使用对应的 Instruct 版本。8B 全参数微调显存开销较大，第一版建议 LoRA。

不要使用 GGUF/Ollama 文件做 SFT；它们主要是推理格式。需要使用 ModelScope snapshot 中的配置、tokenizer 和原始权重文件。

如果还要求训练阶段也完全不使用 Transformers，则需要准备本地 Qwen3 原生实现，并在 `qwen3_adapter.py` 中接入。通常不建议第一版这样做。

```python
model = load_model(model_dir, device)
tokenizer = load_tokenizer(model_dir)
```

其中模型必须实现：

```python
model(input_ids, attention_mask=None, labels=None)
# 返回 {"loss": loss, "logits": logits}
```

tokenizer 必须实现：

```python
tokenizer.encode(text, add_bos=True, add_eos=True)
tokenizer.pad_id
```

当前 `qwen3_adapter.py` 是完全无 Transformers 的备选接口；正常 Qwen3 SFT 使用下面的 `train_qwen3_sft.py`。

## Qwen3-8B 下载与 SFT

安装下载和训练依赖：

```powershell
pip install -r llm_sft\requirements-qwen3.txt
```

从 ModelScope 下载到本地：

```powershell
python llm_sft\download_qwen3_model.py `
  --model Qwen/Qwen3-8B-Base `
  --local-dir D:\models\Qwen3-8B-Base
```

只使用本地模型训练：

```powershell
python llm_sft\train_qwen3_sft.py `
  --model-dir D:\models\Qwen3-8B-Base `
  --train-file llm_sft\data\train.jsonl `
  --eval-file llm_sft\data\valid.jsonl `
  --output-dir outputs\qwen3-rule-sft `
  --epochs 2 `
  --batch-size 1 `
  --gradient-accumulation-steps 16 `
  --max-length 2048 `
  --bf16
```

如果显卡不支持 BF16，可将 `--bf16` 换成 `--fp16`。正式训练时，训练数据必须扩充到人工审核的规则-DSL 数据集，当前仓库中的 3 条样例只用于验证代码链路。

## 本地模型目录格式

```text
local_model/
  config.json   # vocab_size, max_length, hidden_size, layers, heads, dropout
  vocab.json    # 本地 tokenizer 词表
  model.pt      # torch.save(model.state_dict())
```

当前提供的 `TinyCausalLM` 是纯 PyTorch 小型因果 Transformer，用于验证 SFT 闭环；它不是生产级大语言模型。已有本地大模型需要实现相同的 `forward(input_ids, attention_mask, labels)` 接口，并导出匹配的本地 tokenizer。

## 1. 构建本地词表

```powershell
cd D:\program\test
python llm_sft\build_tokenizer.py `
  --files llm_sft\data\train.jsonl llm_sft\data\valid.jsonl `
  --output llm_sft\data\vocab.json
```

## 2. 初始化本地模型

```powershell
python llm_sft\init_local_model.py `
  --vocab llm_sft\data\vocab.json `
  --output-dir llm_sft\base_model `
  --max-length 512 `
  --hidden-size 256 `
  --layers 4 `
  --heads 8
```

这一步初始化的是用于跑通代码的小模型。如果你已经有本地预训练模型，应直接将其适配为上述本地目录格式，不要使用模型仓库 API。

## 3. 执行本地 SFT

```powershell
python llm_sft\train_sft.py `
  --model-dir llm_sft\base_model `
  --train-file llm_sft\data\train.jsonl `
  --eval-file llm_sft\data\valid.jsonl `
  --output-dir outputs\rule-sft-local `
  --epochs 3 `
  --max-length 512 `
  --device cpu
```

接入本地 Qwen3 适配器后使用：

```powershell
python llm_sft\train_sft.py `
  --backend qwen3 `
  --model-dir D:\models\Qwen3-8B `
  --train-file llm_sft\data\train.jsonl `
  --eval-file llm_sft\data\valid.jsonl `
  --output-dir outputs\qwen3-rule-sft `
  --epochs 2 `
  --batch-size 1 `
  --gradient-accumulation-steps 16 `
  --max-length 2048 `
  --device cuda
```

## 4. 本地推理

```powershell
python llm_sft\infer_sft.py `
  --model-dir outputs\rule-sft-local `
  --input llm_sft\data\inference_example.json `
  --device cpu
```

输出必须继续经过 DSL Schema 和白盒评分器校验，生成 JSON 不等于规则正确。
