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
        """测试完整成功流程：意图→探查→澄清(无)→生成→执行→反思(满意)→总结。"""
        # 按调用顺序：intent → clarify → generate_sql → reflect → summarize
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
            # 2. clarify (no ambiguities, probe skips, then clarify returns [])
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
            "系统中共有 42 个用户。",
        ]
        mock_llm = _make_mock_llm(responses)

        # patch 所有节点模块的 create_llm_client
        with patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.probe.create_llm_client", return_value=mock_llm), \
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
            # 2. clarify
            "[]",
            # 3. generate_sql (第一次，有错误)
            "```sql\nSELECT invalid_col FROM users\n```",
            # 4. reflect (需要修正)
            json.dumps({
                "satisfied": False,
                "needs_revision": True,
                "thought": "列名错误，需要修正",
                "suggested_fix": "使用正确的列名",
            }),
            # 5. generate_sql (第二次，正确)
            "```sql\nSELECT COUNT(*) FROM users\n```",
            # 6. reflect (满意)
            json.dumps({
                "satisfied": True,
                "needs_revision": False,
                "thought": "结果正确",
                "suggested_fix": "",
            }),
            # 7. summarize
            "系统中有 42 个用户。",
        ]
        mock_llm = _make_mock_llm(responses)

        with patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm), \
             patch("nl2sql.agent.nodes.probe.create_llm_client", return_value=mock_llm), \
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
