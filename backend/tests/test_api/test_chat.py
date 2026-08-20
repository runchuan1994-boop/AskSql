"""测试聊天 API 和 SSE 流式接口."""

from __future__ import annotations

import importlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from unittest.mock import MagicMock, patch


def _reload_app_modules(tmpdir: str):
    """Set env vars and reload app modules so settings pick up the temp data dir."""
    os.environ["APP_DATA_DIR"] = os.path.join(tmpdir, "data")
    os.environ["APP_DATABASE_URL"] = f"sqlite:///{tmpdir}/data/test.db"
    os.environ["APP_SCHEMAS_DIR"] = os.path.join(tmpdir, "config", "schemas")

    from app.core import config as config_mod

    importlib.reload(config_mod)
    from app.core import database as db_mod

    importlib.reload(db_mod)
    db_mod.init_db()

    # 刷新 chat_service 中的模块级状态（事件队列、任务表）
    try:
        from app.services import chat_service as chat_mod
        importlib.reload(chat_mod)
    except ImportError:
        pass

    from app import main as main_mod

    importlib.reload(main_mod)
    return main_mod


def _make_mock_llm(responses: list[str]) -> MagicMock:
    """创建一个按顺序返回响应的 mock LLM."""
    mock_llm = MagicMock()
    call_idx = 0

    def chat_side_effect(*args, **kwargs):
        nonlocal call_idx
        resp = MagicMock()
        resp.content = responses[min(call_idx, len(responses) - 1)]
        resp.tool_calls = []
        resp.model = "mock-model"
        resp.usage = {}
        call_idx += 1
        return resp

    mock_llm.chat.side_effect = chat_side_effect
    return mock_llm


@contextmanager
def _patch_llm_clients(mock_llm: MagicMock):
    """Context manager: mock 所有 agent 节点模块的 create_llm_client."""
    patches = [
        patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm),
        patch("nl2sql.agent.nodes.probe.create_llm_client", return_value=mock_llm),
        patch("nl2sql.agent.nodes.clarify.create_llm_client", return_value=mock_llm),
        patch("nl2sql.agent.nodes.generate.create_llm_client", return_value=mock_llm),
        patch("nl2sql.agent.nodes.reflect.create_llm_client", return_value=mock_llm),
        patch("nl2sql.agent.nodes.summarize.create_llm_client", return_value=mock_llm),
    ]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in reversed(patches):
            p.stop()


def _success_responses() -> list[str]:
    """返回一个标准成功流程的 LLM 响应列表."""
    return [
        # 1. intent_analyze
        json.dumps({
            "tables": [{"name": "users", "reason": "统计用户"}],
            "filters": [],
            "aggregation": "count",
            "dimensions": [],
            "ambiguities": [],
            "confidence": 0.95,
            "analysis": "用户想统计用户总数",
        }),
        # 2. clarify
        "[]",
        # 3. generate_sql
        "```sql\nSELECT COUNT(*) as total FROM users\n```",
        # 4. reflect (satisfied)
        json.dumps({
            "satisfied": True,
            "needs_revision": False,
            "thought": "SQL 正确执行，结果符合用户问题",
            "suggested_fix": "",
        }),
        # 5. summarize
        "系统中共有 3 个用户。",
    ]


def _create_test_project_and_session(tmpdir, project_id="proj-001", session_title="测试会话"):
    """创建测试项目、数据源、schema 文件，并返回 (session_id, ds_id)."""
    from app.core.database import get_connection
    from app.services.datasource_service import create_datasource
    from app.services.session_service import create_session
    from app.services.schema_import import import_schema_from_database

    # 创建项目
    conn = get_connection()
    conn.execute(
        "INSERT INTO projects (id, name, description) VALUES (?, ?, ?)",
        (project_id, "Test Project", "A test project"),
    )
    conn.commit()
    conn.close()

    # 创建 SQLite 测试数据库
    test_db_path = os.path.join(tmpdir, "test_data.db")
    test_conn = sqlite3.connect(test_db_path)
    test_conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    test_conn.execute("INSERT INTO users (name, status) VALUES ('Alice', 'active')")
    test_conn.execute("INSERT INTO users (name, status) VALUES ('Bob', 'inactive')")
    test_conn.execute("INSERT INTO users (name, status) VALUES ('Charlie', 'active')")
    test_conn.commit()
    test_conn.close()

    # 创建数据源
    ds = create_datasource(
        project_id=project_id,
        name="测试数据库",
        ds_type="sqlite",
        database=test_db_path,
    )

    # 确保 schema 目录存在
    schemas_dir = os.environ.get("APP_SCHEMAS_DIR", "config/schemas")
    os.makedirs(os.path.join(schemas_dir, project_id), exist_ok=True)

    # 导入 schema
    import_schema_from_database(ds["id"])

    # 创建会话
    session = create_session(project_id, title=session_title)
    return session["id"], ds["id"]


def _parse_sse_events(lines: list[str]) -> list[dict]:
    """将 SSE 文本行解析为事件列表."""
    events = []
    current = {}
    for line in lines:
        if line is None:
            continue
        line = line.strip()
        if line.startswith("event:"):
            current["event"] = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current["data"] = line[len("data:"):].strip()
        elif line == "":
            if current:
                events.append(current)
                current = {}
    if current:
        events.append(current)
    return events


class TestPostChat:
    """测试 POST /api/chat 发送消息接口."""

    def test_send_message_returns_started(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from fastapi.testclient import TestClient

            session_id, _ = _create_test_project_and_session(tmpdir)
            mock_llm = _make_mock_llm(_success_responses())
            client = TestClient(main_mod.app)

            with _patch_llm_clients(mock_llm):
                response = client.post(
                    "/api/chat",
                    json={"session_id": session_id, "message": "总共有多少用户？"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["session_id"] == session_id
            assert data["status"] == "started"

    def test_send_message_invalid_session_returns_404(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from fastapi.testclient import TestClient

            client = TestClient(main_mod.app)
            response = client.post(
                "/api/chat",
                json={"session_id": "nonexistent-session", "message": "hello"},
            )
            assert response.status_code == 404


class TestSSEStream:
    """测试 SSE 事件流接口."""

    def test_stream_returns_correct_headers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from fastapi.testclient import TestClient

            session_id, _ = _create_test_project_and_session(tmpdir)
            mock_llm = _make_mock_llm(_success_responses())
            client = TestClient(main_mod.app)

            with _patch_llm_clients(mock_llm):
                client.post(
                    "/api/chat",
                    json={"session_id": session_id, "message": "总共有多少用户？"},
                )
                with client.stream("GET", f"/api/chat/stream/{session_id}") as resp:
                    assert resp.status_code == 200
                    assert "text/event-stream" in resp.headers["content-type"]
                    assert resp.headers["cache-control"] == "no-cache"
                    # 读取完避免挂起
                    for _ in resp.iter_lines():
                        pass

    def test_stream_receives_all_expected_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from fastapi.testclient import TestClient

            session_id, _ = _create_test_project_and_session(tmpdir)
            mock_llm = _make_mock_llm(_success_responses())
            client = TestClient(main_mod.app)

            with _patch_llm_clients(mock_llm):
                start_resp = client.post(
                    "/api/chat",
                    json={"session_id": session_id, "message": "总共有多少用户？"},
                )
                assert start_resp.status_code == 200

                with client.stream("GET", f"/api/chat/stream/{session_id}") as resp:
                    assert resp.status_code == 200
                    lines = list(resp.iter_lines())

            events = _parse_sse_events(lines)
            event_types = [e.get("event") for e in events]

            # 核心事件必须存在
            assert "start" in event_types
            assert "intent_analysis" in event_types
            assert "sql_generated" in event_types
            assert "sql_executed" in event_types
            assert "final_result" in event_types
            assert "done" in event_types  # 来自 summarize_node
            assert "chat_done" in event_types  # 来自 chat_service，代表全部完成

            # final_result 应包含成功标记
            final_events = [e for e in events if e.get("event") == "final_result"]
            assert len(final_events) >= 1
            final_data = json.loads(final_events[0]["data"])
            assert final_data["success"] is True

            # chat_done 应该是最后一个事件
            assert events[-1]["event"] == "chat_done"

    def test_stream_invalid_session_returns_404(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from fastapi.testclient import TestClient

            client = TestClient(main_mod.app)
            with client.stream("GET", "/api/chat/stream/nonexistent") as resp:
                assert resp.status_code == 404


class TestMessagesSavedAfterChat:
    """测试聊天后消息被正确保存."""

    def test_user_and_assistant_messages_saved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from fastapi.testclient import TestClient
            from app.services.session_service import get_messages

            session_id, _ = _create_test_project_and_session(tmpdir)
            mock_llm = _make_mock_llm(_success_responses())
            client = TestClient(main_mod.app)

            with _patch_llm_clients(mock_llm):
                client.post(
                    "/api/chat",
                    json={"session_id": session_id, "message": "总共有多少用户？"},
                )
                # 消费 SSE 流等待完成
                with client.stream("GET", f"/api/chat/stream/{session_id}") as resp:
                    for _ in resp.iter_lines():
                        pass

            messages = get_messages(session_id)
            assert len(messages) == 2
            assert messages[0]["role"] == "user"
            assert messages[0]["content"] == "总共有多少用户？"
            assert messages[1]["role"] == "assistant"
            assert messages[1]["sql_text"] is not None
            assert "COUNT" in messages[1]["sql_text"].upper()
            assert messages[1]["result"] is not None
            assert messages[1]["result"]["row_count"] == 1


class TestGenerationLogAfterChat:
    """测试聊天后生成日志被记录."""

    def test_chat_records_generation_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from fastapi.testclient import TestClient
            from app.services.generation_log import list_generation_logs

            session_id, ds_id = _create_test_project_and_session(tmpdir)
            mock_llm = _make_mock_llm(_success_responses())
            client = TestClient(main_mod.app)

            with _patch_llm_clients(mock_llm):
                client.post(
                    "/api/chat",
                    json={"session_id": session_id, "message": "总共有多少用户？"},
                )
                # 消费 SSE 流等待完成
                with client.stream("GET", f"/api/chat/stream/{session_id}") as resp:
                    for _ in resp.iter_lines():
                        pass

            logs = list_generation_logs("proj-001")
            assert len(logs) >= 1
            log = logs[0]
            assert log["session_id"] == session_id
            assert log["datasource_id"] == ds_id
            assert log["user_query"] == "总共有多少用户？"
            assert log["generated_sql"] is not None
            assert log["execution_success"] == 1
            assert log["row_count"] == 1
            assert log["final_selected"] == 1
            assert log["iteration"] >= 1
