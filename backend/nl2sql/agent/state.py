"""Agent 状态定义。

使用 Pydantic BaseModel 实现，因为：
1. LangGraph 原生支持 Pydantic state
2. 同时支持属性访问 (state.key) 和字典访问 (state["key"])
3. 自带 dict()/model_dump() 序列化方法
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from nl2sql.schema import DatasourceSchema
from nl2sql.llm import Message
from nl2sql.executor import ExecutionResult


class IntentResult(BaseModel):
    """意图分析结果。"""

    tables: list[dict] = Field(default_factory=list)
    filters: list[dict] = Field(default_factory=list)
    aggregation: Optional[str] = None
    dimensions: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    raw_analysis: str = ""


class ProbeFinding(BaseModel):
    """意图探查发现。"""

    action: str
    table: str
    datasource_id: str
    finding: str
    sql: str = ""


class ReactThought(BaseModel):
    """ReAct 思考记录。"""

    thought: str
    action: str = ""
    observation: str = ""


class ChartSpec(BaseModel):
    """单个图表配置."""

    type: str  # line / bar / pie / area / metric / table
    title: str
    description: str = ""
    x_field: Optional[str] = None
    y_field: Optional[str] = None
    y_fields: list[str] = Field(default_factory=list)
    category_field: Optional[str] = None
    value_field: Optional[str] = None
    sort: Optional[str] = None  # asc / desc
    limit: Optional[int] = None
    stacked: bool = False
    config: dict = Field(default_factory=dict)


class VizSpec(BaseModel):
    """可视化规范."""

    charts: list[ChartSpec] = Field(default_factory=list)


class AgentState(BaseModel):
    """LangGraph Agent 的状态。

    继承自 Pydantic BaseModel，因此:
    - 既可以属性访问: state.user_query
    - 也可以字典访问: state["user_query"] / state.get("user_query")
    - LangGraph 原生支持
    """

    project_id: str
    datasources: list[DatasourceSchema] = Field(default_factory=list)
    user_query: str = ""
    conversation_history: list[Message] = Field(default_factory=list)

    # 意图分析
    intent: Optional[IntentResult] = None
    probe_findings: list[ProbeFinding] = Field(default_factory=list)
    probe_iteration: int = 0
    max_probe_iterations: int = 3
    clarification_questions: list[str] = Field(default_factory=list)
    awaiting_clarification: bool = False

    # SQL 与执行
    sql: Optional[str] = None
    execution_result: Optional[ExecutionResult] = None
    selected_datasource_id: Optional[str] = None

    # ReAct 循环
    react_thoughts: list[ReactThought] = Field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 5
    satisfied: bool = False  # 反思是否满意
    needs_revision: bool = False  # 是否需要修正 SQL

    # 可视化
    viz_spec: Optional[dict] = None  # VizSpec dict: {charts: [...]}

    # 输出
    status: str = "thinking"  # thinking / clarifying / executing / done / failed
    final_answer: Optional[str] = None
    error: Optional[str] = None

    # 运行时注入（不参与序列化）
    event_callback: Any = None
    datasource_executors: dict = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __contains__(self, key):
        return hasattr(self, key)
