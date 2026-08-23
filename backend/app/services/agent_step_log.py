"""Agent 步骤耗时日志服务.

记录每个 Agent 步骤（LLM 调用、工具调用等）的耗时，
用于性能分析、调试、前端展示思考过程。
"""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime

from app.core.database import get_connection


def _now_iso() -> str:
    """返回当前时间的 ISO 格式字符串."""
    return datetime.utcnow().isoformat()


def _sanitize_args(args: dict | None) -> dict | None:
    """脱敏处理工具参数，密码等敏感字段不存."""
    if not args:
        return None
    safe = {}
    for k, v in args.items():
        k_lower = k.lower()
        if any(s in k_lower for s in ["password", "passwd", "secret", "token", "key"]):
            safe[k] = "***"
        else:
            safe[k] = v
    return safe


# ---------------------------------------------------------------------------
# 基础 CRUD
# ---------------------------------------------------------------------------

def create_step_log(
    session_id: str,
    project_id: str | None,
    agent_type: str,
    step_name: str,
    step_type: str,
    iteration: int = 0,
    tool_name: str | None = None,
    tool_args: dict | None = None,
) -> str:
    """创建一条步骤日志（开始时调用）.

    Returns:
        step_log_id
    """
    step_id = f"step_{uuid.uuid4().hex}"
    start_time = _now_iso()
    safe_args = _sanitize_args(tool_args)

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO agent_step_logs
                (id, session_id, project_id, agent_type, step_name, step_type,
                 iteration, start_time, tool_name, tool_args_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step_id,
                session_id,
                project_id,
                agent_type,
                step_name,
                step_type,
                iteration,
                start_time,
                tool_name,
                json.dumps(safe_args, ensure_ascii=False) if safe_args else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return step_id


def finish_step_log(
    step_id: str,
    success: bool = True,
    error_message: str | None = None,
    token_input: int | None = None,
    token_output: int | None = None,
) -> None:
    """完成一条步骤日志（结束时调用，补全结束时间和结果）."""
    end_time = _now_iso()

    conn = get_connection()
    try:
        # 计算耗时
        row = conn.execute(
            "SELECT start_time FROM agent_step_logs WHERE id = ?",
            (step_id,),
        ).fetchone()

        duration_ms = None
        if row and row["start_time"]:
            try:
                start_dt = datetime.fromisoformat(row["start_time"])
                end_dt = datetime.fromisoformat(end_time)
                duration_ms = int((end_dt - start_dt).total_seconds() * 1000)
            except (ValueError, TypeError):
                pass

        conn.execute(
            """
            UPDATE agent_step_logs
            SET end_time = ?,
                duration_ms = ?,
                success = ?,
                error_message = ?,
                token_input = ?,
                token_output = ?
            WHERE id = ?
            """,
            (
                end_time,
                duration_ms,
                1 if success else 0,
                error_message,
                token_input,
                token_output,
                step_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_step_logs(session_id: str, limit: int = 200) -> list[dict]:
    """查询某个会话的步骤日志（按时间正序）."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM agent_step_logs
            WHERE session_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_step_log(step_id: str) -> dict | None:
    """根据 ID 获取单条步骤日志."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM agent_step_logs WHERE id = ?",
            (step_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agent 辅助类
# ---------------------------------------------------------------------------

class StepLogger:
    """Agent 专用的步骤日志助手.

    持有 session_id / project_id / agent_type，
    提供便捷的上下文管理器来记录每一步的耗时。

    用法:
        logger = StepLogger(session_id, project_id, "datasource_connector")

        with logger.llm_step("analyze_intent", iteration=1) as step:
            response = llm.chat(messages)
            step.set_tokens(100, 50)  # 可选

        with logger.tool_step("install_driver", "install_driver",
                              {"package": "psycopg2-binary"}, iteration=1) as step:
            result = do_something()
            if failed:
                step.fail("error message")
    """

    def __init__(self, session_id: str, project_id: str | None, agent_type: str):
        self.session_id = session_id
        self.project_id = project_id
        self.agent_type = agent_type
        self._enabled = True  # 可以设置为 False 来临时禁用

    @contextmanager
    def llm_step(self, step_name: str, iteration: int = 0):
        """记录一次 LLM 调用步骤.

        Yields:
            StepContext — 可以调用 set_tokens() / fail()
        """
        step_id = create_step_log(
            session_id=self.session_id,
            project_id=self.project_id,
            agent_type=self.agent_type,
            step_name=step_name,
            step_type="llm_call",
            iteration=iteration,
        )
        ctx = StepContext(step_id)
        try:
            yield ctx
            finish_step_log(
                step_id=step_id,
                success=ctx._success if ctx._success is not None else True,
                error_message=ctx._error,
                token_input=ctx._token_input,
                token_output=ctx._token_output,
            )
        except Exception as e:
            finish_step_log(
                step_id=step_id,
                success=False,
                error_message=str(e),
            )
            raise

    @contextmanager
    def tool_step(self, step_name: str, tool_name: str,
                  tool_args: dict | None = None, iteration: int = 0):
        """记录一次工具调用步骤.

        Yields:
            StepContext — 可以调用 fail()
        """
        step_id = create_step_log(
            session_id=self.session_id,
            project_id=self.project_id,
            agent_type=self.agent_type,
            step_name=step_name,
            step_type="tool_call",
            iteration=iteration,
            tool_name=tool_name,
            tool_args=tool_args,
        )
        ctx = StepContext(step_id)
        try:
            yield ctx
            finish_step_log(
                step_id=step_id,
                success=ctx._success if ctx._success is not None else True,
                error_message=ctx._error,
            )
        except Exception as e:
            finish_step_log(
                step_id=step_id,
                success=False,
                error_message=str(e),
            )
            raise

    @contextmanager
    def node_step(self, step_name: str, iteration: int = 0):
        """记录一个节点/阶段步骤（非 LLM 也非工具的逻辑块）.

        Yields:
            StepContext
        """
        step_id = create_step_log(
            session_id=self.session_id,
            project_id=self.project_id,
            agent_type=self.agent_type,
            step_name=step_name,
            step_type="node",
            iteration=iteration,
        )
        ctx = StepContext(step_id)
        try:
            yield ctx
            finish_step_log(
                step_id=step_id,
                success=ctx._success if ctx._success is not None else True,
                error_message=ctx._error,
            )
        except Exception as e:
            finish_step_log(
                step_id=step_id,
                success=False,
                error_message=str(e),
            )
            raise


class StepContext:
    """步骤上下文，在 with 块内使用."""

    def __init__(self, step_id: str):
        self.step_id = step_id
        self._token_input: int | None = None
        self._token_output: int | None = None
        self._error: str | None = None
        self._success: bool | None = None  # None = 未设置（默认成功）

    def set_tokens(self, input_tokens: int | None, output_tokens: int | None):
        """设置 token 用量."""
        self._token_input = input_tokens
        self._token_output = output_tokens

    def fail(self, error: str):
        """标记为失败并设置错误信息."""
        self._success = False
        self._error = error
