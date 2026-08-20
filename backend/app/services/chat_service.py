"""聊天服务：管理 SSE 事件队列、Agent 构建和异步运行."""

from __future__ import annotations

import asyncio
import json
import time
import traceback
from typing import AsyncGenerator

from app.core.config import settings
from app.core.database import get_connection
from app.services import session_service
from app.services.datasource_service import build_db_url, get_datasource
from app.services.generation_log import log_generation
from app.services.result_cache import result_cache


# ---------------------------------------------------------------------------
# 模块级状态：事件队列和活动任务
# ---------------------------------------------------------------------------

_event_queues: dict[str, asyncio.Queue] = {}
_active_tasks: dict[str, asyncio.Task] = {}


def _get_event_queue(session_id: str) -> asyncio.Queue:
    """获取或创建指定会话的事件队列."""
    if session_id not in _event_queues:
        _event_queues[session_id] = asyncio.Queue()
    return _event_queues[session_id]


def _send_event_sync(session_id: str, event_type: str, data: dict) -> None:
    """同步方式向队列发送事件（必须在事件循环线程中调用）."""
    queue = _get_event_queue(session_id)
    try:
        queue.put_nowait((event_type, data))
    except asyncio.QueueFull:
        pass


def _build_agent_sync(project_id: str, session_id: str, loop: asyncio.AbstractEventLoop):
    """同步构建 NL2SQLAgent 实例（可以在任意线程调用）.

    Args:
        project_id: 项目 ID
        session_id: 会话 ID
        loop: 事件循环，用于 call_soon_threadsafe 发送事件

    Returns:
        NL2SQLAgent 实例或 None
    """
    from nl2sql.agent import NL2SQLAgent
    from nl2sql.schema.loader import SchemaLoader
    from nl2sql.executor.factory import create_executor

    # 获取项目所有数据源
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT id FROM datasources WHERE project_id = ?",
            (project_id,),
        )
        ds_ids = [row["id"] for row in cursor.fetchall()]
    finally:
        conn.close()

    if not ds_ids:
        return None

    # 加载每个数据源的 schema 和执行器
    loader = SchemaLoader()
    datasources = []
    executors = {}

    for ds_id in ds_ids:
        ds = get_datasource(ds_id, include_password=True)
        if ds is None:
            continue

        schema_file = ds.get("schema_file", "")
        if not schema_file:
            continue

        try:
            ds_schema = loader.load_from_yaml(schema_file)
            datasources.append(ds_schema)
        except (FileNotFoundError, Exception):
            continue

        db_url = build_db_url(ds)
        try:
            executor = create_executor(
                datasource_id=ds_id,
                datasource_type=ds["type"],
                db_url=db_url,
                timeout_seconds=30,
            )
            executors[ds_id] = executor
        except Exception:
            continue

    if not datasources:
        return None

    # event_callback: 从 agent 线程调用，用 call_soon_threadsafe 线程安全地发送事件
    def event_callback(event_type: str, data: dict) -> None:
        try:
            loop.call_soon_threadsafe(_send_event_sync, session_id, event_type, data or {})
        except Exception:
            pass

    agent = NL2SQLAgent(
        project_id=project_id,
        datasources=datasources,
        executors=executors,
        event_callback=event_callback,
        max_iterations=settings.agent_max_iterations,
        max_probe_iterations=settings.agent_max_probe_iterations,
    )

    return agent


def _load_history_messages_sync(session_id: str) -> list:
    """同步加载历史消息（可以在任意线程调用）."""
    from nl2sql.llm import Message, MessageRole

    messages = session_service.get_messages(session_id)
    history = []
    for msg in messages[-20:]:
        role_str = msg.get("role", "user")
        try:
            role = MessageRole(role_str)
        except ValueError:
            continue
        content = msg.get("content", "")
        history.append(Message(role=role, content=content))
    return history


def _run_chat_sync(session_id: str, user_query: str, loop: asyncio.AbstractEventLoop) -> None:
    """同步运行整个聊天流程（在线程池中执行）.

    所有操作都在同一个线程中完成：
    - 保存用户消息
    - 构建 agent
    - 运行 agent
    - 保存助手消息
    - 记录生成日志
    - 发送 chat_done 事件
    """
    # 获取 session 和 project_id
    session = session_service.get_session(session_id)
    if session is None:
        loop.call_soon_threadsafe(
            _send_event_sync, session_id, "chat_done",
            {"status": "failed", "error": "会话不存在"},
        )
        return

    project_id = session["project_id"]

    # 更新会话标题
    session_service.update_session_title_from_query(session_id, user_query)

    # 保存用户消息
    session_service.add_message(session_id, "user", user_query)

    # 构建 agent
    agent = _build_agent_sync(project_id, session_id, loop)
    if agent is None:
        loop.call_soon_threadsafe(
            _send_event_sync, session_id, "chat_done",
            {"status": "failed", "error": "没有可用的数据源或 schema"},
        )
        return

    # 加载历史消息
    history = _load_history_messages_sync(session_id)

    start_time = time.perf_counter()

    try:
        # 运行 agent（同步，已经在线程里了）
        result = agent.run(user_query, history)

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        # 提取结果
        answer = result.get("answer", "")
        sql = result.get("sql", "")
        exec_result = result.get("execution_result")
        intent = result.get("intent")
        iteration = result.get("iteration", 0)
        react_thoughts = result.get("react_thoughts", [])
        status = result.get("status", "unknown")
        error = result.get("error")

        # 构建执行结果
        success = exec_result is not None and exec_result.success if exec_result else False
        row_count = exec_result.row_count if exec_result and success else 0
        result_data = None
        if exec_result and success:
            result_data = {
                "columns": exec_result.columns,
                "rows": [list(r) for r in exec_result.rows],
                "row_count": exec_result.row_count,
                "duration_ms": exec_result.duration_ms,
                "truncated": exec_result.truncated,
                "viz": result.get("viz_spec"),
            }

        # 保存助手消息
        msg_result = session_service.add_message(
            session_id,
            "assistant",
            answer,
            sql_text=sql,
            result=result_data,
        )
        msg_id = msg_result.get("id", "")

        # 将全量结果存入缓存，供分页接口使用
        if exec_result and success and exec_result.rows:
            result_cache.set(
                f"msg:{msg_id}",
                {
                    "columns": exec_result.columns,
                    "rows": [list(r) for r in exec_result.rows],
                    "row_count": exec_result.row_count,
                    "success": exec_result.success,
                },
            )

        # 提取 intent summary
        intent_summary = ""
        if intent:
            intent_summary = getattr(intent, "raw_analysis", "") or ""
            if not intent_summary and hasattr(intent, "model_dump"):
                intent_summary = json.dumps(intent.model_dump(), ensure_ascii=False)[:200]

        # 提取反思记录
        reflection_notes = ""
        if react_thoughts:
            notes = []
            for t in react_thoughts:
                if hasattr(t, "thought"):
                    notes.append(t.thought)
            reflection_notes = "; ".join(notes)[:500]

        # 确定 datasource_id
        selected_ds_id = None
        if exec_result and agent.executors:
            # 从 agent 执行器中找第一个（简化处理）
            selected_ds_id = list(agent.executors.keys())[0]

        # 记录生成日志
        log_generation(
            project_id=project_id,
            datasource_id=selected_ds_id,
            session_id=session_id,
            user_query=user_query,
            generated_sql=sql,
            intent_summary=intent_summary,
            execution_success=success,
            execution_time_ms=execution_time_ms,
            row_count=row_count,
            error_message=str(error) if error else (
                exec_result.error if exec_result and not success else None
            ),
            iteration=iteration,
            reflection_notes=reflection_notes,
            model="mock-model",
            final_selected=success,
        )

        # 发送 chat_done 事件
        loop.call_soon_threadsafe(
            _send_event_sync, session_id, "chat_done",
            {
                "status": status,
                "success": success,
                "sql": sql,
                "row_count": row_count,
            },
        )

    except Exception as e:
        execution_time_ms = int((time.perf_counter() - start_time) * 1000)
        error_msg = str(e)
        traceback_str = traceback.format_exc()

        # 保存错误消息
        try:
            session_service.add_message(
                session_id,
                "assistant",
                f"抱歉，处理您的查询时出现错误：{error_msg}",
                sql_text="",
                result=None,
            )
        except Exception:
            pass

        # 记录生成日志（失败）
        try:
            log_generation(
                project_id=project_id,
                datasource_id=None,
                session_id=session_id,
                user_query=user_query,
                generated_sql=None,
                intent_summary=None,
                execution_success=False,
                execution_time_ms=execution_time_ms,
                row_count=0,
                error_message=error_msg,
                iteration=0,
                reflection_notes=traceback_str[:500],
                model=None,
                final_selected=False,
            )
        except Exception:
            pass

        # 发送错误和 chat_done 事件
        loop.call_soon_threadsafe(
            _send_event_sync, session_id, "error", {"message": error_msg},
        )
        loop.call_soon_threadsafe(
            _send_event_sync, session_id, "chat_done",
            {"status": "failed", "error": error_msg},
        )


async def start_chat(session_id: str, user_query: str) -> str:
    """启动一个聊天任务.

    - 取消之前的任务（如果有）
    - 创建新的 asyncio task 在线程池中运行整个聊天流程
    - 返回 session_id
    """
    # 取消之前的任务
    old_task = _active_tasks.get(session_id)
    if old_task and not old_task.done():
        old_task.cancel()

    # 创建新队列（清空旧事件）
    _event_queues[session_id] = asyncio.Queue()

    # 获取当前事件循环
    loop = asyncio.get_running_loop()

    # 创建新任务：整个聊天流程在线程池中运行
    task = asyncio.create_task(
        asyncio.to_thread(_run_chat_sync, session_id, user_query, loop)
    )
    _active_tasks[session_id] = task

    # 任务完成后清理引用
    def _on_done(_t):
        _active_tasks.pop(session_id, None)

    task.add_done_callback(_on_done)

    return session_id


async def event_stream(session_id: str) -> AsyncGenerator[str, None]:
    """SSE 事件流生成器.

    发送格式：
    event: <type>
    data: <json>
    <空行>
    """
    queue = _get_event_queue(session_id)

    # 发送 start 事件
    yield "event: start\n"
    yield f"data: {json.dumps({'session_id': session_id}, ensure_ascii=False)}\n"
    yield "\n"

    # 循环从队列取事件
    while True:
        try:
            # 60 秒超时，期间发送心跳
            event_type, data = await asyncio.wait_for(queue.get(), timeout=60.0)
        except asyncio.TimeoutError:
            # 发送心跳
            yield "event: heartbeat\n"
            yield "data: {}\n"
            yield "\n"
            continue

        # 格式化 SSE 事件
        data_str = json.dumps(data, ensure_ascii=False, default=str)
        yield f"event: {event_type}\n"
        yield f"data: {data_str}\n"
        yield "\n"

        # chat_done 事件后退出（聊天完全结束）
        if event_type == "chat_done":
            break
