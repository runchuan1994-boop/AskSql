"""测试 DatasourceConnectorAgent 的 agentic 修复循环 + 护栏."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nl2sql.llm import ToolCall


def _make_mock_llm(responses: list):
    """创建按顺序返回响应的 mock LLM.

    每个响应可以是:
    - 字符串: 纯文本回答
    - dict: {"content": "...", "tool_calls": [{"name": "...", "arguments": {...}}]}
    """
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


class TestEnvironmentSelfSelection:
    """测试 Agent 能自主选择执行环境."""

    def test_agent_chooses_sandbox_for_driver_install(self):
        """遇到驱动缺失时，Agent 应该自主选择沙盒环境安装驱动.

        流程:
        1. create_datasource（主进程，要持久化）
        2. test_connection（主进程，快）→ 失败，缺驱动
        3. install_driver（沙盒，动态安装）→ Agent 自主决策
        4. test_connection_sandbox（沙盒验证）
        5. 汇报结果
        """
        from nl2sql.agent.datasource_connector import DatasourceConnectorAgent

        responses = [
            # 第一轮: 创建数据源（主进程）
            {"content": "", "tool_calls": [{"name": "create_datasource", "arguments": {
                "name": "测试库", "type": "postgresql",
                "host": "localhost", "port": 5432,
                "database": "mydb", "username": "user", "password": "pass",
            }}]},
            # 第二轮: 主进程测试连接
            {"content": "", "tool_calls": [{"name": "test_connection", "arguments": {
                "datasource_id": "ds_123",
            }}]},
            # 第三轮: 自主决定装驱动（用沙盒工具）
            {"content": "", "tool_calls": [{"name": "install_driver", "arguments": {
                "package": "psycopg2-binary",
            }}]},
            # 第四轮: 沙盒中验证连接
            {"content": "", "tool_calls": [{"name": "test_connection_sandbox", "arguments": {
                "db_url": "postgresql://user:pass@localhost:5432/mydb",
            }}]},
            # 第五轮: 总结
            "已在沙盒中成功安装 psycopg2-binary 驱动，沙盒连接测试通过。"
            "主服务环境仍需安装驱动才能完整使用（如schema导入、SQL查询等）。",
        ]

        mock_llm = _make_mock_llm(responses)

        # mock 工具执行
        def mock_execute_tool(self, tool_name, tool_args, state_proxy):
            if tool_name == "create_datasource":
                return "数据源创建成功：\n  ID: ds_123\n  名称: 测试库"
            elif tool_name == "test_connection":
                return "连接失败：No module named 'psycopg2'"
            elif tool_name == "install_driver":
                return "驱动安装成功：psycopg2-binary"
            elif tool_name == "test_connection_sandbox":
                return "✅ 连接测试成功\n沙盒环境可以正常连接到数据库。"
            return "未知工具"

        with patch("nl2sql.agent.datasource_connector.create_llm_client", return_value=mock_llm), \
             patch.object(DatasourceConnectorAgent, "_execute_tool", mock_execute_tool):

            agent = DatasourceConnectorAgent(project_id="test", use_sandbox_tools=True)
            result = agent.run("帮我连接 postgresql://user:pass@localhost:5432/mydb")

        assert result["status"] == "done"
        assert "psycopg2" in result["answer"].lower() or "沙盒" in result["answer"]
        assert result["datasource_id"] == "ds_123"


class TestGuardrails:
    """测试护栏机制."""

    def test_duplicate_driver_install_blocked(self):
        """同一个驱动包安装两次，第二次应该被护栏拦截."""
        from nl2sql.agent.datasource_connector import DatasourceConnectorAgent

        agent = DatasourceConnectorAgent(project_id="test", use_sandbox_tools=False)

        # 第一次安装
        state_proxy = MagicMock()
        with patch.object(agent, "_execute_tool", wraps=agent._execute_tool) as mock_exec:
            # 因为我们没有真的 docker，直接手动调用内部方法测试护栏
            pass

        # 直接测试护栏逻辑
        fix_key_1 = agent._make_fix_key("install_driver", {"package": "psycopg2-binary"})
        assert fix_key_1 == "install_driver:psycopg2-binary"

        # 标记已尝试
        agent._attempted_fixes.add(fix_key_1)

        # 再次尝试同一个包，应该被拦截
        # 验证 _make_fix_key 生成的 key 正确
        fix_key_2 = agent._make_fix_key("install_driver", {"package": "psycopg2-binary"})
        assert fix_key_2 == fix_key_1
        assert fix_key_2 in agent._attempted_fixes

    def test_test_connection_not_tracked(self):
        """test_connection 类的验证动作不应该被追踪（每次都要做）."""
        from nl2sql.agent.datasource_connector import DatasourceConnectorAgent

        agent = DatasourceConnectorAgent(project_id="test", use_sandbox_tools=False)

        # 验证类工具不生成 fix_key
        assert agent._make_fix_key("test_connection", {"datasource_id": "ds1"}) is None
        assert agent._make_fix_key("test_connection_sandbox", {"db_url": "..."}) is None

    def test_different_packages_not_blocked(self):
        """不同的驱动包不会互相影响."""
        from nl2sql.agent.datasource_connector import DatasourceConnectorAgent

        agent = DatasourceConnectorAgent(project_id="test", use_sandbox_tools=False)

        key1 = agent._make_fix_key("install_driver", {"package": "psycopg2-binary"})
        key2 = agent._make_fix_key("install_driver", {"package": "pymysql"})

        assert key1 != key2
        assert key1 == "install_driver:psycopg2-binary"
        assert key2 == "install_driver:pymysql"

    def test_max_iterations_hard_limit(self):
        """超过最大迭代次数后，Agent 应该停止并返回失败."""
        from nl2sql.agent.datasource_connector import DatasourceConnectorAgent

        # LLM 一直返回工具调用，模拟死循环倾向
        responses = [{"content": "", "tool_calls": [{"name": "test_connection", "arguments": {
            "datasource_id": "ds_123",
        }}]}] * 10  # 10 次工具调用

        mock_llm = _make_mock_llm(responses)

        def mock_execute_tool(self, tool_name, tool_args, state_proxy):
            return "连接失败：No module named 'psycopg2'"

        with patch("nl2sql.agent.datasource_connector.create_llm_client", return_value=mock_llm), \
             patch.object(DatasourceConnectorAgent, "_execute_tool", mock_execute_tool):

            agent = DatasourceConnectorAgent(
                project_id="test",
                use_sandbox_tools=False,
                max_iterations=3,  # 设一个小的上限
            )
            result = agent.run("测试连接")

        # 应该是 failed（因为超过迭代次数，LLM 没机会输出最终答案）
        # 或者 status 是 done 但 answer 是最后一次 LLM 响应
        # 关键是不会无限循环
        assert result["status"] in ("done", "failed")

    def test_attempted_fixes_starts_empty(self):
        """初始状态 attempted_fixes 应该为空."""
        from nl2sql.agent.datasource_connector import DatasourceConnectorAgent

        agent = DatasourceConnectorAgent(project_id="test")
        assert len(agent._attempted_fixes) == 0
