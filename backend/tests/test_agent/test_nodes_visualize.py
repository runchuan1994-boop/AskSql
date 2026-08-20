"""Tests for the visualize node."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from nl2sql.agent.state import AgentState
from nl2sql.llm import ChatResponse
from nl2sql.executor import ExecutionResult


# ===========================================================================
# _extract_json
# ===========================================================================

class TestExtractJson:
    """Tests for the JSON extraction helper."""

    def test_pure_json(self):
        """Should parse pure JSON string."""
        from nl2sql.agent.nodes.visualize import _extract_json
        data = {"charts": [{"type": "bar", "title": "test"}]}
        result = _extract_json(json.dumps(data))
        assert result == data

    def test_markdown_json_block(self):
        """Should extract JSON from ```json ... ``` block."""
        from nl2sql.agent.nodes.visualize import _extract_json
        data = {"charts": [{"type": "line", "title": "trend"}]}
        text = f"```json\n{json.dumps(data)}\n```"
        result = _extract_json(text)
        assert result == data

    def test_markdown_generic_code_block(self):
        """Should extract JSON from ``` ... ``` block without language tag."""
        from nl2sql.agent.nodes.visualize import _extract_json
        data = {"charts": [{"type": "pie", "title": "pie chart"}]}
        text = f"```\n{json.dumps(data)}\n```"
        result = _extract_json(text)
        assert result == data

    def test_json_with_surrounding_text(self):
        """Should extract JSON when surrounded by explanatory text."""
        from nl2sql.agent.nodes.visualize import _extract_json
        data = {"charts": [{"type": "metric", "title": "metric card"}]}
        text = f"以下是可视化配置：\n{json.dumps(data)}\n希望对你有帮助。"
        result = _extract_json(text)
        assert result == data

    def test_invalid_json_returns_none(self):
        """Should return None for invalid JSON."""
        from nl2sql.agent.nodes.visualize import _extract_json
        assert _extract_json("not json at all") is None

    def test_empty_string_returns_none(self):
        """Should return None for empty string."""
        from nl2sql.agent.nodes.visualize import _extract_json
        assert _extract_json("") is None


# ===========================================================================
# _validate_viz_spec
# ===========================================================================

class TestValidateVizSpec:
    """Tests for the VizSpec validation helper."""

    def test_valid_single_chart(self):
        """Should accept a valid single chart spec."""
        from nl2sql.agent.nodes.visualize import _validate_viz_spec
        data = {"charts": [{"type": "bar", "title": "销售对比", "x_field": "region", "y_field": "amount"}]}
        result = _validate_viz_spec(data)
        assert result is not None
        assert len(result["charts"]) == 1
        assert result["charts"][0]["type"] == "bar"
        assert result["charts"][0]["title"] == "销售对比"
        assert result["charts"][0]["x_field"] == "region"
        assert result["charts"][0]["y_field"] == "amount"

    def test_valid_multiple_charts(self):
        """Should accept multiple chart specs."""
        from nl2sql.agent.nodes.visualize import _validate_viz_spec
        data = {"charts": [
            {"type": "line", "title": "趋势", "x_field": "date", "y_field": "value"},
            {"type": "table", "title": "明细数据"},
        ]}
        result = _validate_viz_spec(data)
        assert result is not None
        assert len(result["charts"]) == 2

    def test_invalid_type_skipped(self):
        """Should skip charts with invalid types."""
        from nl2sql.agent.nodes.visualize import _validate_viz_spec
        data = {"charts": [
            {"type": "invalid_type", "title": "bad"},
            {"type": "bar", "title": "good"},
        ]}
        result = _validate_viz_spec(data)
        assert result is not None
        assert len(result["charts"]) == 1
        assert result["charts"][0]["type"] == "bar"

    def test_empty_charts_returns_none(self):
        """Should return None when charts list is empty."""
        from nl2sql.agent.nodes.visualize import _validate_viz_spec
        assert _validate_viz_spec({"charts": []}) is None

    def test_no_charts_key_returns_none(self):
        """Should return None when charts key is missing."""
        from nl2sql.agent.nodes.visualize import _validate_viz_spec
        assert _validate_viz_spec({"other": "data"}) is None

    def test_non_dict_returns_none(self):
        """Should return None for non-dict input."""
        from nl2sql.agent.nodes.visualize import _validate_viz_spec
        assert _validate_viz_spec(None) is None
        assert _validate_viz_spec("string") is None
        assert _validate_viz_spec([]) is None

    def test_default_title_when_missing(self):
        """Should provide default title when title is missing."""
        from nl2sql.agent.nodes.visualize import _validate_viz_spec
        data = {"charts": [{"type": "table"}]}
        result = _validate_viz_spec(data)
        assert result is not None
        assert result["charts"][0]["title"] == "数据图表"

    def test_all_valid_types(self):
        """Should accept all six valid chart types."""
        from nl2sql.agent.nodes.visualize import _validate_viz_spec
        types = ["line", "bar", "pie", "area", "metric", "table"]
        charts = [{"type": t, "title": f"{t} chart"} for t in types]
        data = {"charts": charts}
        result = _validate_viz_spec(data)
        assert result is not None
        assert len(result["charts"]) == 6
        for i, t in enumerate(types):
            assert result["charts"][i]["type"] == t

    def test_non_dict_chart_entries_skipped(self):
        """Should skip non-dict entries in charts list."""
        from nl2sql.agent.nodes.visualize import _validate_viz_spec
        data = {"charts": [
            "not a dict",
            None,
            {"type": "bar", "title": "valid"},
        ]}
        result = _validate_viz_spec(data)
        assert result is not None
        assert len(result["charts"]) == 1

    def test_stacked_defaults_to_false(self):
        """Should default stacked to False."""
        from nl2sql.agent.nodes.visualize import _validate_viz_spec
        data = {"charts": [{"type": "bar", "title": "test"}]}
        result = _validate_viz_spec(data)
        assert result["charts"][0]["stacked"] is False

    def test_stacked_can_be_true(self):
        """Should respect stacked=True."""
        from nl2sql.agent.nodes.visualize import _validate_viz_spec
        data = {"charts": [{"type": "bar", "title": "test", "stacked": True}]}
        result = _validate_viz_spec(data)
        assert result["charts"][0]["stacked"] is True

    def test_config_default_empty_dict(self):
        """Should default config to empty dict."""
        from nl2sql.agent.nodes.visualize import _validate_viz_spec
        data = {"charts": [{"type": "table", "title": "t"}]}
        result = _validate_viz_spec(data)
        assert result["charts"][0]["config"] == {}


# ===========================================================================
# _build_data_preview
# ===========================================================================

class TestBuildDataPreview:
    """Tests for the data preview helper."""

    def test_preview_includes_columns_and_rows(self):
        """Should include column names and row data."""
        from nl2sql.agent.nodes.visualize import _build_data_preview
        result = ExecutionResult(
            success=True,
            sql="SELECT * FROM t",
            columns=["name", "value"],
            rows=[("a", 1), ("b", 2)],
            row_count=2,
        )
        preview = _build_data_preview(result)
        assert "name, value" in preview
        assert "总行数: 2" in preview
        assert "a, 1" in preview

    def test_preview_truncates_long_results(self):
        """Should truncate results beyond max_rows."""
        from nl2sql.agent.nodes.visualize import _build_data_preview
        rows = [(i,) for i in range(100)]
        result = ExecutionResult(
            success=True,
            sql="SELECT * FROM t",
            columns=["n"],
            rows=rows,
            row_count=100,
        )
        preview = _build_data_preview(result, max_rows=30)
        assert "还有 70 行" in preview

    def test_no_data_returns_placeholder(self):
        """Should return placeholder when no data."""
        from nl2sql.agent.nodes.visualize import _build_data_preview
        result = ExecutionResult(success=True, sql="SELECT 1", columns=[], rows=[], row_count=0)
        preview = _build_data_preview(result)
        assert "无数据" in preview


# ===========================================================================
# visualize_node
# ===========================================================================

class TestVisualizeNode:
    """Tests for visualize_node."""

    @pytest.fixture
    def agent_state(self):
        state = AgentState(
            project_id="proj-1",
            datasources=[],
            user_query="每月销售额统计",
        )
        return state

    def test_no_execution_result_returns_none(self, agent_state):
        """Should return viz_spec=None when there is no execution result."""
        from nl2sql.agent.nodes.visualize import visualize_node
        agent_state.execution_result = None
        result = visualize_node(agent_state)
        assert result["viz_spec"] is None

    def test_failed_execution_returns_none(self, agent_state):
        """Should return viz_spec=None when execution failed."""
        from nl2sql.agent.nodes.visualize import visualize_node
        agent_state.execution_result = ExecutionResult(
            success=False,
            sql="SELECT * FROM bad",
            error="table not found",
        )
        result = visualize_node(agent_state)
        assert result["viz_spec"] is None

    def test_empty_data_returns_none(self, agent_state):
        """Should return viz_spec=None when data is empty."""
        from nl2sql.agent.nodes.visualize import visualize_node
        agent_state.execution_result = ExecutionResult(
            success=True,
            sql="SELECT * FROM t",
            columns=["id"],
            rows=[],
            row_count=0,
        )
        result = visualize_node(agent_state)
        assert result["viz_spec"] is None

    def test_success_generates_viz_spec(self, agent_state):
        """Should generate a valid viz_spec on successful LLM call."""
        from nl2sql.agent.nodes.visualize import visualize_node

        agent_state.sql = "SELECT month, amount FROM sales ORDER BY month"
        agent_state.execution_result = ExecutionResult(
            success=True,
            sql="SELECT month, amount FROM sales ORDER BY month",
            columns=["month", "amount"],
            rows=[("2024-01", 100), ("2024-02", 200)],
            row_count=2,
        )

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content=json.dumps({
                "charts": [
                    {"type": "line", "title": "月度销售额趋势", "x_field": "month", "y_field": "amount"}
                ]
            }),
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.visualize.create_llm_client", return_value=mock_llm):
            result = visualize_node(agent_state)

        assert result["viz_spec"] is not None
        assert len(result["viz_spec"]["charts"]) == 1
        assert result["viz_spec"]["charts"][0]["type"] == "line"
        assert result["viz_spec"]["charts"][0]["x_field"] == "month"

    def test_llm_returns_invalid_json_returns_none(self, agent_state):
        """Should return viz_spec=None when LLM returns unparseable content."""
        from nl2sql.agent.nodes.visualize import visualize_node

        agent_state.sql = "SELECT 1"
        agent_state.execution_result = ExecutionResult(
            success=True, sql="SELECT 1", columns=["1"], rows=[(1,)], row_count=1,
        )

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content="我无法生成可视化配置，因为数据太复杂了。",
            model="test-model",
        )

        with patch("nl2sql.agent.nodes.visualize.create_llm_client", return_value=mock_llm):
            result = visualize_node(agent_state)

        assert result["viz_spec"] is None

    def test_sends_viz_ready_event_on_success(self, agent_state):
        """Should send viz_ready event when visualization is ready."""
        from nl2sql.agent.nodes.visualize import visualize_node

        agent_state.sql = "SELECT 1"
        agent_state.execution_result = ExecutionResult(
            success=True, sql="SELECT 1", columns=["1"], rows=[(1,)], row_count=1,
        )

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content=json.dumps({
                "charts": [{"type": "metric", "title": "结果"}]
            }),
            model="test-model",
        )
        event_callback = MagicMock()
        agent_state.event_callback = event_callback

        with patch("nl2sql.agent.nodes.visualize.create_llm_client", return_value=mock_llm):
            visualize_node(agent_state)

        event_types = [call[0][0] for call in event_callback.call_args_list]
        assert "viz_ready" in event_types

        # Find the viz_ready call and check data
        viz_calls = [c for c in event_callback.call_args_list if c[0][0] == "viz_ready"]
        assert len(viz_calls) == 1
        assert len(viz_calls[0][0][1]["charts"]) > 0

    def test_sends_viz_ready_event_on_parse_failure(self, agent_state):
        """Should send viz_ready event with parse_failed note on parse error."""
        from nl2sql.agent.nodes.visualize import visualize_node

        agent_state.sql = "SELECT 1"
        agent_state.execution_result = ExecutionResult(
            success=True, sql="SELECT 1", columns=["1"], rows=[(1,)], row_count=1,
        )

        mock_llm = MagicMock()
        mock_llm.chat.return_value = ChatResponse(
            content="not json at all",
            model="test-model",
        )
        event_callback = MagicMock()
        agent_state.event_callback = event_callback

        with patch("nl2sql.agent.nodes.visualize.create_llm_client", return_value=mock_llm):
            visualize_node(agent_state)

        viz_calls = [c for c in event_callback.call_args_list if c[0][0] == "viz_ready"]
        assert len(viz_calls) == 1
        assert viz_calls[0][0][1]["note"] == "parse_failed"

    def test_llm_exception_returns_none(self, agent_state):
        """Should return viz_spec=None when LLM raises an exception."""
        from nl2sql.agent.nodes.visualize import visualize_node

        agent_state.sql = "SELECT 1"
        agent_state.execution_result = ExecutionResult(
            success=True, sql="SELECT 1", columns=["1"], rows=[(1,)], row_count=1,
        )

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = RuntimeError("LLM service unavailable")

        with patch("nl2sql.agent.nodes.visualize.create_llm_client", return_value=mock_llm):
            result = visualize_node(agent_state)

        assert result["viz_spec"] is None
