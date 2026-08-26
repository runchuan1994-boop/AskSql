"""SQL generation node: generate SQL from intent and schema context."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client
from ._schema_context import build_detailed_schema_context, inject_memories_into_context
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

**数据可读性原则（重要）**：

生成的 SQL 结果应当便于人类阅读，遵循以下原则（在不牺牲正确性的前提下）：

8. **给计算/聚合列起有意义的别名**：
   - 不要用 `count`、`sum`、`total`、`col1` 等模糊名称
   - 用能表达业务含义的名字，如 `monthly_sales`、`active_user_count`、`avg_order_amount`
   - 别名风格与数据库中已有列保持一致（蛇形或驼峰参照已有表结构）

9. **日期/时间字段按粒度格式化**：
   - 按年聚合 → 格式化为年份（如 2024）
   - 按月聚合 → 格式化为年-月（如 2024-01）
   - 按日聚合 → 格式化为年-月-日（如 2024-01-15）
   - 不要返回带时分秒的时间戳给按天/按月的统计结果
   - 使用当前数据库方言的日期格式化函数（如 PostgreSQL 用 TO_CHAR，MySQL 用 DATE_FORMAT，SQLite 用 strftime）

10. **数值精度合理**：
    - 金额类：保留 2 位小数
    - 百分比/比率：保留 1-2 位小数
    - 计数/整数类：不要有小数
    - 使用 ROUND / CAST 等函数控制精度，避免返回多位小数

11. **排序符合直觉**：
    - 时间趋势类 → 按时间正序（从早到晚）
    - Top N / 排名类 → 按数值倒序（从大到小）
    - 分类对比类 → 按数值倒序或按分类名正序
    - 不要返回无意义顺序的结果

12. **百分比/比率类用可读形式**：
    - 如果是比例，乘以 100 并保留 1-2 位小数，让人一眼看懂（如 23.5 而不是 0.234567）
    - 别名里注明是百分比（如 `growth_rate_pct`）

注意：以上是"可读性"优化建议，优先级低于"正确性"。如果不确定最佳格式，以查询正确为第一原则，不要为了可读性引入计算错误。
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


def _send_event(state: dict | Any, event_type: str, data: dict | None = None) -> None:
    """Send an event via callback if set.

    Compatible with both dict state (LangGraph runtime) and Pydantic model state (tests).
    """
    if isinstance(state, dict):
        callback = state.get("event_callback")
    else:
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
        schema_context, db_type = build_detailed_schema_context(state)
        probe_text = _build_probe_findings_text(state)

        # 召回用户记忆并注入 schema context
        memory_retriever = state.get("memory_retriever")
        if memory_retriever and callable(memory_retriever):
            related_table_names = []
            if state.get("intent") and state.get("intent").tables:
                related_table_names = [
                    t.get("name", "") for t in state["intent"].tables
                    if isinstance(t, dict)
                ]
            try:
                memories = memory_retriever(
                    query=state["user_query"],
                    related_tables=related_table_names,
                )
                if memories:
                    schema_context = inject_memories_into_context(schema_context, memories)
            except Exception:
                # 记忆召回失败不影响主流程
                pass

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
