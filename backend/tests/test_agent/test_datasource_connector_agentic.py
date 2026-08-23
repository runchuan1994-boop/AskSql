"""测试 DatasourceConnectorAgent 的 agentic 驱动安装能力."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_llm(responses: list):
    """创建一个按顺序返回响应的 mock LLM.

    每个响应可以是:
    - 字符串: 纯文本回答
    - dict: {"content": "...", "tool_calls": [{"name": "...", "arguments": {...}}]}
    """
    from nl2sql.llm import ToolCall

    mock_llm = MagicMock()
    call_idx = [0]

    def chat_side_effect(*args, **kwargs):
        resp = MagicMock()
        item = responses[min(call_idx[0], len(responses) - 1)]
        call_idx[0] += 1

        if isinstance(item, str):
            resp.content = item
            resp.tool_calls = []
        else:
            resp.content = item.get("content", "")
            tool_calls = []
            for tc in item.get("tool_calls", []):
                tool_calls.append(ToolCall(
                    id=tc.get("id", "call-1"),
                    name=tc["name"],
                    arguments=tc.get("arguments", {}),
                ))
            resp.tool_calls = tool_calls
        return resp

    mock_llm.chat.side_effect = chat_side_effect
    return mock_llm


class TestAgenticDriverInstallation:
    """测试 Agent 能在连接失败时自动安装驱动并重试."""

    def test_connect_without_driver_agent_installs_it(self):
        """连接失败提示缺驱动时，Agent 应该自动安装驱动并重试.

        流程:
        1. Agent 调用 create_datasource → 成功
        2. Agent 调用 test_connection → 失败 (No module named 'psycopg2')
        3. Agent 调用 install_driver(\"psycopg2-binary\") → 成功
        4. Agent 调用 test_connection_sandbox → 成功
        5. Agent 用自然语言总结
        """
        from nl2sql.agent.datasource_connector import DatasourceConnectorAgent

        responses = [
            # 第一轮: 创建数据源
            {
                "content": "",
                "tool_calls": [{"name": "create_datasource", "arguments": {
                    "name": "测试库", "type": "postgresql",
                    "host": "localhost", "port": 5432,
                    "database": "mydb", "username": "user", "password": "pass",
                }}],
            },
            # 第二轮: 测试连接（失败，缺驱动）
            {
                "content": "",
                "tool_calls": [{"name": "test_connection", "arguments": {
                    "datasource_id": "ds_123",
                }}],
            },
            # 第三轮: 安装驱动
            {
                "content": "",
                "tool_calls": [{"name": "install_driver", "arguments": {
                    "package": "psycopg2-binary",
                }}],
            },
            # 第四轮: 沙盒中重新测试连接
            {
                "content": "",
                "tool_calls": [{"name": "test_connection_sandbox", "arguments": {
                    "db_url": "postgresql://user:pass@localhost:5432/mydb",
                }}],
            },
            # 第五轮: 总结回答
            "已在沙盒中成功安装 psycopg2-binary 驱动，沙盒测试连接成功。",
        ]

        mock_llm = _make_mock_llm(responses)

        # mock 工具执行
        def mock_execute_tool(self, tool_name, tool_args, state_proxy):
            if tool_name == "create_datasource":
                return "数据源创建成功：\n  ID: ds_123\n  名称: 测试库"
            elif tool_name == "test_connection":
                return "连接失败：No module named 'psycopg2'"
            elif tool_name == "install_driver":
                return "驱动安装成功：psycopg2-binary\n现在可以调用 test_connection_sandbox 测试连接是否正常。"
            elif tool_name == "test_connection_sandbox":
                return "连接测试成功：沙盒可以正常连接到数据库。"
            return "未知工具"

        with patch("nl2sql.agent.datasource_connector.create_llm_client", return_value=mock_llm), \
             patch.object(DatasourceConnectorAgent, "_execute_tool", mock_execute_tool):

            agent = DatasourceConnectorAgent(
                project_id="test",
                use_sandbox_tools=True,
            )
            result = agent.run("帮我连接 postgresql://user:pass@localhost:5432/mydb")

        assert result["status"] == "done"
        assert result["datasource_id"] == "ds_123"
        assert "psycopg2" in result["answer"] or "沙盒" in result["answer"]

    def test_install_driver_failed_agent_reports(self):
        """驱动安装失败时，Agent 应该告知用户."""
        from nl2sql.agent.datasource_connector import DatasourceConnectorAgent

        responses = [
            # 第一轮: 创建数据源
            {"content": "", "tool_calls": [{"name": "create_datasource", "arguments": {
                "name": "测试库", "type": "postgresql",
                "host": "localhost", "database": "mydb",
                "username": "user", "password": "pass",
            }}]},
            # 第二轮: 测试连接失败
            {"content": "", "tool_calls": [{"name": "test_connection", "arguments": {
                "datasource_id": "ds_123",
            }}]},
            # 第三轮: 尝试安装驱动
            {"content": "", "tool_calls": [{"name": "install_driver", "arguments": {
                "package": "psycopg2-binary",
            }}]},
            # 第四轮: 告知失败
            "很抱歉，psycopg2-binary 驱动安装失败了。可能是网络问题或包名不正确。",
        ]

        mock_llm = _make_mock_llm(responses)

        def mock_execute_tool(self, tool_name, tool_args, state_proxy):
            if tool_name == "create_datasource":
                return "数据源创建成功：\n  ID: ds_123\n  名称: 测试库"
            elif tool_name == "test_connection":
                return "连接失败：No module named 'psycopg2'"
            elif tool_name == "install_driver":
                return "驱动安装失败：psycopg2-binary\n请检查包名是否正确"
            return "未知工具"

        with patch("nl2sql.agent.datasource_connector.create_llm_client", return_value=mock_llm), \
             patch.object(DatasourceConnectorAgent, "_execute_tool", mock_execute_tool):

            agent = DatasourceConnectorAgent(
                project_id="test",
                use_sandbox_tools=True,
            )
            result = agent.run("帮我连接 pg 数据库")

        assert result["status"] == "done"
        assert "失败" in result["answer"] or "抱歉" in result["answer"]


class TestSandboxToolsAvailability:
    """测试沙盒工具的可用性判断."""

    def test_sandbox_disabled_no_sandbox_tools(self):
        """沙盒未启用时，工具列表不包含沙盒工具."""
        from nl2sql.agent.datasource_connector import DatasourceConnectorAgent
        from unittest.mock import patch

        with patch.dict("os.environ", {"SANDBOX_ENABLED": "false"}):
            agent = DatasourceConnectorAgent(project_id="test", use_sandbox_tools=True)
            tools = agent._build_tools()

        tool_names = [t["function"]["name"] for t in tools]
        assert "install_driver" not in tool_names
        assert "test_connection_sandbox" not in tool_names
        # 普通工具应该还在
        assert "create_datasource" in tool_names
        assert "test_connection" in tool_names

    def test_use_sandbox_tools_false(self):
        """use_sandbox_tools=False 时不加载沙盒工具."""
        from nl2sql.agent.datasource_connector import DatasourceConnectorAgent

        agent = DatasourceConnectorAgent(project_id="test", use_sandbox_tools=False)
        tools = agent._build_tools()

        tool_names = [t["function"]["name"] for t in tools]
        assert "install_driver" not in tool_names
        assert "test_connection_sandbox" not in tool_names

    def test_tools_include_basic_datasource_tools(self):
        """基础数据源工具始终可用."""
        from nl2sql.agent.datasource_connector import DatasourceConnectorAgent

        agent = DatasourceConnectorAgent(project_id="test", use_sandbox_tools=False)
        tools = agent._build_tools()

        tool_names = [t["function"]["name"] for t in tools]
        assert "create_datasource" in tool_names
        assert "test_connection" in tool_names
        assert "import_schema" in tool_names
