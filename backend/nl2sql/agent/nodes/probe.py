"""Probe node: use lightweight SQL to resolve technical ambiguities."""
from __future__ import annotations

from typing import TYPE_CHECKING

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client
from nl2sql.agent.tools.probe_tools import PROBE_TOOLS_DEFINITION, PROBE_TOOL_FUNCTIONS

from ..state import ProbeFinding
from ._step_utils import step_start, step_complete, step_error

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

PROBE_SYSTEM_PROMPT = """你是一个数据探查助手，负责通过轻量 SQL 探查来消除查询中的技术歧义。

任务：
1. 根据意图分析中的歧义点，选择合适的探查工具来验证数据。
2. 可以使用的工具：probe_distinct, probe_sample, probe_min_max, probe_count
3. 每次探查解决一个具体的技术歧义。
4. 只解决技术层面的歧义（如列的可选值、数据范围、表的行数等）。
5. 业务语义层面的歧义（如"活跃用户"的定义）无法通过探查解决，交给澄清环节。

如果不需要探查，直接回复"无需探查"，不要调用任何工具。
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _send_event(state: dict, event_type: str, data: dict | None = None) -> None:
    """Send an event via callback if set."""
    callback = getattr(state, "event_callback", None)
    if callback is not None:
        try:
            callback(event_type, data or {})
        except Exception:
            pass


def _build_schema_for_probe(state: dict) -> str:
    """Build compact schema info for probe context."""
    if not state["datasources"]:
        return ""
    # Show tables from first datasource (compact)
    ds = state["datasources"][0]
    lines = [f"数据源: {ds.datasource_name} ({ds.datasource_id})"]
    for tbl in ds.db_schema.tables[:10]:
        col_names = [c.name for c in tbl.columns[:8]]
        extra = "..." if len(tbl.columns) > 8 else ""
        lines.append(f"  - {tbl.name}: {', '.join(col_names)}{extra}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

def intent_probe_node(state: dict) -> dict:
    """Run probe queries to resolve technical ambiguities.

    Returns:
        dict with probe_findings list and probe_iteration
    """
    t0 = step_start(state, "intent_probe", "数据探查")

    try:
        intent = state.get("intent")
        ambiguities = intent.ambiguities if intent else []

        # Skip if no ambiguities or max iterations reached
        if not ambiguities or state.get("probe_iteration", 0) >= state.get("max_probe_iterations", 3):
            step_complete(state, "intent_probe", "数据探查", {
                "probed_tables": [],
                "findings_count": 0,
                "findings": [],
                "skipped": True,
                "reason": "无歧义或已达最大迭代次数",
            }, t0)
            return {
                "probe_findings": state.get("probe_findings", []),
                "probe_iteration": state.get("probe_iteration", 0) + 1,
            }

        schema_info = _build_schema_for_probe(state)

        # Build previous findings context
        prev_findings = ""
        if state.get("probe_findings", []):
            lines = ["已有的探查发现："]
            for f in state.get("probe_findings", []):
                lines.append(f"- {f.action}({f.table}): {f.finding}")
            prev_findings = "\n".join(lines) + "\n\n"

        user_query = state["user_query"]
        user_msg = f"""{prev_findings}用户查询：{user_query}

意图分析发现的歧义：
{chr(10).join(f"- {a}" for a in ambiguities)}

{schema_info}

请判断是否需要进行数据探查来消除技术层面的歧义。
如果需要，请调用合适的探查工具。如果不需要，直接回复"无需探查"。"""

        messages = [
            Message(role=MessageRole.SYSTEM, content=PROBE_SYSTEM_PROMPT),
            Message(role=MessageRole.USER, content=user_msg),
        ]

        llm = create_llm_client()
        response = llm.chat(
            messages,
            tools=PROBE_TOOLS_DEFINITION,
            temperature=0.0,
        )

        new_findings = list(state.get("probe_findings", []))

        # Execute tool calls if any
        if response.tool_calls:
            for tool_call in response.tool_calls:
                func_name = tool_call.name
                func = PROBE_TOOL_FUNCTIONS.get(func_name)
                if func is None:
                    continue

                # Determine datasource_id
                args = dict(tool_call.arguments)
                ds_id = args.pop("datasource_id", None) or state.get("selected_datasource_id")

                try:
                    result_str = func(state, **args)
                    table_name = args.get("table_name", "unknown")

                    new_findings.append(ProbeFinding(
                        action=func_name,
                        table=table_name,
                        datasource_id=ds_id or (state["datasources"][0].datasource_id if state["datasources"] else ""),
                        finding=result_str,
                        sql="",
                    ))
                except Exception as e:
                    new_findings.append(ProbeFinding(
                        action=func_name,
                        table=args.get("table_name", "unknown"),
                        datasource_id=ds_id or "",
                        finding=f"探查失败: {e}",
                        sql="",
                    ))

        new_count = len(new_findings) - len(state.get("probe_findings", []))
        new_finding_objs = new_findings[len(state.get("probe_findings", [])):]

        _send_event(state, "intent_probe", {
            "findings_count": new_count,
            "findings": [
                {"action": f.action, "table": f.table, "finding": f.finding[:200]}
                for f in new_finding_objs
            ],
        })

        probed_tables = list({f.table for f in new_finding_objs})
        step_complete(state, "intent_probe", "数据探查", {
            "probed_tables": probed_tables,
            "findings_count": new_count,
            "findings": [f.finding[:200] for f in new_finding_objs],
        }, t0)

        return {
            "probe_findings": new_findings,
            "probe_iteration": state.get("probe_iteration", 0) + 1,
        }
    except Exception as e:
        step_error(state, "intent_probe", "数据探查", str(e), t0)
        raise
