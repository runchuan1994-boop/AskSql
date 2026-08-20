"""LangGraph Agent 图构建与运行入口。"""
from __future__ import annotations

from typing import Callable

from langgraph.graph import StateGraph, END

from .nodes import (
    intent_analyze_node,
    intent_probe_node,
    clarify_node,
    need_clarify_conditional,
    ask_clarify_node,
    generate_sql_node,
    execute_sql_node,
    visualize_node,
    reflect_node,
    need_retry_conditional,
    summarize_node,
)


def build_graph() -> StateGraph:
    """构建 NL2SQL Agent 的 LangGraph 状态图。

    图结构:
        intent_analyze → intent_probe → clarify
                                            ↓
                              ask_clarify  /  generate_sql
                                                      ↓
                                                execute_sql
                                                      ↓
                                                 visualize
                                                      ↓
                                                  reflect
                                              ↙          ↘
                                   generate_sql (重试)   summarize → END
    """
    from .state import AgentState

    # 用 AgentState (Pydantic BaseModel) 作为 state schema
    # LangGraph 原生支持 Pydantic state
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("intent_analyze", intent_analyze_node)
    graph.add_node("intent_probe", intent_probe_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("ask_clarify", ask_clarify_node)
    graph.add_node("generate_sql", generate_sql_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("visualize", visualize_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("summarize", summarize_node)

    # 设置入口
    graph.set_entry_point("intent_analyze")

    # 边: 意图分析 → 意图探查
    graph.add_edge("intent_analyze", "intent_probe")

    # 边: 意图探查 → 澄清判断
    graph.add_edge("intent_probe", "clarify")

    # 条件边: 澄清判断 → ask_clarify / generate_sql
    graph.add_conditional_edges(
        "clarify",
        need_clarify_conditional,
        {
            "ask_clarify": "ask_clarify",
            "generate_sql": "generate_sql",
        },
    )

    # 边: generate_sql → execute_sql
    graph.add_edge("generate_sql", "execute_sql")

    # 边: execute_sql → visualize → reflect
    graph.add_edge("execute_sql", "visualize")
    graph.add_edge("visualize", "reflect")

    # 条件边: reflect → generate_sql / summarize
    graph.add_conditional_edges(
        "reflect",
        need_retry_conditional,
        {
            "generate_sql": "generate_sql",
            "summarize": "summarize",
        },
    )

    # 边: summarize → END
    graph.add_edge("summarize", END)

    return graph


class NL2SQLAgent:
    """NL2SQL Agent 运行入口。

    用法:
    ```python
    agent = NL2SQLAgent(
        project_id="my_project",
        datasources=[datasource_schema],
        executors={"ds_id": executor},
    )
    result = agent.run("上个月新增了多少用户？")
    print(result["answer"])
    print(result["sql"])
    ```
    """

    def __init__(
        self,
        project_id: str,
        datasources: list,
        executors: dict,
        event_callback: Callable[[str, dict], None] | None = None,
        max_iterations: int = 5,
        max_probe_iterations: int = 3,
    ):
        self.project_id = project_id
        self.datasources = datasources
        self.executors = executors
        self.event_callback = event_callback
        self.max_iterations = max_iterations
        self.max_probe_iterations = max_probe_iterations

        self._graph = build_graph()
        self._app = self._graph.compile()

    def run(self, user_query: str, conversation_history: list | None = None) -> dict:
        """运行一次完整的 Agent 流程（同步版本）。

        Args:
            user_query: 用户的自然语言问题
            conversation_history: 历史对话消息列表

        Returns:
            结果字典，包含:
            - answer: 最终回答（自然语言）
            - sql: 生成的 SQL
            - execution_result: 执行结果
            - viz_spec: 可视化配置
            - intent: 意图分析结果
            - probe_findings: 探查发现
            - react_thoughts: 反思记录
            - iteration: 迭代次数
            - status: 最终状态
            - error: 错误信息（如有）
        """
        from .state import AgentState

        # 用 Pydantic 实例获取默认值，然后手动构建初始 dict
        # 注意：datasource_executors 是运行时对象，不经过 Pydantic 序列化
        state_obj = AgentState(
            project_id=self.project_id,
            datasources=self.datasources,
            user_query=user_query,
            conversation_history=conversation_history or [],
            max_iterations=self.max_iterations,
            max_probe_iterations=self.max_probe_iterations,
            event_callback=self.event_callback,
        )
        initial_state = state_obj.model_dump(exclude={"datasource_executors", "event_callback"}, mode="python")
        initial_state["datasource_executors"] = self.executors
        initial_state["event_callback"] = self.event_callback

        # LangGraph invoke 返回 dict
        final_state = self._app.invoke(initial_state)

        return {
            "answer": final_state.get("final_answer"),
            "sql": final_state.get("sql"),
            "execution_result": final_state.get("execution_result"),
            "viz_spec": final_state.get("viz_spec"),
            "intent": final_state.get("intent"),
            "probe_findings": final_state.get("probe_findings", []),
            "react_thoughts": final_state.get("react_thoughts", []),
            "iteration": final_state.get("iteration", 0),
            "status": final_state.get("status", "unknown"),
            "error": final_state.get("error"),
        }

    def stream(self, user_query: str, conversation_history: list | None = None):
        """流式运行 Agent，yield 每个节点的状态更新。"""
        from .state import AgentState

        state_obj = AgentState(
            project_id=self.project_id,
            datasources=self.datasources,
            user_query=user_query,
            conversation_history=conversation_history or [],
            max_iterations=self.max_iterations,
            max_probe_iterations=self.max_probe_iterations,
            event_callback=self.event_callback,
        )
        initial_state = state_obj.model_dump(exclude={"datasource_executors", "event_callback"}, mode="python")
        initial_state["datasource_executors"] = self.executors
        initial_state["event_callback"] = self.event_callback

        for event in self._app.stream(initial_state):
            yield event
