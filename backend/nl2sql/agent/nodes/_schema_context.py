"""Schema Context 构建工具：将 schema 对象格式化为 LLM 可读的文本。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nl2sql.schema import SchemaMatcher, TableMatch
from nl2sql.schema.models import Column, Table

if TYPE_CHECKING:
    from ..state import AgentState


def _rank_column_relevance(col: Column, table: Table, query: str = "") -> float:
    """计算列的相关性得分，用于列截断时的优先级排序。

    得分越高越重要，截断时优先保留。
    评分规则（加分项）：
    - 主键列: +100
    - 外键列: +80
    - 常用维度列: +60（在 common_dimensions 中）
    - 有业务名称: +30
    - 有描述: +20
    - 有枚举值: +15
    - 语义类型为 amount/timestamp/category: +10 (比默认的 id/other 更有分析价值)
    - 查询关键词命中（简单包含）: +25
    """
    score = 0.0

    if col.is_primary_key:
        score += 100

    if col.is_foreign_key:
        score += 80

    if col.name in table.common_dimensions:
        score += 60

    if col.business_name:
        score += 30

    if col.description:
        score += 20

    if col.enum_values:
        score += 15

    if col.semantic_type in ("amount", "timestamp", "category"):
        score += 10

    if query and col.name.lower() in query.lower():
        score += 25
    if query and col.business_name and col.business_name.lower() in query.lower():
        score += 25

    return score


def _sort_columns_by_relevance(
    columns: list[Column],
    table: Table,
    query: str = "",
) -> list[Column]:
    """按相关性对列排序，高相关列在前。

    注意：主键列始终在最前，然后是高相关列，
    其余列尽量保持原始顺序（稳定排序）。
    """
    indexed = list(enumerate(columns))  # (original_index, column)
    indexed.sort(
        key=lambda pair: (
            -_rank_column_relevance(pair[1], table, query),  # 得分降序
            pair[0],  # 同分按原始顺序（稳定）
        )
    )
    return [col for _, col in indexed]


def _format_column_line(col: Column) -> str:
    """格式化单列信息为紧凑的一行。"""
    parts = [f"  · {col.name}: {col.type}"]

    # 标记
    markers = []
    if col.is_primary_key:
        markers.append("PK")
    if col.is_foreign_key:
        markers.append(f"FK→{col.foreign_key_table}.{col.foreign_key_column}")
    if markers:
        parts.append(f" [{', '.join(markers)}]")

    # 业务名称 / 描述
    desc = col.business_name or col.description
    if desc:
        parts.append(f" {desc}")

    # 语义类型
    if col.semantic_type:
        parts.append(f" [{col.semantic_type}]")

    # 统计信息
    stats = []
    if col.value_min is not None and col.value_max is not None:
        stats.append(f"范围: {col.value_min} ~ {col.value_max}")
    if col.enum_values:
        stats.append(f"枚举: {', '.join(col.enum_values[:5])}")
    if col.distinct_count is not None and col.top_values:
        top3 = ", ".join(
            f"{tv['value']}({tv['ratio']*100:.0f}%)"
            for tv in col.top_values[:3]
        )
        stats.append(f"{col.distinct_count} 个值, Top 3: {top3}")
    if col.null_rate is not None:
        non_null_pct = (1 - col.null_rate) * 100
        stats.append(f"非空 {non_null_pct:.1f}%")

    if stats:
        parts.append(" → " + ", ".join(stats))

    if col.calc_formula:
        parts.append(f" [口径: {col.calc_formula}]")

    return "".join(parts)


def _format_sample_rows(table: Table, max_rows: int = 3) -> list[str]:
    """格式化样例数据为表格形式。"""
    if not table.sample_rows:
        return []

    rows = table.sample_rows[:max_rows]
    if not rows:
        return []

    # 取前 5 列展示，避免太宽
    col_names = list(rows[0].keys())[:5]

    # 计算每列宽度
    col_widths = {c: len(c) for c in col_names}
    for row in rows:
        for c in col_names:
            val_str = str(row.get(c, ""))[:20]
            col_widths[c] = max(col_widths[c], len(val_str))

    lines = [f"样例数据（前 {len(rows)} 行）:"]

    # 表头
    header = "  " + " | ".join(c.ljust(col_widths[c]) for c in col_names)
    lines.append(header)
    lines.append("  " + "-+-".join("-" * col_widths[c] for c in col_names))

    # 数据行
    for row in rows:
        row_str = "  " + " | ".join(
            str(row.get(c, ""))[:20].ljust(col_widths[c]) for c in col_names
        )
        lines.append(row_str)

    return lines


def format_table_context(
    table: Table,
    max_columns: int | None = None,
    query: str = "",
) -> str:
    """格式化单表的详细 schema context。

    Args:
        table: 表对象
        max_columns: 最多显示多少列，None 表示全部显示
        query: 用户查询（用于列相关性排序，可选）

    Returns:
        格式化后的文本
    """
    lines = []

    # 表标题
    title = f"=== 表: {table.name}"
    if table.aliases:
        title += f"（别名: {', '.join(table.aliases)}）"
    title += " ==="
    lines.append(title)

    # 描述
    if table.description:
        lines.append(f"描述: {table.description}")

    # 业务域
    if table.business_domain:
        lines.append(f"业务域: {table.business_domain}")

    # 数据量级
    if table.row_count is not None:
        lines.append(f"数据量级: 约 {table.row_count:,} 行")

    # 常用维度
    if table.common_dimensions:
        lines.append(f"常用维度: {', '.join(table.common_dimensions)}")

    # 常用指标
    if table.common_metrics:
        metric_strs = [
            f"{m['name']}={m['expression']}" for m in table.common_metrics
        ]
        lines.append(f"常用指标: {', '.join(metric_strs)}")

    # 更新频率
    if table.update_frequency:
        lines.append(f"更新频率: {table.update_frequency}")

    # 列：按相关性排序后截断（高相关列在前）
    columns = list(table.columns)
    truncated = False
    if max_columns is not None and len(columns) > max_columns:
        # 只在需要截断时才排序，否则保持原始顺序
        columns = _sort_columns_by_relevance(columns, table, query)
        columns = columns[:max_columns]
        truncated = True

    lines.append("")
    lines.append(f"列（共 {len(table.columns)} 列）:")
    for col in columns:
        lines.append(_format_column_line(col))

    if truncated:
        hidden = len(table.columns) - max_columns
        lines.append(f"  ... 还有 {hidden} 列已省略（高相关列优先展示）")

    # 样例数据
    sample_lines = _format_sample_rows(table, max_rows=3)
    if sample_lines:
        lines.append("")
        lines.extend(sample_lines)

    return "\n".join(lines)


def build_detailed_schema_context(
    state: dict,
    max_columns_per_table: int = 15,
) -> tuple[str, str]:
    """构建详细的 schema context（用于 generate 节点）。

    Returns:
        (schema_text, db_type)
    """
    user_query = state.get("user_query", "") or ""

    # 确定哪些表需要展示
    intent_tables = []
    if state.get("intent") and state.get("intent").tables:
        intent_tables = [
            t.get("name", "") for t in state.get("intent").tables
            if isinstance(t, dict)
        ]

    matcher = SchemaMatcher(state["datasources"])

    selected_matches: list[TableMatch] = []
    if intent_tables:
        for ds in state["datasources"]:
            for tname in intent_tables:
                table = ds.db_schema.get_table(tname)
                if table:
                    selected_matches.append(
                        TableMatch(
                            datasource_id=ds.datasource_id,
                            table=table,
                            score=10.0,
                        )
                    )
    if not selected_matches:
        selected_matches = matcher.match_tables(state["user_query"], top_k=5)

    # 确定 db_type
    db_type = "mysql"
    if state["datasources"]:
        db_type = state["datasources"][0].datasource_type

    if not selected_matches:
        return "（无可用的表）", db_type

    lines = []
    current_ds = None
    for m in selected_matches:
        if m.datasource_id != current_ds:
            ds = next(
                (d for d in state["datasources"] if d.datasource_id == m.datasource_id),
                None,
            )
            if ds:
                lines.append(f"数据源: {ds.datasource_name} ({ds.datasource_id})")
                lines.append(f"类型: {ds.datasource_type}")
                lines.append("")
                current_ds = m.datasource_id

        tbl = m.table
        lines.append(format_table_context(
            tbl,
            max_columns=max_columns_per_table,
            query=user_query,
        ))
        lines.append("")

    return "\n".join(lines), db_type


def build_compact_schema_context(state: dict) -> str:
    """构建紧凑的 schema context（用于 intent 节点）。

    包含表名、别名、描述、列名列表。
    """
    matcher = SchemaMatcher(state["datasources"])
    matches = matcher.match_tables(state["user_query"], top_k=10)

    if not matches:
        return "（无匹配的表）"

    lines = []
    current_ds = None
    for m in matches:
        if m.datasource_id != current_ds:
            ds = next(
                (d for d in state["datasources"] if d.datasource_id == m.datasource_id),
                None,
            )
            if ds:
                lines.append(f"数据源: {ds.datasource_name} ({ds.datasource_id})")
                current_ds = m.datasource_id

        tbl = m.table
        alias_str = f"（别名: {', '.join(tbl.aliases)}）" if tbl.aliases else ""
        row_count_str = f" [约 {tbl.row_count:,} 行]" if tbl.row_count else ""
        lines.append(
            f"  表: {tbl.name}{alias_str}{row_count_str} - {tbl.description} "
            f"(score: {m.score:.1f})"
        )
        # 只显示前 10 个列名
        col_names = [col.name for col in tbl.columns[:10]]
        more = f" 等 {len(tbl.columns)} 列" if len(tbl.columns) > 10 else ""
        lines.append(f"    列: {', '.join(col_names)}{more}")

    return "\n".join(lines)


def inject_memories_into_context(
    schema_text: str,
    memories: list[dict],
) -> str:
    """将用户记忆注入到 schema context 文本中。

    - 术语/指标记忆 → 放在最前面作为"业务术语说明"区块
    - 表级记忆 → 追加在对应表描述后面
    - 列级记忆 → 追加在对应列行后面

    Args:
        schema_text: 原始 schema context 文本
        memories: 记忆列表

    Returns:
        注入记忆后的 schema context 文本
    """
    if not memories:
        return schema_text

    lines = schema_text.split("\n")
    result_lines = list(lines)

    # 分类记忆
    term_memories = [m for m in memories if m.get("memory_type") == "term_mapping"]
    metric_memories = [m for m in memories if m.get("memory_type") == "metric_definition"]
    table_memories = [m for m in memories if m.get("memory_type") == "table_description"]
    join_memories = [m for m in memories if m.get("memory_type") == "join_hint"]
    column_memories = [m for m in memories if m.get("memory_type") == "column_description"]

    # 1. 术语/指标记忆：放在最前面
    preamble_lines = []
    if term_memories or metric_memories:
        preamble_lines.append("业务术语说明（来自用户备注）：")
        for m in term_memories:
            date_str = _format_date(m.get("created_at", ""))
            preamble_lines.append(
                f"  · \"{m.get('entity_name', '')}\" = {m.get('content', '')}（{date_str}）"
            )
        for m in metric_memories:
            date_str = _format_date(m.get("created_at", ""))
            preamble_lines.append(
                f"  · 指标「{m.get('entity_name', '')}」: {m.get('content', '')}（{date_str}）"
            )
        preamble_lines.append("")

    # 2. 表级 + join 记忆：在对应表的描述行后注入
    if table_memories or join_memories:
        table_mem_map: dict[str, list[dict]] = {}
        for m in table_memories + join_memories:
            entity_name = m.get("entity_name", "")
            if entity_name:
                table_mem_map.setdefault(entity_name, []).append(m)

        i = 0
        while i < len(result_lines):
            line = result_lines[i]
            matched_table = None
            for table_name, mems in table_mem_map.items():
                if f"=== 表: {table_name}" in line or line.startswith(f"表: {table_name}"):
                    matched_table = table_name
                    break
            if matched_table:
                # 找到下一个"描述:"行
                j = i + 1
                while j < len(result_lines) and "描述:" not in result_lines[j]:
                    j += 1
                if j < len(result_lines):
                    mems = table_mem_map[matched_table]
                    # 在描述行之后插入
                    insert_pos = j + 1
                    for mem in mems:
                        date_str = _format_date(mem.get("created_at", ""))
                        result_lines.insert(
                            insert_pos,
                            f"📝 用户备注: {mem.get('content', '')}（{date_str}）",
                        )
                        insert_pos += 1
            i += 1

    # 3. 列级记忆：在对应列行后注入
    if column_memories:
        col_mem_map: dict[str, list[dict]] = {}
        for m in column_memories:
            entity_name = m.get("entity_name", "")
            if entity_name:
                # entity_name 格式可能是 table.column 或 column
                if "." in entity_name:
                    col_part = entity_name.split(".")[-1]
                else:
                    col_part = entity_name
                col_mem_map.setdefault(col_part, []).append(m)

        new_lines = []
        for line in result_lines:
            new_lines.append(line)
            # 匹配 "  · col_name: ..." 格式的列行
            stripped = line.lstrip()
            if stripped.startswith("· "):
                # 提取列名（到冒号为止）
                col_part = stripped[2:].split(":")[0].strip()
                if col_part in col_mem_map:
                    for mem in col_mem_map[col_part]:
                        date_str = _format_date(mem.get("created_at", ""))
                        new_lines.append(
                            f"      📝 用户备注: {mem.get('content', '')}（{date_str}）"
                        )
        result_lines = new_lines

    # 组合：术语区块 + 原内容
    if preamble_lines:
        final_lines = preamble_lines + result_lines
    else:
        final_lines = result_lines

    return "\n".join(final_lines)


def _format_date(date_str: str) -> str:
    """格式化日期为简短形式。"""
    if not date_str:
        return ""
    # 2026-08-20 10:30:00 → 2026-08-20
    if " " in date_str:
        return date_str.split(" ")[0]
    if "T" in date_str:
        return date_str.split("T")[0]
    if len(date_str) >= 10:
        return date_str[:10]
    return date_str
