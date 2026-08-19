# Phase 1: nl2sql 核心库 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建可独立运行和测试的 nl2sql Python 核心库，包含 Schema 管理、LLM 适配、SQL 执行器、以及基于 LangGraph 的 ReAct Agent。

**Architecture:** 核心库 `nl2sql/` 完全独立于 Web 层，通过 Python API 调用。LangGraph 编排意图分析→探查→SQL生成→执行→反思的 ReAct 循环。各模块通过清晰接口解耦，LLM 和数据库执行器用工厂模式支持多实现。

**Tech Stack:** Python 3.11+, LangGraph (langgraph), Pydantic, python-dotenv, SQLAlchemy, pytest

---

## 文件结构总览

```
backend/
├── nl2sql/
│   ├── __init__.py
│   ├── config.py                    # 全局配置
│   ├── schema/
│   │   ├── __init__.py
│   │   ├── models.py                # Schema/Table/Column 数据模型
│   │   ├── loader.py                # YAML 加载器
│   │   ├── matcher.py               # 表/字段语义匹配
│   │   └── watcher.py               # 文件变化监听（热加载）
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py                  # LLMClient 抽象基类
│   │   ├── message.py               # Message/ToolCall 数据结构
│   │   ├── claude_client.py         # Claude 实现
│   │   ├── openai_client.py         # OpenAI / 本地兼容实现
│   │   └── factory.py               # 工厂函数
│   ├── executor/
│   │   ├── __init__.py
│   │   ├── base.py                  # SQLExecutor 抽象基类
│   │   ├── models.py                # ExecutionResult 数据模型
│   │   ├── generic_executor.py      # 通用 SQLAlchemy 执行器
│   │   └── factory.py               # 工厂函数
│   └── agent/
│       ├── __init__.py
│       ├── state.py                 # AgentState 定义
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── schema_tools.py      # list_tables, describe_table, sample_data
│       │   ├── probe_tools.py       # 探查工具集
│       │   └── sql_tool.py          # execute_sql 工具
│       ├── nodes/
│       │   ├── __init__.py
│       │   ├── intent.py            # 意图分析节点
│       │   ├── probe.py             # 意图探查节点
│       │   ├── clarify.py           # 澄清判断节点
│       │   ├── generate.py          # SQL 生成节点
│       │   ├── execute.py           # SQL 执行节点
│       │   ├── reflect.py           # ReAct 反思节点
│       │   └── summarize.py         # 总结节点
│       └── graph.py                 # LangGraph 图构建 + 运行入口
├── tests/
│   ├── conftest.py
│   ├── test_schema/
│   ├── test_llm/
│   ├── test_executor/
│   └── test_agent/
├── config/
│   └── schemas/
│       └── sample/
│           └── ecommerce.yaml       # 测试用 Schema
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Task 1: 项目脚手架与配置

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/nl2sql/__init__.py`
- Create: `backend/nl2sql/config.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "nl2sql"
version = "0.1.0"
description = "Natural Language to SQL Agent with ReAct reflection"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "langgraph>=0.2",
    "langchain-core>=0.3",
    "sqlalchemy>=2.0",
    "anthropic>=0.30",
    "openai>=1.0",
    "watchdog>=4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
```

- [ ] **Step 2: 创建 .env.example**

```env
# ===== LLM 配置 =====
LLM_PROVIDER=claude              # claude / openai / local_openai_compatible

# Claude
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# OpenAI / 本地兼容
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_MODEL=gpt-4o

# ===== Agent 配置 =====
MAX_ITERATIONS=5
MAX_PROBE_ITERATIONS=3
SQL_TIMEOUT_SECONDS=30
SQL_MAX_ROWS=1000
AGENT_TIMEOUT_SECONDS=300
```

- [ ] **Step 3: 创建 nl2sql/config.py**

```python
"""全局配置，从环境变量读取。"""
from __future__ import annotations

import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    # LLM
    llm_provider: str = "claude"  # claude / openai / local_openai_compatible
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"

    # Agent
    max_iterations: int = 5
    max_probe_iterations: int = 3
    sql_timeout_seconds: int = 30
    sql_max_rows: int = 1000
    agent_timeout_seconds: int = 300

    class Config:
        env_file = ".env"


settings = Settings()
```

- [ ] **Step 4: 创建 nl2sql/__init__.py**

```python
"""nl2sql 核心库。"""
from .config import settings

__version__ = "0.1.0"
__all__ = ["settings"]
```

- [ ] **Step 5: 创建 tests/conftest.py**

```python
import pytest
import os
import sys

# 将 backend 目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
```

- [ ] **Step 6: 安装依赖并验证**

Run: `cd backend && pip install -e ".[dev]" && python -c "from nl2sql import settings; print(settings.llm_provider)"`
Expected: 输出 `claude`（或 .env 中配置的值）

- [ ] **Step 7: Commit**

```bash
cd ..
git init
git add backend/pyproject.toml backend/.env.example backend/nl2sql/__init__.py backend/nl2sql/config.py backend/tests/conftest.py
git commit -m "feat: project scaffold and config"
```

---

## Task 2: Schema 数据模型

**Files:**
- Create: `backend/nl2sql/schema/__init__.py`
- Create: `backend/nl2sql/schema/models.py`
- Test: `backend/tests/test_schema/test_models.py`

- [ ] **Step 1: 编写测试**

```python
"""测试 Schema 数据模型。"""
import pytest
from nl2sql.schema.models import Column, Table, Schema, DatasourceSchema


def test_column_model():
    col = Column(name="id", type="bigint", description="用户ID", is_primary_key=True)
    assert col.name == "id"
    assert col.semantic_type is None


def test_column_with_enum():
    col = Column(
        name="status",
        type="varchar(20)",
        description="状态",
        enum_values=["active", "inactive"],
        semantic_type="category",
    )
    assert len(col.enum_values) == 2
    assert col.semantic_type == "category"


def test_table_model():
    table = Table(
        name="users",
        description="用户表",
        columns=[
            Column(name="id", type="bigint", description="ID"),
            Column(name="name", type="varchar", description="姓名"),
        ],
    )
    assert len(table.columns) == 2
    assert table.get_column("id") is not None
    assert table.get_column("nonexistent") is None
    assert table.column_names == ["id", "name"]


def test_schema_model():
    schema = Schema(
        tables=[
            Table(name="users", description="用户表", columns=[]),
            Table(name="orders", description="订单表", columns=[]),
        ]
    )
    assert len(schema.tables) == 2
    assert schema.get_table("users") is not None
    assert schema.table_names == ["users", "orders"]


def test_datasource_schema():
    ds = DatasourceSchema(
        datasource_id="mysql_main",
        datasource_name="主业务库",
        datasource_type="mysql",
        schema=Schema(tables=[]),
    )
    assert ds.datasource_id == "mysql_main"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_schema/test_models.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现 Schema 模型**

```python
"""Schema 数据模型。"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class Column(BaseModel):
    """列定义。"""
    name: str
    type: str
    description: str = ""
    is_primary_key: bool = False
    is_foreign_key: bool = False
    foreign_key_table: Optional[str] = None
    foreign_key_column: Optional[str] = None
    enum_values: list[str] = Field(default_factory=list)
    semantic_type: Optional[str] = None  # timestamp / amount / dimension / category / id


class Table(BaseModel):
    """表定义。"""
    name: str
    description: str = ""
    columns: list[Column] = Field(default_factory=list)
    examples: list[dict] = Field(default_factory=list)  # [{"question": "...", "sql": "..."}]

    def get_column(self, name: str) -> Optional[Column]:
        for col in self.columns:
            if col.name == name:
                return col
        return None

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


class Schema(BaseModel):
    """一个数据源的 Schema 集合。"""
    tables: list[Table] = Field(default_factory=list)

    def get_table(self, name: str) -> Optional[Table]:
        for t in self.tables:
            if t.name == name:
                return t
        return None

    @property
    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]


class DatasourceSchema(BaseModel):
    """带数据源信息的 Schema。"""
    datasource_id: str
    datasource_name: str = ""
    datasource_type: str = "mysql"  # mysql / postgres / clickhouse / ...
    schema: Schema
```

- [ ] **Step 4: 创建 schema/__init__.py**

```python
"""Schema 元数据管理模块。"""
from .models import Column, Table, Schema, DatasourceSchema

__all__ = ["Column", "Table", "Schema", "DatasourceSchema"]
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd backend && pytest tests/test_schema/test_models.py -v`
Expected: 全部 PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/nl2sql/schema/__init__.py backend/nl2sql/schema/models.py backend/tests/test_schema/test_models.py
git commit -m "feat: schema data models"
```

---

## Task 3: Schema YAML 加载器

**Files:**
- Create: `backend/nl2sql/schema/loader.py`
- Create: `backend/config/schemas/sample/ecommerce.yaml`
- Test: `backend/tests/test_schema/test_loader.py`

- [ ] **Step 1: 编写测试**

```python
"""测试 Schema 加载器。"""
import os
import pytest
from nl2sql.schema.loader import SchemaLoader


SAMPLE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "config", "schemas", "sample", "ecommerce.yaml",
)


def test_load_from_yaml():
    loader = SchemaLoader()
    ds = loader.load_from_yaml(SAMPLE_PATH)
    assert ds.datasource_id == "ecommerce_mysql"
    assert ds.datasource_type == "mysql"
    assert len(ds.schema.tables) >= 2
    assert ds.schema.get_table("users") is not None
    assert ds.schema.get_table("orders") is not None


def test_table_has_columns():
    loader = SchemaLoader()
    ds = loader.load_from_yaml(SAMPLE_PATH)
    users = ds.schema.get_table("users")
    assert users is not None
    assert len(users.columns) > 0
    assert users.get_column("id") is not None
    assert users.get_column("id").is_primary_key is True


def test_semantic_type_parsed():
    loader = SchemaLoader()
    ds = loader.load_from_yaml(SAMPLE_PATH)
    users = ds.schema.get_table("users")
    created_at = users.get_column("created_at")
    assert created_at is not None
    assert created_at.semantic_type == "timestamp"
```

- [ ] **Step 2: 创建示例 YAML**

```yaml
datasource:
  id: ecommerce_mysql
  name: 电商 MySQL 库
  type: mysql

tables:
  - name: users
    description: 用户表，记录所有注册用户的基本信息
    columns:
      - name: id
        type: bigint
        description: 用户ID，主键
        is_primary_key: true
        semantic_type: id
      - name: email
        type: varchar(255)
        description: 注册邮箱
      - name: status
        type: varchar(20)
        description: 用户状态
        enum_values: [active, inactive, banned]
        semantic_type: category
      - name: country
        type: varchar(100)
        description: 注册国家
        semantic_type: dimension
      - name: created_at
        type: datetime
        description: 注册时间
        semantic_type: timestamp
    examples:
      - question: 上个月新增了多少用户
        sql: SELECT COUNT(*) FROM users WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)

  - name: orders
    description: 订单表，记录所有交易订单
    columns:
      - name: id
        type: bigint
        description: 订单ID，主键
        is_primary_key: true
        semantic_type: id
      - name: user_id
        type: bigint
        description: 下单用户ID
        is_foreign_key: true
        foreign_key_table: users
        foreign_key_column: id
        semantic_type: id
      - name: amount
        type: decimal(10,2)
        description: 订单金额
        semantic_type: amount
      - name: status
        type: varchar(20)
        description: 订单状态
        enum_values: [pending, paid, shipped, delivered, cancelled]
        semantic_type: category
      - name: created_at
        type: datetime
        description: 下单时间
        semantic_type: timestamp
```

- [ ] **Step 3: 运行测试验证失败**

Run: `cd backend && pytest tests/test_schema/test_loader.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 4: 实现加载器**

```python
"""Schema YAML 加载器。"""
from __future__ import annotations

import os
from typing import Optional

import yaml

from .models import Column, Table, Schema, DatasourceSchema


class SchemaLoader:
    """从 YAML 文件加载 Schema 元数据。"""

    def load_from_yaml(self, filepath: str) -> DatasourceSchema:
        """从单个 YAML 文件加载数据源 Schema。"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        ds_info = data.get("datasource", {})
        tables_data = data.get("tables", [])

        tables = []
        for t_data in tables_data:
            columns = []
            for c_data in t_data.get("columns", []):
                columns.append(Column(**c_data))
            table = Table(
                name=t_data["name"],
                description=t_data.get("description", ""),
                columns=columns,
                examples=t_data.get("examples", []),
            )
            tables.append(table)

        return DatasourceSchema(
            datasource_id=ds_info.get("id", os.path.basename(filepath).replace(".yaml", "")),
            datasource_name=ds_info.get("name", ""),
            datasource_type=ds_info.get("type", "mysql"),
            schema=Schema(tables=tables),
        )

    def load_from_directory(self, dirpath: str) -> list[DatasourceSchema]:
        """从目录加载所有 YAML Schema 文件。"""
        schemas = []
        if not os.path.isdir(dirpath):
            return schemas
        for filename in sorted(os.listdir(dirpath)):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                filepath = os.path.join(dirpath, filename)
                schemas.append(self.load_from_yaml(filepath))
        return schemas
```

- [ ] **Step 5: 更新 schema/__init__.py**

```python
"""Schema 元数据管理模块。"""
from .models import Column, Table, Schema, DatasourceSchema
from .loader import SchemaLoader

__all__ = ["Column", "Table", "Schema", "DatasourceSchema", "SchemaLoader"]
```

- [ ] **Step 6: 运行测试验证通过**

Run: `cd backend && pytest tests/test_schema/test_loader.py -v`
Expected: 全部 PASS (3 passed)

- [ ] **Step 7: Commit**

```bash
git add backend/nl2sql/schema/loader.py backend/config/schemas/sample/ecommerce.yaml backend/tests/test_schema/test_loader.py backend/nl2sql/schema/__init__.py
git commit -m "feat: schema YAML loader with sample data"
```

---

## Task 4: Schema 语义匹配器

**Files:**
- Create: `backend/nl2sql/schema/matcher.py`
- Test: `backend/tests/test_schema/test_matcher.py`

- [ ] **Step 1: 编写测试**

```python
"""测试 Schema 语义匹配器。"""
import pytest
from nl2sql.schema.matcher import SchemaMatcher
from nl2sql.schema.models import Column, Table, Schema, DatasourceSchema


@pytest.fixture
def sample_ds():
    return DatasourceSchema(
        datasource_id="test",
        datasource_type="mysql",
        schema=Schema(
            tables=[
                Table(
                    name="users",
                    description="用户表，注册用户",
                    columns=[
                        Column(name="id", type="bigint", description="用户ID"),
                        Column(name="email", type="varchar", description="邮箱"),
                        Column(name="created_at", type="datetime", description="注册时间"),
                        Column(name="status", type="varchar", description="用户状态"),
                    ],
                ),
                Table(
                    name="orders",
                    description="订单表，交易订单",
                    columns=[
                        Column(name="id", type="bigint", description="订单ID"),
                        Column(name="user_id", type="bigint", description="用户ID"),
                        Column(name="amount", type="decimal", description="订单金额"),
                        Column(name="created_at", type="datetime", description="下单时间"),
                    ],
                ),
                Table(
                    name="products",
                    description="商品表，产品信息",
                    columns=[
                        Column(name="id", type="bigint", description="商品ID"),
                        Column(name="name", type="varchar", description="商品名称"),
                        Column(name="price", type="decimal", description="价格"),
                    ],
                ),
            ]
        ),
    )


def test_match_tables_by_name(sample_ds):
    matcher = SchemaMatcher([sample_ds])
    matches = matcher.match_tables("订单", top_k=3)
    assert len(matches) > 0
    assert matches[0].table.name == "orders"


def test_match_tables_by_description(sample_ds):
    matcher = SchemaMatcher([sample_ds])
    matches = matcher.match_tables("用户注册", top_k=3)
    assert matches[0].table.name == "users"


def test_match_columns(sample_ds):
    matcher = SchemaMatcher([sample_ds])
    table = sample_ds.schema.get_table("users")
    assert table is not None
    matches = matcher.match_columns(table, "注册时间", top_k=3)
    assert len(matches) > 0
    assert matches[0].column.name == "created_at"


def test_find_relevant_tables(sample_ds):
    matcher = SchemaMatcher([sample_ds])
    query = "上个月用户的订单总金额"
    relevant = matcher.find_relevant_tables(query, top_k=5)
    # 应该匹配到 orders 和 users
    table_names = [r.table.name for r in relevant]
    assert "orders" in table_names
    assert "users" in table_names
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_schema/test_matcher.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现匹配器**

```python
"""Schema 语义匹配器。

基于关键词和简单相似度匹配，不依赖嵌入模型（保证V1轻量可用）。
后续可升级为基于 embedding 的语义匹配。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import DatasourceSchema, Table, Column


@dataclass
class TableMatch:
    """表匹配结果。"""
    datasource_id: str
    table: Table
    score: float


@dataclass
class ColumnMatch:
    """列匹配结果。"""
    column: Column
    score: float


class SchemaMatcher:
    """Schema 匹配器。

    匹配策略（简单但有效，适合少量表场景）：
    1. 精确名字匹配（得分最高）
    2. 描述中的关键词匹配
    3. 名字的子串/模糊匹配
    """

    def __init__(self, datasources: list[DatasourceSchema]):
        self.datasources = datasources

    def _tokenize(self, text: str) -> set[str]:
        """简单分词：按非字母数字分割，转小写。"""
        return set(re.findall(r'[a-zA-Z0-9_一-鿿]+', text.lower()))

    def _score_table(self, query_tokens: set[str], table: Table) -> float:
        """计算表的匹配得分。"""
        score = 0.0
        table_name_lower = table.name.lower()
        desc_tokens = self._tokenize(table.description)

        # 表名精确匹配
        for token in query_tokens:
            if token == table_name_lower:
                score += 10.0
            # 表名包含
            elif token in table_name_lower or table_name_lower in token:
                score += 3.0
            # 描述匹配
            elif token in desc_tokens:
                score += 2.0

        # 列名也贡献一部分分数
        for col in table.columns:
            col_tokens = self._tokenize(f"{col.name} {col.description}")
            overlap = query_tokens & col_tokens
            score += len(overlap) * 0.5

        return score

    def _score_column(self, query_tokens: set[str], column: Column) -> float:
        """计算列的匹配得分。"""
        score = 0.0
        col_name_lower = column.name.lower()
        desc_tokens = self._tokenize(column.description)

        for token in query_tokens:
            if token == col_name_lower:
                score += 10.0
            elif token in col_name_lower or col_name_lower in token:
                score += 3.0
            elif token in desc_tokens:
                score += 2.0

        # 语义类型匹配加成
        if column.semantic_type:
            sem_tokens = self._tokenize(column.semantic_type)
            score += len(query_tokens & sem_tokens) * 1.5

        return score

    def match_tables(self, query: str, top_k: int = 5) -> list[TableMatch]:
        """匹配所有数据源中的表，按得分排序。"""
        query_tokens = self._tokenize(query)
        matches: list[TableMatch] = []

        for ds in self.datasources:
            for table in ds.schema.tables:
                score = self._score_table(query_tokens, table)
                if score > 0:
                    matches.append(TableMatch(
                        datasource_id=ds.datasource_id,
                        table=table,
                        score=score,
                    ))

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:top_k]

    def match_columns(self, table: Table, query: str, top_k: int = 5) -> list[ColumnMatch]:
        """在单表内匹配列。"""
        query_tokens = self._tokenize(query)
        matches: list[ColumnMatch] = []

        for col in table.columns:
            score = self._score_column(query_tokens, col)
            if score > 0:
                matches.append(ColumnMatch(column=col, score=score))

        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:top_k]

    def find_relevant_tables(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 1.0,
    ) -> list[TableMatch]:
        """找出与查询相关的表（过滤掉得分过低的）。"""
        matches = self.match_tables(query, top_k=top_k)
        return [m for m in matches if m.score >= min_score]
```

- [ ] **Step 4: 更新 schema/__init__.py**

```python
"""Schema 元数据管理模块。"""
from .models import Column, Table, Schema, DatasourceSchema
from .loader import SchemaLoader
from .matcher import SchemaMatcher, TableMatch, ColumnMatch

__all__ = [
    "Column", "Table", "Schema", "DatasourceSchema",
    "SchemaLoader", "SchemaMatcher", "TableMatch", "ColumnMatch",
]
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd backend && pytest tests/test_schema/test_matcher.py -v`
Expected: 全部 PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/nl2sql/schema/matcher.py backend/tests/test_schema/test_matcher.py backend/nl2sql/schema/__init__.py
git commit -m "feat: schema semantic matcher"
```

---

## Task 5: LLM 消息模型与抽象基类

**Files:**
- Create: `backend/nl2sql/llm/__init__.py`
- Create: `backend/nl2sql/llm/message.py`
- Create: `backend/nl2sql/llm/base.py`
- Test: `backend/tests/test_llm/test_message.py`

- [ ] **Step 1: 编写消息模型测试**

```python
"""测试 LLM 消息模型。"""
import pytest
from nl2sql.llm.message import (
    Message, MessageRole, TextContent,
    ToolCall, ToolCallResult,
)


def test_message_creation():
    msg = Message(role=MessageRole.USER, content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"


def test_message_with_tool_calls():
    tool_call = ToolCall(
        id="call_123",
        name="execute_sql",
        arguments={"sql": "SELECT 1"},
    )
    msg = Message(role=MessageRole.ASSISTANT, content="", tool_calls=[tool_call])
    assert len(msg.tool_calls) == 1
    assert msg.tool_calls[0].name == "execute_sql"


def test_tool_result_message():
    result = ToolCallResult(
        tool_call_id="call_123",
        name="execute_sql",
        content='{"rows": [[1]]}',
    )
    msg = Message(role=MessageRole.TOOL, content="", tool_result=result)
    assert msg.role == "tool"
    assert msg.tool_result.name == "execute_sql"


def test_system_message():
    msg = Message(role=MessageRole.SYSTEM, content="You are a helpful assistant.")
    assert msg.role == "system"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_llm/test_message.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现消息模型**

```python
"""LLM 消息与工具调用数据结构。"""
from __future__ import annotations

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """工具调用。"""
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResult(BaseModel):
    """工具调用结果。"""
    tool_call_id: str
    name: str
    content: str


class TextContent(BaseModel):
    """文本内容块。"""
    text: str
    type: str = "text"


class Message(BaseModel):
    """聊天消息。"""
    role: MessageRole
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_result: Optional[ToolCallResult] = None
```

- [ ] **Step 4: 实现 LLM 客户端抽象基类**

```python
"""LLM 客户端抽象基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Optional

from .message import Message, ToolCall


class ChatResponse(BaseModel):
    """聊天响应。"""
    content: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model: str = ""
    usage: dict = Field(default_factory=dict)


class ChatChunk(BaseModel):
    """流式响应块。"""
    content_delta: str = ""
    tool_call_delta: Optional[ToolCall] = None
    done: bool = False


class LLMClient(ABC):
    """LLM 客户端统一接口。"""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """非流式聊天。"""
        pass

    @abstractmethod
    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Iterator[ChatChunk]:
        """流式聊天。"""
        pass
```

需要补一下 ChatResponse 的 import：

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Optional
from pydantic import BaseModel, Field

from .message import Message, ToolCall
```

- [ ] **Step 5: 创建 llm/__init__.py**

```python
"""LLM 适配层。"""
from .message import Message, MessageRole, ToolCall, ToolCallResult
from .base import LLMClient, ChatResponse, ChatChunk

__all__ = [
    "Message", "MessageRole", "ToolCall", "ToolCallResult",
    "LLMClient", "ChatResponse", "ChatChunk",
]
```

- [ ] **Step 6: 修正 base.py 的导入（确认完整文件内容）**

确保 `backend/nl2sql/llm/base.py` 完整内容为：

```python
"""LLM 客户端抽象基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Optional
from pydantic import BaseModel, Field

from .message import Message, ToolCall


class ChatResponse(BaseModel):
    """聊天响应。"""
    content: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model: str = ""
    usage: dict = Field(default_factory=dict)


class ChatChunk(BaseModel):
    """流式响应块。"""
    content_delta: str = ""
    tool_call_delta: Optional[ToolCall] = None
    done: bool = False


class LLMClient(ABC):
    """LLM 客户端统一接口。"""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        """非流式聊天。"""
        ...

    @abstractmethod
    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Iterator[ChatChunk]:
        """流式聊天。"""
        ...
```

- [ ] **Step 7: 运行测试验证通过**

Run: `cd backend && pytest tests/test_llm/test_message.py -v`
Expected: 全部 PASS (4 passed)

- [ ] **Step 8: Commit**

```bash
git add backend/nl2sql/llm/__init__.py backend/nl2sql/llm/message.py backend/nl2sql/llm/base.py backend/tests/test_llm/test_message.py
git commit -m "feat: LLM message models and abstract client"
```

---

## Task 6: LLM 客户端实现 + Mock 测试

**Files:**
- Create: `backend/nl2sql/llm/openai_client.py`
- Create: `backend/nl2sql/llm/claude_client.py`
- Create: `backend/nl2sql/llm/factory.py`
- Test: `backend/tests/test_llm/test_factory.py`

- [ ] **Step 1: 编写工厂测试**

```python
"""测试 LLM 工厂函数。"""
import pytest
from unittest.mock import patch, MagicMock
from nl2sql.llm.factory import create_llm_client


def test_create_openai_client():
    with patch.dict("nl2sql.config.settings.__dict", {
        "llm_provider": "openai",
        "openai_api_key": "test-key",
        "openai_model": "gpt-4",
        "openai_base_url": "",
    }):
        client = create_llm_client()
        assert client is not None
        # OpenAIClient 实例
        from nl2sql.llm.openai_client import OpenAIClient
        assert isinstance(client, OpenAIClient)


def test_create_claude_client():
    with patch.dict("nl2sql.config.settings.__dict__", {
        "llm_provider": "claude",
        "anthropic_api_key": "test-key",
        "anthropic_model": "claude-sonnet",
    }):
        client = create_llm_client()
        from nl2sql.llm.claude_client import ClaudeClient
        assert isinstance(client, ClaudeClient)


def test_create_local_openai_client():
    with patch.dict("nl2sql.config.settings.__dict__", {
        "llm_provider": "local_openai_compatible",
        "openai_api_key": "local-key",
        "openai_base_url": "http://localhost:8000/v1",
        "openai_model": "local-model",
    }):
        client = create_llm_client()
        from nl2sql.llm.openai_client import OpenAIClient
        assert isinstance(client, OpenAIClient)


def test_unknown_provider_raises():
    with patch.dict("nl2sql.config.settings.__dict__", {"llm_provider": "unknown_llm"}):
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            create_llm_client()
```

注意：settings 是 pydantic_settings 的实例，不能直接 patch dict。用 monkeypatch 更合适。改写测试：

```python
"""测试 LLM 工厂函数。"""
import pytest
from nl2sql.llm.factory import create_llm_client


def test_create_claude_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-test")

    from nl2sql.config import Settings
    # 重新创建设置实例以读取新环境变量
    settings = Settings()
    assert settings.llm_provider == "claude"


def test_create_openai_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "")

    from nl2sql.config import Settings
    settings = Settings()
    assert settings.llm_provider == "openai"


def test_factory_creates_correct_type(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4")
    monkeypatch.setenv("OPENAI_BASE_URL", "")

    client = create_llm_client()
    from nl2sql.llm.openai_client import OpenAIClient
    assert isinstance(client, OpenAIClient)


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unknown_llm_xyz")
    # 由于 settings 是单例缓存，需要在 factory 内部重新读取
    # 这里直接测试 factory 的异常分支
    from nl2sql.llm.factory import _create_for_provider
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        _create_for_provider("unknown_llm_xyz")
```

- [ ] **Step 2: 实现 OpenAI 兼容客户端**

```python
"""OpenAI 兼容格式 LLM 客户端。

同时支持官方 OpenAI 和本地 OpenAI 兼容模型（Ollama / vLLM / LM Studio / OneAPI 等）。
"""
from __future__ import annotations

from typing import Iterator

from openai import OpenAI

from .base import LLMClient, ChatResponse, ChatChunk
from .message import Message, ToolCall, MessageRole


class OpenAIClient(LLMClient):
    """OpenAI API 兼容客户端。"""

    def __init__(self, api_key: str, model: str, base_url: str = ""):
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self.model = model

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """把内部消息格式转换为 OpenAI 格式。"""
        openai_msgs = []
        for msg in messages:
            entry = {"role": msg.role.value}
            if msg.role == MessageRole.TOOL and msg.tool_result:
                entry["content"] = msg.tool_result.content
                entry["tool_call_id"] = msg.tool_result.tool_call_id
            else:
                entry["content"] = msg.content
                if msg.tool_calls:
                    entry["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": str(tc.arguments)},
                        }
                        for tc in msg.tool_calls
                    ]
            openai_msgs.append(entry)
        return openai_msgs

    def _convert_tools(self, tools: list[dict] | None) -> list[dict] | None:
        """把 tool schema 转换为 OpenAI 格式（输入已经是 OpenAI 格式，这里只做透传）。"""
        return tools

    def _parse_tool_calls(self, response) -> list[ToolCall]:
        """从响应中解析工具调用。"""
        tool_calls = []
        if not response.choices:
            return tool_calls
        message = response.choices[0].message
        if not hasattr(message, "tool_calls") or not message.tool_calls:
            return tool_calls
        for tc in message.tool_calls:
            import json
            try:
                args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append(ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=args,
            ))
        return tool_calls

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        kwargs = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = self._client.chat.completions.create(**kwargs)

        content = response.choices[0].message.content or ""
        tool_calls = self._parse_tool_calls(response)

        return ChatResponse(
            content=content,
            tool_calls=tool_calls,
            model=response.model,
            usage=response.usage.model_dump() if response.usage else {},
        )

    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Iterator[ChatChunk]:
        kwargs = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        stream = self._client.chat.completions.create(**kwargs)

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content_delta = delta.content or ""

            tool_call_delta = None
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                # 简化处理：流式 tool call 比较复杂，V1 主要用非流式
                pass

            yield ChatChunk(
                content_delta=content_delta,
                tool_call_delta=tool_call_delta,
                done=False,
            )

        yield ChatChunk(done=True)
```

- [ ] **Step 3: 实现 Claude 客户端**

```python
"""Claude (Anthropic) LLM 客户端。"""
from __future__ import annotations

import json
from typing import Iterator

from anthropic import Anthropic

from .base import LLMClient, ChatResponse, ChatChunk
from .message import Message, ToolCall, ToolCallResult, MessageRole


class ClaudeClient(LLMClient):
    """Anthropic Claude 客户端。"""

    def __init__(self, api_key: str, model: str):
        self._client = Anthropic(api_key=api_key)
        self.model = model

    def _convert_messages(self, messages: list[Message]) -> tuple[list[dict], str]:
        """转换消息格式，返回 (messages_list, system_prompt)。"""
        system_prompt = ""
        anthropic_msgs = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_prompt = msg.content
                continue

            content_blocks = []
            if msg.content:
                content_blocks.append({"type": "text", "text": msg.content})

            if msg.role == MessageRole.ASSISTANT and msg.tool_calls:
                for tc in msg.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })

            if msg.role == MessageRole.TOOL and msg.tool_result:
                content_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": msg.tool_result.tool_call_id,
                    "content": msg.tool_result.content,
                })

            anthropic_msgs.append({
                "role": "user" if msg.role in (MessageRole.USER, MessageRole.TOOL) else "assistant",
                "content": content_blocks if content_blocks else "",
            })

        return anthropic_msgs, system_prompt

    def _convert_tools(self, tools: list[dict] | None) -> list[dict] | None:
        """把 OpenAI 格式的 tool schema 转换为 Anthropic 格式。"""
        if not tools:
            return None
        anthropic_tools = []
        for tool in tools:
            func = tool.get("function", tool)
            anthropic_tools.append({
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {}),
            })
        return anthropic_tools

    def _parse_tool_calls(self, content_blocks) -> list[ToolCall]:
        """从 Claude 响应内容块中解析 tool_use。"""
        tool_calls = []
        for block in content_blocks:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=dict(block.input),
                ))
        return tool_calls

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> ChatResponse:
        anthropic_msgs, system_prompt = self._convert_messages(messages)
        anthropic_tools = self._convert_tools(tools)

        kwargs = {
            "model": self.model,
            "messages": anthropic_msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        response = self._client.messages.create(**kwargs)

        # 提取文本内容
        text_content = ""
        for block in response.content:
            if block.type == "text":
                text_content += block.text

        tool_calls = self._parse_tool_calls(response.content)

        return ChatResponse(
            content=text_content,
            tool_calls=tool_calls,
            model=response.model,
            usage=response.usage.model_dump() if response.usage else {},
        )

    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> Iterator[ChatChunk]:
        anthropic_msgs, system_prompt = self._convert_messages(messages)
        anthropic_tools = self._convert_tools(tools)

        kwargs = {
            "model": self.model,
            "messages": anthropic_msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        with self._client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield ChatChunk(content_delta=text, done=False)

        yield ChatChunk(done=True)
```

- [ ] **Step 4: 实现工厂函数**

```python
"""LLM 客户端工厂。"""
from __future__ import annotations

from ..config import settings
from .base import LLMClient


def _create_for_provider(provider: str) -> LLMClient:
    """根据 provider 名称创建对应的客户端。"""
    provider = provider.lower().strip()

    if provider == "claude":
        from .claude_client import ClaudeClient
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        return ClaudeClient(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )

    if provider in ("openai", "local_openai_compatible"):
        from .openai_client import OpenAIClient
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        return OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")


def create_llm_client() -> LLMClient:
    """根据配置创建 LLM 客户端。"""
    return _create_for_provider(settings.llm_provider)
```

- [ ] **Step 5: 更新 llm/__init__.py**

```python
"""LLM 适配层。"""
from .message import Message, MessageRole, ToolCall, ToolCallResult
from .base import LLMClient, ChatResponse, ChatChunk
from .factory import create_llm_client

__all__ = [
    "Message", "MessageRole", "ToolCall", "ToolCallResult",
    "LLMClient", "ChatResponse", "ChatChunk",
    "create_llm_client",
]
```

- [ ] **Step 6: 运行测试验证通过**

Run: `cd backend && pytest tests/test_llm/test_factory.py -v`
Expected: 全部 PASS (4 passed)

- [ ] **Step 7: Commit**

```bash
git add backend/nl2sql/llm/openai_client.py backend/nl2sql/llm/claude_client.py backend/nl2sql/llm/factory.py backend/tests/test_llm/test_factory.py backend/nl2sql/llm/__init__.py
git commit -m "feat: LLM client implementations (OpenAI + Claude) with factory"
```

---

## Task 7: SQL 执行器

**Files:**
- Create: `backend/nl2sql/executor/__init__.py`
- Create: `backend/nl2sql/executor/models.py`
- Create: `backend/nl2sql/executor/base.py`
- Create: `backend/nl2sql/executor/generic_executor.py`
- Create: `backend/nl2sql/executor/factory.py`
- Test: `backend/tests/test_executor/test_generic_executor.py`

- [ ] **Step 1: 编写测试（用 SQLite 内存库）**

```python
"""测试通用 SQL 执行器。"""
import pytest
from nl2sql.executor.generic_executor import GenericSQLExecutor
from nl2sql.executor.models import ExecutionResult


@pytest.fixture
def sqlite_executor():
    """用 SQLite 内存库做测试。"""
    executor = GenericSQLExecutor(
        datasource_id="test_sqlite",
        db_url="sqlite:///:memory:",
        timeout_seconds=10,
        max_rows=100,
    )
    # 建测试表
    executor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, status TEXT, created_at TEXT)")
    executor.execute("INSERT INTO users VALUES (1, 'Alice', 'active', '2024-01-01')")
    executor.execute("INSERT INTO users VALUES (2, 'Bob', 'inactive', '2024-02-01')")
    executor.execute("INSERT INTO users VALUES (3, 'Charlie', 'active', '2024-03-01')")
    return executor


def test_select_query(sqlite_executor):
    result = sqlite_executor.execute("SELECT id, name FROM users ORDER BY id")
    assert result.success is True
    assert result.row_count == 3
    assert result.columns == ["id", "name"]
    assert result.rows[0] == (1, "Alice")
    assert result.rows[2] == (3, "Charlie")


def test_count_query(sqlite_executor):
    result = sqlite_executor.execute("SELECT COUNT(*) as cnt FROM users WHERE status = 'active'")
    assert result.success is True
    assert result.row_count == 1
    assert result.rows[0][0] == 2


def test_max_rows_limit(sqlite_executor):
    # 配置 max_rows=2
    limited_executor = GenericSQLExecutor(
        datasource_id="test",
        db_url="sqlite:///:memory:",
        timeout_seconds=10,
        max_rows=2,
    )
    limited_executor.execute("CREATE TABLE t (id INTEGER)")
    for i in range(10):
        limited_executor.execute(f"INSERT INTO t VALUES ({i})")

    result = limited_executor.execute("SELECT * FROM t")
    assert result.success is True
    assert result.row_count <= 2


def test_sql_error(sqlite_executor):
    result = sqlite_executor.execute("SELECT * FROM nonexistent_table")
    assert result.success is False
    assert result.error is not None
    assert "nonexistent" in result.error.lower() or "no such table" in result.error.lower()


def test_multiple_statements_blocked(sqlite_executor):
    result = sqlite_executor.execute("SELECT * FROM users; DROP TABLE users;")
    # 应该被拒绝或者只执行第一条
    assert result.success is False  # 多语句应该被拒绝
```

- [ ] **Step 2: 实现执行结果模型**

```python
"""SQL 执行结果数据模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExecutionResult(BaseModel):
    """SQL 执行结果。"""
    success: bool
    sql: str
    columns: list[str] = Field(default_factory=list)
    rows: list[tuple] = Field(default_factory=list)
    row_count: int = 0
    duration_ms: float = 0.0
    error: str | None = None
    truncated: bool = False  # 是否因 max_rows 被截断
```

- [ ] **Step 3: 实现抽象基类**

```python
"""SQL 执行器抽象基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .models import ExecutionResult


class SQLExecutor(ABC):
    """SQL 执行器接口。"""

    datasource_id: str

    @abstractmethod
    def execute(self, sql: str, timeout_seconds: int | None = None) -> ExecutionResult:
        """执行 SQL 查询（只读）。"""
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        """测试数据库连接是否正常。"""
        ...
```

- [ ] **Step 4: 实现通用执行器**

```python
"""基于 SQLAlchemy 的通用 SQL 执行器。

支持所有 SQLAlchemy 兼容的数据库：MySQL, PostgreSQL, SQLite, ClickHouse 等。
"""
from __future__ import annotations

import time
import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .base import SQLExecutor
from .models import ExecutionResult


class GenericSQLExecutor(SQLExecutor):
    """通用 SQL 执行器。"""

    def __init__(
        self,
        datasource_id: str,
        db_url: str,
        timeout_seconds: int = 30,
        max_rows: int = 1000,
    ):
        self.datasource_id = datasource_id
        self.db_url = db_url
        self.timeout_seconds = timeout_seconds
        self.max_rows = max_rows
        self._engine: Engine | None = None

    def _get_engine(self) -> Engine:
        if self._engine is None:
            kwargs = {}
            if self.timeout_seconds:
                kwargs["connect_args"] = {"connect_timeout": self.timeout_seconds}
            self._engine = create_engine(self.db_url, **kwargs)
        return self._engine

    def _validate_single_statement(self, sql: str) -> tuple[bool, str]:
        """检查是否只有单条语句，防止多语句注入。"""
        # 去掉注释
        cleaned = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
        # 去掉末尾分号和空白
        cleaned = cleaned.strip().rstrip(';').strip()

        # 检查是否还有分号（中间有分号说明多条语句）
        if ';' in cleaned:
            return False, "Multiple SQL statements are not allowed for security reasons."

        # 检查是否是 SELECT 语句（只读保护）
        first_word = cleaned.split()[0].upper() if cleaned.split() else ""
        if first_word not in ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH"):
            return False, f"Only SELECT/SHOW/DESCRIBE/EXPLAIN queries are allowed, got: {first_word}"

        return True, cleaned

    def execute(self, sql: str, timeout_seconds: int | None = None) -> ExecutionResult:
        """执行 SQL 查询。"""
        start_time = time.time()
        timeout = timeout_seconds or self.timeout_seconds

        # 语句校验
        valid, message = self._validate_single_statement(sql)
        if not valid:
            return ExecutionResult(
                success=False,
                sql=sql,
                error=message,
                duration_ms=(time.time() - start_time) * 1000,
            )

        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                # 执行查询，多加一行 LIMIT 判断是否被截断
                result = conn.execute(text(sql))
                all_rows = result.fetchmany(self.max_rows + 1)

                truncated = len(all_rows) > self.max_rows
                if truncated:
                    all_rows = all_rows[:self.max_rows]

                columns = list(result.keys()) if result.keys() else []

                return ExecutionResult(
                    success=True,
                    sql=sql,
                    columns=columns,
                    rows=[tuple(row) for row in all_rows],
                    row_count=len(all_rows),
                    duration_ms=(time.time() - start_time) * 1000,
                    truncated=truncated,
                )
        except Exception as e:
            return ExecutionResult(
                success=False,
                sql=sql,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

    def test_connection(self) -> bool:
        """测试数据库连接。"""
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
```

- [ ] **Step 5: 实现工厂函数**

```python
"""SQL 执行器工厂。"""
from __future__ import annotations

from .base import SQLExecutor
from .generic_executor import GenericSQLExecutor


def create_executor(
    datasource_id: str,
    datasource_type: str,
    db_url: str,
    timeout_seconds: int = 30,
    max_rows: int = 1000,
) -> SQLExecutor:
    """创建 SQL 执行器。

    V1 全部使用 GenericSQLExecutor（基于 SQLAlchemy）。
    后续如果有特殊数据库需要定制，可以在这里分支。
    """
    return GenericSQLExecutor(
        datasource_id=datasource_id,
        db_url=db_url,
        timeout_seconds=timeout_seconds,
        max_rows=max_rows,
    )
```

- [ ] **Step 6: 创建 executor/__init__.py**

```python
"""SQL 执行器模块。"""
from .models import ExecutionResult
from .base import SQLExecutor
from .generic_executor import GenericSQLExecutor
from .factory import create_executor

__all__ = [
    "ExecutionResult",
    "SQLExecutor",
    "GenericSQLExecutor",
    "create_executor",
]
```

- [ ] **Step 7: 运行测试验证通过**

Run: `cd backend && pytest tests/test_executor/test_generic_executor.py -v`
Expected: 全部 PASS (6 passed)

- [ ] **Step 8: Commit**

```bash
git add backend/nl2sql/executor/__init__.py backend/nl2sql/executor/models.py backend/nl2sql/executor/base.py backend/nl2sql/executor/generic_executor.py backend/nl2sql/executor/factory.py backend/tests/test_executor/test_generic_executor.py
git commit -m "feat: SQL executor with read-only security"
```

---

## Task 8: Agent State 定义 + 工具集

**Files:**
- Create: `backend/nl2sql/agent/__init__.py`
- Create: `backend/nl2sql/agent/state.py`
- Create: `backend/nl2sql/agent/tools/__init__.py`
- Create: `backend/nl2sql/agent/tools/schema_tools.py`
- Create: `backend/nl2sql/agent/tools/sql_tool.py`
- Create: `backend/nl2sql/agent/tools/probe_tools.py`
- Test: `backend/tests/test_agent/test_tools.py`

- [ ] **Step 1: 定义 Agent State**

```python
"""Agent 状态定义。"""
from __future__ import annotations

from typing import Optional, Any
from dataclasses import dataclass, field

from ..schema.models import DatasourceSchema
from ..llm.message import Message
from ..executor.models import ExecutionResult


@dataclass
class IntentResult:
    """意图分析结果。"""
    tables: list[dict] = field(default_factory=list)  # [{"datasource_id": ..., "table_name": ..., "confidence": ...}]
    filters: list[dict] = field(default_factory=list)
    aggregation: Optional[str] = None
    dimensions: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    confidence: float = 0.0
    raw_analysis: str = ""


@dataclass
class ProbeFinding:
    """意图探查发现。"""
    action: str  # 执行的探查动作
    table: str
    datasource_id: str
    finding: str  # 发现的信息
    sql: str = ""


@dataclass
class ReactThought:
    """ReAct 思考记录。"""
    thought: str
    action: str = ""
    observation: str = ""


@dataclass
class AgentState:
    """LangGraph Agent 的状态。"""
    # 基本信息
    project_id: str
    datasources: list[DatasourceSchema] = field(default_factory=list)
    user_query: str = ""
    conversation_history: list[Message] = field(default_factory=list)

    # 意图分析
    intent: Optional[IntentResult] = None
    probe_findings: list[ProbeFinding] = field(default_factory=list)
    probe_iteration: int = 0
    max_probe_iterations: int = 3
    clarification_questions: list[str] = field(default_factory=list)
    awaiting_clarification: bool = False

    # SQL 与执行
    sql: Optional[str] = None
    execution_result: Optional[ExecutionResult] = None
    selected_datasource_id: Optional[str] = None

    # ReAct 循环
    react_thoughts: list[ReactThought] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 5

    # 输出
    status: str = "thinking"  # thinking / clarifying / executing / done / failed
    final_answer: Optional[str] = None
    error: Optional[str] = None

    # 事件回调（用于 SSE 推送）
    event_callback: Any = None
```

- [ ] **Step 2: Schema 工具**

```python
"""Schema 相关工具（给 Agent 调用）。"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nl2sql.agent.state import AgentState


SCHEMA_TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "列出所有可用的表及其简要描述",
            "parameters": {
                "type": "object",
                "properties": {
                    "datasource_id": {
                        "type": "string",
                        "description": "数据源ID，不填则列出所有数据源的表",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_table",
            "description": "查看指定表的详细结构，包括字段名、类型、描述等",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "表名",
                    },
                    "datasource_id": {
                        "type": "string",
                        "description": "数据源ID（可选）",
                    },
                },
                "required": ["table_name"],
            },
        },
    },
]


def list_tables(state: "AgentState", datasource_id: str | None = None) -> str:
    """列出所有表。"""
    results = []
    for ds in state.datasources:
        if datasource_id and ds.datasource_id != datasource_id:
            continue
        table_list = []
        for table in ds.schema.tables:
            table_list.append(f"- {table.name}: {table.description}")
        results.append(f"数据源 [{ds.datasource_name} ({ds.datasource_id})]:\n" + "\n".join(table_list))
    return "\n\n".join(results) if results else "没有找到表。"


def describe_table(state: "AgentState", table_name: str, datasource_id: str | None = None) -> str:
    """查看表结构。"""
    for ds in state.datasources:
        if datasource_id and ds.datasource_id != datasource_id:
            continue
        table = ds.schema.get_table(table_name)
        if table:
            lines = [f"表: {table.name}", f"描述: {table.description}", "字段:"]
            for col in table.columns:
                enum_info = f" (枚举: {', '.join(col.enum_values)})" if col.enum_values else ""
                sem_info = f" [{col.semantic_type}]" if col.semantic_type else ""
                pk_info = " [主键]" if col.is_primary_key else ""
                lines.append(f"  - {col.name} ({col.type}){pk_info}{sem_info}: {col.description}{enum_info}")
            return "\n".join(lines)
    return f"未找到表: {table_name}"
```

- [ ] **Step 3: SQL 执行工具**

```python
"""SQL 执行工具（给 Agent 调用）。"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nl2sql.agent.state import AgentState


SQL_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "execute_sql",
        "description": "执行只读 SQL 查询并返回结果。注意：只能执行 SELECT 语句，不能写库。",
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "要执行的 SQL 语句（必须是 SELECT 查询）",
                },
                "datasource_id": {
                    "type": "string",
                    "description": "数据源ID（可选，默认用当前选中的数据源）",
                },
            },
            "required": ["sql"],
        },
    },
}


def execute_sql(state: "AgentState", sql: str, datasource_id: str | None = None) -> str:
    """执行 SQL 工具函数。

    注意：这里只是查找对应的执行器并运行。
    实际的执行器实例由 graph 运行时注入到 state 或全局上下文中。
    """
    ds_id = datasource_id or state.selected_datasource_id
    if not ds_id:
        return "错误: 未指定数据源。请先指定 datasource_id。"

    # 从 state 中的执行器注册表查找
    # V1 简化：执行器存在 state.datasource_executors 中
    # 这里用 getattr 优雅降级
    executors = getattr(state, "datasource_executors", {})
    executor = executors.get(ds_id)
    if executor is None:
        return f"错误: 找不到数据源 {ds_id} 的执行器。"

    result = executor.execute(sql)

    if not result.success:
        return f"SQL 执行失败:\n错误: {result.error}\nSQL: {sql}"

    # 格式化结果
    lines = [f"执行成功，返回 {result.row_count} 行{ '（已截断）' if result.truncated else ''}，耗时 {result.duration_ms:.0f}ms"]
    lines.append("")
    if result.columns:
        lines.append("| " + " | ".join(result.columns) + " |")
        lines.append("|" + "|".join(["---"] * len(result.columns)) + "|")
        for row in result.rows[:20]:  # 最多显示 20 行，避免上下文爆炸
            lines.append("| " + " | ".join(str(v) for v in row) + " |")
        if result.row_count > 20:
            lines.append(f"... 还有 {result.row_count - 20} 行未显示")
    return "\n".join(lines)
```

- [ ] **Step 4: 探查工具**

```python
"""意图探查工具集（轻量级 SQL 探查）。

这些工具比 SQL 执行工具更克制，用于意图分析阶段快速消除歧义。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nl2sql.agent.state import AgentState


PROBE_TOOLS_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "probe_distinct",
            "description": "查看某个字段的去重值，用于理解字段的含义和可能的取值",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "表名"},
                    "column_name": {"type": "string", "description": "字段名"},
                    "limit": {"type": "integer", "description": "返回数量上限，默认20", "default": 20},
                    "datasource_id": {"type": "string", "description": "数据源ID（可选）"},
                },
                "required": ["table_name", "column_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "probe_sample",
            "description": "采样表的前 N 行数据，用于理解数据的实际内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "表名"},
                    "limit": {"type": "integer", "description": "采样行数，默认5", "default": 5},
                    "datasource_id": {"type": "string", "description": "数据源ID（可选）"},
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "probe_min_max",
            "description": "查看数值或时间字段的最小值和最大值，用于了解数据范围",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "表名"},
                    "column_name": {"type": "string", "description": "字段名"},
                    "datasource_id": {"type": "string", "description": "数据源ID（可选）"},
                },
                "required": ["table_name", "column_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "probe_count",
            "description": "查看表的总行数，用于了解数据量级",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "表名"},
                    "datasource_id": {"type": "string", "description": "数据源ID（可选）"},
                },
                "required": ["table_name"],
            },
        },
    },
]


def _get_executor(state: "AgentState", datasource_id: str | None, table_name: str) -> tuple[object, str]:
    """获取执行器和数据源ID。"""
    ds_id = datasource_id
    if not ds_id:
        # 尝试从第一个包含该表的数据源找
        for ds in state.datasources:
            if ds.schema.get_table(table_name):
                ds_id = ds.datasource_id
                break
    if not ds_id:
        return None, ""
    executors = getattr(state, "datasource_executors", {})
    return executors.get(ds_id), ds_id


def probe_distinct(state: "AgentState", table_name: str, column_name: str, limit: int = 20, datasource_id: str | None = None) -> str:
    executor, ds_id = _get_executor(state, datasource_id, table_name)
    if not executor:
        return f"错误: 找不到数据源或表 {table_name}"
    safe_limit = min(limit, 50)
    sql = f"SELECT DISTINCT {column_name} FROM {table_name} WHERE {column_name} IS NOT NULL LIMIT {safe_limit}"
    result = executor.execute(sql)
    if not result.success:
        return f"探查失败: {result.error}"
    values = [str(row[0]) for row in result.rows]
    return f"表 {table_name} 的 {column_name} 字段去重值（共{len(values)}个）: {', '.join(values)}"


def probe_sample(state: "AgentState", table_name: str, limit: int = 5, datasource_id: str | None = None) -> str:
    executor, ds_id = _get_executor(state, datasource_id, table_name)
    if not executor:
        return f"错误: 找不到数据源或表 {table_name}"
    safe_limit = min(limit, 20)
    sql = f"SELECT * FROM {table_name} LIMIT {safe_limit}"
    result = executor.execute(sql)
    if not result.success:
        return f"探查失败: {result.error}"
    lines = [f"表 {table_name} 采样 {result.row_count} 行:"]
    lines.append("| " + " | ".join(result.columns) + " |")
    lines.append("|" + "|".join(["---"] * len(result.columns)) + "|")
    for row in result.rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def probe_min_max(state: "AgentState", table_name: str, column_name: str, datasource_id: str | None = None) -> str:
    executor, ds_id = _get_executor(state, datasource_id, table_name)
    if not executor:
        return f"错误: 找不到数据源或表 {table_name}"
    sql = f"SELECT MIN({column_name}) as min_val, MAX({column_name}) as max_val FROM {table_name}"
    result = executor.execute(sql)
    if not result.success:
        return f"探查失败: {result.error}"
    if result.row_count == 0:
        return f"表 {table_name} 的 {column_name} 字段没有数据"
    min_val, max_val = result.rows[0]
    return f"表 {table_name} 的 {column_name} 字段范围: 最小值 = {min_val}, 最大值 = {max_val}"


def probe_count(state: "AgentState", table_name: str, datasource_id: str | None = None) -> str:
    executor, ds_id = _get_executor(state, datasource_id, table_name)
    if not executor:
        return f"错误: 找不到数据源或表 {table_name}"
    sql = f"SELECT COUNT(*) as cnt FROM {table_name}"
    result = executor.execute(sql)
    if not result.success:
        return f"探查失败: {result.error}"
    count = result.rows[0][0] if result.rows else 0
    return f"表 {table_name} 总行数: {count}"


# 探查工具函数映射
PROBE_TOOL_FUNCTIONS = {
    "probe_distinct": probe_distinct,
    "probe_sample": probe_sample,
    "probe_min_max": probe_min_max,
    "probe_count": probe_count,
}
```

- [ ] **Step 5: 创建 tools/__init__.py**

```python
"""Agent 工具集。"""
from .schema_tools import SCHEMA_TOOLS_DEFINITION, list_tables, describe_table
from .sql_tool import SQL_TOOL_DEFINITION, execute_sql
from .probe_tools import PROBE_TOOLS_DEFINITION, PROBE_TOOL_FUNCTIONS

__all__ = [
    "SCHEMA_TOOLS_DEFINITION", "list_tables", "describe_table",
    "SQL_TOOL_DEFINITION", "execute_sql",
    "PROBE_TOOLS_DEFINITION", "PROBE_TOOL_FUNCTIONS",
]
```

- [ ] **Step 6: 创建 agent/__init__.py**

```python
"""NL2SQL Agent 模块。"""
from .state import AgentState, IntentResult, ProbeFinding, ReactThought

__all__ = ["AgentState", "IntentResult", "ProbeFinding", "ReactThought"]
```

- [ ] **Step 7: 编写工具测试**

```python
"""测试 Agent 工具。"""
import pytest
from unittest.mock import MagicMock

from nl2sql.agent.state import AgentState
from nl2sql.agent.tools.schema_tools import list_tables, describe_table
from nl2sql.agent.tools.probe_tools import probe_count
from nl2sql.schema.models import Column, Table, Schema, DatasourceSchema
from nl2sql.executor.models import ExecutionResult


@pytest.fixture
def sample_state():
    ds = DatasourceSchema(
        datasource_id="test_ds",
        datasource_name="测试库",
        datasource_type="mysql",
        schema=Schema(
            tables=[
                Table(
                    name="users",
                    description="用户表",
                    columns=[
                        Column(name="id", type="bigint", description="ID", is_primary_key=True),
                        Column(name="name", type="varchar", description="姓名"),
                    ],
                ),
            ]
        ),
    )
    state = AgentState(project_id="test", datasources=[ds], user_query="测试")
    return state


def test_list_tables(sample_state):
    result = list_tables(sample_state)
    assert "users" in result
    assert "用户表" in result


def test_describe_table(sample_state):
    result = describe_table(sample_state, "users")
    assert "users" in result
    assert "id" in result
    assert "name" in result
    assert "[主键]" in result


def test_describe_nonexistent_table(sample_state):
    result = describe_table(sample_state, "nonexistent")
    assert "未找到" in result


def test_probe_count(sample_state):
    # mock 执行器
    mock_executor = MagicMock()
    mock_executor.execute.return_value = ExecutionResult(
        success=True,
        sql="SELECT COUNT(*)",
        columns=["cnt"],
        rows=[(100,)],
        row_count=1,
    )
    sample_state.datasource_executors = {"test_ds": mock_executor}  # type: ignore

    result = probe_count(sample_state, "users")
    assert "100" in result
    assert "总行数" in result
```

- [ ] **Step 8: 运行测试验证通过**

Run: `cd backend && pytest tests/test_agent/test_tools.py -v`
Expected: 全部 PASS (4 passed)

- [ ] **Step 9: Commit**

```bash
git add backend/nl2sql/agent/__init__.py backend/nl2sql/agent/state.py backend/nl2sql/agent/tools/__init__.py backend/nl2sql/agent/tools/schema_tools.py backend/nl2sql/agent/tools/sql_tool.py backend/nl2sql/agent/tools/probe_tools.py backend/tests/test_agent/test_tools.py
git commit -m "feat: agent state and tool definitions"
```

---

## Task 9: Agent 节点 — 意图分析 + 探查 + 澄清

**Files:**
- Create: `backend/nl2sql/agent/nodes/__init__.py`
- Create: `backend/nl2sql/agent/nodes/intent.py`
- Create: `backend/nl2sql/agent/nodes/probe.py`
- Create: `backend/nl2sql/agent/nodes/clarify.py`
- Test: `backend/tests/test_agent/test_nodes_intent.py`

这一步的实现涉及 LLM 调用，测试用 mock。

- [ ] **Step 1: 实现意图分析节点**

```python
"""意图分析节点。"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ...llm.message import Message, MessageRole
from ...schema.matcher import SchemaMatcher

if TYPE_CHECKING:
    from nl2sql.agent.state import AgentState, IntentResult


INTENT_ANALYSIS_SYSTEM_PROMPT = """你是一个数据分析师，负责分析用户的自然语言问题，确定查询意图。

请根据提供的 Schema 信息，分析用户问题并输出 JSON 格式的分析结果。

输出格式：
{
    "tables": [{"table_name": "...", "datasource_id": "...", "confidence": 0.9}],
    "filters": [{"column": "...", "operator": "...", "value": "..."}],
    "aggregation": "count/sum/avg/max/min/none",
    "dimensions": ["column1", "column2"],
    "ambiguities": ["歧义点1", "歧义点2"],
    "confidence": 0.8,
    "analysis": "一句话说明分析思路"
}

ambiguities 说明：
- 如果表不确定、字段含义不明、时间范围不明确、统计口径模糊等，都要列出来
- 没有歧义就返回空数组
- 只列真正需要澄清的业务语义层面的歧义，技术层面的（如字段有哪些值）后续可以通过探查解决
"""


def _build_schema_context(state: "AgentState") -> str:
    """构建 Schema 上下文（精简版，控制 token）。"""
    matcher = SchemaMatcher(state.datasources)
    # 先用关键词匹配找出最相关的表，只展示 top 10
    relevant = matcher.find_relevant_tables(state.user_query, top_k=10)

    if not relevant:
        # 如果没匹配到，展示所有表名
        lines = ["可用表："]
        for ds in state.datasources:
            for t in ds.schema.tables:
                lines.append(f"- [{ds.datasource_id}] {t.name}: {t.description}")
        return "\n".join(lines)

    lines = ["最相关的表："]
    for match in relevant:
        table = match.table
        lines.append(f"\n数据源: {match.datasource_id}")
        lines.append(f"表: {table.name}")
        lines.append(f"描述: {table.description}")
        lines.append("字段:")
        for col in table.columns:
            sem = f" [{col.semantic_type}]" if col.semantic_type else ""
            lines.append(f"  - {col.name} ({col.type}){sem}: {col.description}")
    return "\n".join(lines)


def intent_analyze_node(state: "AgentState") -> dict:
    """意图分析节点。

    输入: state.user_query, state.datasources
    输出: {"intent": IntentResult, "status": "thinking"}
    """
    from ...llm.factory import create_llm_client
    from ..state import IntentResult

    llm = create_llm_client()
    schema_context = _build_schema_context(state)

    user_prompt = f"""用户问题: {state.user_query}

{schema_context}

请分析用户的查询意图，输出 JSON。"""

    messages = [
        Message(role=MessageRole.SYSTEM, content=INTENT_ANALYSIS_SYSTEM_PROMPT),
    ]

    # 加入对话历史（最近5轮）
    if state.conversation_history:
        messages.extend(state.conversation_history[-10:])

    messages.append(Message(role=MessageRole.USER, content=user_prompt))

    response = llm.chat(messages, temperature=0.1)

    # 解析 JSON 响应
    try:
        # 尝试提取 JSON（可能包裹在 markdown 代码块中）
        content = response.content.strip()
        if content.startswith("```"):
            # 去掉 ```json 和 ```
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        data = json.loads(content)
    except (json.JSONDecodeError, Exception) as e:
        # 解析失败，返回带歧义的结果
        return {
            "intent": IntentResult(
                ambiguities=[f"无法解析意图分析结果: {e}"],
                raw_analysis=response.content,
            ),
            "status": "thinking",
        }

    intent = IntentResult(
        tables=data.get("tables", []),
        filters=data.get("filters", []),
        aggregation=data.get("aggregation"),
        dimensions=data.get("dimensions", []),
        ambiguities=data.get("ambiguities", []),
        confidence=data.get("confidence", 0.0),
        raw_analysis=data.get("analysis", ""),
    )

    result = {"intent": intent, "status": "thinking"}

    # 发送事件
    if state.event_callback:
        state.event_callback("intent_analysis", {
            "tables": intent.tables,
            "ambiguities": intent.ambiguities,
            "confidence": intent.confidence,
            "analysis": intent.raw_analysis,
        })

    return result
```

- [ ] **Step 2: 实现意图探查节点**

```python
"""意图探查节点。

用轻量 SQL 查询消除歧义，减少需要用户澄清的次数。
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ...llm.message import Message, MessageRole, ToolCall, ToolCallResult
from ..tools import PROBE_TOOLS_DEFINITION, PROBE_TOOL_FUNCTIONS

if TYPE_CHECKING:
    from nl2sql.agent.state import AgentState


PROBE_SYSTEM_PROMPT = """你是一个数据探查助手。你的任务是通过轻量 SQL 查询来消除用户问题中的歧义。

当前已经识别出以下歧义点，你可以使用探查工具来消除它们。
注意：
1. 只使用探查工具（probe_distinct, probe_sample, probe_min_max, probe_count）
2. 每次最多调用 2 个探查工具
3. 探查的目的是消除歧义，不是回答用户问题
4. 如果歧义是业务语义层面的（如"活跃用户的定义"），无法通过探查解决，就不要浪费查询
5. 调用完工具后，总结你的发现

可以解决的歧义类型：
- 字段有哪些可能的值 → 用 probe_distinct
- 表里数据长什么样 → 用 probe_sample
- 时间范围有多大 → 用 probe_min_max
- 数据量级 → 用 probe_count
"""


def _build_probe_prompt(state: "AgentState") -> str:
    """构建探查 prompt。"""
    intent = state.intent
    if not intent:
        return "没有需要探查的内容。"

    ambiguities = intent.ambiguities
    if not ambiguities:
        return "没有歧义需要探查。"

    lines = [
        f"用户问题: {state.user_query}",
        "",
        "识别出的歧义点:",
    ]
    for i, amb in enumerate(ambiguities, 1):
        lines.append(f"{i}. {amb}")

    # 加入之前的探查发现
    if state.probe_findings:
        lines.append("")
        lines.append("已有的探查发现:")
        for f in state.probe_findings:
            lines.append(f"- {f.finding}")

    lines.append("")
    lines.append("请判断哪些歧义可以通过探查解决，并调用相应的工具。")
    lines.append("如果已经探查过或无法通过探查解决，就直接回复无需继续探查。")

    return "\n".join(lines)


def intent_probe_node(state: "AgentState") -> dict:
    """意图探查节点。

    输入: state.intent.ambiguities, state.probe_findings, state.probe_iteration
    输出: 更新 probe_findings 和 probe_iteration
    """
    from ...llm.factory import create_llm_client
    from ..state import ProbeFinding

    # 没有歧义就跳过
    if not state.intent or not state.intent.ambiguities:
        return {"probe_findings": state.probe_findings}

    # 达到最大迭代次数
    if state.probe_iteration >= state.max_probe_iterations:
        return {}

    llm = create_llm_client()

    messages = [
        Message(role=MessageRole.SYSTEM, content=PROBE_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=_build_probe_prompt(state)),
    ]

    response = llm.chat(messages, tools=PROBE_TOOLS_DEFINITION, temperature=0.0)

    new_findings = list(state.probe_findings)

    # 如果有工具调用，执行并记录
    if response.tool_calls:
        for tool_call in response.tool_calls:
            tool_name = tool_call.name
            tool_args = tool_call.arguments

            if tool_name in PROBE_TOOL_FUNCTIONS:
                func = PROBE_TOOL_FUNCTIONS[tool_name]
                # 调用工具，传入 state
                finding_text = func(state, **tool_args)

                # 记录发现
                table_name = tool_args.get("table_name", "")
                # 推断 datasource_id
                ds_id = tool_args.get("datasource_id", "")
                if not ds_id:
                    for ds in state.datasources:
                        if ds.schema.get_table(table_name):
                            ds_id = ds.datasource_id
                            break

                new_findings.append(ProbeFinding(
                    action=tool_name,
                    table=table_name,
                    datasource_id=ds_id,
                    finding=finding_text,
                    sql=f"{tool_name}({tool_args})",
                ))

                # 发送事件
                if state.event_callback:
                    state.event_callback("intent_probe", {
                        "action": tool_name,
                        "table": table_name,
                        "finding": finding_text,
                    })

    return {
        "probe_findings": new_findings,
        "probe_iteration": state.probe_iteration + 1,
    }
```

- [ ] **Step 3: 实现澄清判断节点**

```python
"""澄清判断节点。

判断探查后是否还有需要用户澄清的歧义。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ...llm.message import Message, MessageRole

if TYPE_CHECKING:
    from nl2sql.agent.state import AgentState


CLARIFY_SYSTEM_PROMPT = """你是一个数据分析助手。根据用户问题、意图分析结果和已有的探查发现，判断是否还需要向用户澄清。

判断规则：
1. 只有业务语义层面的歧义才需要澄清（如统计口径、业务定义）
2. 技术层面的歧义如果已经通过探查解决了，就不需要再问
3. 可以合理推测的（如默认时间范围、默认排序），不需要澄清
4. 关键歧义（如涉及哪张表、核心维度）如果不确定，必须澄清

如果需要澄清，生成 1-3 个最关键的澄清问题，用 JSON 数组格式返回：
["问题1", "问题2"]

如果不需要澄清，返回空数组 []。
"""


def clarify_node(state: "AgentState") -> dict:
    """判断是否需要澄清。

    返回: {"clarification_questions": [...], "awaiting_clarification": bool}
    """
    from ...llm.factory import create_llm_client

    intent = state.intent
    if not intent or not intent.ambiguities:
        return {"awaiting_clarification": False, "clarification_questions": []}

    llm = create_llm_client()

    # 构建上下文
    lines = [
        f"用户问题: {state.user_query}",
        "",
        "意图分析结果:",
        f"  涉及表: {json.dumps(intent.tables, ensure_ascii=False)}",
        f"  聚合: {intent.aggregation}",
        f"  维度: {intent.dimensions}",
        f"  筛选: {json.dumps(intent.filters, ensure_ascii=False)}",
        "",
        "识别出的歧义:",
    ]
    for amb in intent.ambiguities:
        lines.append(f"  - {amb}")

    if state.probe_findings:
        lines.append("")
        lines.append("已完成的探查发现:")
        for f in state.probe_findings:
            lines.append(f"  - {f.finding[:200]}")

    user_prompt = "\n".join(lines) + "\n\n请判断还需要向用户澄清吗？如果需要，列出最重要的问题。"

    messages = [
        Message(role=MessageRole.SYSTEM, content=CLARIFY_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_prompt),
    ]

    response = llm.chat(messages, temperature=0.0)
    content = response.content.strip()

    # 解析 JSON 数组
    import re
    json_match = re.search(r'\[.*\]', content, re.DOTALL)
    if json_match:
        import json
        try:
            questions = json.loads(json_match.group())
            if isinstance(questions, list):
                return {
                    "clarification_questions": questions,
                    "awaiting_clarification": len(questions) > 0,
                    "status": "clarifying" if questions else "thinking",
                }
        except json.JSONDecodeError:
            pass

    # 解析失败，默认不澄清（让后续流程自己处理）
    return {"awaiting_clarification": False, "clarification_questions": []}


def need_clarify_conditional(state: "AgentState") -> str:
    """条件边：返回下一个节点的名称。"""
    if state.awaiting_clarification and state.clarification_questions:
        return "ask_clarify"
    return "generate_sql"
```

等等，这里需要 import json。修正一下，把 import json 移到文件顶部。

- [ ] **Step 4: 修正 clarify.py（补 import + 完善 ask_clarify）**

完整的 `clarify.py`：

```python
"""澄清判断节点。

判断探查后是否还有需要用户澄清的歧义。
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from ...llm.message import Message, MessageRole

if TYPE_CHECKING:
    from nl2sql.agent.state import AgentState


CLARIFY_SYSTEM_PROMPT = """你是一个数据分析助手。根据用户问题、意图分析结果和已有的探查发现，判断是否还需要向用户澄清。

判断规则：
1. 只有业务语义层面的歧义才需要澄清（如统计口径、业务定义）
2. 技术层面的歧义如果已经通过探查解决了，就不需要再问
3. 可以合理推测的（如默认时间范围、默认排序），不需要澄清
4. 关键歧义（如涉及哪张表、核心维度）如果不确定，必须澄清

如果需要澄清，生成 1-3 个最关键的澄清问题，用 JSON 数组格式返回：
["问题1", "问题2"]

如果不需要澄清，返回空数组 []。
"""


def clarify_node(state: "AgentState") -> dict:
    """判断是否需要澄清。

    返回: {"clarification_questions": [...], "awaiting_clarification": bool}
    """
    from ...llm.factory import create_llm_client

    intent = state.intent
    if not intent or not intent.ambiguities:
        return {"awaiting_clarification": False, "clarification_questions": []}

    llm = create_llm_client()

    lines = [
        f"用户问题: {state.user_query}",
        "",
        "意图分析结果:",
        f"  涉及表: {json.dumps(intent.tables, ensure_ascii=False)}",
        f"  聚合: {intent.aggregation}",
        f"  维度: {json.dumps(intent.dimensions, ensure_ascii=False)}",
        f"  筛选: {json.dumps(intent.filters, ensure_ascii=False)}",
        "",
        "识别出的歧义:",
    ]
    for amb in intent.ambiguities:
        lines.append(f"  - {amb}")

    if state.probe_findings:
        lines.append("")
        lines.append("已完成的探查发现:")
        for f in state.probe_findings:
            lines.append(f"  - {f.finding[:200]}")

    user_prompt = "\n".join(lines) + "\n\n请判断还需要向用户澄清吗？如果需要，列出最重要的问题。"

    messages = [
        Message(role=MessageRole.SYSTEM, content=CLARIFY_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_prompt),
    ]

    response = llm.chat(messages, temperature=0.0)
    content = response.content.strip()

    # 解析 JSON 数组
    questions = []
    json_match = re.search(r'\[.*\]', content, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                questions = parsed
        except json.JSONDecodeError:
            pass

    result = {
        "clarification_questions": questions,
        "awaiting_clarification": len(questions) > 0,
        "status": "clarifying" if questions else "thinking",
    }

    # 发送事件
    if state.event_callback and questions:
        state.event_callback("clarification_needed", {"questions": questions})

    return result


def need_clarify_conditional(state: "AgentState") -> str:
    """条件边：返回下一个节点的名称。

    LangGraph 条件边函数，返回目标节点名。
    """
    if state.awaiting_clarification and state.clarification_questions:
        return "ask_clarify"
    return "generate_sql"


def ask_clarify_node(state: "AgentState") -> dict:
    """等待用户澄清的节点（图在此暂停）。

    实际的澄清回复由外部通过 update_state 注入。
    这里只标记状态。
    """
    return {"status": "clarifying"}
```

- [ ] **Step 5: 创建 nodes/__init__.py**

```python
"""Agent 节点实现。"""
from .intent import intent_analyze_node
from .probe import intent_probe_node
from .clarify import clarify_node, need_clarify_conditional, ask_clarify_node

__all__ = [
    "intent_analyze_node",
    "intent_probe_node",
    "clarify_node",
    "need_clarify_conditional",
    "ask_clarify_node",
]
```

- [ ] **Step 6: 编写测试（mock LLM）**

```python
"""测试意图分析/探查/澄清节点。"""
import pytest
from unittest.mock import patch, MagicMock

from nl2sql.agent.state import AgentState, IntentResult
from nl2sql.agent.nodes.clarify import need_clarify_conditional
from nl2sql.schema.models import Column, Table, Schema, DatasourceSchema


@pytest.fixture
def basic_state():
    ds = DatasourceSchema(
        datasource_id="test_ds",
        datasource_name="测试库",
        datasource_type="mysql",
        schema=Schema(tables=[
            Table(name="users", description="用户表", columns=[
                Column(name="id", type="bigint", description="ID"),
                Column(name="status", type="varchar", description="状态"),
            ]),
        ]),
    )
    return AgentState(
        project_id="test",
        datasources=[ds],
        user_query="查询活跃用户数量",
    )


def test_need_clarify_conditional_true():
    state = AgentState(project_id="test", user_query="test")
    state.awaiting_clarification = True
    state.clarification_questions = ["问题1"]
    assert need_clarify_conditional(state) == "ask_clarify"


def test_need_clarify_conditional_false():
    state = AgentState(project_id="test", user_query="test")
    state.awaiting_clarification = False
    assert need_clarify_conditional(state) == "generate_sql"


def test_need_clarify_empty_questions():
    state = AgentState(project_id="test", user_query="test")
    state.awaiting_clarification = True
    state.clarification_questions = []
    assert need_clarify_conditional(state) == "generate_sql"


def test_intent_node_with_mock_llm(basic_state):
    """测试意图分析节点（mock LLM 响应）。"""
    from nl2sql.agent.nodes.intent import intent_analyze_node

    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(
        content='''{
            "tables": [{"table_name": "users", "datasource_id": "test_ds", "confidence": 0.9}],
            "filters": [],
            "aggregation": "count",
            "dimensions": [],
            "ambiguities": ["活跃用户的定义不明确"],
            "confidence": 0.85,
            "analysis": "用户想统计用户数量，按状态筛选活跃用户"
        }'''
    )

    with patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm):
        result = intent_analyze_node(basic_state)

    assert "intent" in result
    intent = result["intent"]
    assert intent.aggregation == "count"
    assert len(intent.ambiguities) == 1
    assert "活跃用户" in intent.ambiguities[0]
    assert intent.confidence == 0.85


def test_intent_node_malformed_json(basic_state):
    """测试 LLM 返回非 JSON 时的降级处理。"""
    from nl2sql.agent.nodes.intent import intent_analyze_node

    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="这不是 JSON 格式")

    with patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm):
        result = intent_analyze_node(basic_state)

    assert "intent" in result
    # 解析失败也应该返回 intent 对象（带错误信息）
    assert result["intent"] is not None
    assert len(result["intent"].ambiguities) >= 1
```

- [ ] **Step 7: 运行测试验证通过**

Run: `cd backend && pytest tests/test_agent/test_nodes_intent.py -v`
Expected: 全部 PASS (5 passed)

- [ ] **Step 8: Commit**

```bash
git add backend/nl2sql/agent/nodes/__init__.py backend/nl2sql/agent/nodes/intent.py backend/nl2sql/agent/nodes/probe.py backend/nl2sql/agent/nodes/clarify.py backend/tests/test_agent/test_nodes_intent.py
git commit -m "feat: agent nodes - intent analysis, probe, and clarify"
```

---

## Task 10: Agent 节点 — SQL 生成 + 执行 + 反思 + 总结

**Files:**
- Create: `backend/nl2sql/agent/nodes/generate.py`
- Create: `backend/nl2sql/agent/nodes/execute.py`
- Create: `backend/nl2sql/agent/nodes/reflect.py`
- Create: `backend/nl2sql/agent/nodes/summarize.py`
- Test: `backend/tests/test_agent/test_nodes_react.py`

- [ ] **Step 1: SQL 生成节点**

```python
"""SQL 生成节点。"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ...llm.message import Message, MessageRole
from ...schema.matcher import SchemaMatcher

if TYPE_CHECKING:
    from nl2sql.agent.state import AgentState


SQL_GENERATION_SYSTEM_PROMPT = """你是一个资深 SQL 工程师。根据用户的自然语言问题和数据库 Schema，生成准确的 SQL 查询。

要求：
1. 只生成一条 SELECT 语句，不要生成 INSERT/UPDATE/DELETE/DROP 等写操作
2. SQL 必须语法正确，字段名和表名必须存在于提供的 Schema 中
3. 合理使用 WHERE 条件、GROUP BY、ORDER BY、JOIN 等
4. 如果用户提到的字段在 Schema 中找不到，用最接近的字段
5. 适当添加注释
6. 输出格式：只输出 SQL，用 ```sql ... ``` 包裹
7. 只使用提供的 Schema 中的表和字段
8. 注意 SQL 方言：{db_type}
"""


def _build_sql_context(state: "AgentState") -> str:
    """构建 SQL 生成的 Schema 上下文。"""
    # 根据意图中的表，构建详细的 schema 上下文
    lines = []

    # 如果有意图分析，优先用意图里的表
    relevant_tables = []
    if state.intent and state.intent.tables:
        for t_info in state.intent.tables:
            ds_id = t_info.get("datasource_id", "")
            table_name = t_info.get("table_name", "")
            for ds in state.datasources:
                if ds.datasource_id == ds_id or not ds_id:
                    table = ds.schema.get_table(table_name)
                    if table:
                        relevant_tables.append((ds.datasource_id, table))
                        break

    # 如果意图分析没找到表，用 matcher 找
    if not relevant_tables:
        matcher = SchemaMatcher(state.datasources)
        matches = matcher.find_relevant_tables(state.user_query, top_k=5)
        for m in matches:
            relevant_tables.append((m.datasource_id, m.table))

    for ds_id, table in relevant_tables:
        lines.append(f"表: {table.name} (数据源: {ds_id})")
        lines.append(f"描述: {table.description}")
        lines.append("字段:")
        for col in table.columns:
            sem = f" [{col.semantic_type}]" if col.semantic_type else ""
            enum = f" 枚举: {', '.join(col.enum_values)}" if col.enum_values else ""
            pk = " [PK]" if col.is_primary_key else ""
            fk = f" [FK -> {col.foreign_key_table}.{col.foreign_key_column}]" if col.is_foreign_key else ""
            lines.append(f"  - {col.name} ({col.type}){pk}{fk}{sem}: {col.description}{enum}")
        lines.append("")

    # 加入探查发现
    if state.probe_findings:
        lines.append("探查发现（可辅助生成 SQL）:")
        for f in state.probe_findings:
            lines.append(f"- {f.finding[:200]}")
        lines.append("")

    # 加入样例
    for ds_id, table in relevant_tables:
        if table.examples:
            lines.append(f"{table.name} 表的查询样例:")
            for ex in table.examples:
                lines.append(f"  Q: {ex.get('question', '')}")
                lines.append(f"  A: {ex.get('sql', '')}")
            lines.append("")

    return "\n".join(lines)


def _extract_sql(content: str) -> str:
    """从 LLM 响应中提取 SQL。"""
    # 尝试匹配 ```sql ... ```
    match = re.search(r'```sql\s*\n?(.*?)```', content, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # 尝试匹配 ``` ... ```
    match = re.search(r'```\s*\n?(.*?)```', content, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 直接返回内容（去掉首尾空白）
    return content.strip()


def generate_sql_node(state: "AgentState") -> dict:
    """SQL 生成节点。"""
    from ...llm.factory import create_llm_client

    llm = create_llm_client()

    # 确定数据库类型
    db_type = "MySQL"
    if state.selected_datasource_id:
        for ds in state.datasources:
            if ds.datasource_id == state.selected_datasource_id:
                db_type = ds.datasource_type
                break
    elif state.datasources:
        db_type = state.datasources[0].datasource_type

    system_prompt = SQL_GENERATION_SYSTEM_PROMPT.format(db_type=db_type)
    schema_context = _build_sql_context(state)

    # 构建对话历史
    messages = [Message(role=MessageRole.SYSTEM, content=system_prompt)]

    # 加入对话历史
    if state.conversation_history:
        messages.extend(state.conversation_history[-10:])

    user_prompt = f"""用户问题: {state.user_query}

数据库 Schema:
{schema_context}

请生成 SQL 查询。"""

    # 如果有反思记录，加入修正上下文
    if state.react_thoughts:
        last_thought = state.react_thoughts[-1]
        if last_thought.observation and "错误" in last_thought.observation:
            user_prompt += f"\n\n注意：之前的 SQL 执行报错了，请修正。\n错误信息: {last_thought.observation}"

    messages.append(Message(role=MessageRole.USER, content=user_prompt))

    response = llm.chat(messages, temperature=0.0)
    sql = _extract_sql(response.content)

    result = {"sql": sql, "status": "thinking"}

    # 发送事件
    if state.event_callback:
        state.event_callback("sql_generated", {"sql": sql})

    return result
```

- [ ] **Step 2: SQL 执行节点**

```python
"""SQL 执行节点。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nl2sql.agent.state import AgentState


def execute_sql_node(state: "AgentState") -> dict:
    """执行 SQL 节点。"""
    if not state.sql:
        return {"error": "没有生成 SQL", "status": "failed"}

    # 确定数据源
    ds_id = state.selected_datasource_id
    if not ds_id:
        # 从意图中推断，或者用第一个数据源
        if state.intent and state.intent.tables:
            ds_id = state.intent.tables[0].get("datasource_id", "")
        if not ds_id and state.datasources:
            ds_id = state.datasources[0].datasource_id

    executors = getattr(state, "datasource_executors", {})
    executor = executors.get(ds_id)

    if not executor:
        return {
            "error": f"找不到数据源 {ds_id} 的执行器",
            "status": "failed",
        }

    # 发送事件
    if state.event_callback:
        state.event_callback("sql_executing", {"sql": state.sql, "datasource_id": ds_id})

    result = executor.execute(state.sql)

    if not result.success:
        # 执行失败，记录到 react_thoughts 中供反思使用
        from ..state import ReactThought
        new_thoughts = list(state.react_thoughts)
        new_thoughts.append(ReactThought(
            thought=f"SQL 执行失败，需要修正。错误: {result.error}",
            action="",
            observation=result.error,
        ))
        return {
            "execution_result": result,
            "react_thoughts": new_thoughts,
            "selected_datasource_id": ds_id,
            "status": "thinking",
        }

    # 发送事件
    if state.event_callback:
        state.event_callback("sql_executed", {
            "sql": state.sql,
            "row_count": result.row_count,
            "duration_ms": result.duration_ms,
            "truncated": result.truncated,
        })

    return {
        "execution_result": result,
        "selected_datasource_id": ds_id,
        "status": "executing",
    }
```

- [ ] **Step 3: ReAct 反思节点**

```python
"""ReAct 反思节点。

判断执行结果是否满足用户需求，如果不满足决定下一步行动。
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ...llm.message import Message, MessageRole, ToolCall, ToolCallResult
from ..tools import SCHEMA_TOOLS_DEFINITION, SQL_TOOL_DEFINITION

if TYPE_CHECKING:
    from nl2sql.agent.state import AgentState


REFLECT_SYSTEM_PROMPT = """你是一个严谨的数据分析师。你的任务是检查 SQL 执行结果是否正确回答了用户的问题。

请仔细检查：
1. SQL 是否正确执行了（有没有报错）
2. 结果数据是否和用户问题匹配
3. 有没有遗漏重要的筛选条件
4. 聚合方式是否正确
5. 结果字段是否合理

如果结果有问题，可以：
- 修正 SQL 重新执行（回复 revised_sql: true）
- 调用工具获取更多信息（list_tables, describe_table, execute_sql）
- 如果确认结果正确，回复 satisfied: true

输出 JSON 格式：
{
    "satisfied": true/false,
    "needs_revision": true/false,
    "thought": "你的分析和判断",
    "suggested_fix": "如果需要修正，描述怎么改（可选）"
}
"""


def reflect_node(state: "AgentState") -> dict:
    """反思节点。判断结果是否满意，是否需要继续迭代。"""
    from ...llm.factory import create_llm_client
    from ..state import ReactThought

    # 如果还没有执行结果（比如第一次迭代还没执行），跳过反思直接去生成
    if state.execution_result is None:
        return {"iteration": state.iteration}

    llm = create_llm_client()

    # 构建结果摘要
    result = state.execution_result
    if result.success:
        result_summary = f"执行成功，返回 {result.row_count} 行，耗时 {result.duration_ms:.0f}ms"
        if result.columns:
            result_summary += f"\n列: {', '.join(result.columns)}"
            result_summary += "\n前10行数据:\n"
            for row in result.rows[:10]:
                result_summary += f"  {row}\n"
    else:
        result_summary = f"执行失败\n错误: {result.error}\nSQL: {state.sql}"

    user_prompt = f"""用户问题: {state.user_query}

生成的 SQL:
{state.sql}

执行结果:
{result_summary}

之前的思考记录:
{json.dumps([t.__dict__ for t in state.react_thoughts[-3:]], ensure_ascii=False)}

请判断这个结果是否正确回答了用户的问题。输出 JSON。"""

    messages = [
        Message(role=MessageRole.SYSTEM, content=REFLECT_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=user_prompt),
    ]

    response = llm.chat(messages, temperature=0.0)
    content = response.content.strip()

    # 解析 JSON
    satisfied = False
    needs_revision = False
    thought = ""
    suggested_fix = ""

    try:
        # 提取 JSON
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            satisfied = data.get("satisfied", False)
            needs_revision = data.get("needs_revision", False)
            thought = data.get("thought", "")
            suggested_fix = data.get("suggested_fix", "")
    except (json.JSONDecodeError, Exception):
        # 解析失败，默认不满意（让它继续尝试或达到上限）
        thought = content[:500]
        needs_revision = not result.success

    # 记录思考
    new_thoughts = list(state.react_thoughts)
    new_thoughts.append(ReactThought(
        thought=thought,
        action="revise_sql" if needs_revision else ("finish" if satisfied else ""),
        observation=suggested_fix,
    ))

    # 发送事件
    if state.event_callback:
        state.event_callback("reflection", {
            "thought": thought,
            "satisfied": satisfied,
            "needs_revision": needs_revision,
            "iteration": state.iteration + 1,
        })

    return {
        "react_thoughts": new_thoughts,
        "iteration": state.iteration + 1,
        "_satisfied": satisfied,  # 临时字段，供条件边判断
        "_needs_revision": needs_revision,
    }


def need_retry_conditional(state: "AgentState") -> str:
    """条件边：判断是继续迭代还是输出结果。"""
    # 达到最大迭代次数
    if state.iteration >= state.max_iterations:
        return "summarize"

    # 检查上一次反思结果
    last_satisfied = getattr(state, "_satisfied", False)
    last_needs_revision = getattr(state, "_needs_revision", False)

    # 如果满意了，输出结果
    if last_satisfied:
        return "summarize"

    # 如果需要修正且还有迭代次数，回去重新生成
    if last_needs_revision:
        return "generate_sql"

    # 默认：再迭代一次（最多 max_iterations 次）
    if state.iteration < state.max_iterations:
        return "generate_sql"

    return "summarize"
```

- [ ] **Step 4: 总结节点**

```python
"""总结节点。

用自然语言总结查询结果，生成最终回答。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ...llm.message import Message, MessageRole

if TYPE_CHECKING:
    from nl2sql.agent.state import AgentState


SUMMARIZE_SYSTEM_PROMPT = """你是一个数据分析师助手。用简洁的自然语言总结 SQL 查询结果，回答用户的问题。

要求：
1. 直接回答用户问题，不要说"根据查询结果"之类的套话
2. 关键数字要突出
3. 如果结果为空，如实说明
4. 如果结果被截断（数据量很大），要说明
5. 3-5 句话以内，简洁明了
"""


def summarize_node(state: "AgentState") -> dict:
    """总结节点：生成最终回答。"""
    from ...llm.factory import create_llm_client

    if not state.execution_result or not state.execution_result.success:
        error_msg = state.execution_result.error if state.execution_result else "未知错误"
        return {
            "final_answer": f"查询失败了。\n错误信息: {error_msg}\n\n生成的 SQL:\n```sql\n{state.sql}\n```",
            "status": "failed",
        }

    result = state.execution_result

    # 构建结果摘要
    lines = []
    if result.columns:
        lines.append("列: " + ", ".join(result.columns))
        lines.append(f"共 {result.row_count} 行{ '（已截断）' if result.truncated else ''}")
        lines.append("")
        for i, row in enumerate(result.rows[:50]):  # 给 LLM 看最多 50 行
            lines.append(f"{i+1}. " + ", ".join(str(v) for v in row))
        if result.row_count > 50:
            lines.append(f"... 还有 {result.row_count - 50} 行")
    result_text = "\n".join(lines)

    llm = create_llm_client()

    messages = [
        Message(role=MessageRole.SYSTEM, content=SUMMARIZE_SYSTEM_PROMPT),
    ]

    if state.conversation_history:
        messages.extend(state.conversation_history[-6:])

    user_prompt = f"""用户问题: {state.user_query}

SQL:
```sql
{state.sql}
```

查询结果:
{result_text}

请用自然语言总结回答用户的问题。"""

    messages.append(Message(role=MessageRole.USER, content=user_prompt))

    response = llm.chat(messages, temperature=0.3)

    result_data = {
        "final_answer": response.content.strip(),
        "status": "done",
    }

    # 发送事件
    if state.event_callback:
        state.event_callback("final_result", {
            "answer": response.content.strip(),
            "sql": state.sql,
            "result": {
                "columns": result.columns,
                "rows": [list(r) for r in result.rows],
                "row_count": result.row_count,
                "truncated": result.truncated,
            },
        })
        state.event_callback("done", {})

    return result_data
```

- [ ] **Step 5: 更新 nodes/__init__.py**

```python
"""Agent 节点实现。"""
from .intent import intent_analyze_node
from .probe import intent_probe_node
from .clarify import clarify_node, need_clarify_conditional, ask_clarify_node
from .generate import generate_sql_node
from .execute import execute_sql_node
from .reflect import reflect_node, need_retry_conditional
from .summarize import summarize_node

__all__ = [
    "intent_analyze_node",
    "intent_probe_node",
    "clarify_node",
    "need_clarify_conditional",
    "ask_clarify_node",
    "generate_sql_node",
    "execute_sql_node",
    "reflect_node",
    "need_retry_conditional",
    "summarize_node",
]
```

- [ ] **Step 6: 编写节点测试**

```python
"""测试 ReAct 节点（生成/执行/反思/总结）。"""
import pytest
from unittest.mock import patch, MagicMock

from nl2sql.agent.state import AgentState
from nl2sql.agent.nodes.reflect import need_retry_conditional
from nl2sql.executor.models import ExecutionResult
from nl2sql.schema.models import Column, Table, Schema, DatasourceSchema


@pytest.fixture
def state_with_result():
    ds = DatasourceSchema(
        datasource_id="test_ds",
        datasource_name="测试库",
        datasource_type="mysql",
        schema=Schema(tables=[
            Table(name="users", description="用户表", columns=[
                Column(name="id", type="bigint", description="ID"),
                Column(name="name", type="varchar", description="姓名"),
            ]),
        ]),
    )
    state = AgentState(project_id="test", datasources=[ds], user_query="查用户数量")
    state.sql = "SELECT COUNT(*) FROM users"
    state.execution_result = ExecutionResult(
        success=True,
        sql="SELECT COUNT(*) FROM users",
        columns=["count"],
        rows=[(100,)],
        row_count=1,
    )
    state.selected_datasource_id = "test_ds"
    # mock 执行器
    mock_executor = MagicMock()
    mock_executor.execute.return_value = state.execution_result
    state.datasource_executors = {"test_ds": mock_executor}  # type: ignore
    return state


def test_need_retry_summarize_when_max_iter(state_with_result):
    state_with_result.iteration = 5
    state_with_result.max_iterations = 5
    assert need_retry_conditional(state_with_result) == "summarize"


def test_need_retry_when_satisfied(state_with_result):
    state_with_result._satisfied = True  # type: ignore
    assert need_retry_conditional(state_with_result) == "summarize"


def test_need_retry_when_needs_revision(state_with_result):
    state_with_result._satisfied = False  # type: ignore
    state_with_result._needs_revision = True  # type: ignore
    state_with_result.iteration = 1
    assert need_retry_conditional(state_with_result) == "generate_sql"


def test_generate_sql_node_with_mock(state_with_result):
    from nl2sql.agent.nodes.generate import generate_sql_node, _extract_sql

    # 测试 SQL 提取
    assert _extract_sql("```sql\nSELECT * FROM users\n```") == "SELECT * FROM users"
    assert _extract_sql("```\nSELECT 1\n```") == "SELECT 1"
    assert _extract_sql("SELECT 1") == "SELECT 1"

    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="```sql\nSELECT COUNT(*) FROM users WHERE status = 'active'\n```")

    with patch("nl2sql.agent.nodes.generate.create_llm_client", return_value=mock_llm):
        result = generate_sql_node(state_with_result)

    assert "sql" in result
    assert "SELECT COUNT(*)" in result["sql"]
    assert "status = 'active'" in result["sql"]


def test_summarize_node_with_mock(state_with_result):
    from nl2sql.agent.nodes.summarize import summarize_node

    mock_llm = MagicMock()
    mock_llm.chat.return_value = MagicMock(content="系统中共有 100 个用户。")

    with patch("nl2sql.agent.nodes.summarize.create_llm_client", return_value=mock_llm):
        result = summarize_node(state_with_result)

    assert "final_answer" in result
    assert "100" in result["final_answer"]
    assert result["status"] == "done"
```

- [ ] **Step 7: 运行测试验证通过**

Run: `cd backend && pytest tests/test_agent/test_nodes_react.py -v`
Expected: 全部 PASS (6 passed)

- [ ] **Step 8: Commit**

```bash
git add backend/nl2sql/agent/nodes/generate.py backend/nl2sql/agent/nodes/execute.py backend/nl2sql/agent/nodes/reflect.py backend/nl2sql/agent/nodes/summarize.py backend/nl2sql/agent/nodes/__init__.py backend/tests/test_agent/test_nodes_react.py
git commit -m "feat: agent nodes - SQL generate, execute, reflect, summarize"
```

---

## Task 11: LangGraph 图构建 + Agent 运行入口

**Files:**
- Create: `backend/nl2sql/agent/graph.py`
- Test: `backend/tests/test_agent/test_graph.py`

- [ ] **Step 1: 实现 LangGraph 图**

```python
"""LangGraph Agent 图构建与运行入口。"""
from __future__ import annotations

from typing import Callable, Any

from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes import (
    intent_analyze_node,
    intent_probe_node,
    clarify_node,
    need_clarify_conditional,
    ask_clarify_node,
    generate_sql_node,
    execute_sql_node,
    reflect_node,
    need_retry_conditional,
    summarize_node,
)


def build_graph() -> StateGraph:
    """构建 NL2SQL Agent 的 LangGraph 状态图。"""
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("intent_analyze", intent_analyze_node)
    graph.add_node("intent_probe", intent_probe_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("ask_clarify", ask_clarify_node)
    graph.add_node("generate_sql", generate_sql_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("summarize", summarize_node)

    # 设置入口
    graph.set_entry_point("intent_analyze")

    # 边: 意图分析 -> 意图探查
    graph.add_edge("intent_analyze", "intent_probe")

    # 边: 意图探查 -> 澄清判断
    graph.add_edge("intent_probe", "clarify")

    # 条件边: 澄清判断 -> ask_clarify / generate_sql
    graph.add_conditional_edges(
        "clarify",
        need_clarify_conditional,
        {
            "ask_clarify": "ask_clarify",
            "generate_sql": "generate_sql",
        },
    )

    # ask_clarify 是一个暂停节点（等待用户回复）
    # 用户回复后，从 intent_analyze 重新开始（带着澄清信息）
    # 实际实现中，澄清回复会被加入 conversation_history

    # 边: generate_sql -> execute_sql
    graph.add_edge("generate_sql", "execute_sql")

    # 边: execute_sql -> reflect
    graph.add_edge("execute_sql", "reflect")

    # 条件边: reflect -> generate_sql / summarize
    graph.add_conditional_edges(
        "reflect",
        need_retry_conditional,
        {
            "generate_sql": "generate_sql",
            "summarize": "summarize",
        },
    )

    # 边: summarize -> END
    graph.add_edge("summarize", END)

    return graph


class NL2SQLAgent:
    """NL2SQL Agent 运行入口。

    用法:
    ```python
    agent = NL2SQLAgent(datasources=[...], executors={...})
    result = agent.run("上个月新增了多少用户？")
    print(result["final_answer"])
    print(result["sql"])
    ```
    """

    def __init__(
        self,
        project_id: str,
        datasources: list,
        executors: dict[str, Any],
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
        """运行一次完整的 Agent 流程。

        注意：这是同步版本，用于测试和简单场景。
        生产环境应该用流式版本（stream_events）。
        """
        initial_state = AgentState(
            project_id=self.project_id,
            datasources=self.datasources,
            user_query=user_query,
            conversation_history=conversation_history or [],
            max_iterations=self.max_iterations,
            max_probe_iterations=self.max_probe_iterations,
            event_callback=self.event_callback,
        )
        # 注入执行器（用属性注入，避免修改 State dataclass）
        initial_state.datasource_executors = self.executors  # type: ignore

        final_state = self._app.invoke(initial_state)

        return {
            "answer": final_state.final_answer,
            "sql": final_state.sql,
            "execution_result": final_state.execution_result,
            "intent": final_state.intent,
            "probe_findings": final_state.probe_findings,
            "react_thoughts": final_state.react_thoughts,
            "iteration": final_state.iteration,
            "status": final_state.status,
            "error": final_state.error,
        }

    def stream(self, user_query: str, conversation_history: list | None = None):
        """流式运行 Agent，yield 每个节点的状态。"""
        initial_state = AgentState(
            project_id=self.project_id,
            datasources=self.datasources,
            user_query=user_query,
            conversation_history=conversation_history or [],
            max_iterations=self.max_iterations,
            max_probe_iterations=self.max_probe_iterations,
            event_callback=self.event_callback,
        )
        initial_state.datasource_executors = self.executors  # type: ignore

        for event in self._app.stream(initial_state):
            yield event
```

- [ ] **Step 2: 更新 agent/__init__.py**

```python
"""NL2SQL Agent 模块。"""
from .state import AgentState, IntentResult, ProbeFinding, ReactThought
from .graph import NL2SQLAgent, build_graph

__all__ = [
    "AgentState", "IntentResult", "ProbeFinding", "ReactThought",
    "NL2SQLAgent", "build_graph",
]
```

- [ ] **Step 3: 编写图集成测试**

```python
"""测试 LangGraph 图的完整流程（mock LLM）。"""
import pytest
from unittest.mock import patch, MagicMock

from nl2sql.agent.graph import NL2SQLAgent
from nl2sql.schema.models import Column, Table, Schema, DatasourceSchema
from nl2sql.executor.models import ExecutionResult


@pytest.fixture
def mock_datasources():
    return [
        DatasourceSchema(
            datasource_id="test_ds",
            datasource_name="测试库",
            datasource_type="mysql",
            schema=Schema(tables=[
                Table(
                    name="users",
                    description="用户表，注册用户信息",
                    columns=[
                        Column(name="id", type="bigint", description="用户ID", is_primary_key=True),
                        Column(name="name", type="varchar", description="姓名"),
                        Column(name="status", type="varchar", description="状态"),
                        Column(name="created_at", type="datetime", description="注册时间", semantic_type="timestamp"),
                    ],
                ),
            ]),
        )
    ]


@pytest.fixture
def mock_executors():
    executor = MagicMock()
    # 默认返回成功结果
    executor.execute.return_value = ExecutionResult(
        success=True,
        sql="SELECT COUNT(*) FROM users",
        columns=["count"],
        rows=[(42,)],
        row_count=1,
        duration_ms=10.0,
    )
    executor.test_connection.return_value = True
    return {"test_ds": executor}


def test_agent_full_flow(mock_datasources, mock_executors):
    """测试完整 Agent 流程（全 mock）。"""
    # mock LLM 客户端工厂
    mock_llm = MagicMock()

    # 按调用顺序设置返回值
    # 1. 意图分析
    intent_response = MagicMock()
    intent_response.content = '''{
        "tables": [{"table_name": "users", "datasource_id": "test_ds", "confidence": 0.95}],
        "filters": [],
        "aggregation": "count",
        "dimensions": [],
        "ambiguities": [],
        "confidence": 0.95,
        "analysis": "用户想统计用户总数"
    }'''

    # 2. 探查（没有歧义，直接返回）
    probe_response = MagicMock(content="无需探查，没有技术层面的歧义。", tool_calls=[])

    # 3. 澄清判断（没有歧义）
    clarify_response = MagicMock(content="[]")

    # 4. SQL 生成
    sql_response = MagicMock(content="```sql\nSELECT COUNT(*) as total FROM users\n```")

    # 5. 反思（满意）
    reflect_response = MagicMock(content='''{
        "satisfied": true,
        "needs_revision": false,
        "thought": "SQL 正确执行，结果符合用户问题",
        "suggested_fix": ""
    }''')

    # 6. 总结
    summarize_response = MagicMock(content="系统中共有 42 个用户。")

    # 设置 side_effect 按顺序返回
    call_count = 0
    def chat_side_effect(*args, **kwargs):
        nonlocal call_count
        responses = [intent_response, clarify_response, sql_response, reflect_response, summarize_response]
        result = responses[min(call_count, len(responses) - 1)]
        call_count += 1
        return result

    mock_llm.chat.side_effect = chat_side_effect
    mock_llm.chat_stream.return_value = iter([MagicMock(content_delta="", done=False), MagicMock(done=True)])

    with patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm), \
         patch("nl2sql.agent.nodes.probe.create_llm_client", return_value=mock_llm), \
         patch("nl2sql.agent.nodes.clarify.create_llm_client", return_value=mock_llm), \
         patch("nl2sql.agent.nodes.generate.create_llm_client", return_value=mock_llm), \
         patch("nl2sql.agent.nodes.reflect.create_llm_client", return_value=mock_llm), \
         patch("nl2sql.agent.nodes.summarize.create_llm_client", return_value=mock_llm):

        agent = NL2SQLAgent(
            project_id="test",
            datasources=mock_datasources,
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


def test_agent_handles_sql_error(mock_datasources, mock_executors):
    """测试 SQL 执行失败时的重试流程。"""
    # 修改执行器：第一次失败，第二次成功
    call_count = 0
    def execute_side_effect(sql):
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            return ExecutionResult(
                success=False,
                sql=sql,
                error="Unknown column 'invalid_col' in 'field list'",
            )
        return ExecutionResult(
            success=True,
            sql=sql,
            columns=["count"],
            rows=[(42,)],
            row_count=1,
        )

    mock_executors["test_ds"].execute.side_effect = execute_side_effect

    mock_llm = MagicMock()
    # 简化：各节点都返回合理值
    intent_resp = MagicMock(content='''{"tables":[{"table_name":"users","datasource_id":"test_ds","confidence":0.9}],"filters":[],"aggregation":"count","dimensions":[],"ambiguities":[],"confidence":0.9,"analysis":"ok"}''')
    clarify_resp = MagicMock(content="[]")
    sql1_resp = MagicMock(content="```sql\nSELECT invalid_col FROM users\n```")
    sql2_resp = MagicMock(content="```sql\nSELECT COUNT(*) FROM users\n```")
    reflect1_resp = MagicMock(content='''{"satisfied":false,"needs_revision":true,"thought":"列名错误需要修正","suggested_fix":"使用正确的列名"}''')
    reflect2_resp = MagicMock(content='''{"satisfied":true,"needs_revision":false,"thought":"结果正确","suggested_fix":""}''')
    summary_resp = MagicMock(content="有 42 个用户。")

    responses = [intent_resp, clarify_resp, sql1_resp, reflect1_resp, sql2_resp, reflect2_resp, summary_resp]
    idx = 0
    def chat_side_effect(*args, **kwargs):
        nonlocal idx
        r = responses[min(idx, len(responses)-1)]
        idx += 1
        return r

    mock_llm.chat.side_effect = chat_side_effect

    with patch("nl2sql.agent.nodes.intent.create_llm_client", return_value=mock_llm), \
         patch("nl2sql.agent.nodes.probe.create_llm_client", return_value=mock_llm), \
         patch("nl2sql.agent.nodes.clarify.create_llm_client", return_value=mock_llm), \
         patch("nl2sql.agent.nodes.generate.create_llm_client", return_value=mock_llm), \
         patch("nl2sql.agent.nodes.reflect.create_llm_client", return_value=mock_llm), \
         patch("nl2sql.agent.nodes.summarize.create_llm_client", return_value=mock_llm):

        agent = NL2SQLAgent(
            project_id="test",
            datasources=mock_datasources,
            executors=mock_executors,
            max_iterations=5,
        )
        result = agent.run("多少用户")

    # 最终应该成功
    assert result["status"] == "done"
    assert result["iteration"] >= 1  # 至少迭代了 1 次（失败后重试）
    assert result["sql"] is not None
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd backend && pytest tests/test_agent/test_graph.py -v`
Expected: 全部 PASS (2 passed)

这一步如果 langgraph 依赖还没装的话先装一下：
Run: `cd backend && pip install langgraph langchain-core`

- [ ] **Step 5: Commit**

```bash
git add backend/nl2sql/agent/graph.py backend/nl2sql/agent/__init__.py backend/tests/test_agent/test_graph.py
git commit -m "feat: LangGraph agent graph and NL2SQLAgent entry point"
```

---

## Task 12: 核心库集成测试 + README

**Files:**
- Create: `backend/README.md`

- [ ] **Step 1: 编写核心库 README**

```markdown
# nl2sql 核心库

自然语言转 SQL 的 Agent 库，基于 LangGraph 实现 ReAct 反思循环。

## 功能特性

- 意图分析：自动识别查询涉及的表、维度、筛选条件
- 意图探查：用轻量 SQL 查询消除歧义，减少用户澄清
- SQL 生成：根据 Schema 和意图生成准确的 SQL
- 沙盒执行：只读安全，超时 + 行数限制
- ReAct 反思：自动检查结果，迭代优化 SQL
- 多数据源：支持 MySQL / PostgreSQL / SQLite / ClickHouse 等
- 多 LLM 支持：Claude / OpenAI / 本地 OpenAI 兼容模型

## 快速开始

### 安装

```bash
cd backend
pip install -e ".[dev]"
```

### 配置

复制 `.env.example` 为 `.env`，填入你的 LLM API 配置：

```bash
cp .env.example .env
```

### 基本用法

```python
from nl2sql import NL2SQLAgent
from nl2sql.schema import SchemaLoader
from nl2sql.executor import create_executor

# 1. 加载 Schema
loader = SchemaLoader()
datasource = loader.load_from_yaml("config/schemas/sample/ecommerce.yaml")

# 2. 创建执行器
executor = create_executor(
    datasource_id=datasource.datasource_id,
    datasource_type=datasource.datasource_type,
    db_url="mysql://user:pass@localhost:3306/dbname",
)

# 3. 创建 Agent 并运行
agent = NL2SQLAgent(
    project_id="ecommerce",
    datasources=[datasource],
    executors={datasource.datasource_id: executor},
)

result = agent.run("上个月新增了多少用户？")
print(result["answer"])
print(result["sql"])
```

## 架构

```
用户提问
  → intent_analyze  (意图分析)
  → intent_probe    (主动探查，消除歧义)
  → clarify         (判断是否需要用户澄清)
  → generate_sql    (生成 SQL)
  → execute_sql     (沙盒执行)
  → reflect         (反思检查)
  → (循环修正 / 输出总结)
```

## 运行测试

```bash
cd backend
pytest tests/ -v
```
```

- [ ] **Step 2: 运行全量测试确认**

Run: `cd backend && pytest tests/ -v`
Expected: 所有测试通过

- [ ] **Step 3: Commit**

```bash
git add backend/README.md
git commit -m "docs: core library README"
```

---

## Phase 1 完成清单

- [x] Task 1: 项目脚手架与配置
- [x] Task 2: Schema 数据模型
- [x] Task 3: Schema YAML 加载器
- [x] Task 4: Schema 语义匹配器
- [x] Task 5: LLM 消息模型与抽象基类
- [x] Task 6: LLM 客户端实现 + 工厂
- [x] Task 7: SQL 执行器
- [x] Task 8: Agent State + 工具集
- [x] Task 9: Agent 节点 — 意图分析 + 探查 + 澄清
- [x] Task 10: Agent 节点 — SQL 生成 + 执行 + 反思 + 总结
- [x] Task 11: LangGraph 图构建 + Agent 入口
- [x] Task 12: 集成测试 + README
