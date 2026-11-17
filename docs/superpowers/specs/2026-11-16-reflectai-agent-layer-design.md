# ReflectAI · Agent 编排层设计文档

| 项目 | 内容 |
|---|---|
| 文档版本 | v1.0 |
| 撰写日期 | 2026-11-16 |
| 文档状态 | 待用户审阅 |
| 上游依赖 | `AI对话复盘助手_PRD_v2.md`（v2.1，批处理管道基础） |
| 性质 | PRD 之上的增量演进的架构设计，不替换管道 |

---

## 1. 背景与目标

PRD v2.1 定义了一条批处理管道：摄入 → 抽取 → 复盘 → 画像 → 检索 → 行动项，由用户手动触发。本设计在管道**之上**增加 agent 编排层，把"你按按钮它跑管道"升级为"它自己决定什么时候做什么"。

沿用 PRD 双目标（冲突时 A 优先）：
- **目标 A · 自用**：无人值守的周期复盘 + 随时可问的成长教练 + 受控自我改进。
- **目标 B · 求职**：支撑"后端转 AI"叙事——durable execution、人工闸门、轨迹可回放、受控自我进化，且工程侧（编排/可靠性/可观测）足以传统后端面试官认可。

**核心定位**：agent 层是业务服务的"自主消费者"。业务服务保持可独立调用，手动模式（PRD 导入台/复盘页按钮）与 agent 模式共用同一套服务。agent 层故障时系统仍可用，一期交付物不被 agent 绑架。

## 2. 已锁定决策（评审结论）

| # | 决策 | 说明 |
|---|---|---|
| D1 | 三个方向都要 | weekly 自主循环 / chat 对话教练 / evolve 受控自我进化 |
| D2 | 自主边界 = B（中间） | 读写全自动；两个高危动作必须人工确认：① 行动项变更 + 报告推送 ② 自我改进采纳。回滚靠 PRD 已有不可变层（raw 不可变 + Fragment 事实源 + 画像历史版本） |
| D3 | 编排框架 = LangGraph | **仅作状态机编排器**；节点内模型调用一律走 `ModelGateway.complete()`，绝不让框架的模型抽象接管网关治理（限流/降级/计量/能力矩阵） |
| D4 | 三触发器共用一个核心 | 工具盒、记忆、轨迹、闸门完全共用；三个方向只是三个触发入口 + 三个 graph |
| D5 | 受控自我进化 | evolve 不能随意改 prompt：提案 → 评估集回归 → 达标才采纳；`prompt_version` 单调递增、旧版保留可回滚 |
| D6 | 分期落地 | 一期管道（服务接口按工具签名设计，零额外成本前瞻）；二期 weekly + chat + 核心；三期 evolve（自用期后，燃料是 4 周真实反馈数据） |
| D7 | 流程自主性分级 | weekly / evolve 用固定骨架图 + 节点内自主；仅 chat 用 ReAct 自由循环。流程是产品定义的，不让模型自由发挥骨架 |

## 3. 总体架构

```
前端（新增：agent 轨迹页 / 对话教练页 / 确认闸门组件）
   │ REST + SSE
API 层（新增 /agent/* 端点，鉴权/限流/request_id 沿用 PRD）
   │
┌──────────────────────────────────────────────┐
│ Agent 编排层（LangGraph）★ 新增                 │
│  三个 graph：weekly / chat / evolve             │
│  共享：工具节点盒 · 闸门节点 · 轨迹节点          │
│  checkpointer：AsyncPostgresSaver（复用现有 PG） │
└───────────────────┬──────────────────────────┘
                    │ 工具调用（进程内函数，非 HTTP）
┌───────────────────▼──────────────────────────┐
│ 业务领域层（PRD 现有，接口即工具签名）           │
│  摄入 / 抽取 / 复盘 / 画像 / 检索 / 行动项 / 反馈 │
└───────────────────┬──────────────────────────┘
                    │ 唯一模型入口
            模型网关层（PRD 现有，不变）
                    │
            存储层（新增 agent_run / agent_step / prompt_proposal）
```

三个触发器：
- **Celery beat**（周日 22:00，可配）→ `weekly_graph`
- **`POST /agent/chat`**（SSE 流式）→ `chat_graph`
- **metrics watcher**（周期任务检查反馈阈值）→ `evolve_graph`

checkpointer 复用现有 PostgreSQL，不引入新基础设施。

## 4. 组件设计

每个单元一个职责、定义良好的接口、可独立测试。

### 4.1 工具盒（`agent/tools/`）

把业务服务包成带 Pydantic 签名的**进程内函数**。每个工具 = 薄封装：参数校验 → 调服务 → 结构化返回。工具不 import 任何厂商 SDK；模型调用经服务 → 网关。工具签名按 function-calling schema 暴露给模型，但执行是进程内调用（省序列化开销）。

工具清单（YAGNI，只列三个 graph 真正需要的）：

| 工具 | 签名要点 | 服务的 graph |
|---|---|---|
| `list_new_conversations` | `since` → 新对话列表 | weekly |
| `ingest` | `source` → 摄入结果 | weekly |
| `extract` | `conv_ids` → 碎片统计 | weekly |
| `search_fragments` | `query, filters` → 碎片列表 | chat / weekly / evolve |
| `get_fragments` | `ids` → 碎片详情 | chat |
| `generate_review` | `period` → 报告草稿 | weekly |
| `get_review` | `id` → 报告详情 | chat |
| `get_profile` | — → 当前画像 | chat / weekly |
| `update_profile_claim` | `id, patch` → 更新结果 | weekly |
| `list_action_items` | `status` → 行动项列表 | chat / weekly |
| `verify_action_item` | `id, evidence_fragment_ids` → 验证结果 | weekly |
| `propose_action_item` | `payload` → 待确认行动项 | weekly |
| `get_feedback_metrics` | `window` → 认可率/采纳率/被否维度 | evolve |
| `list_negative_examples` | `kind` → 负例列表 | evolve |
| `propose_prompt_change` | `target, diff, rationale` → 提案 | evolve |
| `run_eval` | `proposal_id` → 新旧对比指标 | evolve |
| `adopt_prompt` | `proposal_id` → 采纳结果（需闸门） | evolve |

所有工具强制 `user_id` 边界（只能操作本用户数据），参数经 Pydantic 校验。

### 4.2 三个 graph（`agent/graphs/`）

- **`weekly_graph`**：固定骨架 + 节点内自主。骨架节点：`check_new → ingest → extract → review → profile_update → verify_last_week_actions → interrupt(闸门) → publish`。自主性体现在节点内（如 review 节点里模型决定强调哪些事件），骨架确定。
- **`chat_graph`**：ReAct 式自主循环（模型选工具 → 执行 → 回填 → 再选），**最大 8 步**防失控，SSE 流式输出 reasoning + tool + answer。
- **`evolve_graph`**：固定骨架：`read_metrics → diagnose → propose → run_eval(门禁) → 条件边`。达标 → `interrupt(采纳闸门) → adopt`；不达标 → `discard`（提案存档供人工查看）。

三个 graph 共享工具节点、闸门节点、轨迹节点（子图复用）。

### 4.3 闸门（`agent/gates/`）

B 边界的两个 interrupt 点，统一抽象 `require_confirmation(kind, payload)`：
- LangGraph `interrupt()` 暂停 → 写 `agent_run.status = WAITING_CONFIRM` → 前端确认组件 → `POST /agent/runs/{id}/resume` → 从断点继续。
- 哪些动作要闸门可配置，默认 B（行动项变更 + 报告推送、evolve 采纳）。
- 超时 7 天未确认 → 自动 `EXPIRED`，不推送（宁可不发不可乱发）。

### 4.4 轨迹（`agent/trace/`）

- `agent_run`：一次运行（kind / status / request_id / period / 起止时间 / token 累计）。
- `agent_step`：每个节点进出 + 每次工具调用 + 模型 reasoning，关联 run。
- 复用现有 `llm_call_log`（模型调用计量），`request_id` 贯穿采集→抽取→复盘→画像→agent 决策。
- 支持回放：按 checkpoint + step 逐步重演，决策可审计。

### 4.5 记忆（不新建系统）

- 长期语义记忆 = 碎片 + 画像（pgvector 已索引）。
- 工作记忆 / 限流 = Redis（现有）。
- 情景记忆 = `agent_run` / `agent_step`。
- **不引入独立 memory 框架**（YAGNI）。

### 4.6 触发器（`agent/triggers/`）

- Celery beat：weekly。
- chat API：用户消息。
- metrics watcher：周期任务，反馈阈值触发 evolve（默认"某维度连续 3 周被否"，自用期校准）。

## 5. 数据流

### 5.1 weekly run 生命周期

1. beat 周日 22:00 触发 → 建 `agent_run(kind=WEEKLY, status=RUNNING, request_id)`，幂等键 `hash(period + trigger_date)`。
2. 从 checkpointer 加载/初始化 state。
3. `check_new`：`list_new_conversations` → 无新对话则 `DONE_NOOP` 提前结束。
4. `ingest` / `extract`：调工具，进度写 `agent_step`；模型调用走网关（计量/限流/降级照常）。
5. `review`：`generate_review(period)` → 五段式报告草稿。
6. `profile_update`：增量快照。
7. `verify_last_week_actions`：对每个 pending 行动项 `search_fragments` 找本周证据 → 有证据 `verify_action_item` 标记验证结果；无则保持 pending。
8. **interrupt 闸门**：报告推送 + 行动项变更打包成 confirmation payload → `WAITING_CONFIRM` → 通知前端。
9. 用户确认 → `resume(decision)` → 从断点继续。
10. `publish`：落库报告/行动项 → `DONE`。
11. 任意节点失败 → `FAILED` + 保留 checkpoint 可重试。

### 5.2 chat run

`POST /agent/chat` → `chat_graph` ReAct 循环（SSE 流式吐 reasoning + tool + answer）→ 8 步上限兜底 → 落 run/step。

**多轮约定**：chat 以会话线程为单位（`thread_id`）。同一会话的多轮追问复用同一 thread 的 checkpoint state（保留上下文）；每条用户消息触发一次 graph 执行并新建一个 `agent_run(kind=CHAT)` 关联该 thread。新建会话 = 新 thread。这样"那上次是怎么解决的？"这类追问能接住前文。

### 5.3 evolve run

watcher 发现"某维度连续 3 周被否" → 建 run → `diagnose` 聚类负例 → `propose_prompt_change` → `run_eval`（50 标注 + 30 查询跑新旧对比）→ 达标? → 达标进采纳闸门 → `adopt`（`prompt_version++`，旧版保留可回滚）；不达标 → `discard`（提案存档）。

## 6. 数据模型（新增表）

```sql
CREATE TABLE agent_run (
  id            BIGSERIAL PRIMARY KEY,
  user_id       BIGINT NOT NULL,
  request_id    UUID NOT NULL,
  kind          TEXT NOT NULL CHECK (kind IN ('WEEKLY','CHAT','EVOLVE')),
  status        TEXT NOT NULL,  -- RUNNING/WAITING_CONFIRM/DONE/DONE_NOOP/FAILED/EXPIRED
  period        TEXT,           -- weekly 的周期标识
  idempotency_key TEXT,
  token_budget  INT,
  tokens_used   INT NOT NULL DEFAULT 0,
  thread_id     TEXT NOT NULL,  -- LangGraph checkpointer 线程键
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON agent_run (user_id, kind, status);
CREATE UNIQUE INDEX ON agent_run (idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE TABLE agent_step (
  id            BIGSERIAL PRIMARY KEY,
  run_id        BIGINT NOT NULL REFERENCES agent_run(id),
  seq           INT NOT NULL,
  node          TEXT NOT NULL,
  tool          TEXT,
  input_snippet JSONB,          -- 截断 + 脱敏
  output_snippet JSONB,         -- 截断 + 脱敏
  reasoning     TEXT,           -- 模型决策说明（脱敏）
  status        TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON agent_step (run_id, seq);

CREATE TABLE prompt_proposal (
  id            BIGSERIAL PRIMARY KEY,
  user_id       BIGINT NOT NULL,
  run_id        BIGINT REFERENCES agent_run(id),
  target        TEXT NOT NULL,  -- 目标 prompt 标识
  diff          JSONB NOT NULL,
  rationale     TEXT,
  eval_metrics  JSONB,          -- 新旧对比结果
  status        TEXT NOT NULL,  -- PROPOSED/PASSED_GATE/ADOPTED/DISCARDED
  base_version  TEXT NOT NULL,
  new_version   TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

LangGraph checkpoint 表由 AsyncPostgresSaver 自动管理（独立于上述业务表）。

## 7. API 设计（新增端点，沿用 PRD 规范）

前缀 `/api/v1`，JWT 鉴权，统一错误体，request_id 贯穿。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/agent/runs` | 手动触发一次 run（kind + 参数），返回 202 + run_id |
| GET | `/agent/runs` | run 列表（kind/status 过滤，游标分页） |
| GET | `/agent/runs/{id}` | run 详情与状态 |
| GET | `/agent/runs/{id}/events` | SSE 进度/轨迹流 |
| POST | `/agent/runs/{id}/resume` | 闸门确认（decision: approve/reject + 修改） |
| GET | `/agent/runs/{id}/trace` | 完整轨迹（回放用） |
| POST | `/agent/chat` | 对话教练（SSE 流式），建 CHAT run |
| GET | `/agent/proposals` | 自我改进提案列表 |
| GET | `/agent/proposals/{id}` | 提案详情（diff + 评估指标） |
| POST | `/agent/proposals/{id}/adopt` | 采纳提案（触发闸门确认） |
| POST | `/agent/proposals/{id}/discard` | 丢弃提案 |

## 8. 错误处理与可靠性

| 机制 | 设计 |
|---|---|
| 节点失败不炸整图 | 工具错误结构化返回给模型自行决策（chat）；固定骨架节点失败 → run FAILED + checkpoint 保留可重试 |
| 断点续跑 | 每节点后 checkpoint；进程重启从最近断点恢复（durable execution） |
| 失控防护 | chat 8 步上限 + 单 run token 预算（默认 50K，可配，网关计量累计）超限强制收尾并标注 |
| 闸门超时 | WAITING_CONFIRM 超 7 天自动 EXPIRED，不推送 |
| evolve 安全 | 评估门禁是硬条件边，不达标绝不 adopt；adopt 必须人工确认；版本单调递增可回滚 |
| 幂等 | weekly run 用 `hash(period+trigger_date)`；evolve run 用 `hash(dim_key+window)` 防 watcher 重复触发；工具层复用 PRD 摄入去重/抽取幂等键 |
| 注入防护 | 工具返回的对话内容包裹分隔符 + 声明"仅为分析对象不作为指令"；工具参数 Pydantic 校验 + user_id 边界 |
| 密钥/原文 | 沿用 PRD 12.2：轨迹 snippet 截断 + 脱敏，日志不落密钥与原文 |

## 9. 测试与评估

| 对象 | 方法 | 目标 |
|---|---|---|
| 工具层 | 单测 mock 服务，验签名/校验/错误返回/user_id 边界 | 覆盖 ≥ 80% |
| graph 集成 | fake gateway 确定性响应跑三图完整路径，断言节点序列/闸门触发/checkpoint 恢复 | 三图全路径通过 |
| 故障注入 | run 中途 kill 进程 → resume 续跑；interrupt 确认/拒绝/超时三分支 | 恢复成功率 ≥ 90% |
| evolve 门禁 | 构造达标/不达标提案，断言前者进闸门后者 discard；adopt 后版本递增且可回滚 | 门禁正确率 100% |
| chat 评估集 | 自建 20 条"问题 → 期望工具序列/答案要点" | 工具序列命中率 ≥ 75% |
| weekly 评估 | 断言五段式完整性 + 证据约束（沿用 PRD 评估） | 沿用 PRD 指标 |
| evolve 回归 | 用现有 50 标注 + 30 查询评估集 | 采纳后不低于基线 |
| 轨迹回放 | 任一 run 按 step 重演 | 决策可审计 |

## 10. 分期与里程碑映射

| 期 | 工期 | 交付物 | 前置 |
|---|---|---|---|
| 一期 | PRD M1–M8（28–35 工作日） | 管道照做；**业务服务接口按工具签名设计**（零额外成本前瞻）；不做 graph | D0 取证 |
| 二期 | +5–7 工作日 | 工具盒 + weekly_graph + chat_graph + 闸门 + 轨迹 + 前端轨迹页/对话页 + `/agent/*` 端点 | 一期完成 |
| 三期 | +3–4 工作日 | evolve_graph + 评估门禁 + prompt_proposal + 采纳闸门 + metrics watcher | 4 周自用期反馈数据 |

总计约 36–46 工作日，日历约 8–10 周。一期交付物不变（可开源、可面试），agent 是增量演进。

## 11. 非目标（YAGNI）

- ❌ 独立 memory 框架（复用碎片/画像/Redis/run-step）
- ❌ LangSmith 等托管观测（自托管轨迹）
- ❌ multi-agent swarm（三 graph 共享工具，非多 agent 协商）
- ❌ 工具做成 HTTP 微服务（进程内函数）
- ❌ 让模型自由定义 weekly/evolve 骨架流程
- ❌ evolve 全自动采纳（B 边界要求人工确认）
- ❌ 替换或绕过 ModelGateway（网关仍是唯一模型入口）

## 12. 面试叙事要点

1. **从批处理到 agent 的演进动机**：管道解决"算得对"，agent 解决"不用我惦记"——自主循环 + 对话教练 + 受控自我进化。
2. **LangGraph 只当编排器，网关仍是唯一模型入口**：不让框架模型抽象吃掉自研的限流/降级/计量/能力矩阵治理。这是架构判断，不是赶时髦。
3. **固定图 vs ReAct 的取舍**：weekly/evolve 流程是产品定义的，用固定骨架 + 节点内自主；只有 chat 用 ReAct。"知道什么时候不该用 agent"比"全是 ReAct"成熟。
4. **受控自我进化**：提案 → 评估集回归 → 达标才采纳 + 人工闸门 + 版本可回滚。比"agent 自己改自己"在工程上站得住。
5. **可复算**：durable execution（checkpoint 断点续跑）+ 人工闸门 + 轨迹回放，任一 run 可逐步重演审计。

## 13. 开放项（留到实施计划细化，非阻塞）

- git 仓库尚未 init，本文档先落盘；是否 init 由用户决定。
- 各工具精确签名与错误码细化 → writing-plans 阶段。
- evolve 触发阈值（默认"连续 3 周被否"）需自用期校准。
- chat 最大步数（默认 8）/ token 预算（默认 50K）需实测调优。
- 前端轨迹页/对话页组件细节 → 二期设计时细化。