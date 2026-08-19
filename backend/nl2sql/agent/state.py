"""Agent state definitions using dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nl2sql.schema import DatasourceSchema
from nl2sql.llm import Message
from nl2sql.executor import ExecutionResult


@dataclass
class IntentResult:
    """Result of intent analysis on a user query."""
    tables: list[dict] = field(default_factory=list)
    filters: list[dict] = field(default_factory=list)
    aggregation: str | None = None
    dimensions: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    confidence: float = 0.0
    raw_analysis: str = ""


@dataclass
class ProbeFinding:
    """A single finding from a probe operation."""
    action: str
    table: str
    datasource_id: str
    finding: str
    sql: str = ""


@dataclass
class ReactThought:
    """A single ReAct thought/action/observation step."""
    thought: str
    action: str = ""
    observation: str = ""


@dataclass
class AgentState:
    """State for the NL2SQL agent (LangGraph-compatible dataclass)."""
    project_id: str
    datasources: list[DatasourceSchema] = field(default_factory=list)
    user_query: str = ""
    conversation_history: list[Message] = field(default_factory=list)
    intent: IntentResult | None = None
    probe_findings: list[ProbeFinding] = field(default_factory=list)
    probe_iteration: int = 0
    max_probe_iterations: int = 3
    clarification_questions: list[str] = field(default_factory=list)
    awaiting_clarification: bool = False
    sql: str | None = None
    execution_result: ExecutionResult | None = None
    selected_datasource_id: str | None = None
    react_thoughts: list[ReactThought] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 5
    status: str = "thinking"  # thinking/clarifying/executing/done/failed
    final_answer: str | None = None
    error: str | None = None
    event_callback: Any = None  # optional callback for SSE
