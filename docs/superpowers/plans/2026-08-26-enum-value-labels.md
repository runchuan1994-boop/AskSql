# 枚举值多语言标签（Value Labels）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为数据库中的低基数枚举列生成多语言（中英）显示标签，在前端表格和图表中根据用户语言和开关状态展示翻译值，提升非技术用户的数据可读性。

**Architecture:**
- Schema 层：Column 模型新增 `value_labels` 字段（`dict[lang, dict[value, label]]`），持久化到 YAML
- Profiling 层：SchemaProfiler 探测后，对符合条件的低基数类别列调用 LLM 批量生成中文标签
- API 层：聊天结果响应附带 `translations` 字典（`table.column -> lang -> value -> label`）
- 前端层：新增全局"显示翻译值"开关，表格和图表组件根据开关 + 当前语言渲染枚举值

**Tech Stack:** Python 3.12 + Pydantic + FastAPI + LLM Client, React 18 + TypeScript + Recharts + @tanstack/react-table

---

## 任务清单

---

## Task 1: Column 模型新增 value_labels 字段

**Files:**
- Modify: `backend/nl2sql/schema/models.py:31`
- Modify: `backend/nl2sql/schema/profiler.py:338`
- Modify: `backend/nl2sql/schema/loader.py` (验证自动解析)
- Test: `backend/tests/test_schema/test_models.py`

### Step 1: 编写测试 — 验证 value_labels 默认值和结构

在 `backend/tests/test_schema/test_models.py` 末尾添加：

```python
def test_column_value_labels_default():
    """value_labels 默认是空 dict。"""
    col = Column(name="status", type="varchar")
    assert col.value_labels == {}


def test_column_value_labels_structure():
    """value_labels 结构: {lang: {value: label}}。"""
    col = Column(
        name="status",
        type="varchar",
        value_labels={
            "zh-CN": {"active": "活跃", "inactive": "未激活"},
        },
    )
    assert col.value_labels["zh-CN"]["active"] == "活跃"
    assert col.value_labels["zh-CN"]["inactive"] == "未激活"


def test_column_model_dump_includes_value_labels():
    """model_dump 输出包含 value_labels。"""
    col = Column(
        name="status",
        type="varchar",
        value_labels={"zh-CN": {"active": "活跃"}},
    )
    data = col.model_dump()
    assert "value_labels" in data
    assert data["value_labels"]["zh-CN"]["active"] == "活跃"
```

### Step 2: 运行测试，验证失败

Run: `cd backend && python -m pytest tests/test_schema/test_models.py::test_column_value_labels_default -v`
Expected: FAIL with `AttributeError: 'Column' object has no attribute 'value_labels'`

### Step 3: 实现 — Column 新增 value_labels 字段

在 `backend/nl2sql/schema/models.py` 的 `Column` 类中，在 `calc_formula` 字段后面（第 31 行之后）添加：

```python
    value_labels: dict[str, dict[str, str]] = Field(default_factory=dict)
    # 枚举值多语言标签：{ "zh-CN": { "active": "活跃", "pending": "待处理" }, "en": { ... } }
```

### Step 4: 运行测试，验证通过

Run: `cd backend && python -m pytest tests/test_schema/test_models.py::test_column_value_labels_default tests/test_schema/test_models.py::test_column_value_labels_structure tests/test_schema/test_models.py::test_column_model_dump_includes_value_labels -v`
Expected: 3 passed

### Step 5: 验证 YAML 序列化 — 修改 write_profile_to_yaml

在 `backend/nl2sql/schema/profiler.py` 的 `write_profile_to_yaml` 函数中，在 `col.null_rate` 写入之后（第 347 行之后）添加：

```python
            if col.value_labels:
                col_dict["value_labels"] = col.value_labels
```

### Step 6: 编写 YAML 读写测试

在 `backend/tests/test_schema/test_profiler.py` 末尾添加：

```python
def test_write_profile_to_yaml_includes_value_labels():
    """write_profile_to_yaml 输出包含 value_labels 字段。"""
    ds = DatasourceSchema(
        datasource_id="test",
        datasource_name="test",
        datasource_type="sqlite",
        db_schema=Schema(tables=[
            Table(name="orders", columns=[
                Column(
                    name="status",
                    type="varchar",
                    enum_values=["pending", "paid", "shipped"],
                    value_labels={
                        "zh-CN": {"pending": "待支付", "paid": "已支付", "shipped": "已发货"},
                    },
                ),
            ]),
        ]),
    )
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        filepath = f.name
    try:
        write_profile_to_yaml(ds, filepath)
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        assert "value_labels" in content
        assert "待支付" in content
        assert "zh-CN" in content
    finally:
        os.unlink(filepath)
```

### Step 7: 运行 YAML 测试

Run: `cd backend && python -m pytest tests/test_schema/test_profiler.py::test_write_profile_to_yaml_includes_value_labels -v`
Expected: PASS

### Step 8: 验证 YAML 加载（loader 自动解析）

在 `backend/tests/test_schema/test_loader.py` 末尾添加：

```python
def test_loader_loads_value_labels_from_yaml():
    """SchemaLoader 能从 YAML 中正确解析 value_labels。"""
    yaml_content = """
datasource:
  id: test-ds
  name: Test
  type: sqlite
tables:
  - name: orders
    columns:
      - name: status
        type: varchar
        enum_values: [pending, paid]
        value_labels:
          zh-CN:
            pending: 待支付
            paid: 已支付
"""
    import tempfile, os
    from nl2sql.schema.loader import SchemaLoader
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w", encoding="utf-8") as f:
        f.write(yaml_content)
        filepath = f.name
    try:
        loader = SchemaLoader()
        ds = loader.load_from_yaml(filepath)
        table = ds.db_schema.get_table("orders")
        assert table is not None
        col = table.get_column("status")
        assert col is not None
        assert "zh-CN" in col.value_labels
        assert col.value_labels["zh-CN"]["pending"] == "待支付"
        assert col.value_labels["zh-CN"]["paid"] == "已支付"
    finally:
        os.unlink(filepath)
```

Run: `cd backend && python -m pytest tests/test_schema/test_loader.py::test_loader_loads_value_labels_from_yaml -v`
Expected: PASS（Pydantic 模型自动解析 dict 字段）

### Step 9: 提交

```bash
git add backend/nl2sql/schema/models.py backend/nl2sql/schema/profiler.py \
  backend/tests/test_schema/test_models.py \
  backend/tests/test_schema/test_profiler.py \
  backend/tests/test_schema/test_loader.py
git commit -m "feat(schema): add value_labels field to Column model for multilingual enum labels"
```

---

## Task 2: EnumLabelGenerator — LLM 生成枚举标签服务

**Files:**
- Create: `backend/nl2sql/schema/label_generator.py`
- Test: `backend/tests/test_schema/test_label_generator.py`

### Step 1: 编写测试 — 生成器接口和解析逻辑

创建 `backend/tests/test_schema/test_label_generator.py`：

```python
"""测试枚举值标签生成器。"""

from __future__ import annotations

import pytest

from nl2sql.schema.label_generator import (
    EnumLabelGenerator,
    _parse_label_response,
    _build_label_prompt,
)


class DummyLLMClient:
    """模拟 LLM 客户端，返回预设响应。"""

    def __init__(self, response_content: str):
        self._response = response_content
        self.last_messages = None
        self.last_temperature = None

    def chat(self, messages, tools=None, temperature=0.0, max_tokens=4096):
        from nl2sql.llm.base import ChatResponse
        self.last_messages = messages
        self.last_temperature = temperature
        return ChatResponse(content=self._response, model="dummy", usage={})


def test_parse_label_response_valid_json():
    """正确解析 JSON 格式的标签响应。"""
    content = '''```json
{
  "pending": "待支付",
  "paid": "已支付",
  "shipped": "已发货",
  "completed": "已完成",
  "cancelled": "已取消"
}
```'''
    result = _parse_label_response(content)
    assert result["pending"] == "待支付"
    assert result["paid"] == "已支付"
    assert len(result) == 5


def test_parse_label_response_plain_json():
    """没有代码块包裹的纯 JSON 也能解析。"""
    content = '{"active": "活跃", "inactive": "未激活"}'
    result = _parse_label_response(content)
    assert result["active"] == "活跃"
    assert result["inactive"] == "未激活"


def test_parse_label_response_invalid():
    """无法解析时返回空 dict。"""
    result = _parse_label_response("some random text")
    assert result == {}


def test_build_label_prompt_includes_values_and_context():
    """提示词包含列名、列描述和枚举值。"""
    prompt = _build_label_prompt(
        table_name="orders",
        column_name="status",
        column_description="订单状态",
        values=["pending", "paid", "shipped"],
        target_language="zh-CN",
    )
    assert "orders" in prompt
    assert "status" in prompt
    assert "订单状态" in prompt
    assert "pending" in prompt
    assert "zh-CN" in prompt or "中文" in prompt


def test_generator_generate_labels_for_column():
    """EnumLabelGenerator 为单列生成标签。"""
    llm = DummyLLMClient('{"active": "活跃", "inactive": "未激活"}')
    gen = EnumLabelGenerator(llm)
    result = gen.generate_for_column(
        table_name="users",
        column_name="status",
        column_description="用户状态",
        values=["active", "inactive"],
        target_language="zh-CN",
    )
    assert result["active"] == "活跃"
    assert result["inactive"] == "未激活"
    # 验证调用了 LLM
    assert llm.last_messages is not None
    assert llm.last_temperature == 0.3


def test_generator_generate_labels_batch():
    """EnumLabelGenerator 批量为多列生成标签。"""
    llm = DummyLLMClient(
        '{"status": {"active": "活跃", "inactive": "未激活"}, '
        '"gender": {"male": "男", "female": "女"}}'
    )
    gen = EnumLabelGenerator(llm)
    columns = [
        {"table": "users", "column": "status", "description": "用户状态",
         "values": ["active", "inactive"]},
        {"table": "users", "column": "gender", "description": "性别",
         "values": ["male", "female"]},
    ]
    result = gen.generate_batch(columns, target_language="zh-CN")
    assert "users.status" in result
    assert "users.gender" in result
    assert result["users.status"]["active"] == "活跃"
```

### Step 2: 运行测试，验证失败

Run: `cd backend && python -m pytest tests/test_schema/test_label_generator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nl2sql.schema.label_generator'`

### Step 3: 实现 — EnumLabelGenerator

创建 `backend/nl2sql/schema/label_generator.py`：

```python
"""枚举值多语言标签生成器。

使用 LLM 为低基数枚举列生成多语言显示标签。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from nl2sql.llm.base import LLMClient

logger = logging.getLogger(__name__)


# 翻译阈值：单个列最多翻译多少个枚举值
MAX_VALUES_PER_COLUMN = 50


def _build_label_prompt(
    table_name: str,
    column_name: str,
    column_description: str,
    values: list[str],
    target_language: str,
) -> str:
    """构建生成标签的提示词。"""
    lang_name = "简体中文" if target_language == "zh-CN" else target_language
    desc = column_description or "无描述"
    values_list = "\n".join(f"- {v}" for v in values)

    return f"""你是一个数据字段翻译专家。请将下面数据库列的枚举值翻译成{lang_name}。

表名：{table_name}
列名：{column_name}
列描述：{desc}

枚举值列表：
{values_list}

要求：
1. 输出严格的 JSON 格式，key 是原始枚举值，value 是翻译后的标签
2. 翻译要符合业务场景的常用表达，不要字面上直译
3. 保持简洁，标签长度尽量不超过 6 个汉字（或等效长度）
4. 不要输出任何解释文字，只输出 JSON
5. 如果某个值不需要翻译（如纯数字、缩写等），value 等于原值即可

JSON 格式示例：
{{
  "pending": "待支付",
  "paid": "已支付"
}}"""


def _parse_label_response(content: str) -> dict[str, str]:
    """从 LLM 响应中解析 JSON 标签字典。"""
    # 尝试提取代码块中的 JSON
    code_block_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", content, re.DOTALL)
    if code_block_match:
        content = code_block_match.group(1).strip()

    try:
        data = json.loads(content)
        if isinstance(data, dict):
            # 确保所有 value 都是字符串
            return {str(k): str(v) for k, v in data.items()}
    except json.JSONDecodeError:
        logger.warning("Failed to parse label response as JSON: %s", content[:200])

    return {}


class EnumLabelGenerator:
    """枚举值标签生成器。"""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def generate_for_column(
        self,
        table_name: str,
        column_name: str,
        column_description: str,
        values: list[str],
        target_language: str = "zh-CN",
    ) -> dict[str, str]:
        """为单列生成标签。

        Args:
            table_name: 表名
            column_name: 列名
            column_description: 列描述
            values: 枚举值列表
            target_language: 目标语言代码

        Returns:
            {原值: 标签} 字典
        """
        if not values:
            return {}

        # 截断过多的值
        values = values[:MAX_VALUES_PER_COLUMN]

        prompt = _build_label_prompt(
            table_name, column_name, column_description, values, target_language
        )
        from nl2sql.llm.message import Message, MessageRole

        messages = [
            Message(role=MessageRole.SYSTEM, content="你是一个专业的数据字段翻译专家。"),
            Message(role=MessageRole.USER, content=prompt),
        ]

        try:
            response = self.llm.chat(messages, temperature=0.3, max_tokens=2000)
            return _parse_label_response(response.content)
        except Exception as e:
            logger.warning(
                "Failed to generate labels for %s.%s: %s", table_name, column_name, e
            )
            return {}

    def generate_batch(
        self,
        columns: list[dict[str, Any]],
        target_language: str = "zh-CN",
    ) -> dict[str, dict[str, str]]:
        """批量为多列生成标签。

        Args:
            columns: 列信息列表，每项包含 table/column/description/values
            target_language: 目标语言代码

        Returns:
            {"table.column": {原值: 标签}} 字典
        """
        results: dict[str, dict[str, str]] = {}

        for col_info in columns:
            key = f"{col_info['table']}.{col_info['column']}"
            labels = self.generate_for_column(
                table_name=col_info["table"],
                column_name=col_info["column"],
                column_description=col_info.get("description", ""),
                values=col_info.get("values", []),
                target_language=target_language,
            )
            if labels:
                results[key] = labels

        return results
```

### Step 4: 运行测试，验证通过

Run: `cd backend && python -m pytest tests/test_schema/test_label_generator.py -v`
Expected: 6 passed

### Step 5: 提交

```bash
git add backend/nl2sql/schema/label_generator.py backend/tests/test_schema/test_label_generator.py
git commit -m "feat(schema): add EnumLabelGenerator for LLM-based enum value translation"
```

---

## Task 3: 集成到 SchemaProfiler — profiling 阶段自动生成标签

**Files:**
- Modify: `backend/nl2sql/schema/profiler.py`
- Modify: `backend/app/services/profiling_service.py`
- Test: `backend/tests/test_schema/test_profiler.py`

### Step 1: 编写测试 — 翻译列识别 + 生成集成

在 `backend/tests/test_schema/test_profiler.py` 末尾添加：

```python
def test_generate_labels_integrates_with_profiler():
    """SchemaProfiler 能在探测后为类别列生成标签。"""
    # 准备 mock executor
    executor = MockExecutor()
    executor.register_handler(
        lambda sql: "COUNT(*)" in sql and "orders" in sql,
        lambda sql: MockExecutionResult(rows=[[1000]], columns=["cnt"], row_count=1, success=True)
    )
    executor.register_handler(
        lambda sql: "COUNT(DISTINCT" in sql and "status" in sql,
        lambda sql: MockExecutionResult(rows=[[5]], columns=["cnt"], row_count=1, success=True)
    )
    executor.register_handler(
        lambda sql: "GROUP BY" in sql and "status" in sql,
        lambda sql: MockExecutionResult(
            rows=[
                ["pending", 400],
                ["paid", 300],
                ["shipped", 200],
                ["completed", 80],
                ["cancelled", 20],
            ],
            columns=["status", "cnt"],
            row_count=5,
            success=True,
        )
    )
    executor.register_handler(
        lambda sql: "LIMIT" in sql and "orders" in sql,
        lambda sql: MockExecutionResult(
            rows=[["1", "pending"]],
            columns=["id", "status"],
            row_count=1,
            success=True,
        )
    )

    profiler = SchemaProfiler(executor, sample_row_count=1)
    table = Table(
        name="orders",
        columns=[
            Column(name="id", type="int", is_primary_key=True),
            Column(name="status", type="varchar", semantic_type="category",
                   enum_values=["pending", "paid", "shipped", "completed", "cancelled"]),
        ],
    )
    profiler.profile_table(table)

    # 验证 top_values 已生成
    status_col = table.get_column("status")
    assert status_col is not None
    assert status_col.top_values
    assert len(status_col.top_values) == 5

    # 初始 value_labels 为空
    assert status_col.value_labels == {}
```

### Step 2: 运行测试，验证通过（这是基线测试）

Run: `cd backend && python -m pytest tests/test_schema/test_profiler.py::test_generate_labels_integrates_with_profiler -v`
Expected: PASS

### Step 3: 编写 generate_labels 方法测试

在 `backend/tests/test_schema/test_profiler.py` 中添加：

```python
def test_generate_labels_for_table_calls_llm():
    """generate_labels_for_table 为符合条件的列调用 LLM 生成标签。"""
    from nl2sql.schema.label_generator import EnumLabelGenerator

    class DummyLLM:
        def __init__(self):
            self.call_count = 0

        def chat(self, messages, tools=None, temperature=0.0, max_tokens=4096):
            from nl2sql.llm.base import ChatResponse
            self.call_count += 1
            return ChatResponse(
                content='{"pending": "待支付", "paid": "已支付", "shipped": "已发货"}',
                model="dummy",
                usage={},
            )

    table = Table(
        name="orders",
        columns=[
            Column(name="id", type="int", is_primary_key=True),
            Column(
                name="status",
                type="varchar",
                semantic_type="category",
                distinct_count=3,
                top_values=[
                    {"value": "pending", "count": 100, "ratio": 0.5},
                    {"value": "paid", "count": 60, "ratio": 0.3},
                    {"value": "shipped", "count": 40, "ratio": 0.2},
                ],
            ),
            # 高基数列，不应生成标签
            Column(
                name="city",
                type="varchar",
                semantic_type="category",
                distinct_count=200,
                top_values=[],
            ),
            # 数值列，不应生成标签
            Column(
                name="amount",
                type="decimal",
                semantic_type="amount",
                distinct_count=50,
            ),
        ],
    )

    llm = DummyLLM()
    generator = EnumLabelGenerator(llm)

    from nl2sql.schema.profiler import generate_labels_for_table

    generate_labels_for_table(table, generator, target_language="zh-CN")

    # 只有 status 列应该生成了标签
    status_col = table.get_column("status")
    assert status_col is not None
    assert "zh-CN" in status_col.value_labels
    assert status_col.value_labels["zh-CN"]["pending"] == "待支付"

    # city 列（高基数）不生成
    city_col = table.get_column("city")
    assert city_col is not None
    assert city_col.value_labels == {}

    # amount 列（数值型）不生成
    amount_col = table.get_column("amount")
    assert amount_col is not None
    assert amount_col.value_labels == {}

    # LLM 只被调用一次（只有 status 列符合条件）
    assert llm.call_count == 1
```

### Step 4: 运行测试，验证失败

Run: `cd backend && python -m pytest tests/test_schema/test_profiler.py::test_generate_labels_for_table_calls_llm -v`
Expected: FAIL with `ImportError: cannot import name 'generate_labels_for_table'`

### Step 5: 实现 — profiler.py 中新增函数和常量

在 `backend/nl2sql/schema/profiler.py` 顶部常量区域（第 20 行之后）添加：

```python
# 生成翻译标签的 distinct_count 阈值（超过此值的列不生成翻译）
_LABEL_GENERATION_THRESHOLD = 50
```

在 `backend/nl2sql/schema/profiler.py` 末尾（`write_profile_to_yaml` 函数之后）添加：

```python
# 生成翻译标签需要的列条件
def _should_generate_labels(col: Column) -> bool:
    """判断一个列是否应该生成翻译标签。

    条件：
    1. 是类别列
    2. distinct_count 在阈值范围内（0 < count <= _LABEL_GENERATION_THRESHOLD）
    3. 有 top_values 或 enum_values（有值可翻译）
    4. 该语言尚未生成过 value_labels
    """
    if not _is_category_column(col):
        return False
    if col.distinct_count is None or col.distinct_count == 0:
        return False
    if col.distinct_count > _LABEL_GENERATION_THRESHOLD:
        return False
    if not col.top_values and not col.enum_values:
        return False
    return True


def _collect_label_values(col: Column) -> list[str]:
    """收集列中需要翻译的值，优先用 enum_values，否则用 top_values。"""
    if col.enum_values:
        return list(col.enum_values)
    return [tv["value"] for tv in col.top_values if tv.get("value") is not None]


def generate_labels_for_table(
    table: Table,
    label_generator: Any,
    target_language: str = "zh-CN",
) -> None:
    """为表中符合条件的列生成翻译标签。

    Args:
        table: 表对象（原地修改 value_labels）
        label_generator: EnumLabelGenerator 实例
        target_language: 目标语言代码
    """
    # 收集需要生成标签的列
    columns_to_label = []
    for col in table.columns:
        if not _should_generate_labels(col):
            continue
        # 如果该语言已有标签，跳过（避免重复生成）
        if target_language in col.value_labels and col.value_labels[target_language]:
            continue
        values = _collect_label_values(col)
        if not values:
            continue
        columns_to_label.append({
            "table": table.name,
            "column": col.name,
            "description": col.description or col.business_name,
            "values": values,
        })

    if not columns_to_label:
        return

    # 逐列生成（单列提示词质量更好，且单列失败不影响其他列）
    for col_info in columns_to_label:
        col = table.get_column(col_info["column"])
        if col is None:
            continue
        labels = label_generator.generate_for_column(
            table_name=col_info["table"],
            column_name=col_info["column"],
            column_description=col_info["description"],
            values=col_info["values"],
            target_language=target_language,
        )
        if labels:
            if target_language not in col.value_labels:
                col.value_labels[target_language] = {}
            col.value_labels[target_language].update(labels)
            logger.info(
                "Generated %d labels for %s.%s (%s)",
                len(labels), table.name, col.name, target_language,
            )
```

### Step 6: 运行测试，验证通过

Run: `cd backend && python -m pytest tests/test_schema/test_profiler.py::test_generate_labels_for_table_calls_llm -v`
Expected: PASS

### Step 7: 集成到 profiling_service.py

在 `backend/app/services/profiling_service.py` 中，找到 `_run_profiling` 函数，在 `write_profile_to_yaml` 调用之前添加标签生成步骤。

先查看现有结构确认位置：
需要在 profile_table 循环完成后、write_profile_to_yaml 之前插入：

```python
    # 6. 生成枚举值翻译标签
    try:
        from nl2sql.llm.factory import create_llm_client
        from nl2sql.schema.label_generator import EnumLabelGenerator
        from nl2sql.schema.profiler import generate_labels_for_table

        llm_client = create_llm_client()
        label_gen = EnumLabelGenerator(llm_client)

        for table in ds_schema.db_schema.tables:
            try:
                generate_labels_for_table(table, label_gen, target_language="zh-CN")
            except Exception as e:
                logger.warning("Generating labels for table %s failed: %s", table.name, e)

        _update_profiling_progress(datasource_id, "generating_labels", 0.9)
    except Exception as e:
        logger.warning("Label generation skipped: %s", e)
```

（注意：这一步的精确插入位置需要根据 profiling_service.py 的实际代码行号调整，核心是在写 YAML 之前执行。）

### Step 8: 运行现有 profiling 测试确保不破坏

Run: `cd backend && python -m pytest tests/test_schema/test_profiler.py -v`
Expected: All tests pass

### Step 9: 提交

```bash
git add backend/nl2sql/schema/profiler.py backend/app/services/profiling_service.py \
  backend/tests/test_schema/test_profiler.py
git commit -m "feat(schema): integrate enum label generation into profiling pipeline"
```

---

## Task 4: 聊天 API 返回翻译字典

**Files:**
- Modify: `backend/app/services/chat_service.py`
- Test: `backend/tests/test_chat/test_translations.py`（新建）

### Step 1: 编写测试 — 翻译字典收集

创建 `backend/tests/test_chat/test_translations.py`（如果目录不存在，先创建 `__init__.py`）：

```python
"""测试聊天结果中的翻译字典。"""

from __future__ import annotations

import pytest

from nl2sql.schema.models import Column, DatasourceSchema, Schema, Table


def _make_test_schema():
    return DatasourceSchema(
        datasource_id="ds1",
        datasource_name="test",
        datasource_type="sqlite",
        db_schema=Schema(tables=[
            Table(name="orders", columns=[
                Column(
                    name="status",
                    type="varchar",
                    semantic_type="category",
                    value_labels={
                        "zh-CN": {"pending": "待支付", "paid": "已支付", "shipped": "已发货"},
                    },
                ),
                Column(
                    name="order_type",
                    type="varchar",
                    semantic_type="category",
                    value_labels={
                        "zh-CN": {"normal": "普通", "return": "退货", "exchange": "换货"},
                    },
                ),
                Column(name="amount", type="decimal", semantic_type="amount"),
            ]),
            Table(name="users", columns=[
                Column(
                    name="status",
                    type="varchar",
                    semantic_type="category",
                    value_labels={
                        "zh-CN": {"active": "活跃", "inactive": "未激活"},
                    },
                ),
            ]),
        ]),
    )


def test_collect_translations_for_columns():
    """根据查询结果的列名，从 schema 中收集对应的翻译字典。"""
    from app.services.chat_service import _collect_translations

    ds_schema = _make_test_schema()

    # 模拟查询结果：从 orders 表查 status 和 amount
    result_columns = ["status", "amount"]
    translations = _collect_translations(ds_schema, result_columns, language="zh-CN")

    # status 有翻译
    assert "status" in translations
    assert translations["status"]["pending"] == "待支付"
    assert translations["status"]["paid"] == "已支付"

    # amount 是数值列，没有翻译
    assert "amount" not in translations

    # 只返回结果中出现的列（users.status 不在结果中，不返回）
    assert len(translations) == 1


def test_collect_translations_unknown_column():
    """结果中有 schema 里找不到的列时，跳过。"""
    from app.services.chat_service import _collect_translations

    ds_schema = _make_test_schema()
    translations = _collect_translations(ds_schema, ["unknown_col"], language="zh-CN")
    assert translations == {}


def test_collect_translations_no_labels_for_language():
    """请求的语言没有翻译时，返回空。"""
    from app.services.chat_service import _collect_translations

    ds_schema = _make_test_schema()
    translations = _collect_translations(ds_schema, ["status"], language="en")
    # en 语言下没有翻译（原值就是英文）
    assert translations == {} or "status" not in translations or translations.get("status") == {}
```

### Step 2: 运行测试，验证失败

Run: `cd backend && python -m pytest tests/test_chat/test_translations.py -v`
Expected: FAIL with `ImportError` or `AttributeError`

### Step 3: 实现 — _collect_translations 函数

在 `backend/app/services/chat_service.py` 中添加辅助函数：

```python
def _collect_translations(
    ds_schema: DatasourceSchema,
    result_columns: list[str],
    language: str = "zh-CN",
) -> dict[str, dict[str, str]]:
    """从 schema 中收集查询结果列的翻译字典。

    Args:
        ds_schema: 数据源 schema
        result_columns: 查询结果的列名列表
        language: 目标语言

    Returns:
        {列名: {原值: 译文}} 字典，只包含有翻译的列
    """
    translations: dict[str, dict[str, str]] = {}

    if not result_columns or not language:
        return translations

    # 遍历所有表，尝试匹配列名
    for table in ds_schema.db_schema.tables:
        for col_name in result_columns:
            if col_name in translations:
                continue  # 已有翻译，跳过
            col = table.get_column(col_name)
            if col is None:
                continue
            if language in col.value_labels and col.value_labels[language]:
                translations[col_name] = dict(col.value_labels[language])

    return translations
```

### Step 4: 在结果数据中附带 translations

在 `chat_service.py` 中找到构建 `result_data` 的位置（`_run_chat_sync` 函数中，`viz` 之后），在返回 `final_result` 事件之前，将 translations 添加到结果数据中：

```python
    # 收集翻译字典
    translations = {}
    try:
        if ds_schema and exec_result.columns:
            translations = _collect_translations(
                ds_schema, exec_result.columns, language="zh-CN"
            )
    except Exception as e:
        logger.warning("Failed to collect translations: %s", e)

    result_data = {
        "columns": exec_result.columns,
        "rows": [list(r) for r in exec_result.rows],
        "row_count": exec_result.row_count,
        "duration_ms": exec_result.duration_ms,
        "truncated": exec_result.truncated,
        "viz": result.get("viz_spec"),
        "translations": translations,  # 新增：翻译字典
    }
```

同时确保 `translations` 字段也出现在 `viz_ready` / `final_result` 等下游事件中，或者至少在 `sql_executed` 事件的结果数据中。

**注意：** 具体修改位置需要查看 `chat_service.py` 中 result_data 的构建和传递方式，确保 translations 随着结果数据一起传到前端。

### Step 5: 运行测试

Run: `cd backend && python -m pytest tests/test_chat/test_translations.py -v`
Expected: 3 passed

### Step 6: 运行已有 chat 相关测试确保不破坏

Run: `cd backend && python -m pytest tests/test_chat/ -v`
Expected: All pass

### Step 7: 提交

```bash
git add backend/app/services/chat_service.py backend/tests/test_chat/test_translations.py
git commit -m "feat(api): include translations dict in chat result response"
```

---

## Task 5: 前端 — 类型定义 + 翻译 Context

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Create: `frontend/src/hooks/useTranslationToggle.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en.ts`

### Step 1: 新增 TranslationMap 类型

在 `frontend/src/lib/types.ts` 的 QueryResult 附近添加：

```typescript
/** 翻译字典：列名 -> { 原值: 译文 } */
export type TranslationMap = Record<string, Record<string, string>>
```

在 `QueryResult` 接口中添加 `translations` 字段：

```typescript
export interface QueryResult {
  columns: string[]
  rows: unknown[][]
  row_count: number
  duration_ms?: number
  truncated?: boolean
  /** 枚举值翻译字典（列名 -> {原值: 译文}） */
  translations?: TranslationMap
}
```

### Step 2: 新增翻译开关 Hook

创建 `frontend/src/hooks/useTranslationToggle.ts`：

```typescript
/**
 * 枚举值翻译开关 Hook
 *
 * 控制表格和图表中是否展示翻译后的值。
 * 持久化到 localStorage。
 */
import { useState, useEffect, useCallback } from 'react'

const STORAGE_KEY = 'asksql-translation-enabled'

export function useTranslationToggle(): {
  translationEnabled: boolean
  setTranslationEnabled: (enabled: boolean) => void
  toggleTranslation: () => void
} {
  const [translationEnabled, setTranslationEnabled] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      // 默认开启（对非技术用户更友好）
      return saved !== null ? saved === 'true' : true
    } catch {
      return true
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(translationEnabled))
    } catch {
      // ignore
    }
  }, [translationEnabled])

  const toggleTranslation = useCallback(() => {
    setTranslationEnabled((prev) => !prev)
  }, [])

  return { translationEnabled, setTranslationEnabled, toggleTranslation }
}
```

### Step 3: 新增 i18n 翻译键

在 `frontend/src/i18n/locales/zh-CN.ts` 中添加：

```typescript
  // 翻译开关
  'toggle.showTranslated': '显示翻译值',
  'toggle.showOriginal': '显示原始值',
```

在 `frontend/src/i18n/locales/en.ts` 中添加对应的英文：

```typescript
  'toggle.showTranslated': 'Show Translated',
  'toggle.showOriginal': 'Show Original',
```

### Step 4: 验证类型编译

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

### Step 5: 提交

```bash
git add frontend/src/lib/types.ts frontend/src/hooks/useTranslationToggle.ts \
  frontend/src/i18n/locales/zh-CN.ts frontend/src/i18n/locales/en.ts
git commit -m "feat(frontend): add TranslationMap type and translation toggle hook"
```

---

## Task 6: 前端 — ResultTable 表格翻译渲染

**Files:**
- Modify: `frontend/src/components/chat/ResultTable.tsx`

### Step 1: 为 ResultTable 添加翻译能力

在 `ResultTable.tsx` 中：

1. 导入翻译相关的 hooks 和类型
2. 读取当前语言和翻译开关状态
3. 在表格渲染时，对有翻译字典的列应用翻译

核心修改点：
- 表格的单元格渲染：如果 translationEnabled + 当前语言是 zh-CN + 该列有 translations，则显示译文
- 表头列名保持不变（列名翻译是另一个功能，不在本次范围）
- 翻译在显示层做，原始数据（rows）保持不变

伪代码结构：

```tsx
// 在 ResultTable 组件内
const { locale } = useTranslation()
const { translationEnabled } = useTranslationToggle()

// 根据当前语言和开关状态，获取某列某值的显示文本
const getDisplayValue = useCallback((colName: string, value: unknown): string => {
  if (!translationEnabled || locale !== 'zh-CN') {
    return String(value ?? '')
  }
  const colTranslations = result.translations?.[colName]
  if (colTranslations && value !== null && value !== undefined) {
    const key = String(value)
    if (key in colTranslations) {
      return colTranslations[key]
    }
  }
  return String(value ?? '')
}, [translationEnabled, locale, result.translations])
```

然后在表格的 cell 渲染中使用 `getDisplayValue(columnName, cellValue)`。

**注意：** 具体修改需要结合 `@tanstack/react-table` 的 column 定义方式，确保每个单元格都经过翻译处理。

### Step 2: 验证编译

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

### Step 3: 提交

```bash
git add frontend/src/components/chat/ResultTable.tsx
git commit -m "feat(frontend): apply enum value translations in ResultTable"
```

---

## Task 7: 前端 — 图表组件翻译渲染

**Files:**
- Modify: `frontend/src/components/chart/chartUtils.ts`
- Modify: `frontend/src/components/chart/BarChartView.tsx`
- Modify: `frontend/src/components/chart/LineChartView.tsx`
- Modify: `frontend/src/components/chart/PieChartView.tsx`（如果存在）
- Modify: `frontend/src/components/chart/AreaChartView.tsx`（如果存在）
- Modify: `frontend/src/components/chart/ChartRenderer.tsx`
- Modify: `frontend/src/components/chart/ChartGrid.tsx`

### Step 1: 在 chartUtils 中添加翻译工具函数

在 `frontend/src/components/chart/chartUtils.ts` 中添加：

```typescript
import type { TranslationMap } from '../../lib/types'

/**
 * 对图表数据应用枚举值翻译。
 * 只翻译类别型字段（x_field / category_field），数值字段不翻译。
 */
export function applyTranslationsToData(
  data: Record<string, unknown>[],
  fields: string[],
  translations: TranslationMap | undefined,
  translationEnabled: boolean,
  locale: string,
): Record<string, unknown>[] {
  if (!translationEnabled || locale !== 'zh-CN' || !translations || !fields.length) {
    return data
  }

  // 找出有翻译的字段
  const translatableFields = fields.filter((f) => f in translations)
  if (translatableFields.length === 0) {
    return data
  }

  return data.map((row) => {
    const newRow = { ...row }
    for (const field of translatableFields) {
      const val = newRow[field]
      if (val !== null && val !== undefined) {
        const key = String(val)
        if (key in translations[field]) {
          newRow[field] = translations[field][key]
        }
      }
    }
    return newRow
  })
}
```

### Step 2: ChartGrid 向下传递 translations

修改 `ChartGrid.tsx`，将 `result.translations` 传递给每个 `ChartRenderer`。

在 `ChartGridProps` 中添加 `translations?: TranslationMap`，或者直接从传入的 `result` 中读取。

### Step 3: ChartRenderer 应用翻译

修改 `ChartRenderer.tsx`：
- 接收 `translations` prop
- 使用 `useTranslationToggle()` 获取开关状态
- 使用 `useTranslation()` 获取当前语言
- 调用 `applyTranslationsToData` 处理 rows 后传给图表组件
- 对 x_field / category_field 对应的列应用翻译

**注意：** 需要识别哪些字段是类别字段（需要翻译），哪些是数值字段（不需要翻译）。判断依据：
- x_field（X 轴类别轴）→ 需要翻译
- category_field（分类字段，如堆叠图/饼图的分类）→ 需要翻译
- y_field / y_fields（数值轴）→ 不需要翻译

### Step 4: 验证编译

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

### Step 5: 提交

```bash
git add frontend/src/components/chart/chartUtils.ts \
  frontend/src/components/chart/ChartGrid.tsx \
  frontend/src/components/chart/ChartRenderer.tsx
git commit -m "feat(frontend): apply enum value translations in charts"
```

---

## Task 8: 前端 — 翻译开关 UI

**Files:**
- Modify: 结果区域的某个设置入口（如消息气泡的工具栏，或设置面板）
- Modify: 某个设置/工具栏组件

### Step 1: 选择合适的开关位置

在聊天界面中，在结果区域附近添加一个翻译开关按钮。建议位置：
- 结果表格上方的工具栏
- 或者图表区域的右上角设置菜单
- 或者侧边栏的设置面板中

具体位置根据现有 UI 结构决定，遵循以下原则：
- 不占太多空间（用图标按钮或小 toggle）
- 用户容易找到（在结果数据附近）
- 状态可见（能看出当前是开还是关）

### Step 2: 实现开关组件

创建一个小的翻译切换按钮组件（或在现有设置面板中加一项）：

```tsx
// 示例：TranslationToggleButton.tsx
import { Languages } from 'lucide-react'
import { useTranslation } from '../../i18n'
import { useTranslationToggle } from '../../hooks/useTranslationToggle'

export function TranslationToggleButton() {
  const { t } = useTranslation()
  const { translationEnabled, toggleTranslation } = useTranslationToggle()

  return (
    <button
      onClick={toggleTranslation}
      title={translationEnabled ? t('toggle.showOriginal') : t('toggle.showTranslated')}
      className="... "
    >
      <Languages size={14} />
      <span>{translationEnabled ? '译' : '原'}</span>
    </button>
  )
}
```

### Step 3: 集成到结果区域

将开关按钮放到 `ResultTable` 上方或旁边，以及图表区域的工具栏中。

### Step 4: 验证编译

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

### Step 5: 提交

```bash
git add frontend/src/components/... 
git commit -m "feat(frontend): add translation toggle UI in result area"
```

---

## Task 9: SSE 事件流和分页 API 中的 translations

**Files:**
- Modify: `backend/app/api/chat.py`（分页结果接口）
- Modify: `backend/app/services/chat_service.py`（结果缓存）
- Modify: `frontend/src/hooks/useSSE.ts`（如果需要）
- Modify: `frontend/src/lib/api.ts`（分页查询）

### Step 1: 确保 SSE 的 sql_executed 事件包含 translations

检查 `chat_service.py` 中发送 `sql_executed` 事件的代码，确保 `translations` 字段随结果数据一起发送。

如果 `sql_executed` 事件的数据中已经包含完整的 `result_data`，且 Task 4 中已将 translations 加入 result_data，则这一步可能已经完成。需要验证。

### Step 2: 分页结果 API 也返回 translations

检查 `backend/app/api/chat.py` 中的分页接口 `GET /messages/{message_id}/result`，确保分页结果也包含 `translations` 字段。

如果结果缓存中存储了完整的 result_data（包括 translations），则分页接口直接从缓存读取即可。

### Step 3: 前端分页 API 读取 translations

检查 `frontend/src/lib/api.ts` 中的 `getResultPage` 函数，确保返回类型包含 `translations`。

### Step 4: 验证

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors

### Step 5: 提交

```bash
git add backend/app/api/chat.py frontend/src/lib/api.ts
git commit -m "feat(api): ensure translations are included in SSE events and paginated results"
```

---

## Task 10: 端到端验证 + 文档

**Files:**
- Modify: `backend/config/schemas/sample/ecommerce.yaml`（添加示例翻译）
- Create: `docs/superpowers/specs/2026-08-26-enum-value-labels-design.md`（设计文档摘要）

### Step 1: 为示例 ecommerce schema 添加翻译数据

手动为 `ecommerce.yaml` 中的枚举列添加 value_labels，方便前端测试和演示。

### Step 2: 编写简短的设计文档摘要

创建 `docs/superpowers/specs/2026-08-26-enum-value-labels-design.md`，简要说明功能、架构、使用方式。

### Step 3: 运行全部后端测试

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests pass

### Step 4: 前端构建检查

Run: `cd frontend && npm run build`
Expected: Build succeeds

### Step 5: 提交

```bash
git add backend/config/schemas/sample/ecommerce.yaml \
  docs/superpowers/specs/2026-08-26-enum-value-labels-design.md
git commit -m "docs: enum value labels design doc and sample data"
```

---

## 完成标准

- [ ] Column.value_labels 字段可用，YAML 读写正常
- [ ] EnumLabelGenerator 能通过 LLM 生成中文标签
- [ ] Profiling 流程自动生成标签并持久化到 YAML
- [ ] 聊天 API 响应包含 translations 字典
- [ ] 前端表格根据开关展示翻译值/原始值
- [ ] 前端图表（柱状图、折线图、饼图等）根据开关展示翻译值
- [ ] 翻译开关有 UI 入口，状态持久化
- [ ] 所有后端测试通过
- [ ] 前端构建无错误
