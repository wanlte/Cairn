# Cairn 架构说明

## 分层

```text
前端 apps/web
  └─ API 客户端（认证头、统一错误体、SSE 流）
        ↓ HTTP /api/v1
FastAPI apps/api
  ├─ auth        注册、登录、刷新、JWT
  ├─ gateway     模型网关：Provider 适配、能力矩阵、降级、限流、熔断、计量
  ├─ credentials 凭证加密、掩码、能力探测
  ├─ ingestion   采集、归一化、去重、预览、纠错
  ├─ extraction  四类碎片、版本化 prompt、批内去重
  ├─ review      五段式复盘、证据约束、反馈
  ├─ profile     画像增量快照、用户修正、diff
  ├─ retrieval   embedding、BM25、RRF、Rerank、问答
  ├─ evaluation  字段准确率、复盘一致率、Recall@5
  ├─ usage       用量与成本
  ├─ agents      LangGraph 多 Agent 编排（整理/复盘/画像/问答/审核）
  └─ workspace   对话式任务 API、SSE 事件、人工确认闸门
PostgreSQL + pgvector + Redis
```

## 多 Agent 编排边界（M10）

```text
前端对话首页
  ↓ REST 创建任务 + SSE 订阅进度
workspace API / service
  ↓ 组装 WorkspaceState
LangGraph StateGraph（编排器）
  ├─ 整理师 → 复盘师 → 画像师 → 问答教练 → 审核员 → 完成
  └─ 审核证据不足 → 条件边回到复盘师修订一次 → 人工确认闸门
       ↓
LangChain 工具层（ingest/extract/review/profile/retrieval）
       ↓
GatewayChatModel（自定义 BaseChatModel 适配器）
       ↓
ModelGateway.complete() → 能力矩阵/降级/限流/熔断/计量
```

关键边界：**LangGraph 只做编排**。它不直接调用任何厂商 SDK，也不让 LangChain 原生 ChatModel 接管模型调用；节点内的每次请求都通过 `apps/api/gateway/langchain_adapter.py` 把 LangChain 消息翻译为 `GatewayRequest`，再交给 `ModelGateway.complete()`。业务服务（摄入、抽取、复盘、画像、检索）保持可独立调用，手动模式与 Agent 模式共用同一套服务。

任务状态与事件落在 `workspace_tasks` / `workspace_task_events`：前者记录 QUEUED / RUNNING / WAITING_CONFIRM / DONE / FAILED，后者供 SSE 增量推送友好角色气泡；人工确认通过后由 confirm 接口恢复并聚合结果，不依赖进程内 checkpoint，天然支持重启与多进程。

## 聊天直连链路（M18）

纯聊天不进入上面的 LangGraph 图，也不做意图模型分类：

```text
前端无附件输入
  ↓ POST /api/v1/workspace/chat（JWT）
chat 规则分流（fallback_intent，零模型调用）
  ├─ 画像修改 / 具体任务 / 有证据的复盘 → 前端转调 /workspace/tasks 完整链路
  └─ 自由聊天 / 自我介绍 / 链接 / 无证据的复盘
       ↓ 链接正文（SSRF 防护）+ 画像与相关碎片 + 最近 12 条会话消息
  ModelGateway.complete_stream() → 共享限流器（令牌桶/并发/熔断）
       ↓ meta → delta* → done/error 帧（text/event-stream）
  chat_messages + workspace_tasks 历史壳落库
```

`ModelGateway.complete_stream()` 只走首个 provider：不做降级链、幂等与结构化解析；仅首字前允许退避重试，流末聚合一次 usage 与 latency 写计量。`prompts/chat/v1.txt` 是聊天系统提示词的唯一来源，原图节点也复用它，复盘/画像/改画像链路的业务语义保持不变。

会话标识复用 `workspace_tasks.task_key`，消息正文存 `chat_messages(user_id, session_id, role, content, created_at)`。同一会话内继续上传材料时，材料经 `ingest_and_extract()` 写入当前任务的 `conversation_ids_json`，正文摘录与附件名进入本轮提示词，不会新建任务或历史条目。`build_history()` 发现任务已有聊天消息时改用消息表重建对话并回传 `session_id`；没有聊天消息的老任务仍按 `workspace_task_events` 回放，因此历史侧栏、置顶、归档与删除能力无需改动。

## 关键数据流

1. **摄入**：原始文本/ZIP → `Collector` → `Normalizer` → `raw_conversations` + `turn_pairs`
2. **抽取**：每个 turn pair 单次模型调用 → `events/knowledge/traits/state` → `fragments`
3. **复盘**：fragments → 五段式报告 → `review_items` + `action_items`
4. **画像**：fragments + 上期快照 + 用户修正 → 新快照 → `profile_claims`
5. **检索**：fragments → embedding/BM25 → RRF → Rerank → 画像感知回答

## 不可变与可追溯

- `raw_conversations` 保存原文与内容哈希；纠错只发生在预览层，确认后写入轮次。
- 所有下游结论均通过 `fragment_id` 或 `evidence_fragment_ids` 回指证据。
- 用户删除的画像结论不会在下一轮重新生成。
- 模型调用记录包含 `request_id`、模型、供应商、重试次数、token 与成本。

## 凭证安全

- 单用户本地部署：`.env` 中的 `*_API_KEY` 由服务端读取，密钥不经过 API、不落库。
- 多用户部署：按用户凭证用 Fernet 加密存储，API 只回显掩码，写操作要求二次确认头。
- 模型快速通道的临时密钥用 `SecretStr` 作为单次请求字段，仅在本次 Provider 构造时解密；不写数据库、不写日志、不写 localStorage、不回显（Pydantic `exclude=True`），优先级高于已保存凭证与本机配置。
- 真实密钥不得写入源码、测试、标签集或 Git。

## 失败策略

- 模型网关将限流/配额/鉴权/模型缺失/上下文超限统一映射为错误码。
- 抽取与复盘的单轮失败写入 `error_json` 或 `error_code`，不静默丢弃。
- 结构化输出按 `json_schema → json_object → 自由文本 + 修复解析` 降级。
