"""Schema 记忆服务：管理用户纠错记忆的 CRUD 和召回。"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.database import get_connection


MEMORY_TYPES = {
    "column_description": "column",
    "table_description": "table",
    "metric_definition": "metric",
    "term_mapping": "term",
    "join_hint": "table",
}


def _generate_id() -> str:
    return f"mem_{uuid.uuid4().hex[:12]}"


def add_memory(
    datasource_id: str,
    memory_type: str,
    entity_type: str | None,
    entity_name: str | None,
    content: str,
    *,
    raw_content: str | None = None,
    source: str = "user_correction",
    source_session_id: str | None = None,
    source_message_id: str | None = None,
    confidence: float = 0.8,
) -> dict:
    """添加一条记忆。

    Returns:
        新建的记忆记录 dict
    """
    mem_id = _generate_id()

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO schema_memories
            (id, datasource_id, memory_type, entity_type, entity_name,
             content, raw_content, source, source_session_id, source_message_id,
             confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (mem_id, datasource_id, memory_type, entity_type, entity_name,
             content, raw_content, source, source_session_id, source_message_id,
             confidence),
        )
        conn.commit()
    finally:
        conn.close()

    return get_memory(mem_id) or {}


def get_memory(memory_id: str) -> dict | None:
    """根据 ID 获取单条记忆。"""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM schema_memories WHERE id = ?",
            (memory_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_memories_for_table(datasource_id: str, table_name: str) -> list[dict]:
    """获取某张表的所有相关记忆（表级 + 列级）。"""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT * FROM schema_memories
            WHERE datasource_id = ?
              AND is_active = 1
              AND (
                  (entity_type = 'table' AND entity_name = ?)
                  OR (entity_type = 'column' AND entity_name LIKE ?)
              )
            ORDER BY confidence DESC, access_count DESC, created_at DESC
            """,
            (datasource_id, table_name, f"{table_name}.%"),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_memories_for_query(
    datasource_id: str,
    query: str,
    related_tables: list[str] | None = None,
    related_columns: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """根据查询和相关表召回相关记忆。

    Args:
        datasource_id: 数据源 ID
        query: 用户查询文本
        related_tables: 相关表名列表
        related_columns: 相关列名列表（格式: table.column）
        limit: 最多返回条数

    Returns:
        按相关性排序的记忆列表
    """
    conn = get_connection()
    try:
        memories: dict[str, dict] = {}

        # 1. 表级 + 列级精确匹配
        if related_tables:
            placeholders = ",".join("?" * len(related_tables))
            # 表描述 + join_hint（按表名匹配）
            params = [datasource_id] + related_tables
            cursor = conn.execute(
                f"""
                SELECT * FROM schema_memories
                WHERE datasource_id = ?
                  AND is_active = 1
                  AND entity_type = 'table'
                  AND entity_name IN ({placeholders})
                """,
                params,
            )
            for row in cursor.fetchall():
                mem = dict(row)
                memories[mem["id"]] = mem

            # 列描述：匹配 related_columns 或 table.column 格式
            all_col_refs = list(related_columns or [])
            # 从 related_tables 生成 table.column 模糊匹配
            # （这里简化：只精确匹配 related_columns）
            if all_col_refs:
                col_placeholders = ",".join("?" * len(all_col_refs))
                params_col = [datasource_id] + all_col_refs
                cursor = conn.execute(
                    f"""
                    SELECT * FROM schema_memories
                    WHERE datasource_id = ?
                      AND is_active = 1
                      AND entity_type = 'column'
                      AND entity_name IN ({col_placeholders})
                    """,
                    params_col,
                )
                for row in cursor.fetchall():
                    mem = dict(row)
                    memories[mem["id"]] = mem

        # 2. 术语型记忆：关键词匹配
        if query:
            query_lower = query.lower()
            cursor = conn.execute(
                """
                SELECT * FROM schema_memories
                WHERE datasource_id = ?
                  AND is_active = 1
                  AND memory_type = 'term_mapping'
                """,
                (datasource_id,),
            )
            for row in cursor.fetchall():
                mem = dict(row)
                entity_name = mem.get("entity_name") or ""
                content = mem.get("content") or ""
                if entity_name and entity_name.lower() in query_lower:
                    memories[mem["id"]] = mem
                elif any(
                    kw and kw in query_lower
                    for kw in content.lower().split()
                ):
                    memories[mem["id"]] = mem

        # 3. 指标型记忆：关键词匹配
        if query:
            query_lower = query.lower()
            cursor = conn.execute(
                """
                SELECT * FROM schema_memories
                WHERE datasource_id = ?
                  AND is_active = 1
                  AND memory_type = 'metric_definition'
                """,
                (datasource_id,),
            )
            for row in cursor.fetchall():
                mem = dict(row)
                entity_name = mem.get("entity_name") or ""
                if entity_name and entity_name.lower() in query_lower:
                    memories[mem["id"]] = mem

        # 4. 排序：confidence 高的在前，access_count 多的在前，新的在前
        result = sorted(
            memories.values(),
            key=lambda m: (
                m.get("confidence", 0),
                m.get("access_count", 0),
                m.get("created_at", ""),
            ),
            reverse=True,
        )

        return result[:limit]
    finally:
        conn.close()


def update_memory(memory_id: str, updates: dict) -> dict | None:
    """更新记忆内容。

    Args:
        memory_id: 记忆 ID
        updates: 要更新的字段 dict（content, confidence, entity_name 等）

    Returns:
        更新后的记忆记录
    """
    allowed_fields = {
        "content", "memory_type", "entity_type", "entity_name",
        "confidence", "raw_content",
    }
    update_parts = []
    params = []
    for key, value in updates.items():
        if key in allowed_fields:
            update_parts.append(f"{key} = ?")
            params.append(value)

    if not update_parts:
        return get_memory(memory_id)

    update_parts.append("updated_at = CURRENT_TIMESTAMP")
    params.append(memory_id)

    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE schema_memories SET {', '.join(update_parts)} WHERE id = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()

    return get_memory(memory_id)


def delete_memory(memory_id: str) -> bool:
    """删除记忆（软删除，is_active=0）。"""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE schema_memories SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (memory_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def list_memories(
    datasource_id: str,
    *,
    memory_type: str | None = None,
    entity_type: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
    include_inactive: bool = False,
) -> dict:
    """列出某数据源的记忆（分页、筛选）。

    Returns:
        {items, total, page, page_size, has_more}
    """
    conn = get_connection()
    try:
        conditions = ["datasource_id = ?"]
        params: list[Any] = [datasource_id]

        if not include_inactive:
            conditions.append("is_active = 1")

        if memory_type:
            conditions.append("memory_type = ?")
            params.append(memory_type)

        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)

        if search:
            conditions.append("(content LIKE ? OR entity_name LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where_clause = " AND ".join(conditions)

        # 总数
        cursor = conn.execute(
            f"SELECT COUNT(*) as total FROM schema_memories WHERE {where_clause}",
            params,
        )
        total = cursor.fetchone()["total"]

        # 分页数据
        offset = (page - 1) * page_size
        cursor = conn.execute(
            f"""
            SELECT * FROM schema_memories
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        )
        items = [dict(row) for row in cursor.fetchall()]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": offset + len(items) < total,
        }
    finally:
        conn.close()


def increment_access(memory_id: str) -> None:
    """增加记忆的访问计数。"""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE schema_memories SET access_count = access_count + 1 WHERE id = ?",
            (memory_id,),
        )
        conn.commit()
    finally:
        conn.close()
