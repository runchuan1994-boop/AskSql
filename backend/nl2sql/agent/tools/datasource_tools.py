"""Datasource management tools for the agent.

Provides tools to create, test, and import schemas for datasources.
Uses delayed import to avoid circular dependencies with app.services.
"""
from __future__ import annotations

import json


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

DATASOURCE_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "create_datasource",
            "description": "Create a new datasource connection in the current project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the datasource.",
                    },
                    "type": {
                        "type": "string",
                        "description": "Database type (mysql, postgresql, sqlite, etc.).",
                    },
                    "host": {
                        "type": "string",
                        "description": "Host address of the database server.",
                    },
                    "port": {
                        "type": "integer",
                        "description": "Port number of the database server.",
                    },
                    "database": {
                        "type": "string",
                        "description": "Database name (or file path for sqlite).",
                    },
                    "username": {
                        "type": "string",
                        "description": "Username for database authentication.",
                    },
                    "password": {
                        "type": "string",
                        "description": "Password for database authentication.",
                    },
                },
                "required": ["name", "type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "test_connection",
            "description": "Test the connection of an existing datasource by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "datasource_id": {
                        "type": "string",
                        "description": "ID of the datasource to test.",
                    },
                },
                "required": ["datasource_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "import_schema",
            "description": "Import schema (tables and columns) from an existing datasource.",
            "parameters": {
                "type": "object",
                "properties": {
                    "datasource_id": {
                        "type": "string",
                        "description": "ID of the datasource to import schema from.",
                    },
                },
                "required": ["datasource_id"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

def execute_datasource_tool(name: str, args: dict, project_id: str) -> str:
    """Execute a datasource tool by name.

    Args:
        name: Tool name (create_datasource, test_connection, import_schema)
        args: Tool arguments as a dict
        project_id: The project context

    Returns:
        Formatted result string
    """
    # Delayed imports to avoid circular dependency with app.services
    from app.services import datasource_service
    from app.services import schema_import

    if name == "create_datasource":
        return _create_datasource(args, project_id, datasource_service)
    elif name == "test_connection":
        return _test_connection(args, datasource_service)
    elif name == "import_schema":
        return _import_schema(args, schema_import)
    else:
        return f"错误: 未知的数据源工具 '{name}'。"


def _create_datasource(args: dict, project_id: str, datasource_service) -> str:
    """Create a datasource and return the result as formatted text."""
    try:
        result = datasource_service.create_datasource(
            project_id=project_id,
            name=args.get("name", ""),
            ds_type=args.get("type", "sqlite"),
            host=args.get("host", ""),
            port=args.get("port"),
            database=args.get("database", ""),
            username=args.get("username", ""),
            password=args.get("password", ""),
        )
        return (
            f"数据源创建成功：\n"
            f"  ID: {result.get('id')}\n"
            f"  名称: {result.get('name')}\n"
            f"  类型: {result.get('type')}\n"
            f"  主机: {result.get('host')}\n"
            f"  端口: {result.get('port')}\n"
            f"  数据库: {result.get('database')}\n"
            f"  用户名: {result.get('username')}"
        )
    except Exception as e:
        return f"创建数据源失败: {e}"


def _test_connection(args: dict, datasource_service) -> str:
    """Test a datasource connection and return the result as formatted text."""
    datasource_id = args.get("datasource_id", "")
    if not datasource_id:
        return "错误: 缺少 datasource_id 参数。"

    try:
        success, message = datasource_service.test_connection_by_id(datasource_id)
        if success:
            return f"连接测试成功: {message}"
        else:
            return f"连接测试失败: {message}"
    except Exception as e:
        return f"连接测试异常: {e}"


def _import_schema(args: dict, schema_import) -> str:
    """Import schema from a datasource and return the result as formatted text."""
    datasource_id = args.get("datasource_id", "")
    if not datasource_id:
        return "错误: 缺少 datasource_id 参数。"

    try:
        result = schema_import.import_schema_from_database(datasource_id)
        if result.get("success"):
            table_count = result.get("table_count", 0)
            tables = result.get("tables", [])
            lines = [f"Schema 导入成功，共 {table_count} 张表：", ""]
            for t in tables:
                lines.append(f"  - {t['name']} ({t['column_count']} 列)")
            return "\n".join(lines)
        else:
            return f"Schema 导入失败: {result.get('error', '未知错误')}"
    except Exception as e:
        return f"Schema 导入异常: {e}"
