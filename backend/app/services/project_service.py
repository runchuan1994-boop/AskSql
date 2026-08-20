"""项目管理服务。"""
from __future__ import annotations

import os
import uuid

from app.core.config import settings
from app.core.database import get_connection


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_projects() -> list[dict]:
    """列出所有项目。"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_project(project_id: str) -> dict | None:
    """根据 ID 获取项目。"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


def _generate_short_id() -> str:
    """生成 8 位的短 UUID。"""
    return uuid.uuid4().hex[:8]


def create_project(name: str, description: str = "") -> dict:
    """创建项目，自动创建 schema 目录。"""
    project_id = _generate_short_id()

    # 创建 schema 目录
    schema_dir = os.path.join(settings.schemas_dir, project_id)
    os.makedirs(schema_dir, exist_ok=True)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO projects (id, name, description) VALUES (?, ?, ?)",
            (project_id, name, description),
        )
        conn.commit()
    finally:
        conn.close()

    result = get_project(project_id)
    assert result is not None
    return result


def update_project(
    project_id: str,
    name: str | None = None,
    description: str | None = None,
) -> dict | None:
    """更新项目信息。"""
    existing = get_project(project_id)
    if existing is None:
        return None

    new_name = name if name is not None else existing["name"]
    new_desc = description if description is not None else existing["description"]

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE projects SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_name, new_desc, project_id),
        )
        conn.commit()
    finally:
        conn.close()

    return get_project(project_id)


def delete_project(project_id: str) -> bool:
    """删除项目（级联删除数据源和会话）。"""
    existing = get_project(project_id)
    if existing is None:
        return False

    conn = get_connection()
    try:
        cursor = conn.cursor()
        # 级联删除: messages -> sessions -> datasources -> projects
        cursor.execute(
            "DELETE FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE project_id = ?)",
            (project_id,),
        )
        cursor.execute("DELETE FROM sessions WHERE project_id = ?", (project_id,))
        cursor.execute("DELETE FROM datasources WHERE project_id = ?", (project_id,))
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
    finally:
        conn.close()

    return True
