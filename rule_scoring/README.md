# Rule Scoring

该目录实现白盒规则评分。正式扣分只由阈值谓词决定，`confidence` 不会直接缩放扣分。

```powershell
python -m rule_scoring --rules rules\rules.yaml --evidence examples\evidence.json --mode strict --output examples\score_strict.json
python -m rule_scoring --rules rules\rules.yaml --evidence examples\evidence.json --mode review --output examples\score_review.json
python -m rule_scoring --rules rules\rules.yaml --evidence examples\evidence.json --mode soft --output examples\score_soft.json
```

- `strict`：规则成立就扣固定分。
- `review`：在测量不确定范围内或置信度过低时标记 `manual_review`。
- `soft`：额外输出透明的 `soft_violation_score`，但不改变正式扣分。
