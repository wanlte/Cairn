# 人工标注规范（评测集）

## 1. 目的与边界

当前 `eval/labels/` 下的 50/30/30 条标签由 `eval/generate_synthetic_labels.py` 循环生成，属于**合成标签**，只用于验证评测管线与指标计算逻辑，不能对外宣称质量门槛已通过。

本规范用于建设**人工标注集**，回答企业面试时最容易被追问的三个问题：样本从哪来、指标怎么算、结果是否可复核。人工集与合成集分开存放：

- 合成集：`eval/labels/*.jsonl`（保留，用于回归管线）
- 人工集：`eval/labels/human/*.jsonl`（新建，用于正式质量评估）

## 2. 样本来源与去标识

1. 样本从自用导入的真实对话（Markdown / TXT / DeepSeek ZIP）中抽取，覆盖以下场景：技术方案复盘、情绪状态记录、承诺的行动项、模糊/矛盾表达、需要证据支撑的结论。
2. 入库前去除真实姓名、手机号、邮箱、公司名等可识别信息，用占位符替代。
3. 样本分类按场景标注分布，避免全部集中在技术决策一类。

建议规模：抽取 50 条、复盘判断 30 条、检索查询 30 条，与 `docs/EVALUATION.md` 的门槛口径一致。

## 3. 抽取样本标注口径（对应 `extraction`）

每条样本包含一段 user + assistant 对话，`expected` 字段对齐抽取输出 schema：

| 字段 | 标注规则 |
|---|---|
| `events[].what` | 对话中明确发生的决策/行动，必须能在原文找到依据；推断内容不得写入 |
| `events[].domain` | 归属领域（如 backend / auth / rag / api / llm），取系统枚举内的值 |
| `events[].decision` | 采取的方案或结论，一句话概括 |
| `events[].outcome_status` | 结果状态：结论已被事实验证用 CORRECT；证据不足用 UNVERIFIED；错误结论用 WRONG |
| `events[].confidence` | 0–1 之间，标注者对该抽取是否成立的把握，不是模型自评 |
| `knowledge[].concept` | 从对话中沉淀的知识点概念名 |
| `knowledge[].summary` | 知识点一句话摘要 |
| `knowledge[].category` | 概念 / 方法 / 经验 等现有分类 |
| `knowledge[].mastery_hint` | 对话体现的掌握程度（used / learned / weak 等现有枚举） |
| `traits[].trait` | 观察到的行为特质，必须有原文证据支撑 |
| `traits[].polarity` | POSITIVE / NEGATIVE / NEUTRAL |
| `traits[].evidence` | 支撑该特质的原文片段或行为描述 |
| `state` | frustration / curiosity / clarity，取 LOW / MEDIUM / HIGH |

判定原则：
- 字段为空时留空数组或省略，不要为了凑结构补写。
- 同一段对话可拆出多条事件/知识/特质，不只标第一条。
- 原文没有依据的，标 UNVERIFIED，不允许根据上下文脑补。

## 4. 复盘判断标注口径（对应 `review`）

`verdict` 枚举：`CORRECT`（结论与证据一致）、`PARTIAL`（方向对但不完整或表述过度）、`WRONG`（结论与证据矛盾）、`UNVERIFIED`（缺少可核验证据）。

每条复盘判断标注：
- `fragment_key`：对应证据片段的概念或关键词；
- `expected_verdict`：按上述枚举给出的判定；
- `reason`：一句话说明判定依据，便于复核；
- 必要时记录归因：`KNOWLEDGE_GAP` / `VERIFICATION_MISSING` / `ASSUMPTION_WRONG` / `TIME_PRESSURE` / `COMMUNICATION`。

## 5. 检索查询标注口径（对应 `retrieval`）

每条查询标注：
- `query`：用户自然语言问题；
- `expected_concepts`：应当被召回的概念名列表；
- `relevant_fragment_ids`：在已有片段库中与该查询相关的片段 id（供后续片段级命中判断）。

> 现状代码用“概念名字符串是否出现在 Top5 结果里”判断命中，属于弱口径。人工集落地时应优先用 `relevant_fragment_ids` 做片段级命中，避免同义词、改写导致的误判。

## 6. 双人标注与一致性

1. 先由标注者 A 按规范完成全部样本；再选 20 条由标注者 B 独立双标。
2. 计算两套一致率：字段级一致率（抽取）、verdict 一致率（复盘/检索）。
3. 不一致条目对照规范讨论后定标；仍有争议的样本单独列入待澄清，不计入正式集。
4. 个人项目阶段不强制做 Cohen's Kappa，但要在评测报告中写明：双标样本量、一致率、争议处理方式。

## 7. 存储与接入

- 人工集格式与现有 jsonl 一致，UTF-8、每行一条 JSON。
- 建议路径：`eval/labels/human/extraction_50.jsonl`、`retrieval_30.jsonl`、`review_30.jsonl`。
- 评测 API 通过 `dataset` 参数指定数据集；正式报告只引用人工集结果，合成集结果仅用于管线回归。

## 8. 评测代码待修点（Backlog）

1. **检索命中口径**：从子串匹配升级为 `relevant_fragment_ids` 片段级命中，记录 Recall@5 与 MRR。
2. **抽取评测覆盖度**：当前只比对首条事件/知识/特质，需扩展到多碎片、知识点合并与失败记录。
3. **复盘评测冷启动**：一致率依赖库内已有报告，需补一条离线构造样本的评测路径，不依赖线上数据。
4. **结果归档**：每次正式评测导出失败样本明细（sample_id、字段、期望、实际、归因），写入评测报告。
