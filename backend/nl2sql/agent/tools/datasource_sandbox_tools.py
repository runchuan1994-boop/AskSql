"""基于沙盒的数据源管理工具.

和 datasource_tools.py 的区别：
- test_connection 在沙盒里执行，可以动态安装驱动
- install_driver 在沙盒里 pip install 数据库驱动
- 驱动不会污染主进程环境
- 配合 DatasourceConnectorAgent 使用，Agent 可以自主决定装什么驱动

注意：
- 数据源创建、schema 导入等操作仍然在主进程做（datasource_tools.py）
- 只有需要驱动的连接测试在沙盒里做
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..state import AgentState


# ---------------------------------------------------------------------------
# 工具定义（OpenAI function-calling 格式）
# ---------------------------------------------------------------------------

SANDBOX_DATASOURCE_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "install_driver",
            "description": (
                "在沙盒中安装数据库驱动（pip install）。"
                "当连接测试失败且提示缺少驱动模块时，可以调用此工具安装对应的驱动，然后重试连接。"
                "安装成功后应该再次调用 test_connection 验证。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "package": {
                        "type": "string",
                        "description": (
                            "要安装的 Python 包名，例如："
                            "psycopg2-binary (PostgreSQL), "
                            "mysql-connector-python (MySQL), "
                            "pymysql (MySQL 轻量版)"
                        ),
                    },
                    "datasource_id": {
                        "type": "string",
                        "description": "数据源 ID（可选，用于关联）",
                    },
                },
                "required": ["package"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "test_connection_sandbox",
            "description": (
                "在沙盒环境中测试数据库连接。"
                "沙盒里可以动态安装驱动，适合验证驱动是否可用。"
                "如果失败且提示缺少驱动，可以先调用 install_driver 安装驱动，再重试。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "db_url": {
                        "type": "string",
                        "description": "数据库连接 URL，例如 postgresql://user:pass@host:port/dbname",
                    },
                },
                "required": ["db_url"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# 错误分类
# ---------------------------------------------------------------------------

def classify_connection_error(error_message: str) -> dict:
    """将连接错误信息结构化分类，帮助 Agent 诊断问题.

    Args:
        error_message: 原始错误信息字符串

    Returns:
        结构化错误信息字典:
        - error_type: 错误类型（driver_missing / authentication_failed / ...）
        - error_message: 原始错误信息
        - missing_module: 缺少的模块名（仅 driver_missing 类型）
        - db_type_hint: 推测的数据库类型
        - human_readable: 人类可读的简短描述
    """
    error_lower = error_message.lower()
    result = {
        "error_type": "unknown",
        "error_message": error_message,
        "missing_module": None,
        "db_type_hint": None,
        "human_readable": error_message[:200],
    }

    # --- 驱动缺失 ---
    driver_missing_patterns = [
        "no module named",
        "modulenotfounderror",
        "module not found",
        "cannot load driver",
        "driver not found",
        "could not load driver",
    ]
    if any(p in error_lower for p in driver_missing_patterns):
        result["error_type"] = "driver_missing"
        # 尝试提取缺失的模块名
        import re
        # 匹配 "No module named 'xxx'" 或 "ModuleNotFoundError: No module named 'xxx'"
        m = re.search(r"no module named ['\"]?([\w\.\-]+)", error_lower)
        if m:
            result["missing_module"] = m.group(1).strip()
        # 推测数据库类型
        for db_type, keywords in _DB_TYPE_KEYWORDS.items():
            if any(k in error_lower for k in keywords):
                result["db_type_hint"] = db_type
                break

    # --- 认证失败 ---
    auth_failed_patterns = [
        "password authentication",
        "access denied for user",
        "authentication failed",
        "invalid password",
        "login failed",
        "peer authentication failed",
    ]
    if any(p in error_lower for p in auth_failed_patterns):
        result["error_type"] = "authentication_failed"

    # --- 连接拒绝 ---
    conn_refused_patterns = [
        "connection refused",
        "errno 61",
        "could not connect to server",
        "connection could not be established",
        "failed to connect",
        "can't connect to",
    ]
    if any(p in error_lower for p in conn_refused_patterns):
        result["error_type"] = "connection_refused"

    # --- 数据库不存在 ---
    db_not_found_patterns = [
        "database \"",
        "does not exist",
        "unknown database",
        "database not found",
        "no such database",
    ]
    if any(p in error_lower for p in db_not_found_patterns) and "exist" in error_lower:
        result["error_type"] = "database_not_found"

    # --- 网络超时 ---
    timeout_patterns = [
        "timeout",
        "timed out",
        "operation timed out",
        "connection timed out",
    ]
    if any(p in error_lower for p in timeout_patterns):
        result["error_type"] = "network_timeout"

    # --- 生成人类可读描述 ---
    type_descriptions = {
        "driver_missing": f"缺少数据库驱动模块 ({result['missing_module'] or '未知'})",
        "authentication_failed": "认证失败（用户名或密码错误）",
        "connection_refused": "连接被拒绝（主机或端口不可达）",
        "database_not_found": "数据库不存在",
        "network_timeout": "网络连接超时",
        "unknown": "未知错误",
    }
    result["human_readable"] = type_descriptions.get(result["error_type"], "未知错误")

    return result


# 数据库类型关键词映射（用于从错误信息中推测数据库类型）
_DB_TYPE_KEYWORDS: dict[str, list[str]] = {
    "postgresql": ["psycopg", "postgresql", "pg_", "pgsql"],
    "mysql": ["mysql", "mysqldb", "pymysql", "mysqlconnector"],
    "sqlite": ["sqlite", "sqlite3"],
    "oracle": ["oracle", "cx_oracle", "oracledb"],
    "sqlserver": ["pyodbc", "pymssql", "mssql", "sql server"],
}


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------

def _get_sandbox_manager():
    """延迟导入沙盒管理器，避免没有 docker 环境时报错."""
    from sandbox.manager import get_sandbox_manager
    return get_sandbox_manager()


def _is_sandbox_available(state: dict) -> bool:
    """检查沙盒是否可用."""
    # 从 state 中检查是否配置了沙盒
    # 简化处理：尝试导入 sandbox 模块，能导入且配置启用了就算可用
    try:
        from sandbox.config import SandboxConfig
        config = SandboxConfig.from_env()
        return config.enabled
    except (ImportError, Exception):
        return False


def install_driver(
    state: dict,
    package: str,
    datasource_id: str | None = None,
) -> str:
    """在沙盒中安装数据库驱动.

    Args:
        state: Agent state
        package: pip 包名
        datasource_id: 可选的数据源 ID

    Returns:
        安装结果描述
    """
    if not _is_sandbox_available(state):
        return (
            "沙盒环境未启用，无法动态安装驱动。\n"
            "请管理员在服务器上手动安装：\n"
            f"  pip install {package}\n"
            "安装完成后再重试连接。"
        )

    try:
        manager = _get_sandbox_manager()
        sandbox = manager.acquire()
    except Exception as e:
        return f"获取沙盒失败：{e}\n无法安装驱动 {package}。"

    try:
        success = sandbox.install_driver(package)
        if success:
            return (
                f"驱动安装成功：{package}\n"
                "现在可以调用 test_connection_sandbox 测试连接是否正常。"
            )
        else:
            return (
                f"驱动安装失败：{package}\n"
                "请检查包名是否正确，或尝试其他可用的驱动包。\n"
                "常见驱动包：\n"
                "  - PostgreSQL: psycopg2-binary\n"
                "  - MySQL: mysql-connector-python / pymysql\n"
                "  - SQLite: 内置，无需安装"
            )
    except Exception as e:
        return f"安装驱动时出错：{e}"
    finally:
        manager.release(sandbox)


def _adjust_db_url_for_sandbox(db_url: str) -> tuple[str, str | None]:
    """调整数据库 URL 以适应沙盒环境.

    沙盒运行在 Docker 容器内，localhost/127.0.0.1 指向沙盒自己而非宿主机。
    需要替换为 host.docker.internal 才能访问宿主机上映射的端口。

    Args:
        db_url: 原始数据库连接 URL

    Returns:
        (调整后的 URL, 调整说明或 None)
    """
    from urllib.parse import urlparse, urlunparse

    try:
        parsed = urlparse(db_url)
        hostname = parsed.hostname or ""

        if hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
            # 替换为 host.docker.internal（Docker 桌面/引擎提供的宿主机别名）
            netloc = parsed.netloc.replace(hostname, "host.docker.internal", 1)
            new_url = urlunparse(parsed._replace(netloc=netloc))
            note = f"沙盒环境下已将 {hostname} 自动转换为 host.docker.internal"
            return new_url, note

        return db_url, None
    except Exception:
        # URL 解析失败就原样返回
        return db_url, None


def test_connection_sandbox(
    state: dict,
    db_url: str,
) -> str:
    """在沙盒中测试数据库连接.

    Args:
        state: Agent state
        db_url: 数据库连接 URL

    Returns:
        连接测试结果描述（包含结构化错误信息，便于 Agent 诊断）
    """
    import json

    if not _is_sandbox_available(state):
        return (
            "沙盒环境未启用，无法在沙盒中测试连接。\n"
            "请改用常规的 test_connection 工具，或联系管理员启用沙盒。"
        )

    # 调整 URL 以适应沙盒环境（localhost → host.docker.internal）
    adjusted_url, adjust_note = _adjust_db_url_for_sandbox(db_url)

    try:
        manager = _get_sandbox_manager()
        sandbox = manager.acquire()
    except Exception as e:
        return f"获取沙盒失败：{e}"

    try:
        # 沙盒的 test_connection 只返回 bool，拿不到具体错误
        # 我们用 execute_sql 执行 SELECT 1 来获取详细错误
        result = sandbox.execute_sql(adjusted_url, "SELECT 1", timeout_seconds=10)

        if result.get("success", False):
            lines = ["✅ 连接测试成功", "沙盒环境可以正常连接到数据库。"]
            if adjust_note:
                lines.append(f"ℹ️  {adjust_note}")
            lines.append(f"测试地址：{db_url}")
            if adjusted_url != db_url:
                lines.append(f"实际连接地址：{adjusted_url}")
            return "\n".join(lines)
        else:
            error_msg = result.get("error", "未知错误")
            error_info = classify_connection_error(error_msg)

            lines = ["❌ 连接测试失败"]
            if adjust_note:
                lines.append(f"ℹ️  {adjust_note}")
            lines.extend([
                f"错误类型: {error_info['error_type']}",
                f"错误描述: {error_info['human_readable']}",
                f"详细信息: {error_msg}",
                "",
                f"结构化诊断信息 (JSON):\n{json.dumps(error_info, ensure_ascii=False, indent=2)}",
            ])
            return "\n".join(lines)
    except Exception as e:
        error_info = classify_connection_error(str(e))
        lines = ["❌ 连接测试异常"]
        if adjust_note:
            lines.append(f"ℹ️  {adjust_note}")
        lines.extend([
            f"错误类型: {error_info['error_type']}",
            f"错误描述: {error_info['human_readable']}",
            f"详细信息: {e}",
            "",
            f"结构化诊断信息 (JSON):\n{json.dumps(error_info, ensure_ascii=False, indent=2)}",
        ])
        return "\n".join(lines)
    finally:
        manager.release(sandbox)


# ---------------------------------------------------------------------------
# 函数映射表
# ---------------------------------------------------------------------------

SANDBOX_DATASOURCE_TOOL_FUNCTIONS: dict[str, callable] = {
    "install_driver": install_driver,
    "test_connection_sandbox": test_connection_sandbox,
}
