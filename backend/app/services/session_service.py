"""会话管理服务."""

from __future__ import annotations

import json
import uuid

from app.core.database import get_connection


def _row_to_dict(row) -> dict:
    return dict(row)


def list_sessions(project_id: str) -> list[dict]:
    """列出项目的所有会话，按更新时间倒序."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM sessions WHERE project_id = ? ORDER BY updated_at DESC, rowid DESC",
            (project_id,),
        )
        return [_row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_session(session_id: str) -> dict | None:
    """获取单个会话详情."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def create_session(project_id: str, title: str = "新对话") -> dict:
    """创建新会话，使用 UUID 作为长 ID."""
    session_id = str(uuid.uuid4())
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO sessions (id, project_id, title) VALUES (?, ?, ?)",
            (session_id, project_id, title),
        )
        conn.commit()
        cursor = conn.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update_session(session_id: str, title: str | None = None) -> dict | None:
    """更新会话（目前仅支持标题）."""
    if title is None:
        return get_session(session_id)

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (title, session_id),
        )
        conn.commit()
        cursor = conn.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def delete_session(session_id: str) -> bool:
    """删除会话及其所有消息，级联删除."""
    conn = get_connection()
    try:
        # 先检查是否存在
        cursor = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if cursor.fetchone() is None:
            return False

        # 级联删除消息
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        # 删除会话
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def get_messages(session_id: str) -> list[dict]:
    """获取会话的所有消息，按时间正序排列，解析 result_json."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        results = []
        for row in cursor.fetchall():
            msg = _row_to_dict(row)
            # 解析 result_json
            result_json = msg.pop("result_json", None)
            if result_json:
                try:
                    msg["result"] = json.loads(result_json)
                except (json.JSONDecodeError, TypeError):
                    msg["result"] = None
            else:
                msg["result"] = None
            results.append(msg)
        return results
    finally:
        conn.close()


def add_message(
    session_id: str,
    role: str,
    content: str,
    sql_text: str | None = None,
    result: dict | list | None = None,
) -> dict:
    """添加一条消息，同时更新会话的 updated_at."""
    msg_id = str(uuid.uuid4())
    result_json = json.dumps(result, ensure_ascii=False, default=str) if result is not None else None
    # 防御：确保 content 是字符串
    if content is None:
        content = ""

    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO messages (id, session_id, role, content, sql_text, result_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (msg_id, session_id, role, content, sql_text, result_json),
        )
        # 更新会话的 updated_at
        conn.execute(
            "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )
        conn.commit()

        cursor = conn.execute(
            "SELECT * FROM messages WHERE id = ?",
            (msg_id,),
        )
        row = cursor.fetchone()
        msg = _row_to_dict(row)
        result_json_val = msg.pop("result_json", None)
        if result_json_val:
            try:
                msg["result"] = json.loads(result_json_val)
            except (json.JSONDecodeError, TypeError):
                msg["result"] = None
        else:
            msg["result"] = None
        return msg
    finally:
        conn.close()


def update_session_title_from_query(session_id: str, query: str) -> None:
    """如果会话标题仍是默认"新对话"，用 query 前 30 字作为标题."""
    session = get_session(session_id)
    if session is None:
        return
    if session.get("title") == "新对话":
        new_title = query[:30]
        update_session(session_id, title=new_title)
