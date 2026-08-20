"""生成日志服务：记录每次 SQL 生成的详情."""

from __future__ import annotations

import uuid

from app.core.database import get_connection


def log_generation(
    project_id: str,
    datasource_id: str | None,
    session_id: str | None,
    user_query: str,
    generated_sql: str | None,
    intent_summary: str | None,
    execution_success: bool,
    execution_time_ms: int,
    row_count: int,
    error_message: str | None,
    iteration: int,
    reflection_notes: str | None,
    model: str | None,
    final_selected: bool = False,
) -> str:
    """插入一条生成日志，返回 log_id."""
    log_id = str(uuid.uuid4())

    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO generation_logs
               (id, project_id, datasource_id, session_id, user_query, generated_sql,
                intent_summary, execution_success, execution_time_ms, row_count,
                error_message, iteration, reflection_notes, model, final_selected)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                log_id,
                project_id,
                datasource_id,
                session_id,
                user_query,
                generated_sql,
                intent_summary,
                1 if execution_success else 0,
                execution_time_ms,
                row_count,
                error_message,
                iteration,
                reflection_notes,
                model,
                1 if final_selected else 0,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return log_id


def list_generation_logs(project_id: str, limit: int = 100) -> list[dict]:
    """按时间倒序返回项目的生成日志."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM generation_logs WHERE project_id = ? ORDER BY timestamp DESC, rowid DESC LIMIT ?",
            (project_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
