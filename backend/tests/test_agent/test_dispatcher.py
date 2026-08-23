"""测试 Dispatcher Agent 和各子 Agent."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from nl2sql.agent.dispatcher import DispatcherAgent, DispatchResult, _parse_json_response
from nl2sql.schema.models import Column, Table, Schema, DatasourceSchema


@pytest.fixture
def sample_datasources():
    return [
        DatasourceSchema(
            datasource_id="test_ds",
            datasource_name="测试库",
            datasource_type="sqlite",
            db_schema=Schema(tables=[
                Table(
                    name="users",
                    description="用户表",
                    columns=[
                        Column(name="id", type="integer", description="用户ID", is_primary_key=True, semantic_type="id"),
                        Column(name="name", type="text", description="姓名"),
                        Column(name="status", type="text", description="状态", semantic_type="category"),
                    ],
                ),
                Table(
                    name="orders",
                    description="订单表",
                    columns=[
                        Column(name="id", type="integer", description="订单ID", is_primary_key=True, semantic_type="id"),
                        Column(name="amount", type="real", description="金额", semantic_type="amount"),
                        Column(name="user_id", type="integer", description="用户ID", is_foreign_key=True),
                    ],
                ),
            ]),
        )
    ]


@pytest.fixture
def mock_executors():
    from nl2sql.executor import ExecutionResult

    executor = MagicMock()
    executor.datasource_id = "test_ds"
    executor.execute.return_value = ExecutionResult(
        success=True,
        sql="SELECT COUNT(*) FROM users",
        columns=["count"],
        rows=[(42,)],
        row_count=1,
        duration_ms=5.0,
    )
    executor.test_connection.return_value = True
    return {"test_ds": executor}


def _make_mock_llm(responses: list[str]):
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


# ===========================================================================
# JSON 解析测试
# ===========================================================================

class TestParseJsonResponse:
    def test_plain_json(self):
        assert _parse_json_response('{"a": 1}') == {"a": 1}

    def test_json_with_markdown(self):
        assert _parse_json_response("```json\n{\"a\": 1}\n```") == {"a": 1}

    def test_json_with_plain_code_block(self):
        assert _parse_json_response("```\n{\"a\": 1}\n```") == {"a": 1}

    def test_invalid_json_returns_none(self):
        assert _parse_json_response("not json") is None


# ===========================================================================
# DispatchResult 测试
# ===========================================================================

class TestDispatchResult:
    def test_default_values(self):
        dr = DispatchResult(intent="query")
        assert dr.intent == "query"
        assert dr.confidence == 0.0
        assert dr.reasoning == ""
        assert dr.datasource_info == {}
        assert dr.schema_target == {}


# ===========================================================================
# Dispatcher 意图分类测试
# ===========================================================================

class TestDispatcherClassification:
    def test_classify_query_intent(self):
        """能正确识别数据查询意图."""
        mock_llm = MagicMock()
        mock_llm.chat.return_value.content = json.dumps({
            "intent": "query",
            "confidence": 0.95,
            "reasoning": "用户想统计用户数量",
        })

        with patch("nl2sql.agent.dispatcher.create_llm_client", return_value=mock_llm):
            dispatcher = DispatcherAgent(project_id="test")
            result = dispatcher._classify_intent("有多少用户？")

        assert result.intent == "query"
        assert result.confidence == 0.95

    def test_classify_schema_exploration_intent(self):
        """能正确识别 schema 探索意图."""
        mock_llm = MagicMock()
        mock_llm.chat.return_value.content = json.dumps({
            "intent": "schema_exploration",
            "confidence": 0.9,
            "reasoning": "用户想了解表结构",
            "schema_target": {"table_name": "users", "column_name": None, "action": "describe_table"},
        })

        with patch("nl2sql.agent.dispatcher.create_llm_client", return_value=mock_llm):
            dispatcher = DispatcherAgent(project_id="test")
            result = dispatcher._classify_intent("users 表有哪些列？")

        assert result.intent == "schema_exploration"
        assert result.schema_target["table_name"] == "users"

    def test_classify_connect_datasource_intent(self):
        """能正确识别数据源接入意图."""
        mock_llm = MagicMock()
        mock_llm.chat.return_value.content = json.dumps({
            "intent": "connect_datasource",
            "confidence": 0.92,
            "reasoning": "用户想连接数据库",
            "datasource_info": {"type": "postgresql", "host": "localhost"},
        })

        with patch("nl2sql.agent.dispatcher.create_llm_client", return_value=mock_llm):
            dispatcher = DispatcherAgent(project_id="test")
            result = dispatcher._classify_intent("帮我连接一个数据库")

        assert result.intent == "connect_datasource"
        assert result.datasource_info["type"] == "postgresql"

    def test_classify_chitchat_intent(self):
        """能正确识别闲聊意图."""
        mock_llm = MagicMock()
        mock_llm.chat.return_value.content = json.dumps({
            "intent": "chitchat",
            "confidence": 0.8,
            "reasoning": "用户在打招呼",
        })

        with patch("nl2sql.agent.dispatcher.create_llm_client", return_value=mock_llm):
            dispatcher = DispatcherAgent(project_id="test")
            result = dispatcher._classify_intent("你好")

        assert result.intent == "chitchat"

    def test_invalid_intent_defaults_to_query(self):
        """无效的 intent 值默认回退到 query."""
        mock_llm = MagicMock()
        mock_llm.chat.return_value.content = json.dumps({
            "intent": "something_unknown",
            "confidence": 0.5,
            "reasoning": "未知",
        })

        with patch("nl2sql.agent.dispatcher.create_llm_client", return_value=mock_llm):
            dispatcher = DispatcherAgent(project_id="test")
            result = dispatcher._classify_intent("test")

        assert result.intent == "query"

    def test_unparseable_response_defaults_to_query(self):
        """无法解析的响应默认按 query 处理."""
        mock_llm = MagicMock()
        mock_llm.chat.return_value.content = "这不是 JSON"

        with patch("nl2sql.agent.dispatcher.create_llm_client", return_value=mock_llm):
            dispatcher = DispatcherAgent(project_id="test")
            result = dispatcher._classify_intent("test")

        assert result.intent == "query"
        assert result.confidence == 0.5


# ===========================================================================
# Dispatcher 路由测试（完整 run）
# ===========================================================================

class TestDispatcherRouting:
    def test_query_routes_to_nl2sql_agent(self, sample_datasources, mock_executors):
        """query 意图应路由到 NL2SQLAgent."""
        # dispatcher 分类 LLM 返回 query
        classify_resp = json.dumps({
            "intent": "query",
            "confidence": 0.9,
            "reasoning": "数据查询",
        })
        # NL2SQL 子流程的 LLM 响应
        nl2sql_responses = [
            json.dumps({"tables": [], "filters": [], "aggregation": "count", "dimensions": [], "ambiguities": [], "confidence": 0.9, "analysis": "ok"}),
            "[]",
            "SELECT COUNT(*) FROM users",
            json.dumps({"satisfied": True, "needs_revision": False, "thought": "ok", "suggested_fix": ""}),
            "答案",
        ]
        all_responses = [classify_resp] + nl2sql_responses
        mock_llm = _make_mock_llm(all_responses)

        with patch("nl2sql.agent.dispatcher.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.probe.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.clarify.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.generate.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.reflect.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.summarize.create_llm_client", return_value=mock_llm):

            dispatcher = DispatcherAgent(
                project_id="test",
                datasources=sample_datasources,
                executors=mock_executors,
            )
            result = dispatcher.run("有多少用户？")

        assert result["status"] == "done"
        assert result["answer"] is not None
        assert "execution_result" in result

    def test_chitchat_routes_to_chitchat_handler(self):
        """chitchat 意图应走闲聊处理."""
        mock_llm = MagicMock()
        responses = [
            json.dumps({"intent": "chitchat", "confidence": 0.8, "reasoning": "打招呼"}),
            "你好！我是数据查询助手，有什么可以帮你的？",
        ]
        idx = [0]

        def chat_side_effect(*a, **kw):
            r = MagicMock()
            r.content = responses[idx[0] % len(responses)]
            idx[0] += 1
            r.tool_calls = []
            return r

        mock_llm.chat.side_effect = chat_side_effect

        with patch("nl2sql.agent.dispatcher.create_llm_client", return_value=mock_llm):
            dispatcher = DispatcherAgent(project_id="test")
            result = dispatcher.run("你好")

        assert result["status"] == "done"
        assert result["intent"] == "chitchat"
        assert result["answer"] != ""

    def test_schema_exploration_no_datasource_returns_error(self):
        """schema 探索但没有数据源时应返回错误."""
        mock_llm = MagicMock()
        mock_llm.chat.return_value.content = json.dumps({
            "intent": "schema_exploration",
            "confidence": 0.9,
            "reasoning": "查看表结构",
        })

        with patch("nl2sql.agent.dispatcher.create_llm_client", return_value=mock_llm):
            dispatcher = DispatcherAgent(project_id="test", datasources=[], executors={})
            result = dispatcher.run("有哪些表？")

        assert result["status"] == "failed"
        assert "数据源" in result["answer"]


# ===========================================================================
# SchemaExplorerAgent 测试
# ===========================================================================

class TestSchemaExplorerAgent:
    def test_explore_list_tables(self, sample_datasources, mock_executors):
        """Schema Explorer 能列出所有表."""
        from nl2sql.agent.schema_explorer import SchemaExplorerAgent
        from nl2sql.llm import ToolCall

        # LLM 先调用 list_tables 工具，然后总结回答
        tool_call = ToolCall(id="call_1", name="list_tables", arguments={})
        resp_with_tool = MagicMock(content="", tool_calls=[tool_call])
        resp_final = MagicMock(content="当前数据库有 2 张表：users 和 orders。", tool_calls=[])

        responses = [resp_with_tool, resp_final]
        call_idx = [0]

        def chat_side_effect(*a, **kw):
            r = responses[call_idx[0] % len(responses)]
            call_idx[0] += 1
            return r

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = chat_side_effect

        with patch("nl2sql.agent.schema_explorer.create_llm_client", return_value=mock_llm):
            agent = SchemaExplorerAgent(
                datasources=sample_datasources,
                executors=mock_executors,
            )
            result = agent.run("有哪些表？")

        assert result["status"] == "done"
        assert "2 张表" in result["answer"] or "users" in result["answer"]
        assert result["tool_calls_count"] == 1

    def test_explore_no_tool_calls_direct_answer(self, sample_datasources, mock_executors):
        """如果 LLM 直接回答，不调用工具也能正常返回."""
        from nl2sql.agent.schema_explorer import SchemaExplorerAgent

        mock_llm = MagicMock()
        mock_llm.chat.return_value = MagicMock(
            content="用户表（users）存储用户信息，订单表（orders）存储订单数据。",
            tool_calls=[],
        )

        with patch("nl2sql.agent.schema_explorer.create_llm_client", return_value=mock_llm):
            agent = SchemaExplorerAgent(
                datasources=sample_datasources,
                executors=mock_executors,
            )
            result = agent.run("简单介绍下这些表")

        assert result["status"] == "done"
        assert result["tool_calls_count"] == 0
        assert "用户表" in result["answer"]

    def test_event_callback_called(self, sample_datasources, mock_executors):
        """Schema Explorer 会正确调用 event_callback."""
        from nl2sql.agent.schema_explorer import SchemaExplorerAgent

        events = []
        def cb(evt, data):
            events.append(evt)

        mock_llm = MagicMock()
        mock_llm.chat.return_value = MagicMock(
            content="这是测试回答。",
            tool_calls=[],
        )

        with patch("nl2sql.agent.schema_explorer.create_llm_client", return_value=mock_llm):
            agent = SchemaExplorerAgent(
                datasources=sample_datasources,
                executors=mock_executors,
                event_callback=cb,
            )
            agent.run("test")

        assert "schema_exploring" in events
        assert "schema_explore_done" in events
