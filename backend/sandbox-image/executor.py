#!/usr/bin/env python3
"""沙盒内的 SQL 执行器.

跑在 Docker 容器里，从 stdin 读取 JSON-RPC 请求，执行后写到 stdout。

支持的方法：
- ping: 健康检查
- execute_sql: 执行 SQL
- test_connection: 测试数据库连接
- install_driver: pip install 数据库驱动
"""
from __future__ import annotations

import datetime
import decimal
import json
import subprocess
import sys
import time
import uuid
from uuid import UUID


def _json_default(obj):
    """json.dumps 默认序列化函数：处理非 JSON 原生类型."""
    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        # 用 float 可能丢失精度，但 JSON 没有原生 Decimal 类型
        # 用字符串更安全，主进程可以按需转换
        return float(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.hex()
    if hasattr(obj, "__str__"):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _jsonify_rows(rows):
    """将行数据中的非 JSON 类型转换为可序列化类型.

    相比于依赖 json.dumps 的 default 参数，
    提前转换可以确保返回结构在主进程端也是一致的基本类型。
    """
    result = []
    for row in rows:
        new_row = []
        for val in row:
            if val is None:
                new_row.append(None)
            elif isinstance(val, bool):
                new_row.append(val)
            elif isinstance(val, (int, float)):
                new_row.append(val)
            elif isinstance(val, str):
                new_row.append(val)
            elif isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
                new_row.append(val.isoformat())
            elif isinstance(val, decimal.Decimal):
                new_row.append(float(val))
            elif isinstance(val, UUID):
                new_row.append(str(val))
            elif isinstance(val, bytes):
                new_row.append(val.hex())
            else:
                new_row.append(str(val))
        result.append(new_row)
    return result


def _send_response(resp_id: str, success: bool, result: dict | None = None,
                  error: str | None = None):
    """发送 JSON 响应到 stdout."""
    resp = {
        "id": resp_id,
        "success": success,
        "result": result,
        "error": error,
    }
    line = json.dumps(resp, ensure_ascii=False, default=_json_default)
    print(line, flush=True)


def handle_ping(req_id: str, params: dict) -> None:
    """健康检查."""
    _send_response(req_id, success=True, result={"pong": True})


def handle_install_driver(req_id: str, params: dict) -> None:
    """安装 Python 包（数据库驱动）."""
    package = params.get("package", "")
    if not package:
        _send_response(req_id, success=False, error="package name is required")
        return

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", package],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            _send_response(req_id, success=True, result={"installed": package})
        else:
            _send_response(
                req_id,
                success=False,
                error=f"pip install failed: {result.stderr.strip()}",
            )
    except subprocess.TimeoutExpired:
        _send_response(req_id, success=False, error="pip install timed out")
    except Exception as e:
        _send_response(req_id, success=False, error=str(e))


def _get_engine(db_url: str):
    """根据 db_url 创建 SQLAlchemy engine."""
    from sqlalchemy import create_engine
    return create_engine(db_url, pool_pre_ping=False)


def handle_execute_sql(req_id: str, params: dict) -> None:
    """执行 SQL 查询."""
    db_url = params.get("db_url", "")
    sql = params.get("sql", "")
    timeout = params.get("timeout", 30)

    if not db_url:
        _send_response(req_id, success=False, error="db_url is required")
        return
    if not sql:
        _send_response(req_id, success=False, error="sql is required")
        return

    start = time.perf_counter()
    try:
        from sqlalchemy import text

        engine = _get_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text(sql))

            columns = list(result.keys()) if result.returns_rows else []
            rows = []
            row_count = 0

            if result.returns_rows:
                # 限制最多返回 1000 行，避免沙盒内存爆
                all_rows = result.fetchmany(1001)
                raw_rows = [list(r) for r in all_rows[:1000]]
                # 将非 JSON 类型转换为可序列化类型（datetime, Decimal 等）
                rows = _jsonify_rows(raw_rows)
                row_count = len(rows)
                truncated = len(all_rows) > 1000
            else:
                # DML/DCL 等不返回行的语句
                row_count = result.rowcount or 0
                truncated = False
                columns = []

            duration_ms = (time.perf_counter() - start) * 1000

            _send_response(req_id, success=True, result={
                "columns": columns,
                "rows": rows,
                "row_count": row_count,
                "duration_ms": round(duration_ms, 2),
                "truncated": truncated,
            })

    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        _send_response(req_id, success=False, error=str(e))


def handle_test_connection(req_id: str, params: dict) -> None:
    """测试数据库连接."""
    db_url = params.get("db_url", "")
    if not db_url:
        _send_response(req_id, success=False, error="db_url is required")
        return

    try:
        engine = _get_engine(db_url)
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("SELECT 1"))
        _send_response(req_id, success=True, result={"connected": True})
    except Exception as e:
        _send_response(req_id, success=False, result={"connected": False}, error=str(e))


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------

METHOD_HANDLERS = {
    "ping": handle_ping,
    "install_driver": handle_install_driver,
    "execute_sql": handle_execute_sql,
    "test_connection": handle_test_connection,
}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            # 忽略非法输入
            continue

        req_id = request.get("id", str(uuid.uuid4()))
        method = request.get("method", "")
        params = request.get("params", {})

        handler = METHOD_HANDLERS.get(method)
        if handler is None:
            _send_response(req_id, success=False, error=f"unknown method: {method}")
            continue

        try:
            handler(req_id, params)
        except Exception as e:
            _send_response(req_id, success=False, error=f"handler error: {e}")


if __name__ == "__main__":
    main()
