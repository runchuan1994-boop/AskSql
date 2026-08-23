"""Tests for connect_datasource node."""
from __future__ import annotations

import importlib
import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from nl2sql.llm import ChatResponse, Message, MessageRole, ToolCall
from nl2sql.agent.state import AgentState, IntentResult


# ---------------------------------------------------------------------------
# Helpers for app-service based tests
# ---------------------------------------------------------------------------

def _reload_app_modules(tmpdir: str):
    """Set env vars and reload app modules so settings pick up the temp data dir."""
    os.environ["APP_DATA_DIR"] = os.path.join(tmpdir, "data")
    os.environ["APP_DATABASE_URL"] = f"sqlite:///{tmpdir}/data/test.db"
    os.environ["APP_SCHEMAS_DIR"] = os.path.join(tmpdir, "schemas")

    from app.core import config as config_mod
    importlib.reload(config_mod)
    from app.core import database as db_mod
    importlib.reload(db_mod)
    from app.services import project_service as ps_mod
    importlib.reload(ps_mod)
    from app.services import datasource_service as ds_mod
    importlib.reload(ds_mod)
    from app.services import schema_import as si_mod
    importlib.reload(si_mod)

    db_mod.init_db()


def _create_project():
    from app.services import project_service
    result = project_service.create_project("Test Project")
    return result["id"]


def _make_tool_call(id: str, name: str, arguments: dict) -> ToolCall:
    """Helper to build a ToolCall."""
    return ToolCall(id=id, name=name, arguments=arguments)


def _make_mock_llm(responses: list[ChatResponse]) -> MagicMock:
    """Create a mock LLM client that returns responses in sequence."""
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = responses
    return mock_llm


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_intent():
    """A connect_datasource intent with full info."""
    return IntentResult(
        action="connect_datasource",
        datasource_info={
            "type": "sqlite",
            "database": ":memory:",
            "name": "Test DS",
        },
    )


@pytest.fixture
def events_collector():
    """Collect SSE events sent by the node."""
    events: list[tuple[str, dict]] = []

    def _callback(event_type: str, data: dict):
        events.append((event_type, data))

    return events, _callback


# ===========================================================================
# Test 1: Normal flow - create → test → import → text answer
# ===========================================================================

class TestNormalFlow:
    def test_three_tool_calls_then_final_answer(self, events_collector):
        """LLM calls create → test → import, then returns text answer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            events, callback = events_collector

            # We need real tool execution, so we use the real execute_datasource_tool.
            # We mock only the LLM client.
            from nl2sql.agent.nodes.connect_datasource import connect_datasource_node

            # Build a sample SQLite file with tables (so import_schema works)
            db_path = os.path.join(tmpdir, "sample.db")
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT)"
            )
            conn.execute(
                "CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL)"
            )
            conn.commit()
            conn.close()

            # We'll capture the datasource_id from the first tool call result
            # by reading it from the create_datasource response and using it
            # in subsequent tool calls.
            captured_ds_id: dict[str, str] = {}

            def mock_chat_side_effect(messages, tools=None, temperature=0.0, max_tokens=4096):
                # Find the last message to determine what to respond with
                # Count tool result messages to know which round we're in
                tool_result_count = sum(
                    1 for m in messages if m.role == MessageRole.TOOL
                )

                if tool_result_count == 0:
                    # Round 1: LLM calls create_datasource
                    return ChatResponse(
                        content="",
                        tool_calls=[
                            _make_tool_call(
                                id="call_create_1",
                                name="create_datasource",
                                arguments={
                                    "name": "My SQLite DS",
                                    "type": "sqlite",
                                    "database": db_path,
                                },
                            )
                        ],
                    )
                elif tool_result_count == 1:
                    # Round 2: Extract ds_id from the tool result and call test_connection
                    # Find the tool result message for create_datasource
                    for m in messages:
                        if m.role == MessageRole.TOOL and m.tool_result:
                            if m.tool_result.name == "create_datasource":
                                import re
                                match = re.search(r"ID:\s*(\S+)", m.tool_result.content)
                                if match:
                                    captured_ds_id["id"] = match.group(1)

                    ds_id = captured_ds_id.get("id", "unknown")
                    return ChatResponse(
                        content="",
                        tool_calls=[
                            _make_tool_call(
                                id="call_test_1",
                                name="test_connection",
                                arguments={"datasource_id": ds_id},
                            )
                        ],
                    )
                elif tool_result_count == 2:
                    # Round 3: Call import_schema
                    ds_id = captured_ds_id.get("id", "unknown")
                    return ChatResponse(
                        content="",
                        tool_calls=[
                            _make_tool_call(
                                id="call_import_1",
                                name="import_schema",
                                arguments={"datasource_id": ds_id},
                            )
                        ],
                    )
                else:
                    # Round 4: Return final answer
                    return ChatResponse(
                        content="数据源已成功创建并连接，共导入 2 张表（users 和 orders）。",
                        tool_calls=[],
                    )

            mock_llm = MagicMock()
            mock_llm.chat.side_effect = mock_chat_side_effect

            state = AgentState(
                project_id=project_id,
                user_query="帮我连接一个 SQLite 数据库",
                intent=IntentResult(
                    action="connect_datasource",
                    datasource_info={
                        "type": "sqlite",
                        "database": db_path,
                        "name": "My SQLite DS",
                    },
                ),
                event_callback=callback,
            )

            with patch(
                "nl2sql.agent.nodes.connect_datasource.create_llm_client",
                return_value=mock_llm,
            ):
                result = connect_datasource_node(state)

            # Check return values
            assert result["status"] == "done"
            assert result["datasource_id"] is not None
            assert result["tables_imported"] == 2
            assert "成功" in result["final_answer"]

            # Check SSE events were sent
            event_types = [e[0] for e in events]
            assert "ds_creating" in event_types
            assert "ds_created" in event_types
            assert "ds_testing" in event_types
            assert "ds_connected" in event_types
            assert "ds_importing" in event_types
            assert "ds_imported" in event_types
            assert "final_result" in event_types
            assert "done" in event_types

            # Verify datasource_id matches between create result and return value
            assert result["datasource_id"] == captured_ds_id.get("id")


# ===========================================================================
# Test 2: Missing info - LLM asks user to provide more details
# ===========================================================================

class TestMissingInfo:
    def test_llm_asks_for_more_info_no_tool_calls(self, events_collector):
        """When info is insufficient, LLM returns text directly without tool calls."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            events, callback = events_collector

            from nl2sql.agent.nodes.connect_datasource import connect_datasource_node

            # Mock LLM returns only text, no tool calls
            mock_llm = MagicMock()
            mock_llm.chat.return_value = ChatResponse(
                content="请提供更多信息：数据库类型、主机地址、端口号、数据库名、用户名和密码。",
                tool_calls=[],
            )

            state = AgentState(
                project_id=project_id,
                user_query="我想连接一个数据库",
                intent=IntentResult(
                    action="connect_datasource",
                    datasource_info={},
                ),
                event_callback=callback,
            )

            with patch(
                "nl2sql.agent.nodes.connect_datasource.create_llm_client",
                return_value=mock_llm,
            ):
                result = connect_datasource_node(state)

            assert result["status"] == "done"
            assert result["datasource_id"] is None
            assert result["tables_imported"] == 0
            assert "请提供" in result["final_answer"]

            # Only final_result and done events should be sent (no tool events)
            event_types = [e[0] for e in events]
            assert "final_result" in event_types
            assert "done" in event_types
            assert "ds_creating" not in event_types
            assert "ds_testing" not in event_types


# ===========================================================================
# Test 3: Connection failure - test_connection fails, LLM informs user
# ===========================================================================

class TestConnectionFailure:
    def test_test_connection_fails_llm_informs_user(self, events_collector):
        """If test_connection fails, LLM should inform user and not proceed to import."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            events, callback = events_collector

            from nl2sql.agent.nodes.connect_datasource import connect_datasource_node

            captured_ds_id: dict[str, str] = {}

            def mock_chat_side_effect(messages, tools=None, temperature=0.0, max_tokens=4096):
                tool_result_count = sum(
                    1 for m in messages if m.role == MessageRole.TOOL
                )

                if tool_result_count == 0:
                    # Round 1: create datasource (but with bad config that will fail test)
                    return ChatResponse(
                        content="",
                        tool_calls=[
                            _make_tool_call(
                                id="call_create_1",
                                name="create_datasource",
                                arguments={
                                    "name": "Bad MySQL DS",
                                    "type": "mysql",
                                    "host": "localhost",
                                    "port": 9999,
                                    "database": "nonexistent",
                                    "username": "root",
                                    "password": "wrong",
                                },
                            )
                        ],
                    )
                elif tool_result_count == 1:
                    # Round 2: test connection (will fail because mysql on port 9999)
                    for m in messages:
                        if m.role == MessageRole.TOOL and m.tool_result:
                            if m.tool_result.name == "create_datasource":
                                import re
                                match = re.search(r"ID:\s*(\S+)", m.tool_result.content)
                                if match:
                                    captured_ds_id["id"] = match.group(1)

                    ds_id = captured_ds_id.get("id", "unknown")
                    return ChatResponse(
                        content="",
                        tool_calls=[
                            _make_tool_call(
                                id="call_test_1",
                                name="test_connection",
                                arguments={"datasource_id": ds_id},
                            )
                        ],
                    )
                else:
                    # Round 3: connection failed, inform user
                    return ChatResponse(
                        content="抱歉，数据库连接测试失败了。请检查主机地址、端口号、用户名和密码是否正确。",
                        tool_calls=[],
                    )

            mock_llm = MagicMock()
            mock_llm.chat.side_effect = mock_chat_side_effect

            state = AgentState(
                project_id=project_id,
                user_query="帮我连接一个 MySQL 数据库",
                intent=IntentResult(
                    action="connect_datasource",
                    datasource_info={
                        "type": "mysql",
                        "host": "localhost",
                        "port": 9999,
                        "database": "nonexistent",
                        "username": "root",
                        "password": "wrong",
                        "name": "Bad MySQL DS",
                    },
                ),
                event_callback=callback,
            )

            with patch(
                "nl2sql.agent.nodes.connect_datasource.create_llm_client",
                return_value=mock_llm,
            ):
                result = connect_datasource_node(state)

            # Status is still "done" because the LLM successfully responded with info
            assert result["status"] == "done"
            assert result["datasource_id"] is not None  # ds was created, just not connected
            assert result["tables_imported"] == 0  # import was never called
            assert "失败" in result["final_answer"]

            # Check events: create succeeded, test failed, no import
            event_types = [e[0] for e in events]
            assert "ds_creating" in event_types
            assert "ds_created" in event_types
            assert "ds_testing" in event_types
            assert "ds_connection_failed" in event_types
            assert "ds_importing" not in event_types
            assert "ds_imported" not in event_types


# ===========================================================================
# Test 4: Max iteration protection
# ===========================================================================

class TestMaxIterations:
    def test_stops_after_max_iterations(self, events_collector):
        """If LLM keeps calling tools indefinitely, node should stop after 4 rounds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            events, callback = events_collector

            from nl2sql.agent.nodes.connect_datasource import connect_datasource_node

            # LLM always returns a tool call (never text)
            call_counter = {"count": 0}

            def mock_chat_side_effect(messages, tools=None, temperature=0.0, max_tokens=4096):
                call_counter["count"] += 1
                return ChatResponse(
                    content="",
                    tool_calls=[
                        _make_tool_call(
                            id=f"call_{call_counter['count']}",
                            name="create_datasource",
                            arguments={
                                "name": f"DS {call_counter['count']}",
                                "type": "sqlite",
                                "database": ":memory:",
                            },
                        )
                    ],
                )

            mock_llm = MagicMock()
            mock_llm.chat.side_effect = mock_chat_side_effect

            state = AgentState(
                project_id=project_id,
                user_query="帮我创建数据源",
                intent=IntentResult(
                    action="connect_datasource",
                    datasource_info={},
                ),
                event_callback=callback,
            )

            with patch(
                "nl2sql.agent.nodes.connect_datasource.create_llm_client",
                return_value=mock_llm,
            ):
                result = connect_datasource_node(state)

            # Should have failed due to max iterations
            assert result["status"] == "failed"
            assert "最大迭代次数" in result["final_answer"]
            # LLM.chat should have been called exactly 4 times
            assert mock_llm.chat.call_count == 4


# ===========================================================================
# Test 5: datasource_id correctly extracted from create_datasource result
# ===========================================================================

class TestDatasourceIdExtraction:
    def test_datasource_id_extracted_from_tool_result(self):
        """The returned datasource_id should match the ID from create_datasource."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            from nl2sql.agent.nodes.connect_datasource import connect_datasource_node

            db_path = os.path.join(tmpdir, "test_extract.db")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE t1 (id INTEGER PRIMARY KEY)")
            conn.commit()
            conn.close()

            captured_ids: list[str] = []

            def mock_chat_side_effect(messages, tools=None, temperature=0.0, max_tokens=4096):
                tool_result_count = sum(
                    1 for m in messages if m.role == MessageRole.TOOL
                )

                if tool_result_count == 0:
                    return ChatResponse(
                        content="",
                        tool_calls=[
                            _make_tool_call(
                                id="call_1",
                                name="create_datasource",
                                arguments={
                                    "name": "Extract Test DS",
                                    "type": "sqlite",
                                    "database": db_path,
                                },
                            )
                        ],
                    )
                else:
                    # After first tool call, capture the ds_id from message history
                    for m in messages:
                        if m.role == MessageRole.TOOL and m.tool_result:
                            if m.tool_result.name == "create_datasource":
                                import re
                                match = re.search(r"ID:\s*(\S+)", m.tool_result.content)
                                if match:
                                    captured_ids.append(match.group(1))
                    return ChatResponse(
                        content="数据源创建完成。",
                        tool_calls=[],
                    )

            mock_llm = MagicMock()
            mock_llm.chat.side_effect = mock_chat_side_effect

            state = AgentState(
                project_id=project_id,
                user_query="创建一个数据源",
                intent=IntentResult(
                    action="connect_datasource",
                    datasource_info={},
                ),
            )

            with patch(
                "nl2sql.agent.nodes.connect_datasource.create_llm_client",
                return_value=mock_llm,
            ):
                result = connect_datasource_node(state)

            # The datasource_id in the result should match the one from the tool output
            assert len(captured_ids) == 1
            assert result["datasource_id"] == captured_ids[0]
            assert result["datasource_id"] is not None


# ===========================================================================
# Test 6: SSE event data structure
# ===========================================================================

class TestSSEEventData:
    def test_final_result_event_has_correct_fields(self, events_collector):
        """final_result event should contain answer, success, datasource_id, tables_imported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            project_id = _create_project()

            events, callback = events_collector

            from nl2sql.agent.nodes.connect_datasource import connect_datasource_node

            mock_llm = MagicMock()
            mock_llm.chat.return_value = ChatResponse(
                content="请提供数据库连接信息。",
                tool_calls=[],
            )

            state = AgentState(
                project_id=project_id,
                user_query="我想连数据库",
                intent=IntentResult(action="connect_datasource", datasource_info={}),
                event_callback=callback,
            )

            with patch(
                "nl2sql.agent.nodes.connect_datasource.create_llm_client",
                return_value=mock_llm,
            ):
                connect_datasource_node(state)

            # Find final_result event
            final_result_events = [e for e in events if e[0] == "final_result"]
            assert len(final_result_events) == 1
            _, data = final_result_events[0]
            assert "answer" in data
            assert "success" in data
            assert "datasource_id" in data
            assert "tables_imported" in data
            assert data["success"] is True  # got answer, status is "done"

            # Find done event
            done_events = [e for e in events if e[0] == "done"]
            assert len(done_events) == 1
            _, data = done_events[0]
            assert "status" in data
            assert data["status"] == "done"
