from __future__ import annotations

"""工作区任务的持久化边界。

LangGraph 图本身是短事务的：一次创建任务对应一次图执行。跨请求的可恢复状态
复用 workspace_tasks 表（status / confirm_prompt / result_json），事件轨迹复用
workspace_task_events 表，因此不额外引入 AsyncPostgresSaver 依赖。
人工确认恢复通过 POST /workspace/tasks/{key}/confirm 触发新的图分支完成，
而不是依赖进程内 checkpoint，天然支持多进程与重启。
"""
