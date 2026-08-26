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


def _calc_match_score(mem: dict, query: str, related_tables: list[str]) -> float:
    """计算记忆与查询的匹配得分（0-10 分），用于排序加权。

    评分规则：
    - 表级精确匹配: 8 分
    - 列级精确匹配: 7 分
    - 列级表前缀匹配: 5 分
    - 术语/指标：实体名精确出现在查询中: 6 分
    - 术语/指标：内容关键词命中: 3 分
    - 查询中包含列名（business_name 或列名本身）: +2 分
    """
    score = 0.0
    query_lower = query.lower() if query else ""
    mem_type = mem.get("memory_type", "")
    entity_name = mem.get("entity_name", "") or ""
    entity_type = mem.get("entity_type", "")
    content = mem.get("content", "") or ""

    if entity_type == "table" and entity_name in (related_tables or []):
        score = max(score, 8.0)

    if mem_type == "column_description":
        # 精确匹配 related_columns（格式 table.column）
        if related_tables and entity_name:
            if "." in entity_name:
                tbl = entity_name.split(".")[0]
                if tbl in related_tables:
                    score = max(score, 5.0)  # 表前缀匹配

    # 术语/指标的关键词匹配评分
    if mem_type in ("term_mapping", "metric_definition"):
        if entity_name and entity_name.lower() in query_lower:
            score = max(score, 6.0)  # 实体名精确匹配
        else:
            # 内容关键词命中
            content_words = [w for w in content.lower().split() if len(w) >= 2]
            hit_count = sum(1 for w in content_words if w in query_lower)
            if hit_count > 0:
                score = max(score, min(3.0, hit_count * 1.5))

    # 额外加分：查询中提到了实体名或业务名
    if query_lower and entity_name and entity_name.lower() in query_lower:
        score += 1.0
    if query_lower and content and any(
        kw in query_lower for kw in content.lower().split() if len(kw) >= 3
    ):
        score += 0.5

    return min(score, 10.0)


def get_memories_for_query(
    datasource_id: str,
    query: str,
    related_tables: list[str] | None = None,
    related_columns: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """根据查询和相关表召回相关记忆。

    排序规则：相关性得分 × confidence + access_count 加权，综合排序。
    这样既考虑了记忆本身的可信度，也考虑了与当前查询的相关性。

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
        related_tables = related_tables or []

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
                mem["_match_score"] = 8.0  # 表级精确匹配
                memories[mem["id"]] = mem

            # 列描述：精确匹配 related_columns
            all_col_refs = list(related_columns or [])
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
                    # 精确匹配的列得分更高
                    mem["_match_score"] = 7.0
                    memories[mem["id"]] = mem

            # 列描述：通过表名前缀匹配（entity_name 以 "table." 开头）
            for table_name in related_tables:
                cursor = conn.execute(
                    """
                    SELECT * FROM schema_memories
                    WHERE datasource_id = ?
                      AND is_active = 1
                      AND entity_type = 'column'
                      AND entity_name LIKE ?
                    """,
                    (datasource_id, f"{table_name}.%"),
                )
                for row in cursor.fetchall():
                    mem = dict(row)
                    if mem["id"] not in memories:  # 精确匹配的已加入，不覆盖
                        mem["_match_score"] = 5.0
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
                matched = False
                if entity_name and entity_name.lower() in query_lower:
                    matched = True
                    mem["_match_score"] = 6.0
                elif any(
                    kw and len(kw) >= 2 and kw in query_lower
                    for kw in content.lower().split()
                ):
                    matched = True
                    # 根据命中关键词数量给分
                    content_words = [w for w in content.lower().split() if len(w) >= 2]
                    hits = sum(1 for w in content_words if w in query_lower)
                    mem["_match_score"] = min(3.0, hits * 1.5)
                if matched:
                    # 已存在的保留更高得分
                    if mem["id"] not in memories or \
                       mem.get("_match_score", 0) > memories[mem["id"]].get("_match_score", 0):
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
                content = mem.get("content") or ""
                matched = False
                if entity_name and entity_name.lower() in query_lower:
                    matched = True
                    mem["_match_score"] = 6.0
                elif any(
                    kw and len(kw) >= 2 and kw in query_lower
                    for kw in content.lower().split()
                ):
                    matched = True
                    content_words = [w for w in content.lower().split() if len(w) >= 2]
                    hits = sum(1 for w in content_words if w in query_lower)
                    mem["_match_score"] = min(3.0, hits * 1.5)
                if matched:
                    if mem["id"] not in memories or \
                       mem.get("_match_score", 0) > memories[mem["id"]].get("_match_score", 0):
                        memories[mem["id"]] = mem

        # 4. 计算综合排序得分
        # 综合得分 = 匹配度(0-10) * 0.3 + confidence(0-1) * 10 * 0.5 + access_count * 0.01 * 10 * 0.2
        # 即：相关性 30% + 置信度 50% + 访问量 20%
        def _rank_score(mem: dict) -> float:
            match_score = mem.get("_match_score", 0.0)
            confidence = mem.get("confidence", 0.0)
            access = mem.get("access_count", 0)
            return (
                match_score * 0.3
                + confidence * 10 * 0.5
                + min(access * 0.1, 10.0) * 0.2
            )

        result = sorted(
            memories.values(),
            key=lambda m: (_rank_score(m), m.get("created_at", "")),
            reverse=True,
        )

        result = result[:limit]

        # 5. 批量增加访问计数（失败不影响返回结果）
        if result:
            try:
                increment_access_batch([m["id"] for m in result])
            except Exception:
                pass

        return result
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
        "confidence", "raw_content", "source",
        "source_session_id", "source_message_id",
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


def find_memory_by_entity(
    datasource_id: str,
    memory_type: str,
    entity_name: str | None,
) -> dict | None:
    """查找指定数据源、类型、实体名的活跃记忆。

    按 confidence DESC 排序，返回优先级最高的一条。
    找不到返回 None。
    """
    conn = get_connection()
    try:
        if entity_name is not None:
            cursor = conn.execute(
                """
                SELECT * FROM schema_memories
                WHERE datasource_id = ?
                  AND memory_type = ?
                  AND entity_name = ?
                  AND is_active = 1
                ORDER BY confidence DESC, created_at DESC
                LIMIT 1
                """,
                (datasource_id, memory_type, entity_name),
            )
        else:
            cursor = conn.execute(
                """
                SELECT * FROM schema_memories
                WHERE datasource_id = ?
                  AND memory_type = ?
                  AND entity_name IS NULL
                  AND is_active = 1
                ORDER BY confidence DESC, created_at DESC
                LIMIT 1
                """,
                (datasource_id, memory_type),
            )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_correction_memory(
    datasource_id: str,
    memory_type: str,
    entity_type: str | None,
    entity_name: str | None,
    content: str,
    *,
    raw_content: str | None = None,
    source_session_id: str | None = None,
    source_message_id: str | None = None,
) -> dict:
    """更新或插入一条纠错记忆。

    逻辑：
    - 已有同实体同类型且 source 以 'user_correction' 开头的记忆：更新内容、重置 confidence=0.8
    - 已有同实体同类型但 source 是 'manual_add' 的记忆：不覆盖，创建新记录（并存）
    - 没有匹配记忆：调用 add_memory 创建新记录

    Returns:
        更新后或新建的记忆记录 dict
    """
    existing = find_memory_by_entity(datasource_id, memory_type, entity_name)

    if existing is None:
        # 没有旧记忆，直接创建
        return add_memory(
            datasource_id=datasource_id,
            memory_type=memory_type,
            entity_type=entity_type,
            entity_name=entity_name,
            content=content,
            raw_content=raw_content,
            source="user_correction",
            source_session_id=source_session_id,
            source_message_id=source_message_id,
            confidence=0.8,
        )

    source = existing.get("source", "")

    # 手动添加的记忆优先级更高，不自动覆盖，创建新记忆并存
    if source == "manual_add":
        return add_memory(
            datasource_id=datasource_id,
            memory_type=memory_type,
            entity_type=entity_type,
            entity_name=entity_name,
            content=content,
            raw_content=raw_content,
            source="user_correction",
            source_session_id=source_session_id,
            source_message_id=source_message_id,
            confidence=0.8,
        )

    # 自动纠错产生的记忆，更新覆盖
    updated = update_memory(
        existing["id"],
        {
            "content": content,
            "raw_content": raw_content,
            "confidence": 0.8,
            "source": "user_correction",
            "source_session_id": source_session_id,
            "source_message_id": source_message_id,
        },
    )

    return updated or {}


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


def increment_access_batch(memory_ids: list[str]) -> None:
    """批量增加记忆的访问计数。

    更新失败不抛出异常，静默忽略。
    """
    if not memory_ids:
        return
    try:
        conn = get_connection()
        try:
            placeholders = ",".join("?" * len(memory_ids))
            conn.execute(
                f"UPDATE schema_memories SET access_count = access_count + 1 WHERE id IN ({placeholders})",
                memory_ids,
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
