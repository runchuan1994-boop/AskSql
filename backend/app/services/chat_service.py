"""聊天服务：管理 SSE 事件队列、Agent 构建和异步运行."""

from __future__ import annotations

import asyncio
import json
import threading
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

# 待确认记忆队列：session_id -> [memory1, memory2, ...]
# （上一轮检测到的纠错记忆，本轮 summarize 时确认）
_pending_confirmations: dict[str, list[dict]] = {}
_pending_lock = threading.Lock()  # type: ignore  # threading 下面导入


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


# ---------------------------------------------------------------------------
# 待确认记忆队列
# ---------------------------------------------------------------------------

def add_pending_confirmation(session_id: str, memory: dict) -> None:
    """添加一条待确认的记忆（下一轮对话中确认）。"""
    with _pending_lock:
        if session_id not in _pending_confirmations:
            _pending_confirmations[session_id] = []
        _pending_confirmations[session_id].append(memory)


def get_pending_confirmations(session_id: str) -> list[dict]:
    """获取并清空待确认的记忆列表。"""
    with _pending_lock:
        mems = _pending_confirmations.pop(session_id, [])
        return mems


def peek_pending_confirmations(session_id: str) -> list[dict]:
    """查看待确认记忆（不清空）。"""
    with _pending_lock:
        return list(_pending_confirmations.get(session_id, []))


# ---------------------------------------------------------------------------
# 记忆确认（提升 confidence）
# ---------------------------------------------------------------------------

def confirm_pending_memories(session_id: str, memory_ids: list[str]) -> None:
    """将待确认记忆的 confidence 从 0.8 提升到 0.9，并标记为已确认。

    - 只更新 source 以 'user_correction' 开头的记忆
    - confidence 只升不降（已经 >= 0.9 的不修改）
    - 更新失败不抛异常，log warning 即可
    """
    import logging

    from app.services.memory_service import get_memory, update_memory

    logger = logging.getLogger(__name__)

    if not memory_ids:
        return

    for mem_id in memory_ids:
        try:
            mem = get_memory(mem_id)
            if not mem:
                logger.warning("Memory %s not found, skipping confirmation", mem_id)
                continue

            # 只处理 user_correction 来源的记忆
            source = mem.get("source", "") or ""
            if not source.startswith("user_correction"):
                continue

            # confidence 只升不降
            current_conf = mem.get("confidence", 0) or 0
            if current_conf >= 0.9:
                continue

            update_memory(mem_id, {
                "confidence": 0.9,
                "source": "user_correction_confirmed",
            })
        except Exception as e:
            logger.warning("Failed to confirm memory %s: %s", mem_id, e)


# ---------------------------------------------------------------------------
# 异步纠错检测
# ---------------------------------------------------------------------------

def _start_async_correction_detection(
    session_id: str,
    user_query: str,
    project_id: str,
    user_msg_id: str,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """启动异步纠错检测（后台线程，不阻塞主流程）。"""
    import logging

    logger = logging.getLogger(__name__)

    def _detect():
        try:
            from app.services.correction_detector import (
                detect_correction,
                validate_memory_against_schema,
            )
            from app.services.memory_service import upsert_correction_memory
            from app.services.session_service import get_messages
            from nl2sql.schema.loader import SchemaLoader

            # 获取上下文消息
            messages = get_messages(session_id)
            context = [
                {"role": m.get("role", ""), "content": m.get("content", "")}
                for m in messages[-10:]  # 最近 10 条
            ]

            # 检测
            correction = detect_correction(user_query, context=context)
            if not correction.is_correction:
                return

            # 获取项目的数据源和 schema，用于验证
            conn = get_connection()
            try:
                cursor = conn.execute(
                    "SELECT id, schema_file FROM datasources WHERE project_id = ?",
                    (project_id,),
                )
                ds_rows = cursor.fetchall()
            finally:
                conn.close()

            # 收集所有表用于验证
            all_tables = []
            datasource_id_for_memory = None
            loader = SchemaLoader()
            for ds_row in ds_rows:
                schema_file = ds_row["schema_file"]
                if not schema_file:
                    continue
                try:
                    ds = loader.load_from_yaml(schema_file)
                    all_tables.extend(ds.db_schema.tables)
                    if datasource_id_for_memory is None:
                        datasource_id_for_memory = ds_row["id"]
                except Exception:
                    continue

            if not all_tables:
                return

            # 验证
            correction = validate_memory_against_schema(correction, all_tables)
            if not correction.is_correction:
                return

            if not datasource_id_for_memory:
                return

            # 存储记忆（已有同实体纠错则覆盖，手动添加的不覆盖）
            memory = upsert_correction_memory(
                datasource_id=datasource_id_for_memory,
                memory_type=correction.memory_type,
                entity_type=correction.entity_type,
                entity_name=correction.entity_name,
                content=correction.content,
                raw_content=correction.raw_content,
                source_session_id=session_id,
                source_message_id=user_msg_id,
            )

            # 加入待确认队列
            add_pending_confirmation(session_id, memory)

            # 发送 SSE 事件通知前端
            try:
                loop.call_soon_threadsafe(
                    _send_event_sync, session_id, "memory_saved",
                    {
                        "memory_id": memory["id"],
                        "content": memory["content"],
                        "entity_name": memory.get("entity_name"),
                        "memory_type": memory.get("memory_type"),
                    },
                )
            except Exception:
                pass

        except Exception as e:
            logger.warning("Async correction detection failed: %s", e)

    t = threading.Thread(
        target=_detect,
        daemon=True,
        name=f"correction-detect-{session_id}",
    )
    t.start()


def _build_dispatcher_sync(project_id: str, session_id: str, loop: asyncio.AbstractEventLoop):
    """同步构建 DispatcherAgent 实例（可以在任意线程调用）.

    Dispatcher 作为统一入口，会根据用户意图自动路由到：
    - NL2SQLAgent（数据查询）
    - SchemaExplorerAgent（schema 探索）
    - DatasourceConnectorAgent（数据源接入）

    Args:
        project_id: 项目 ID
        session_id: 会话 ID
        loop: 事件循环，用于 call_soon_threadsafe 发送事件

    Returns:
        DispatcherAgent 实例
    """
    from nl2sql.agent.dispatcher import DispatcherAgent
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

    # 加载每个数据源的 schema 和执行器
    loader = SchemaLoader()
    datasources = []
    executors = {}

    for ds_id in ds_ids:
        ds = get_datasource(ds_id, include_password=True)
        if ds is None:
            continue

        schema_file = ds.get("schema_file", "")
        if schema_file:
            try:
                ds_schema = loader.load_from_yaml(schema_file)
                datasources.append(ds_schema)
            except (FileNotFoundError, Exception):
                pass

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

    # event_callback: 从 agent 线程调用，用 call_soon_threadsafe 线程安全地发送事件
    def event_callback(event_type: str, data: dict) -> None:
        try:
            loop.call_soon_threadsafe(_send_event_sync, session_id, event_type, data or {})
        except Exception:
            pass

    dispatcher = DispatcherAgent(
        project_id=project_id,
        datasources=datasources,
        executors=executors,
        event_callback=event_callback,
        max_iterations=settings.agent_max_iterations,
        max_probe_iterations=settings.agent_max_probe_iterations,
    )

    return dispatcher


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
        content = msg.get("content") or ""
        history.append(Message(role=role, content=content))
    return history


def _run_chat_sync(session_id: str, user_query: str, loop: asyncio.AbstractEventLoop,
                   datasource_id: str | None = None) -> None:
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
    msg_result = session_service.add_message(session_id, "user", user_query)
    user_msg_id = msg_result.get("id", "") if isinstance(msg_result, dict) else ""

    # 启动异步纠错检测（不阻塞主流程）
    _start_async_correction_detection(
        session_id=session_id,
        user_query=user_query,
        project_id=project_id,
        user_msg_id=user_msg_id,
        loop=loop,
    )

    # 构建 dispatcher（统一入口，自动路由到对应子 Agent）
    dispatcher = _build_dispatcher_sync(project_id, session_id, loop)

    # 加载历史消息
    history = _load_history_messages_sync(session_id)

    # 构建记忆召回回调（从所有数据源召回）
    def memory_retriever(query: str, related_tables: list[str]) -> list[dict]:
        from app.services.memory_service import get_memories_for_query
        all_memories = []
        conn = get_connection()
        try:
            cursor = conn.execute(
                "SELECT id FROM datasources WHERE project_id = ?",
                (project_id,),
            )
            ds_ids = [row["id"] for row in cursor.fetchall()]
        finally:
            conn.close()

        for ds_id in ds_ids:
            try:
                mems = get_memories_for_query(
                    ds_id, query, related_tables=related_tables
                )
                all_memories.extend(mems)
            except Exception:
                pass
        return all_memories

    # 待确认记忆（上一轮检测到的，本轮在 summarize 中确认）
    pending_mems = get_pending_confirmations(session_id)

    extra_state = {
        "memory_retriever": memory_retriever,
        "pending_memories": pending_mems,
    }

    start_time = time.perf_counter()

    try:
        # 运行 dispatcher（同步，已经在线程里了）
        result = dispatcher.run(user_query, history, datasource_id, extra_state)

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        # 提取结果
        answer = result.get("answer", "")
        sql = result.get("sql", "")
        exec_result = result.get("execution_result")
        intent_obj = result.get("intent")  # 可能是 IntentResult 对象或字符串
        iteration = result.get("iteration", 0)
        react_thoughts = result.get("react_thoughts", [])
        status = result.get("status", "unknown")
        error = result.get("error")
        intent_type = result.get("intent_type", "")

        # 构建执行结果（仅 query 类型有）
        success = exec_result is not None and exec_result.success if exec_result else False
        # schema_exploration / connect_datasource 也视为成功如果 status 是 done
        if not exec_result:
            success = status == "done" and not error

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

        # 查询改写假设：保存到 result_data 中，供前端展示
        query_assumptions = result.get("query_assumptions", []) or []
        if query_assumptions and result_data is not None:
            result_data["query_assumptions"] = query_assumptions

        # 澄清状态：将澄清问题作为消息内容保存，方便用户刷新后仍可见
        clarification_questions = result.get("clarification_questions", []) or []
        if status == "clarifying" and clarification_questions:
            # 构造友好的引导文本
            q_list = "\n".join(
                f"{i+1}. {q}" for i, q in enumerate(clarification_questions)
            )
            answer = f"为了更准确地帮你查询，需要先确认几个问题：\n\n{q_list}\n\n请在下方输入框中回复你的想法。"
            result_data = {
                "columns": ["问题"],
                "rows": [[q] for q in clarification_questions],
                "row_count": len(clarification_questions),
                "duration_ms": 0,
                "truncated": False,
                "is_clarification": True,
                "clarification_questions": clarification_questions,
            }

        # 保存助手消息
        msg_result = session_service.add_message(
            session_id,
            "assistant",
            answer,
            sql_text=sql or None,
            result=result_data,
        )
        msg_id = msg_result.get("id", "")

        # 将全量结果存入缓存，供分页接口使用（仅查询有结果时）
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
        if intent_obj and hasattr(intent_obj, "raw_analysis"):
            intent_summary = intent_obj.raw_analysis or ""
        elif isinstance(intent_obj, str):
            intent_summary = intent_obj
        if not intent_summary and intent_type:
            intent_summary = intent_type
        if not intent_summary and hasattr(intent_obj, "model_dump"):
            intent_summary = json.dumps(intent_obj.model_dump(), ensure_ascii=False)[:200]

        # 提取反思记录
        reflection_notes = ""
        if react_thoughts:
            notes = []
            for t in react_thoughts:
                if hasattr(t, "thought"):
                    notes.append(t.thought)
            reflection_notes = "; ".join(notes)[:500]

        # 确定 datasource_id
        selected_ds_id = result.get("datasource_id")
        if not selected_ds_id and exec_result and dispatcher.executors:
            # 从 dispatcher 执行器中找第一个（简化处理）
            selected_ds_id = list(dispatcher.executors.keys())[0]

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

        # 确认本轮展示的待确认记忆（提升 confidence）
        if pending_mems:
            pending_ids = [m["id"] for m in pending_mems if m.get("id")]
            confirm_pending_memories(session_id, pending_ids)

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

        # 确认本轮展示的待确认记忆（即使出错也确认，因为 summarize 节点已显示确认文本）
        try:
            if pending_mems:
                pending_ids = [m["id"] for m in pending_mems if m.get("id")]
                confirm_pending_memories(session_id, pending_ids)
        except Exception:
            pass


async def start_chat(session_id: str, user_query: str, datasource_id: str | None = None) -> str:
    """启动一个聊天任务.

    - 取消之前的任务（如果有）
    - 清空事件队列（复用同一个队列对象，避免 SSE 端引用失效）
    - 创建新的 asyncio task 在线程池中运行整个聊天流程
    - 返回 session_id
    """
    # 取消之前的任务
    old_task = _active_tasks.get(session_id)
    if old_task and not old_task.done():
        old_task.cancel()

    # 清空队列（复用同一个队列对象，避免 SSE 端持有的引用失效）
    queue = _get_event_queue(session_id)
    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    # 获取当前事件循环
    loop = asyncio.get_running_loop()

    # 创建新任务：整个聊天流程在线程池中运行
    task = asyncio.create_task(
        asyncio.to_thread(_run_chat_sync, session_id, user_query, loop, datasource_id)
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
