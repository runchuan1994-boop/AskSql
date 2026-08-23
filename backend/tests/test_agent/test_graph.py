"""测试 LangGraph Agent 图的完整流程。"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from nl2sql.agent.graph import NL2SQLAgent
from nl2sql.schema.models import Column, Table, Schema, DatasourceSchema
from nl2sql.executor import ExecutionResult


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
                    description="用户表，注册用户信息",
                    columns=[
                        Column(name="id", type="integer", description="用户ID", is_primary_key=True, semantic_type="id"),
                        Column(name="name", type="text", description="姓名"),
                        Column(name="status", type="text", description="状态"),
                        Column(name="created_at", type="datetime", description="注册时间", semantic_type="timestamp"),
                    ],
                ),
            ]),
        )
    ]


@pytest.fixture
def mock_executors():
    """模拟执行器，返回成功结果。"""
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
    """创建一个按顺序返回响应的 mock LLM。"""
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


class TestNL2SQLAgent:
    def test_agent_full_flow_success(self, sample_datasources, mock_executors):
        """测试完整成功流程：意图→探查→改写(跳过)→澄清(快速跳过)→生成→执行→反思(满意)→总结。"""
        # 调用顺序：intent → probe(skip, 无歧义) → rewrite(skip, 高置信度)
        #          → clarify(fast-path, 高置信度) → generate_sql → reflect → summarize
        # 高置信度 (>=0.7) 且无歧义时，rewrite 和 clarify 都快速跳过，不调用 LLM
        responses = [
            # 1. intent_analyze
            json.dumps({
                "tables": [{"table_name": "users", "datasource_id": "test_ds", "confidence": 0.95}],
                "filters": [],
                "aggregation": "count",
                "dimensions": [],
                "ambiguities": [],
                "confidence": 0.95,
                "analysis": "用户想统计用户总数",
            }),
            # 2. generate_sql (probe/rewrite/clarify 均快速跳过，不调用 LLM)
            "```sql\nSELECT COUNT(*) as total FROM users\n```",
            # 3. reflect (satisfied)
            json.dumps({
                "satisfied": True,
                "needs_revision": False,
                "thought": "SQL 正确执行，结果符合用户问题",
                "suggested_fix": "",
            }),
            # 4. summarize
            "系统中共有 42 个用户。",
        ]
        mock_llm = _make_mock_llm(responses)

        # patch 所有节点模块的 create_llm_client
        with patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.probe.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.rewrite.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.clarify.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.generate.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.reflect.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.summarize.create_llm_client", return_value=mock_llm):

            agent = NL2SQLAgent(
                project_id="test",
                datasources=sample_datasources,
                executors=mock_executors,
                max_iterations=3,
            )
            result = agent.run("总共有多少用户？")

        assert result["status"] == "done"
        assert result["sql"] is not None
        assert "COUNT(*)" in result["sql"]
        assert result["answer"] is not None
        assert "42" in result["answer"]
        assert result["execution_result"] is not None
        assert result["execution_result"].success is True
        assert result["iteration"] >= 1

    def test_agent_with_sql_error_then_fix(self, sample_datasources, mock_executors):
        """测试 SQL 出错后重试成功的流程。"""
        # 设置执行器：第一次失败，第二次成功
        call_count = 0

        def execute_side_effect(sql):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return ExecutionResult(
                    success=False,
                    sql=sql,
                    error="no such column: invalid_col",
                )
            return ExecutionResult(
                success=True,
                sql=sql,
                columns=["count"],
                rows=[(42,)],
                row_count=1,
                duration_ms=5.0,
            )

        mock_executors["test_ds"].execute.side_effect = execute_side_effect

        responses = [
            # 1. intent
            json.dumps({
                "tables": [{"table_name": "users", "datasource_id": "test_ds", "confidence": 0.9}],
                "filters": [],
                "aggregation": "count",
                "dimensions": [],
                "ambiguities": [],
                "confidence": 0.9,
                "analysis": "统计用户数量",
            }),
            # 2. generate_sql (第一次，有错误) — probe/rewrite/clarify 均快速跳过
            "```sql\nSELECT invalid_col FROM users\n```",
            # 3. reflect (需要修正)
            json.dumps({
                "satisfied": False,
                "needs_revision": True,
                "thought": "列名错误，需要修正",
                "suggested_fix": "使用正确的列名",
            }),
            # 4. generate_sql (第二次，正确)
            "```sql\nSELECT COUNT(*) FROM users\n```",
            # 5. reflect (满意)
            json.dumps({
                "satisfied": True,
                "needs_revision": False,
                "thought": "结果正确",
                "suggested_fix": "",
            }),
            # 6. summarize
            "系统中有 42 个用户。",
        ]
        mock_llm = _make_mock_llm(responses)

        with patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.probe.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.rewrite.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.clarify.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.generate.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.reflect.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.summarize.create_llm_client", return_value=mock_llm):

            agent = NL2SQLAgent(
                project_id="test",
                datasources=sample_datasources,
                executors=mock_executors,
                max_iterations=5,
            )
            result = agent.run("多少用户")

        assert result["status"] == "done"
        assert result["iteration"] >= 1
        assert result["sql"] is not None
        assert result["answer"] is not None

    def test_build_graph_returns_state_graph(self):
        """测试 build_graph 函数返回 StateGraph。"""
        from nl2sql.agent.graph import build_graph
        from langgraph.graph import StateGraph

        graph = build_graph()
        assert isinstance(graph, StateGraph)


# ===========================================================================
# route_after_clarify 路由函数测试
# ===========================================================================

class TestRouteAfterClarify:
    def test_query_intent_routes_to_generate_sql(self):
        """普通查询意图应路由到 generate_sql。"""
        from nl2sql.agent.graph import route_after_clarify
        from nl2sql.agent.state import IntentResult

        state = {
            "intent": IntentResult(action="query"),
            "awaiting_clarification": False,
            "clarification_questions": [],
        }
        assert route_after_clarify(state) == "generate_sql"

    def test_connect_datasource_routes_to_connect_node(self):
        """connect_datasource 意图应路由到 connect_datasource 节点。"""
        from nl2sql.agent.graph import route_after_clarify
        from nl2sql.agent.state import IntentResult

        state = {
            "intent": IntentResult(action="connect_datasource"),
            "awaiting_clarification": False,
            "clarification_questions": [],
        }
        assert route_after_clarify(state) == "connect_datasource"

    def test_needs_clarification_routes_to_ask_clarify(self):
        """有未解决的澄清问题时，优先路由到 ask_clarify。"""
        from nl2sql.agent.graph import route_after_clarify
        from nl2sql.agent.state import IntentResult

        state = {
            "intent": IntentResult(action="query"),
            "awaiting_clarification": True,
            "clarification_questions": ["时间范围是？"],
        }
        assert route_after_clarify(state) == "ask_clarify"

    def test_connect_datasource_with_clarification_routes_to_ask(self):
        """connect_datasource 意图需要澄清时，也走 ask_clarify。"""
        from nl2sql.agent.graph import route_after_clarify
        from nl2sql.agent.state import IntentResult

        state = {
            "intent": IntentResult(action="connect_datasource"),
            "awaiting_clarification": True,
            "clarification_questions": ["密码是？"],
        }
        assert route_after_clarify(state) == "ask_clarify"

    def test_default_to_generate_sql_when_no_intent(self):
        """没有 intent 时默认走 generate_sql（兼容旧行为）。"""
        from nl2sql.agent.graph import route_after_clarify

        state = {
            "intent": None,
            "awaiting_clarification": False,
            "clarification_questions": [],
        }
        assert route_after_clarify(state) == "generate_sql"


# ===========================================================================
# AgentState 新字段测试
# ===========================================================================

class TestAgentStateDatasourceFields:
    def test_datasource_id_default_none(self):
        """AgentState 的 datasource_id 默认为 None。"""
        from nl2sql.agent.state import AgentState

        state = AgentState(project_id="p1")
        assert state.datasource_id is None

    def test_tables_imported_default_zero(self):
        """AgentState 的 tables_imported 默认为 0。"""
        from nl2sql.agent.state import AgentState

        state = AgentState(project_id="p1")
        assert state.tables_imported == 0

    def test_can_set_datasource_fields(self):
        """可以设置 datasource_id 和 tables_imported。"""
        from nl2sql.agent.state import AgentState

        state = AgentState(project_id="p1", datasource_id="ds_123", tables_imported=5)
        assert state.datasource_id == "ds_123"
        assert state.tables_imported == 5


class TestSelectedDatasourceId:
    """测试 selected_datasource_id 在 agent 初始化时的传递。"""

    def test_run_with_selected_datasource_id(self, sample_datasources, mock_executors):
        """NL2SQLAgent.run() 接受 selected_datasource_id 并写入初始 state。"""
        from nl2sql.agent.graph import NL2SQLAgent

        mock_llm = _make_mock_llm([
            json.dumps({
                "tables": [{"name": "users", "reason": "用户表"}],
                "filters": [],
                "aggregation": "count",
                "dimensions": [],
                "ambiguities": [],
                "confidence": 0.9,
                "analysis": "用户想查用户数",
            }),
        ])

        agent = NL2SQLAgent(
            project_id="test_proj",
            datasources=sample_datasources,
            executors=mock_executors,
        )

        # 用 invoke 的初始 state 来验证
        # 通过 mock _app.invoke 来捕获传入的 state
        original_invoke = agent._app.invoke
        captured_state = {}

        def mock_invoke(state, config=None):
            captured_state.update(state)
            return original_invoke(state, config)

        with patch.object(agent._app, 'invoke', side_effect=mock_invoke):
            with patch('nl2sql.agent.nodes.intent.create_llm_client', return_value=mock_llm):
                try:
                    agent.run("test query", None, selected_datasource_id="test_ds")
                except Exception:
                    # 流程可能因为 mock 不全而失败，但我们只关心初始 state
                    pass

        assert captured_state.get("selected_datasource_id") == "test_ds"

    def test_run_without_selected_datasource_id_defaults_none(
        self, sample_datasources, mock_executors
    ):
        """不传 selected_datasource_id 时默认为 None。"""
        from nl2sql.agent.graph import NL2SQLAgent

        mock_llm = _make_mock_llm([
            json.dumps({
                "tables": [{"name": "users", "reason": "用户表"}],
                "filters": [],
                "aggregation": "count",
                "dimensions": [],
                "ambiguities": [],
                "confidence": 0.9,
                "analysis": "用户想查用户数",
            }),
        ])

        agent = NL2SQLAgent(
            project_id="test_proj",
            datasources=sample_datasources,
            executors=mock_executors,
        )

        captured_state = {}
        original_invoke = agent._app.invoke

        def mock_invoke(state, config=None):
            captured_state.update(state)
            return original_invoke(state, config)

        with patch.object(agent._app, 'invoke', side_effect=mock_invoke):
            with patch('nl2sql.agent.nodes.intent.create_llm_client', return_value=mock_llm):
                try:
                    agent.run("test query", None)
                except Exception:
                    pass

        assert captured_state.get("selected_datasource_id") is None
