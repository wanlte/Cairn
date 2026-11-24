# 评测报告

> 本报告只记录人工标注集 + 真实 Provider 跑出的结果。合成标签集仅用于验证评测管线，结果不写入本报告结论。

## 1. 评测元信息

| 项目 | 记录 |
|---|---|
| 评测日期 | 2026-11-24 |
| Provider / 模型 | DeepSeek / `deepseek-chat`（`.env` 真实 Key，非 mock） |
| 抽取数据集 | `eval/labels/human/extraction_50.jsonl`（50 条真实 turn pair） |
| 复盘数据集 | `eval/labels/human/review_30.jsonl`（30 条判断标注） |
| 检索数据集 | `eval/labels/human/retrieval_30.jsonl`（30 条查询） |
| 标注人 / 双标人 | 豆包 AI 辅助标注（逐条阅读原文）；**未做人工双标** |
| 标注一致性 | 未测（无第二标注人）；正式对外结论前需按 `EVAL_LABELING_GUIDE.md` 补双标 |

### 1.1 数据来源与构建方式

- 素材：`samples/deepseek_data-2026-11-23.zip`（DeepSeek 官方导出，814 会话 / 4117 组 turn pair）与 `samples/选择真实痛点主题_2026-11-18_13-20.md`（Qoder 导出）。
- 构建脚本：`eval/build_human_labels.py`（可复现：从 samples 重新提取 → 按内置标注生成 jsonl 与摄入语料 `eval/real_corpus.zip`）。
- 抽取集覆盖 10 类场景：knowledge_qa 17、tech_decision 7、action_plan 4、health 4、life 4、emotion 4、ambiguous 4、career 3、creative 2、study 1。
- 去标识化：手机号、邮箱、appid/openid、昵称、本机用户名路径已替换为占位符；助手回复中的导出 hook 行已剔除。
- 摄入语料与标注同源（同 50 组 turn pair），保证复盘/检索评测的碎片库与标注对应。

### 1.2 运行链路（全部真实执行）

| 阶段 | 方式 | 结果 |
|---|---|---|
| 摄入 | HTTP API `ingestion/preview + commit` | 50 轮，0 低置信度 |
| 抽取 | HTTP API `extraction/runs`，同步 50 次真实调用 | DONE 50/50，failed=0，耗时 311.8s，prompt `extraction-v1` |
| 碎片 | 真实模型产出 | 200 片：event 33 / knowledge 103 / trait 37 / state 27 |
| 复盘 | HTTP API `reviews`，真实调用 | 报告 #17，26 条目（12 条 judgment），3 条行动项，耗时 42.5s |
| 向量索引 | HTTP API `retrieval/index` | **500：模型不存在或已下线**（DeepSeek 无 embedding API，`deepseek-embedding` 返回 404），向量路径不可用 |
| 抽取/复盘/检索评测 | 评测服务进程内调用（与 HTTP API 同一实现；首次 HTTP 长连接被后端进程重启中断后续跑） | 见下表，总耗时 356.4s |

结果原始文件：`eval/results/real_2026-11-24/`（含全部失败明细）。

## 2. 离线质量指标

| 指标 | 数据集 | 门槛 | 样本量 | 实际值 | 是否通过 | 备注 |
|---|---|---|---|---|---|---|
| 抽取字段准确率 | human/extraction 50 | ≥ 80% | 50（510 字段） | **43.1%**（220/510） | ❌ | 逐字段精确匹配；失败集中于自由文本字段与枚举词表漂移 |
| 复盘一致率 | human/review 30 | ≥ 70% | 30（仅 5 条匹配到判断） | **60%**（3/5） | ❌ | 覆盖率仅 16.7%：25/30 标签无对应判断；一致率按 matched 计算 |
| 检索 Recall@5 | human/retrieval 30 | ≥ 75% | 30 | **100%**（30/30） | ✅ | 仅 BM25 路径（无向量）；查询与语料同源，属域内词汇召回 |

门槛对应配置：`EVAL_EXTRACTION_ACCURACY_THRESHOLD=0.8`、`EVAL_REVIEW_CONSISTENCY_THRESHOLD=0.7`、`EVAL_RETRIEVAL_RECALL_THRESHOLD=0.75`。

## 3. 在线质量与成本指标

| 指标 | 口径 | 数值 | 样本量 |
|---|---|---|---|
| Schema 通过率 | 抽取任务 ok 比例 | 100%（50/50） | 50 |
| 证据命中率 | 复盘 judgment 绑定证据片段比例 | 100%（12/12 均有 evidence_fragment_ids） | 12 |
| 画像稳定性 | 相邻快照画像主张保留率 | 未采集 | — |
| 申诉改判率 | 申诉后被接受比例 | 未采集 | — |
| 置信度均值 | 复盘条目 confidence_high 均值 | 未采集 | — |
| 覆盖率均值 | 复盘报告覆盖度评分均值 | 见报告 #17 coverage 字段 | 1 |
| 延迟（均值代理） | 抽取 6.2s/轮；复盘 42.5s/报告；评测抽取约 7s/样本 | 非分位数口径 | 50/1/50 |
| 单次任务成本 | Token 用量与费用 | 未采集（网关未回传 usage 统计） | — |

## 4. Badcase 明细

| 样本 ID | 类型 | 现象 | 期望 | 实际 | 归因 | 改进动作 |
|---|---|---|---|---|---|---|
| ext-002 | 抽取 | summary 语义正确的同义改写被判错 | 通过版本链与Read View可见性规则控制并发事务访问 | 通过版本链和 Read View 判断事务能看见哪个数据版本的并发控制机制 | 指标口径（精确匹配） | 自由文本字段改语义匹配（embedding 相似度或 LLM-judge） |
| ext-001 | 抽取 | mastery_hint 词表漂移 | read | designed | Prompt 约束（枚举仅举例未强制） | schema 层约束枚举值 |
| ext-001 | 抽取 | domain 自由组合 | database | backend/auth 等复合值 | Prompt 约束 | 给定 domain 受控词表 |
| ext-001 | 抽取 | 首个 knowledge 选择不同 | 双Token机制 | Access Token 短有效期 | 多知识点排序无约定 | 标注与 prompt 约定"核心概念优先"，或评测改集合匹配 |
| ext-002 | 抽取 | trait 措辞不同 | 贴原文求证 | 直接承认未理解 | 指标口径（自由文本） | 同 ext-002 summary |
| rev-027 | 复盘 | 诈骗短信判断偏保守 | CORRECT | UNVERIFIED | VERIFICATION_MISSING（模型要求官方核验） | 明确 verdict 口径：证据支撑的合理怀疑是否算 CORRECT |
| rev-026 | 复盘 | AI 学习主张被跨证据改判 | UNVERIFIED | WRONG | 模型用后续证据否定先前主张 | 标注口径补充"跨轮证据"规则 |
| review 整体 | 复盘 | 30 标签仅 5 条匹配到判断 | 覆盖主要话题 | 引擎只产出 12 条 judgment，话题集中 | 复盘引擎覆盖率不足 | 提高 judgment 产出覆盖；评测增加 unmatched 单列 |
| retrieval/index | 检索 | 向量索引 500 | 可建向量索引 | deepseek-embedding 404 | Provider 能力缺口 | 接入真实 embedding Provider 后重跑向量+混合路径 |

归因分类：KNOWLEDGE_GAP / VERIFICATION_MISSING / ASSUMPTION_WRONG / TIME_PRESSURE / COMMUNICATION / 检索召回 / Prompt 约束 / 模型能力 / 指标口径。

## 5. 结论

- **检索 Recall@5 达标（100%）**，但仅证明 BM25 词汇召回在同源语料上有效；向量与语义泛化能力未测（DeepSeek 无 embedding API）。
- **抽取准确率 43.1% 未达标**：失败明细显示大部分是"语义正确但措辞不同"的自由文本字段（concept/summary/trait/evidence）与未受控枚举（mastery_hint/domain）。当前精确匹配口径系统性低估真实抽取质量，**不能据此断言模型抽取能力差**；需先改语义匹配口径再重跑。
- **复盘一致率 60% 未达标且覆盖率仅 16.7%**：主要瓶颈是复盘引擎产出的 judgment 数量与话题覆盖不足，其次才是 verdict 口径分歧。
- 真实数据还暴露了两个工程问题并已修复/记录：① DeepSeek 采集器原先无法解析官方导出的 fragments 结构（已修复，`tests/test_ingestion.py` 新增回归测试）；② 向量索引对无 embedding 能力的 Provider 返回 500 而非明确的能力错误（待改进）。
- 对外表述口径：本次为 **AI 辅助标注 + 真实 Provider** 的首轮真实运行，未完成人工双标；指标可用于内部改进定位，不作为对外质量结论。

## 6. 评测记录归档

| 日期 | 数据集 | Provider/模型 | 抽取准确率 | 复盘一致率 | Recall@5 | 失败样本链接 |
|---|---|---|---|---|---|---|
| 2026-11-24 | human/*（samples 真实对话，AI 辅助标注） | DeepSeek / deepseek-chat | 43.1%（220/510） | 60%（3/5，matched 5/30） | 100%（30/30，BM25） | `eval/results/real_2026-11-24/06_eval_*.json` |

## 7. 复现步骤

```powershell
docker compose up -d
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn apps.api.main:create_app --factory --port 8000
.venv\Scripts\python.exe eval\build_human_labels.py      # 从 samples 重建数据集与语料
.venv\Scripts\python.exe eval\run_real_evaluation.py     # 摄入→抽取→复盘（HTTP API）
.venv\Scripts\python.exe eval\resume_real_evaluation.py  # 三个评测（进程内服务调用）
```