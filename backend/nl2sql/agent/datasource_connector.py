"""Datasource Connector Agent: 数据源接入 Agent.

负责帮助用户创建并配置数据源，流程：
1. 从用户消息中提取连接信息
2. 创建数据源
3. 测试连接（沙盒中测试，支持动态安装驱动）
4. 导入 schema

从原来的 connect_datasource_node 拆分为独立 Agent，
便于 dispatcher 统一调度。

Agentic 特性：
- 如果测试连接失败且提示缺少驱动，Agent 可以自动调用 install_driver
  在沙盒中安装驱动，然后重试连接。
- 驱动安装在沙盒里，不污染主进程环境。
"""
from __future__ import annotations

import re
from typing import Callable

from nl2sql.llm import Message, MessageRole, ToolCall, ToolCallResult
from nl2sql.llm.factory import create_llm_client

from nl2sql.agent.tools.datasource_tools import DATASOURCE_TOOLS, execute_datasource_tool
from nl2sql.agent.tools.datasource_sandbox_tools import (
    SANDBOX_DATASOURCE_TOOLS,
    SANDBOX_DATASOURCE_TOOL_FUNCTIONS,
)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

CONNECT_DS_SYSTEM_PROMPT = """你是一个数据源连接助手，负责帮助用户创建并配置数据源。

你是一个自主智能体（agentic assistant），你需要自己判断：
- 每一步做什么
- 在哪个执行环境中做（主进程 或 沙盒）
- 遇到问题时怎么诊断、怎么修复
- 什么时候放弃、什么时候寻求用户帮助

## 一、两种执行环境（你自己选择）

你有两种执行环境可用，根据操作性质自己选择：

【主进程环境】
- 可用工具: create_datasource, test_connection, import_schema
- 特点: 执行快、结果持久化（写入数据库/文件）、功能完整
- 限制: 驱动是固定的，不能动态安装；出错可能影响主服务
- 适合: 创建数据源、导入Schema、需要持久化结果的正式操作

【沙盒环境】
- 可用工具: test_connection_sandbox, install_driver（沙盒中还可以执行SQL探查等）
- 特点: 完全隔离、安全、可以动态 pip install 任何驱动包
- 限制: 不持久化（沙盒用完即毁）、启动稍慢
- 适合: 验证驱动是否可用、测试连接、实验性操作、缺驱动时的临时方案

选择原则（你自己判断，不是硬性规定）：
1. 需要持久化的正式操作 → 主进程
2. 需要动态装驱动 / 不确定会不会成功 → 先在沙盒里试
3. 主进程因为缺驱动失败了 → 换到沙盒试试
4. 沙盒验证通过了 → 再在主进程做正式操作（如果主进程也有驱动的话）

## 二、常见数据库驱动参考

以下是常见数据库对应的 Python 驱动包（仅供参考，你可以自由选择或尝试其他包）：

- PostgreSQL: psycopg2-binary（推荐）, psycopg2
- MySQL: mysql-connector-python（官方）, pymysql（纯Python）, mysqlclient
- SQLite: 内置，无需安装
- Oracle: oracledb, cx_Oracle
- SQL Server: pyodbc, pymssql

## 三、错误诊断与修复循环

连接测试失败时，不要直接告诉用户失败。按照以下思考框架自主诊断和修复：

### 诊断
仔细阅读错误信息中的结构化诊断（error_type）：
- driver_missing: 缺少驱动模块 → 用 install_driver 安装
- authentication_failed: 认证失败 → 确认用户名密码，必要时询问用户
- connection_refused: 连接被拒绝 → 检查host/port，必要时询问用户
- database_not_found: 数据库不存在 → 确认数据库名，必要时询问用户
- network_timeout: 网络超时 → 检查网络或重试
- unknown: 未知错误 → 分析错误信息，自行判断方案

### 修复循环（反思式）
1. 【诊断】理解错误类型和原因
2. 【生成方案】想出 2-3 种可能的修复方案，按成功概率排序
3. 【筛选】排除已经尝试过的方案（工具返回中会告诉你哪些试过了）
4. 【执行】选择最可能成功的方案
5. 【验证】测试连接验证是否修复成功
6. 【反思】
   - 成功了？→ 继续后续流程
   - 失败了？→ 错误类型变了吗？有进展吗？
   - 还有新方案吗？→ 回到步骤4
   - 没新方案了？→ 向用户汇报

### 护栏规则（必须严格遵守）
1. **不重复尝试**：同一个修复方案（比如安装同一个包）只能试一次，试过了就换别的
2. **最多 3 次修复尝试**：驱动安装类的修复最多试 3 个不同的包
3. **有进展才能继续**：如果连续 2 次都是同一个错误类型（说明修复没生效），换思路或向用户求助
4. **每次尝试要有差异**：每次尝试新方案时，心里想清楚"这次和上次有什么不同"
5. **总共最多 8 轮迭代**：到上限了就向用户汇报情况

## 四、工作流程（建议，你可以灵活调整）

建议的典型流程（但你可以根据情况自行调整）：

1. 提取连接信息 → 信息不够就问用户
2. 创建数据源（主进程，需要持久化）
3. 测试连接（主进程先试试，因为快）
   - 成功 → 导入 Schema → 完成
   - 失败且是驱动问题 → 换到沙盒
4. 沙盒中安装驱动 → 沙盒中验证连接
   - 沙盒成功 → 告知用户：沙盒验证通过，但主服务还缺驱动才能完整使用
   - 沙盒也失败 → 继续诊断和修复
5. 所有方案都试过后 → 向用户汇报结果和建议

## 五、最终汇报

完成或放弃时，用自然语言清晰地告诉用户：
- 做了哪些尝试
- 结果是什么
- 如果没解决，建议下一步怎么做
- 如果沙盒验证成功但主进程缺驱动，明确告诉用户需要在主服务环境安装驱动才能用完整功能

注意：
- 每一步只调用一个工具
- 用用户的语言回答
- 不要编造信息，所有操作基于真实结果
- 主动解决问题，但遇到真正无法解决的问题时，及时向用户说明，不要死循环
"""


# ---------------------------------------------------------------------------
# Event mapping for tool calls
# ---------------------------------------------------------------------------

_TOOL_EVENT_MAP: dict[str, tuple[str, str, str]] = {
    "create_datasource": ("ds_creating", "ds_created", "ds_create_failed"),
    "test_connection": ("ds_testing", "ds_connected", "ds_connection_failed"),
    "import_schema": ("ds_importing", "ds_imported", "ds_import_failed"),
    "install_driver": ("ds_installing_driver", "ds_driver_installed", "ds_driver_install_failed"),
    "test_connection_sandbox": ("ds_testing", "ds_connected", "ds_connection_failed"),
}


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class DatasourceConnectorAgent:
    """数据源接入 Agent.

    使用 tool calling 驱动 创建 → 测试 → 安装驱动（如需要）→ 导入 流程。

    支持 agentic 驱动安装：连接失败时自动在沙盒中安装驱动并重试。

    用法:
    ```python
    agent = DatasourceConnectorAgent(
        project_id="my_project",
        event_callback=my_callback,
    )
    result = agent.run("帮我连接 postgresql://user:pass@localhost:5432/mydb")
    ```
    """

    def __init__(
        self,
        project_id: str,
        event_callback: Callable[[str, dict], None] | None = None,
        max_iterations: int = 6,
        use_sandbox_tools: bool = True,
        session_id: str | None = None,
        step_logger=None,
    ):
        self.project_id = project_id
        self.event_callback = event_callback
        self.max_iterations = max_iterations
        self.use_sandbox_tools = use_sandbox_tools
        self.session_id = session_id

        # 护栏：已尝试的修复方案（防止重复尝试）
        # key: "install_driver:psycopg2-binary" 这样的标识
        self._attempted_fixes: set[str] = set()

        # 步骤耗时记录器（可选，None 则不记录）
        self._step_logger = step_logger

    def _send_event(self, event_type: str, data: dict | None = None) -> None:
        if self.event_callback is not None:
            try:
                self.event_callback(event_type, data or {})
            except Exception:
                pass

    def _send_tool_start_event(self, tool_name: str, args: dict) -> None:
        events = _TOOL_EVENT_MAP.get(tool_name)
        if events is None:
            return
        self._send_event(events[0], {"tool": tool_name, "args": args})

    def _send_tool_end_event(self, tool_name: str, result: str, success: bool) -> None:
        events = _TOOL_EVENT_MAP.get(tool_name)
        if events is None:
            return
        event_type = events[1] if success else events[2]
        self._send_event(event_type, {"tool": tool_name, "result": result})

    def _extract_datasource_id(self, result: str) -> str | None:
        match = re.search(r"ID:\s*(\S+)", result)
        if match:
            return match.group(1).strip()
        return None

    def _extract_table_count(self, result: str) -> int:
        match = re.search(r"共\s*(\d+)\s*张表", result)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return 0
        return 0

    def _build_tools(self) -> list[dict]:
        """构建可用工具列表.

        如果启用了沙盒工具，把沙盒工具也加进去。
        """
        tools = list(DATASOURCE_TOOLS)  # 复制一份
        if self.use_sandbox_tools:
            # 检查沙盒是否真的可用
            try:
                from sandbox.config import SandboxConfig
                config = SandboxConfig.from_env()
                if config.enabled:
                    tools.extend(SANDBOX_DATASOURCE_TOOLS)
            except (ImportError, Exception):
                pass
        return tools

    def _execute_tool(self, tool_name: str, tool_args: dict, state_proxy: dict) -> str:
        """执行一个工具调用.

        优先从沙盒工具里找，然后从 datasource 工具里找。
        包含护栏逻辑：防止重复尝试同一个修复方案。
        """
        # --- 护栏 1：重复尝试检查 ---
        fix_key = self._make_fix_key(tool_name, tool_args)
        if fix_key and fix_key in self._attempted_fixes:
            return (
                f"⚠️ 此方案已尝试过：{fix_key}\n"
                "请换一个不同的方案再试。"
                "如果想不出新方案，可以向用户说明情况。"
            )

        # 检查是否是沙盒工具
        if tool_name in SANDBOX_DATASOURCE_TOOL_FUNCTIONS:
            func = SANDBOX_DATASOURCE_TOOL_FUNCTIONS[tool_name]
            result = func(state_proxy, **tool_args)
            # 记录已尝试的修复方案
            if fix_key:
                self._attempted_fixes.add(fix_key)
            return result

        # 普通 datasource 工具
        result = execute_datasource_tool(tool_name, tool_args, self.project_id)
        if fix_key:
            self._attempted_fixes.add(fix_key)
        return result

    def _make_fix_key(self, tool_name: str, tool_args: dict) -> str | None:
        """生成修复方案的唯一标识，用于去重.

        只追踪"修复动作"类的工具调用，不追踪 test_connection 等验证动作
        （因为验证每次都要做）。
        """
        # 驱动安装：按包名去重
        if tool_name == "install_driver":
            package = tool_args.get("package", "").strip().lower()
            if package:
                return f"install_driver:{package}"

        # create_datasource / import_schema 只允许成功做一次
        # （失败的话可以重试，但我们不在这里追踪，留给 LLM 判断）

        # test_connection / test_connection_sandbox 不追踪（每次都要测）
        return None

    def run(self, user_query: str, conversation_history: list | None = None,
            datasource_info: dict | None = None) -> dict:
        """运行数据源接入流程.

        Args:
            user_query: 用户的自然语言请求
            conversation_history: 历史对话消息
            datasource_info: 预提取的连接信息（从 dispatcher 传来）

        Returns:
            {answer, status, datasource_id, tables_imported}
        """
        user_msg_parts = [f"用户请求：{user_query}"]
        if datasource_info:
            info_lines = [f"  {k}: {v}" for k, v in datasource_info.items() if v]
            if info_lines:
                user_msg_parts.append("")
                user_msg_parts.append("从用户消息中提取到的连接信息：")
                user_msg_parts.extend(info_lines)

        user_msg = "\n".join(user_msg_parts)

        messages: list[Message] = [
            Message(role=MessageRole.SYSTEM, content=CONNECT_DS_SYSTEM_PROMPT),
            Message(role=MessageRole.USER, content=user_msg),
        ]

        self._send_event("ds_connect_started", {})

        llm = create_llm_client()
        tools = self._build_tools()

        # state proxy：给工具函数用（沙盒工具需要 state 来访问配置）
        state_proxy = _StateProxy(project_id=self.project_id)

        datasource_id: str | None = None
        tables_imported = 0
        final_answer = ""
        status = "done"

        for iteration in range(self.max_iterations):
            iter_num = iteration + 1

            # --- 记录 LLM 调用耗时 ---
            if self._step_logger:
                with self._step_logger.llm_step(
                    f"llm_call_{iter_num}", iteration=iter_num
                ) as step_ctx:
                    response = llm.chat(messages, tools=tools, temperature=0.0)
                    # 尝试从响应中提取 token 用量
                    usage = getattr(response, "usage", None)
                    if usage:
                        input_tokens = getattr(usage, "input_tokens", None) or usage.get("input_tokens")
                        output_tokens = getattr(usage, "output_tokens", None) or usage.get("output_tokens")
                        step_ctx.set_tokens(input_tokens, output_tokens)
            else:
                response = llm.chat(messages, tools=tools, temperature=0.0)

            if not response.tool_calls:
                # LLM 返回了纯文本回答
                final_answer = response.content.strip()
                messages.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                ))
                break

            # 添加助手消息（带 tool calls）
            messages.append(Message(
                role=MessageRole.ASSISTANT,
                content=response.content or "",
                tool_calls=list(response.tool_calls),
            ))

            # 执行每个工具调用
            for tool_call in response.tool_calls:
                tool_name = tool_call.name
                tool_args = tool_call.arguments or {}

                self._send_tool_start_event(tool_name, tool_args)

                # --- 记录工具调用耗时 ---
                if self._step_logger:
                    with self._step_logger.tool_step(
                        step_name=tool_name,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        iteration=iter_num,
                    ) as step_ctx:
                        try:
                            tool_result_str = self._execute_tool(tool_name, tool_args, state_proxy)
                        except Exception as e:
                            tool_result_str = f"工具执行异常: {e}"
                            step_ctx.fail(str(e))

                        # 判断成功/失败
                        is_success = not (
                            "失败" in tool_result_str
                            or "错误" in tool_result_str
                            or "异常" in tool_result_str
                            or "not found" in tool_result_str.lower()
                        )
                        if tool_name == "install_driver":
                            is_success = "安装成功" in tool_result_str
                        if not is_success and "⚠️" not in tool_result_str:
                            step_ctx.fail(tool_result_str[:200])
                else:
                    try:
                        tool_result_str = self._execute_tool(tool_name, tool_args, state_proxy)
                    except Exception as e:
                        tool_result_str = f"工具执行异常: {e}"

                    # 判断成功/失败
                    is_success = not (
                        "失败" in tool_result_str
                        or "错误" in tool_result_str
                        or "异常" in tool_result_str
                        or "not found" in tool_result_str.lower()
                    )

                    # install_driver 的成功判断特殊处理：包含"安装成功"才算成功
                    if tool_name == "install_driver":
                        is_success = "安装成功" in tool_result_str

                self._send_tool_end_event(tool_name, tool_result_str, is_success)

                # 追踪 datasource_id
                if tool_name == "create_datasource" and is_success:
                    extracted_id = self._extract_datasource_id(tool_result_str)
                    if extracted_id:
                        datasource_id = extracted_id

                # 追踪导入表数
                if tool_name == "import_schema" and is_success:
                    tables_imported = self._extract_table_count(tool_result_str)

                # 添加工具结果消息
                messages.append(Message(
                    role=MessageRole.TOOL,
                    tool_result=ToolCallResult(
                        tool_call_id=tool_call.id,
                        name=tool_name,
                        content=tool_result_str,
                    ),
                ))

        else:
            # 达到最大迭代次数
            status = "failed"
            final_answer = "抱歉，数据源连接过程超过了最大迭代次数，请稍后再试。"

        return {
            "answer": final_answer,
            "status": status,
            "datasource_id": datasource_id,
            "tables_imported": tables_imported,
        }


# ---------------------------------------------------------------------------
# State proxy — 为工具函数提供类 state 的接口
# ---------------------------------------------------------------------------

class _StateProxy:
    """轻量代理对象，模拟 AgentState 的访问接口供工具函数使用."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __contains__(self, key):
        return hasattr(self, key)
