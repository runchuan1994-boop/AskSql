"""SQL generation node: generate SQL from intent and schema context."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client
from nl2sql.schema import SchemaMatcher
from ._step_utils import step_start, step_complete, step_error

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

GENERATE_SYSTEM_PROMPT = """你是一位资深 SQL 工程师，擅长根据自然语言描述编写高质量的 SQL 查询。

规则：
1. 只生成 SELECT 查询，不要生成 INSERT/UPDATE/DELETE 等写操作。
2. 严格按照提供的表结构和列名编写 SQL，不要使用不存在的表或列。
3. 注意 SQL 方言：{db_type}
4. 输出格式：用 ```sql ... ``` 包裹 SQL 语句。
5. 只输出一个最终的 SQL 语句，不要输出多个备选。
6. 如果有示例查询，可以参考其风格和模式。
7. 尽量使用明确的列名，避免 SELECT *。
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_sql_from_text(text: str) -> str:
    """Extract SQL from text, handling markdown code block wrappers.

    Handles:
    - ```sql ... ```
    - ``` ... ```
    - plain SQL text
    """
    # Try sql code block first
    match = re.search(r"```sql\s*\n?(.*?)\n?```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Try generic code block
    match = re.search(r"```\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: return as-is
    return text.strip()


def _build_detailed_schema_context(state: dict) -> tuple[str, str]:
    """Build detailed schema context and determine db_type.

    Returns:
        (schema_text, db_type)
    """
    # Determine which tables to use
    intent_tables = []
    if state.get("intent") and state.get("intent").tables:
        intent_tables = [t.get("name", "") for t in state.get("intent").tables if isinstance(t, dict)]

    matcher = SchemaMatcher(state["datasources"])

    # If we have intent tables, use those; otherwise match by query
    selected_matches = []
    if intent_tables:
        for ds in state["datasources"]:
            for tname in intent_tables:
                table = ds.db_schema.get_table(tname)
                if table:
                    from nl2sql.schema.matcher import TableMatch
                    selected_matches.append(
                        TableMatch(datasource_id=ds.datasource_id, table=table, score=10.0)
                    )
    if not selected_matches:
        selected_matches = matcher.match_tables(state["user_query"], top_k=5)

    # Determine db_type (use first datasource's type)
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
                current_ds = m.datasource_id

        tbl = m.table
        lines.append("")
        lines.append(f"表: {tbl.name}")
        lines.append(f"描述: {tbl.description}")
        lines.append("列:")
        for col in tbl.columns:
            markers = []
            if col.is_primary_key:
                markers.append("PK")
            if col.is_foreign_key:
                markers.append(f"FK -> {col.foreign_key_table}.{col.foreign_key_column}")
            marker_str = f" [{', '.join(markers)}]" if markers else ""
            sem_type = f" ({col.semantic_type})" if col.semantic_type else ""
            enum_str = ""
            if col.enum_values:
                enum_str = f" 枚举值: {', '.join(col.enum_values)}"
            lines.append(f"  - {col.name}: {col.type}{marker_str}{sem_type} - {col.description}{enum_str}")

        if tbl.examples:
            lines.append("示例数据:")
            for ex in tbl.examples:
                lines.append(f"  {ex}")

    return "\n".join(lines), db_type


def _build_probe_findings_text(state: dict) -> str:
    """Build probe findings text for context."""
    if not state.get("probe_findings", []):
        return ""
    lines = ["探查发现："]
    for f in state.get("probe_findings", []):
        lines.append(f"- [{f.action}] {f.table}: {f.finding}")
        if f.sql:
            lines.append(f"  SQL: {f.sql}")
    return "\n".join(lines)


def _send_event(state: dict, event_type: str, data: dict | None = None) -> None:
    """Send an event via callback if set."""
    callback = getattr(state, "event_callback", None)
    if callback is not None:
        try:
            callback(event_type, data or {})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def generate_sql_node(state: dict) -> dict:
    """Generate SQL from intent and schema context.

    Returns:
        dict with "sql" and "status"
    """
    iteration = state.get("iteration", 0) + 1
    step_label = f"生成 SQL（第 {iteration} 轮）" if iteration > 1 else "生成 SQL"
    t0 = step_start(state, "sql_generated", step_label)

    try:
        schema_context, db_type = _build_detailed_schema_context(state)
        probe_text = _build_probe_findings_text(state)

        # Build error context from last execution failure
        error_context = ""
        if state.get("execution_result") and not state.get("execution_result").success:
            error_context = (
                f"上次执行的 SQL 出错了，请修正：\n"
                f"  原 SQL: {state.get("sql")}\n"
                f"  错误信息: {state.get("execution_result").error}\n"
            )

        # Build conversation history (for multi-turn)
        history_text = ""
        if state.get("conversation_history", []):
            history_lines = []
            for msg in state.get("conversation_history", [])[-6:]:  # last 6 messages
                if msg.role == MessageRole.USER:
                    history_lines.append(f"用户: {msg.content}")
                elif msg.role == MessageRole.ASSISTANT:
                    history_lines.append(f"助手: {msg.content}")
            if history_lines:
                history_text = "对话历史：\n" + "\n".join(history_lines) + "\n"

        user_msg_parts = []
        if history_text:
            user_msg_parts.append(history_text)
        user_query = state["user_query"]
        user_msg_parts.extend([
            f"用户查询：{user_query}",
            "",
            f"数据库表结构：\n{schema_context}",
        ])
        if probe_text:
            user_msg_parts.extend(["", probe_text])
        if error_context:
            user_msg_parts.extend(["", error_context])
        user_msg_parts.extend([
            "",
            "请生成正确的 SQL 查询，用 ```sql ... ``` 包裹输出。",
        ])
        user_msg = "\n".join(user_msg_parts)

        system_prompt = GENERATE_SYSTEM_PROMPT.format(db_type=db_type)
        messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=user_msg),
        ]

        llm = create_llm_client()
        response = llm.chat(messages, temperature=0.0)

        sql = extract_sql_from_text(response.content)

        _send_event(state, "sql_generated", {"sql": sql})

        step_complete(state, "sql_generated", step_label, {
            "sql": sql,
            "iteration": iteration,
        }, t0)

        return {"sql": sql, "status": "thinking"}
    except Exception as e:
        step_error(state, "sql_generated", step_label, str(e), t0)
        raise
