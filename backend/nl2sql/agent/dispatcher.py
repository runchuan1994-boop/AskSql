"""Dispatcher Agent: 统一分发入口，根据用户意图路由到不同子 Agent.

职责：
1. 接收用户消息，判断意图类型
2. 选择合适的子 Agent 执行
3. 转发子 Agent 的 SSE 事件
4. 返回统一格式的结果

支持的意图类型：
- query: 数据查询 → NL2SQLAgent
- schema_exploration: schema 探索 → SchemaExplorerAgent
- connect_datasource: 数据源接入 → DatasourceConnectorAgent
- chitchat: 闲聊/无法归类 → 直接回答
"""
from __future__ import annotations

import json
import re
from typing import Callable

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

DISPATCHER_SYSTEM_PROMPT = """你是一个任务分发助手，负责判断用户消息的类型并分发给合适的专业 Agent。

请分析用户的消息，判断属于以下哪种类型：

1. **query**（数据查询）：用户想查询数据库中的数据、做统计分析、生成报表等。
   示例："上个月销售额多少？"、"有多少活跃用户？"、"按地区统计订单量"

2. **schema_exploration**（schema 探索）：用户想了解数据库的结构、表、列、数据样例等。
   示例："有哪些表？"、"users 表结构是什么？"、"status 字段有哪些值？"、"orders 表有多少行？"

3. **connect_datasource**（数据源接入）：用户想连接/创建/配置一个新的数据源。
   示例："帮我连接数据库 postgresql://..."、"添加一个 MySQL 数据源"、"配置数据库连接"

4. **chitchat**（闲聊/其他）：无法归入以上三类的问题，比如打招呼、问你是谁、无关问题等。

输出格式：严格的 JSON 格式，包含：
- intent: 字符串，必须是 query / schema_exploration / connect_datasource / chitchat 之一
- confidence: 数字 0-1，置信度
- reasoning: 字符串，简要说明判断理由
- datasource_info: 对象，仅当 intent 为 connect_datasource 时有效，提取到的连接信息（type/host/port/database/username/password/name）
- schema_target: 对象，仅当 intent 为 schema_exploration 时有效，包含：
  - table_name: 字符串或 null，用户提到的表名
  - column_name: 字符串或 null，用户提到的列名
  - action: 字符串，用户想做的操作（list_tables / describe_table / probe_values / probe_sample / probe_count / other）
"""


# ---------------------------------------------------------------------------
# Dispatch result
# ---------------------------------------------------------------------------

class DispatchResult:
    """分发结果."""

    def __init__(self, intent: str, confidence: float = 0.0,
                 reasoning: str = "", datasource_info: dict | None = None,
                 schema_target: dict | None = None):
        self.intent = intent
        self.confidence = confidence
        self.reasoning = reasoning
        self.datasource_info = datasource_info or {}
        self.schema_target = schema_target or {}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_json_response(text: str) -> dict | None:
    """从 LLM 响应中解析 JSON，处理 markdown 代码块包裹."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class DispatcherAgent:
    """统一分发 Agent.

    根据用户意图路由到不同的子 Agent。

    用法:
    ```python
    dispatcher = DispatcherAgent(
        project_id="my_project",
        datasources=[ds_schema],
        executors={"ds_id": executor},
        event_callback=my_callback,
    )
    result = dispatcher.run("上个月销售额多少？")
    ```
    """

    def __init__(
        self,
        project_id: str,
        datasources: list | None = None,
        executors: dict | None = None,
        event_callback: Callable[[str, dict], None] | None = None,
        max_iterations: int = 5,
        max_probe_iterations: int = 3,
        session_id: str | None = None,
        step_logger=None,
    ):
        self.project_id = project_id
        self.datasources = datasources or []
        self.executors = executors or {}
        self.event_callback = event_callback
        self.max_iterations = max_iterations
        self.max_probe_iterations = max_probe_iterations
        self.session_id = session_id
        self._step_logger = step_logger  # 可选：步骤耗时记录器（鸭子类型）

    def _send_event(self, event_type: str, data: dict | None = None) -> None:
        if self.event_callback is not None:
            try:
                self.event_callback(event_type, data or {})
            except Exception:
                pass

    def _classify_intent(self, user_query: str, conversation_history: list | None = None) -> DispatchResult:
        """调用 LLM 判断用户意图类型."""
        messages = [
            Message(role=MessageRole.SYSTEM, content=DISPATCHER_SYSTEM_PROMPT),
        ]

        if conversation_history:
            # 加入最近几轮历史作为上下文
            for msg in conversation_history[-6:]:
                if hasattr(msg, "role") and msg.role != MessageRole.SYSTEM:
                    messages.append(msg)

        user_msg = f"用户消息：{user_query}\n\n请判断意图类型，只输出 JSON。"
        messages.append(Message(role=MessageRole.USER, content=user_msg))

        llm = create_llm_client()

        # 记录 LLM 调用耗时
        if self._step_logger:
            with self._step_logger.llm_step("dispatch_classify", iteration=1) as step_ctx:
                response = llm.chat(messages, temperature=0.0)
                usage = getattr(response, "usage", None)
                if usage:
                    it = getattr(usage, "input_tokens", None) or usage.get("input_tokens")
                    ot = getattr(usage, "output_tokens", None) or usage.get("output_tokens")
                    step_ctx.set_tokens(it, ot)
        else:
            response = llm.chat(messages, temperature=0.0)

        parsed = _parse_json_response(response.content)

        if parsed is None:
            # 解析失败，默认按 query 处理
            return DispatchResult(
                intent="query",
                confidence=0.5,
                reasoning="无法解析分类结果，默认按 query 处理",
            )

        intent = parsed.get("intent", "query")
        # 容错：确保 intent 是有效值
        valid_intents = {"query", "schema_exploration", "connect_datasource", "chitchat"}
        if intent not in valid_intents:
            intent = "query"

        return DispatchResult(
            intent=intent,
            confidence=float(parsed.get("confidence", 0.5)),
            reasoning=parsed.get("reasoning", ""),
            datasource_info=parsed.get("datasource_info", {}) or {},
            schema_target=parsed.get("schema_target", {}) or {},
        )

    def _run_chitchat(self, user_query: str) -> dict:
        """处理闲聊/无法归类的问题."""
        messages = [
            Message(
                role=MessageRole.SYSTEM,
                content="你是一个数据查询助手。用户问了一个与数据查询无关的问题，请友好地回复，并引导用户提出数据相关的问题。用用户的语言回答。",
            ),
            Message(role=MessageRole.USER, content=user_query),
        ]
        llm = create_llm_client()
        response = llm.chat(messages, temperature=0.7)
        return {
            "answer": response.content.strip(),
            "status": "done",
            "intent": "chitchat",
        }

    def _run_query(
        self,
        user_query: str,
        conversation_history: list | None = None,
        selected_datasource_id: str | None = None,
        extra_state: dict | None = None,
    ) -> dict:
        """运行 NL2SQLAgent 处理数据查询."""
        from nl2sql.agent.graph import NL2SQLAgent

        agent = NL2SQLAgent(
            project_id=self.project_id,
            datasources=self.datasources,
            executors=self.executors,
            event_callback=self.event_callback,
            max_iterations=self.max_iterations,
            max_probe_iterations=self.max_probe_iterations,
        )
        return agent.run(
            user_query, conversation_history, selected_datasource_id, extra_state
        )

    def _run_schema_exploration(self, user_query: str, conversation_history: list | None = None) -> dict:
        """运行 SchemaExplorerAgent 处理 schema 探索."""
        from nl2sql.agent.schema_explorer import SchemaExplorerAgent

        agent = SchemaExplorerAgent(
            datasources=self.datasources,
            executors=self.executors,
            event_callback=self.event_callback,
            max_iterations=self.max_iterations,
        )
        result = agent.run(user_query, conversation_history)
        # 补充 dispatcher 层的统一字段
        result["intent"] = "schema_exploration"
        return result

    def _run_connect_datasource(self, user_query: str, conversation_history: list | None = None,
                                datasource_info: dict | None = None) -> dict:
        """运行 DatasourceConnectorAgent 处理数据源接入."""
        from nl2sql.agent.datasource_connector import DatasourceConnectorAgent

        agent = DatasourceConnectorAgent(
            project_id=self.project_id,
            event_callback=self.event_callback,
            max_iterations=8,  # 给修复循环留空间
            session_id=self.session_id,
            step_logger=self._step_logger,
        )
        result = agent.run(user_query, conversation_history, datasource_info)
        result["intent"] = "connect_datasource"
        return result

    def run(
        self,
        user_query: str,
        conversation_history: list | None = None,
        selected_datasource_id: str | None = None,
        extra_state: dict | None = None,
    ) -> dict:
        """运行完整的分发 + 执行流程.

        Args:
            user_query: 用户的自然语言消息
            conversation_history: 历史对话消息列表
            selected_datasource_id: 可选，用户指定的数据源 ID（优先使用）

        Returns:
            统一格式的结果字典，包含:
            - answer: 最终回答
            - status: 状态 (done/failed)
            - intent: 识别的意图类型
            - 各子 Agent 特有的字段
        """
        # Step 1: 意图分类
        import time
        dispatch_start = time.perf_counter()
        self._send_event("dispatch_started", {"query": user_query})
        self._send_event("step_detail", {
            "step": "dispatch",
            "name": "分析任务",
            "status": "active",
        })

        dispatch = self._classify_intent(user_query, conversation_history)

        self._send_event("dispatch_result", {
            "intent": dispatch.intent,
            "confidence": dispatch.confidence,
            "reasoning": dispatch.reasoning,
        })
        dispatch_duration = int((time.perf_counter() - dispatch_start) * 1000)
        self._send_event("step_detail", {
            "step": "dispatch",
            "name": "分析任务",
            "status": "completed",
            "duration_ms": dispatch_duration,
            "detail": {
                "intent": dispatch.intent,
                "confidence": dispatch.confidence,
                "reasoning": dispatch.reasoning,
            },
        })

        # Step 2: 路由到对应子 Agent
        if dispatch.intent == "query":
            result = self._run_query(
                user_query, conversation_history, selected_datasource_id, extra_state
            )
            result["intent"] = result.get("intent", "query")

        elif dispatch.intent == "schema_exploration":
            if not self.datasources:
                return {
                    "answer": "当前项目还没有配置数据源，无法探索 schema。请先连接一个数据源。",
                    "status": "failed",
                    "intent": "schema_exploration",
                    "error": "no datasource",
                }
            result = self._run_schema_exploration(user_query, conversation_history)

        elif dispatch.intent == "connect_datasource":
            result = self._run_connect_datasource(
                user_query, conversation_history, dispatch.datasource_info
            )

        else:  # chitchat
            result = self._run_chitchat(user_query)

        # 发送 final_result 事件
        # 注意：query 类型由 graph 内的 summarize_node 负责发送 final_result 和 done
        # 非 query 类型（schema_exploration / connect_datasource / chitchat）
        # 没有 summarize_node，由 dispatcher 统一发送
        if dispatch.intent != "query":
            answer = result.get("answer", "")
            sql = result.get("sql", "") or ""
            exec_result = result.get("execution_result")
            viz_spec = result.get("viz_spec")

            result_payload = None
            if exec_result and hasattr(exec_result, "success") and exec_result.success:
                result_payload = {
                    "columns": exec_result.columns,
                    "rows": [list(r) for r in exec_result.rows[:100]],
                    "row_count": exec_result.row_count,
                    "success": exec_result.success,
                    "duration_ms": getattr(exec_result, "duration_ms", None),
                    "truncated": len(exec_result.rows) < exec_result.row_count,
                }

            self._send_event("final_result", {
                "answer": answer,
                "success": result.get("status") == "done",
                "sql": sql,
                "result": result_payload,
                "viz": viz_spec,
                "intent": dispatch.intent,
            })
            self._send_event("done", {"status": result.get("status", "unknown")})

        return result
