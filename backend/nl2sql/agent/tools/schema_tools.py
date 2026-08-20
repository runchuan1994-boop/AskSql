"""Schema-related tools for the agent."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

SCHEMA_TOOLS_DEFINITION: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "List all tables in a datasource schema, with table names and descriptions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "datasource_id": {
                        "type": "string",
                        "description": "ID of the datasource. If not provided, uses the first datasource.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_table",
            "description": "Get detailed structure of a table, including columns, types, keys and descriptions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table to describe.",
                    },
                    "datasource_id": {
                        "type": "string",
                        "description": "ID of the datasource. If not provided, uses the first datasource.",
                    },
                },
                "required": ["table_name"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_datasource(state: "AgentState", datasource_id: str | None = None):
    """Return the matching DatasourceSchema, or None."""
    if not state["datasources"]:
        return None
    if datasource_id:
        for ds in state["datasources"]:
            if ds.datasource_id == datasource_id:
                return ds
        return None
    # default to first
    return state["datasources"][0]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def list_tables(state: "AgentState", datasource_id: str | None = None) -> str:
    """List all tables in the datasource."""
    ds = _get_datasource(state, datasource_id)
    if ds is None:
        return f"未找到 datasource_id={datasource_id or '(default)'} 的数据源。"

    schema = ds.db_schema
    if not schema.tables:
        return "当前数据源中没有表。"

    lines = [f"数据源: {ds.datasource_name} ({ds.datasource_id})", ""]
    for tbl in schema.tables:
        lines.append(f"- {tbl.name}: {tbl.description}")
    return "\n".join(lines)


def describe_table(state: "AgentState", table_name: str, datasource_id: str | None = None) -> str:
    """Describe the structure of a table."""
    ds = _get_datasource(state, datasource_id)
    if ds is None:
        return f"未找到 datasource_id={datasource_id or '(default)'} 的数据源。"

    table = ds.db_schema.get_table(table_name)
    if table is None:
        return f"未找到表 '{table_name}'。可用的表: {', '.join(ds.db_schema.table_names)}"

    lines = [f"表: {table.name}", f"描述: {table.description}", "", "列:"]
    for col in table.columns:
        markers = []
        if col.is_primary_key:
            markers.append("PK")
        if col.is_foreign_key:
            markers.append("FK")
        marker_str = f" [{', '.join(markers)}]" if markers else ""
        desc = f" - {col.description}" if col.description else ""
        lines.append(f"  {col.name} ({col.type}){marker_str}{desc}")

    if table.examples:
        lines.append("")
        lines.append("示例数据:")
        for ex in table.examples:
            lines.append(f"  {ex}")

    return "\n".join(lines)
