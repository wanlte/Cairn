# 评测说明

## 指标与门槛

| 指标 | 数据集 | 门槛 | 计算方式 |
|---|---|---|---|
| 抽取字段准确率 | `eval/labels/extraction_50.jsonl` | ≥ 80% | 逐字段精确匹配；置信度容差 ±0.1 |
| 复盘一致率 | `eval/labels/review_30.jsonl` | ≥ 70% | 模型中判断与标签 verdict 一致比例 |
| 检索 Recall@5 | `eval/labels/retrieval_30.jsonl` | ≥ 75% | Top 5 命中期望概念的查询比例 |

真实对话标注集（samples 来源，AI 辅助标注，`synthetic=False`）：`eval/labels/human/extraction_50.jsonl`、`human/review_30.jsonl`、`human/retrieval_30.jsonl`。由 `eval/build_human_labels.py` 从 `samples/` 复现构建；首轮真实运行结果见 `docs/EVAL_REPORT.md`。

门槛可通过 `.env` 调整：

```text
EVAL_EXTRACTION_ACCURACY_THRESHOLD=0.8
EVAL_REVIEW_CONSISTENCY_THRESHOLD=0.7
EVAL_RETRIEVAL_RECALL_THRESHOLD=0.75
```

## API

```text
GET  /api/v1/evaluation/datasets
POST /api/v1/evaluation/extraction
POST /api/v1/evaluation/review
POST /api/v1/evaluation/retrieval
```

请求体支持 `provider`、`credential_id`、`model`、`limit`、`offset`、`dataset`。

## 重要说明

当前 `eval/labels/` 中的 50/30/30 条标签均由 `eval/generate_synthetic_labels.py` 生成，属于**合成标签**，用于验证评测管线与指标计算逻辑。

它们**不是人工标注集**，不能用于宣称 PRD 中的质量门槛已通过。正式验收需要：

1. 由人工标注 50 条抽取样本、30 条复盘判断、30 条检索查询
2. 用真实 provider 跑完整评测
3. 将结果记录到 `docs/EVALUATION.md` 或单独的评测报告
4. 未达标时回写 prompt/模型配置并重跑

合成标签可通过以下命令重建：

```bash
.venv/Scripts/python.exe eval/generate_synthetic_labels.py
```
