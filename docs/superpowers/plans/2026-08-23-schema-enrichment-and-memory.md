# Schema 信息增肥 + 用户纠错记忆系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 丰富传给 LLM 的 schema 上下文信息提升 SQL 生成准确率，并建立用户纠错记忆系统使知识可沉淀复用。

**Architecture:**
- Phase 1 Schema 增肥：扩展 Table/Column 模型字段 → SchemaProfiler 自动探测服务 → 重构 schema context 输出格式 → 集成到服务层
- Phase 2 记忆系统：SQLite 建表 + MemoryService → 管理 API + 前端页面 → 注入 schema context → 纠错检测服务 → 集成到对话流程 → 隐式确认

**Tech Stack:** Python (Pydantic, SQLAlchemy, FastAPI), SQLite, React + TypeScript + TailwindCSS, LangGraph nodes

---

## 任务清单

---

# Phase 1: Schema 信息增肥

## Task 1.1: 扩展 Table / Column 模型字段

**Files:**
- Modify: `backend/nl2sql/schema/models.py`
- Modify: `backend/nl2sql/schema/loader.py`
- Modify: `backend/tests/test_schema/test_models.py`
- Modify: `backend/tests/test_schema/test_loader.py`

### Step 1: 为 Column 模型新增字段

在 `backend/nl2sql/schema/models.py` 的 `Column` 类中添加：

```python
# 在 Column 类中添加以下字段（放在 enum_values 之后）
    business_name: str = ""          # 业务名称（YAML 配置）
    distinct_count: int | None = None  # 去重值数量（自动探测）
    top_values: list[dict] = []      # 高频值及占比 [{value, count, ratio}]
    value_min: str | None = None     # 最小值（数值/时间/字符串通用，存字符串方便序列化）
    value_max: str | None = None     # 最大值
    null_count: int | None = None    # NULL 行数
    null_rate: float | None = None   # NULL 率（0.0 ~ 1.0）
    calc_formula: str = ""           # 计算口径说明（衍生字段，YAML 配置）
```

### Step 2: 为 Table 模型新增字段

在 `Table` 类中添加：

```python
# 在 Table 类中添加以下字段
    aliases: list[str] = []          # 业务别名列表（YAML 配置）
    business_domain: str = ""        # 所属业务域（YAML 配置）
    row_count: int | None = None     # 数据行数（自动探测）
    common_dimensions: list[str] = []  # 常用维度列名（YAML + 推断）
    common_metrics: list[dict] = []    # 常用指标 [{name, expression}]（YAML + 推断）
    sample_rows: list[dict] = []     # 样例数据（前 N 行，列名→值）
    update_frequency: str = ""       # 更新频率描述（YAML 配置）
```

同时为 `Table` 增加一个工具方法：

```python
    def has_profiling_data(self) -> bool:
        """是否包含自动探测的数据。"""
        return self.row_count is not None or any(
            col.null_rate is not None or col.value_min is not None
            for col in self.columns
        )
```

### Step 3: 为 Schema 模型新增 profiling 配置字段

在 `Schema` 类中添加：

```python
    profiling_enabled: bool = True
    sample_row_count: int = 5
    max_rows_for_full_profiling: int = 1_000_000
```

### Step 4: 编写模型单元测试

在 `backend/tests/test_schema/test_models.py` 末尾添加：

```python
class TestColumnEnrichment:
    def test_default_values(self):
        col = Column(name="amount", type="decimal")
        assert col.business_name == ""
        assert col.distinct_count is None
        assert col.top_values == []
        assert col.value_min is None
        assert col.value_max is None
        assert col.null_count is None
        assert col.null_rate is None
        assert col.calc_formula == ""

    def test_with_profiling_data(self):
        col = Column(
            name="status",
            type="varchar",
            business_name="订单状态",
            distinct_count=5,
            top_values=[
                {"value": "paid", "count": 1000, "ratio": 0.6},
                {"value": "shipped", "count": 400, "ratio": 0.24},
            ],
            null_count=10,
            null_rate=0.006,
        )
        assert col.business_name == "订单状态"
        assert col.distinct_count == 5
        assert len(col.top_values) == 2
        assert col.top_values[0]["ratio"] == 0.6
        assert col.null_rate == 0.006

    def test_numeric_range(self):
        col = Column(
            name="total_amount",
            type="decimal(10,2)",
            value_min="0.01",
            value_max="99999.99",
        )
        assert col.value_min == "0.01"
        assert col.value_max == "99999.99"

    def test_calc_formula(self):
        col = Column(
            name="final_amount",
            type="decimal",
            calc_formula="total_amount + shipping_fee - discount",
        )
        assert "total_amount" in col.calc_formula


class TestTableEnrichment:
    def test_default_values(self):
        table = Table(name="orders")
        assert table.aliases == []
        assert table.business_domain == ""
        assert table.row_count is None
        assert table.common_dimensions == []
        assert table.common_metrics == []
        assert table.sample_rows == []
        assert table.update_frequency == ""
        assert not table.has_profiling_data()

    def test_with_aliases_and_domain(self):
        table = Table(
            name="orders",
            aliases=["交易表", "下单表"],
            business_domain="交易域",
            update_frequency="实时",
        )
        assert "交易表" in table.aliases
        assert table.business_domain == "交易域"

    def test_with_common_metrics(self):
        table = Table(
            name="orders",
            common_dimensions=["user_id", "channel", "created_at"],
            common_metrics=[
                {"name": "GMV", "expression": "SUM(total_amount)"},
                {"name": "订单量", "expression": "COUNT(*)"},
            ],
        )
        assert len(table.common_dimensions) == 3
        assert table.common_metrics[0]["name"] == "GMV"

    def test_with_sample_rows_and_profiling(self):
        table = Table(
            name="orders",
            row_count=523400,
            sample_rows=[
                {"order_id": 10001, "total_amount": 299.00},
                {"order_id": 10002, "total_amount": 599.00},
            ],
        )
        assert table.row_count == 523400
        assert len(table.sample_rows) == 2
        assert table.has_profiling_data()
```

### Step 5: 运行模型测试验证通过

Run: `cd backend && python -m pytest tests/test_schema/test_models.py -v`
Expected: All tests PASS

### Step 6: 验证 YAML Loader 向后兼容

SchemaLoader 使用 Pydantic 模型构造，自动支持新字段（有默认值）。编写测试验证：

在 `backend/tests/test_schema/test_loader.py` 的 `TestSchemaLoaderLoadFromYaml` 类中添加：

```python
    def test_enriched_yaml_fields(self):
        yaml_content = """
datasource:
  id: test_db
  name: test
  type: mysql
tables:
  - name: orders
    description: 订单表
    aliases: [交易表, 下单表]
    business_domain: 交易域
    update_frequency: 实时
    row_count: 523400
    common_dimensions: [user_id, channel, created_at]
    common_metrics:
      - name: GMV
        expression: SUM(total_amount)
    sample_rows:
      - order_id: 10001
        total_amount: 299.00
    columns:
      - name: order_id
        type: bigint
        is_primary_key: true
        business_name: 订单编号
      - name: total_amount
        type: decimal(10,2)
        description: 订单总金额
        business_name: 商品原价
        semantic_type: amount
        value_min: "0.01"
        value_max: "99999.99"
        null_rate: 0.005
      - name: status
        type: varchar
        semantic_type: category
        distinct_count: 5
        top_values:
          - value: paid
            count: 1000
            ratio: 0.6
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            tmp_path = f.name

        try:
            loader = SchemaLoader()
            ds = loader.load_from_yaml(tmp_path)
            orders = ds.db_schema.get_table("orders")

            assert orders is not None
            assert orders.aliases == ["交易表", "下单表"]
            assert orders.business_domain == "交易域"
            assert orders.update_frequency == "实时"
            assert orders.row_count == 523400
            assert orders.common_dimensions == ["user_id", "channel", "created_at"]
            assert len(orders.common_metrics) == 1
            assert orders.common_metrics[0]["name"] == "GMV"
            assert len(orders.sample_rows) == 1
            assert orders.sample_rows[0]["order_id"] == 10001

            order_id_col = orders.get_column("order_id")
            assert order_id_col.business_name == "订单编号"

            amount_col = orders.get_column("total_amount")
            assert amount_col.business_name == "商品原价"
            assert amount_col.value_min == "0.01"
            assert amount_col.value_max == "99999.99"
            assert amount_col.null_rate == 0.005

            status_col = orders.get_column("status")
            assert status_col.distinct_count == 5
            assert len(status_col.top_values) == 1
            assert status_col.top_values[0]["value"] == "paid"
            assert status_col.top_values[0]["ratio"] == 0.6
        finally:
            os.unlink(tmp_path)

    def test_backward_compatible_old_yaml(self):
        """旧 YAML 文件（没有新增字段）也能正常加载。"""
        yaml_content = """
datasource:
  id: old_db
tables:
  - name: items
    description: old table
    columns:
      - name: id
        type: int
        is_primary_key: true
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            tmp_path = f.name

        try:
            loader = SchemaLoader()
            ds = loader.load_from_yaml(tmp_path)
            items = ds.db_schema.get_table("items")

            # 新增字段都是默认值
            assert items.aliases == []
            assert items.business_domain == ""
            assert items.row_count is None
            assert items.sample_rows == []
            assert items.common_metrics == []

            id_col = items.get_column("id")
            assert id_col.business_name == ""
            assert id_col.distinct_count is None
            assert id_col.top_values == []
            assert id_col.null_rate is None
        finally:
            os.unlink(tmp_path)
```

### Step 7: 运行 Loader 测试验证通过

Run: `cd backend && python -m pytest tests/test_schema/test_loader.py -v`
Expected: All tests PASS

### Step 8: 检查 loader.py 是否需要改造

由于 Pydantic 模型直接接收 `dict` 构造，`Column(**col)` 和 `Table(...)` 会自动接受新字段。
如果 `_parse_table` 中没有显式传递的字段需要确认能从 `table_data` 中透传。

检查当前 `_parse_table` 方法：它是逐个字段传递的（`name`, `description`, `columns`, `examples`），新增的字段不会自动加载。需要改造：

将 `loader.py` 的 `_parse_table` 改为：

```python
    def _parse_table(self, table_data: dict[str, Any]) -> Table:
        columns_data = table_data.get("columns", [])
        columns = [Column(**col) for col in columns_data]

        # 过滤掉不支持的字段，避免 Pydantic 报错
        valid_fields = set(Table.model_fields.keys())
        table_kwargs = {k: v for k, v in table_data.items() if k in valid_fields}
        table_kwargs["columns"] = columns

        return Table(**table_kwargs)
```

`_parse_datasource` 方法也需要类似处理以支持 `profiling` 配置：

```python
    def _parse_datasource(self, data: dict[str, Any]) -> DatasourceSchema:
        ds_info = data.get("datasource", {})
        tables_data = data.get("tables", [])

        tables = [self._parse_table(t) for t in tables_data]

        # profiling 配置（schema 级别）
        profiling = data.get("profiling", {})

        schema_kwargs = {"tables": tables}
        if isinstance(profiling, dict):
            if "enabled" in profiling:
                schema_kwargs["profiling_enabled"] = profiling["enabled"]
            if "sample_row_count" in profiling:
                schema_kwargs["sample_row_count"] = profiling["sample_row_count"]
            if "max_rows_for_full_profiling" in profiling:
                schema_kwargs["max_rows_for_full_profiling"] = profiling["max_rows_for_full_profiling"]

        return DatasourceSchema(
            datasource_id=ds_info.get("id", ""),
            datasource_name=ds_info.get("name", ""),
            datasource_type=ds_info.get("type", "mysql"),
            db_schema=Schema(**schema_kwargs),
        )
```

### Step 9: 再次运行所有测试

Run: `cd backend && python -m pytest tests/test_schema/ -v`
Expected: All tests PASS

### Step 10: Commit

```bash
git add backend/nl2sql/schema/models.py backend/nl2sql/schema/loader.py \
        backend/tests/test_schema/test_models.py backend/tests/test_schema/test_loader.py
git commit -m "feat(schema): extend Table/Column models with enrichment fields"
```

---

## Task 1.2: SchemaProfiler 自动探测服务

**Files:**
- Create: `backend/nl2sql/schema/profiler.py`
- Create: `backend/tests/test_schema/test_profiler.py`
- Modify: `backend/nl2sql/schema/__init__.py`

### Step 1: 创建 SchemaProfiler 类

创建 `backend/nl2sql/schema/profiler.py`：

```python
"""Schema 自动探测服务：从数据库中统计信息并填充到 schema 对象中。"""

from __future__ import annotations

import logging
from typing import Any

from .models import Column, DatasourceSchema, Table

logger = logging.getLogger(__name__)

# 数值型类型关键字
_NUMERIC_TYPES = {"int", "bigint", "smallint", "tinyint", "decimal", "float", "double", "numeric", "real"}
# 日期时间型类型关键字
_DATETIME_TYPES = {"datetime", "date", "timestamp", "time", "year"}
# 类别型判断阈值：distinct_count 小于此值视为低基数类别列
_LOW_CARDINALITY_THRESHOLD = 100


def _is_numeric(col_type: str) -> bool:
    """判断列类型是否为数值型。"""
    t = col_type.lower()
    return any(kw in t for kw in _NUMERIC_TYPES)


def _is_datetime(col_type: str) -> bool:
    """判断列类型是否为日期时间型。"""
    t = col_type.lower()
    return any(kw in t for kw in _DATETIME_TYPES)


def _is_category_column(col: Column) -> bool:
    """判断列是否为类别型（需要统计 top_values）。"""
    if col.semantic_type == "category":
        return True
    if col.enum_values:
        return True
    t = col.type.lower()
    if "varchar" in t or "char" in t or "text" in t or "enum" in t:
        return True
    return False


def _needs_range_stats(col: Column) -> bool:
    """判断列是否需要统计数值/时间范围。"""
    if col.semantic_type in ("amount", "timestamp"):
        return True
    return _is_numeric(col.type) or _is_datetime(col.type)


class SchemaProfiler:
    """Schema 自动探测器。

    通过执行 SQL 查询从数据库中收集统计信息，填充到 Table/Column 对象中。
    """

    def __init__(
        self,
        executor: Any,
        sample_row_count: int = 5,
        max_rows_for_full_profiling: int = 1_000_000,
    ):
        """
        Args:
            executor: SQL 执行器（需要有 execute(sql) -> ExecutionResult 方法）
            sample_row_count: 采样行数
            max_rows_for_full_profiling: 超过此行数的表不做全量 top_values 统计
        """
        self.executor = executor
        self.sample_row_count = sample_row_count
        self.max_rows_for_full_profiling = max_rows_for_full_profiling

    def profile_datasource(self, ds_schema: DatasourceSchema) -> DatasourceSchema:
        """对整个数据源的所有表进行探测。

        Args:
            ds_schema: 数据源 schema 对象

        Returns:
            填充了探测数据的 DatasourceSchema（原地修改后返回）
        """
        for table in ds_schema.db_schema.tables:
            try:
                self.profile_table(table)
            except Exception as e:
                logger.warning("Profiling table %s failed: %s", table.name, e)
        return ds_schema

    def profile_table(self, table: Table) -> Table:
        """对单张表进行探测。

        Args:
            table: 表对象（原地修改）

        Returns:
            填充了探测数据的 Table
        """
        table_name = table.name

        # 1. 表行数
        row_count = self._get_row_count(table_name)
        table.row_count = row_count

        # 2. 样例数据
        if self.sample_row_count > 0:
            table.sample_rows = self._get_sample_rows(table_name, table.columns, self.sample_row_count)

        # 判断是否为大表
        is_large_table = row_count is not None and row_count > self.max_rows_for_full_profiling

        # 3. 逐列统计
        for col in table.columns:
            try:
                self._profile_column(table_name, col, row_count, is_large_table)
            except Exception as e:
                logger.warning("Profiling column %s.%s failed: %s", table_name, col.name, e)

        return table

    def _get_row_count(self, table_name: str) -> int | None:
        """获取表行数。"""
        try:
            result = self.executor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
            if result.success and result.rows:
                return int(result.rows[0][0])
        except Exception as e:
            logger.warning("Failed to get row count for %s: %s", table_name, e)
        return None

    def _get_sample_rows(self, table_name: str, columns: list[Column], limit: int) -> list[dict]:
        """获取样例数据。"""
        try:
            col_names = ", ".join(f"`{c.name}`" for c in columns)
            result = self.executor.execute(
                f"SELECT {col_names} FROM `{table_name}` LIMIT {limit}"
            )
            if not result.success or not result.rows:
                return []

            sample_rows = []
            for row in result.rows:
                row_dict = {}
                for i, col in enumerate(columns):
                    row_dict[col.name] = row[i]
                sample_rows.append(row_dict)
            return sample_rows
        except Exception as e:
            logger.warning("Failed to get sample rows for %s: %s", table_name, e)
            return []

    def _profile_column(
        self,
        table_name: str,
        col: Column,
        row_count: int | None,
        is_large_table: bool,
    ) -> None:
        """对单列进行统计。"""
        col_name = col.name

        # NULL 统计（所有列都做）
        null_count, null_rate = self._get_null_stats(table_name, col_name, row_count)
        col.null_count = null_count
        col.null_rate = null_rate

        # 数值/时间范围统计
        if _needs_range_stats(col):
            value_min, value_max = self._get_value_range(table_name, col_name)
            col.value_min = str(value_min) if value_min is not None else None
            col.value_max = str(value_max) if value_max is not None else None

        # 类别型列：distinct_count + top_values
        if _is_category_column(col):
            distinct_count = self._get_distinct_count(table_name, col_name)
            col.distinct_count = distinct_count

            # 高基数列跳过 top_values，避免性能问题
            if distinct_count is not None and distinct_count > _LOW_CARDINALITY_THRESHOLD:
                return
            # 大表降级：跳过 top_values
            if is_large_table:
                return

            top_values = self._get_top_values(table_name, col_name, row_count, limit=10)
            col.top_values = top_values

    def _get_null_stats(
        self, table_name: str, col_name: str, row_count: int | None
    ) -> tuple[int | None, float | None]:
        """获取 NULL 数量和比率。"""
        try:
            result = self.executor.execute(
                f"SELECT COUNT(*) - COUNT(`{col_name}`) FROM `{table_name}`"
            )
            if result.success and result.rows:
                null_count = int(result.rows[0][0])
                null_rate = null_count / row_count if row_count and row_count > 0 else None
                return null_count, null_rate
        except Exception as e:
            logger.warning("Failed to get null stats for %s.%s: %s", table_name, col_name, e)
        return None, None

    def _get_value_range(self, table_name: str, col_name: str) -> tuple[Any | None, Any | None]:
        """获取列的最小值和最大值。"""
        try:
            result = self.executor.execute(
                f"SELECT MIN(`{col_name}`), MAX(`{col_name}`) FROM `{table_name}`"
            )
            if result.success and result.rows:
                return result.rows[0][0], result.rows[0][1]
        except Exception as e:
            logger.warning("Failed to get value range for %s.%s: %s", table_name, col_name, e)
        return None, None

    def _get_distinct_count(self, table_name: str, col_name: str) -> int | None:
        """获取去重值数量。"""
        try:
            result = self.executor.execute(
                f"SELECT COUNT(DISTINCT `{col_name}`) FROM `{table_name}`"
            )
            if result.success and result.rows:
                return int(result.rows[0][0])
        except Exception as e:
            logger.warning("Failed to get distinct count for %s.%s: %s", table_name, col_name, e)
        return None

    def _get_top_values(
        self, table_name: str, col_name: str, row_count: int | None, limit: int = 10
    ) -> list[dict]:
        """获取高频值及其占比。"""
        try:
            result = self.executor.execute(
                f"SELECT `{col_name}`, COUNT(*) as cnt "
                f"FROM `{table_name}` "
                f"WHERE `{col_name}` IS NOT NULL "
                f"GROUP BY `{col_name}` "
                f"ORDER BY cnt DESC "
                f"LIMIT {limit}"
            )
            if not result.success or not result.rows:
                return []

            top_values = []
            for row in result.rows:
                value = row[0]
                count = int(row[1])
                ratio = count / row_count if row_count and row_count > 0 else 0.0
                top_values.append({
                    "value": str(value) if value is not None else None,
                    "count": count,
                    "ratio": round(ratio, 4),
                })
            return top_values
        except Exception as e:
            logger.warning("Failed to get top values for %s.%s: %s", table_name, col_name, e)
            return []
```

### Step 2: 更新 schema __init__.py 导出

修改 `backend/nl2sql/schema/__init__.py`，添加：

```python
from .profiler import SchemaProfiler

__all__ = [
    ...,
    "SchemaProfiler",
]
```

### Step 3: 编写 Profiler 单元测试

创建 `backend/tests/test_schema/test_profiler.py`：

```python
"""测试 Schema 自动探测服务。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from nl2sql.schema.models import Column, DatasourceSchema, Schema, Table
from nl2sql.schema.profiler import (
    SchemaProfiler,
    _is_numeric,
    _is_datetime,
    _is_category_column,
    _needs_range_stats,
)


# ---- Mock executor ----

@dataclass
class MockExecutionResult:
    success: bool = True
    rows: list[list[Any]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    row_count: int = 0


class MockExecutor:
    def __init__(self):
        self._responses: dict[str, MockExecutionResult] = {}

    def set_response(self, sql_keyword: str, result: MockExecutionResult):
        self._responses[sql_keyword.lower()] = result

    def execute(self, sql: str) -> MockExecutionResult:
        sql_lower = sql.lower()
        for keyword, result in self._responses.items():
            if keyword in sql_lower:
                return result
        # 默认返回空结果
        return MockExecutionResult(success=True, rows=[])


# ---- Tests for helper functions ----

class TestHelperFunctions:
    def test_is_numeric(self):
        assert _is_numeric("INT")
        assert _is_numeric("BIGINT")
        assert _is_numeric("DECIMAL(10,2)")
        assert _is_numeric("FLOAT")
        assert not _is_numeric("VARCHAR(255)")
        assert not _is_numeric("DATETIME")

    def test_is_datetime(self):
        assert _is_datetime("DATETIME")
        assert _is_datetime("TIMESTAMP")
        assert _is_datetime("DATE")
        assert not _is_datetime("INT")
        assert not _is_datetime("VARCHAR")

    def test_is_category_column(self):
        # semantic_type = category
        col = Column(name="status", type="varchar", semantic_type="category")
        assert _is_category_column(col)
        # 有 enum_values
        col = Column(name="status", type="varchar", enum_values=["a", "b"])
        assert _is_category_column(col)
        # varchar 类型
        col = Column(name="name", type="VARCHAR(100)")
        assert _is_category_column(col)
        # int 类型且没有 category 标记
        col = Column(name="count", type="int")
        assert not _is_category_column(col)

    def test_needs_range_stats(self):
        # amount semantic_type
        col = Column(name="amount", type="decimal", semantic_type="amount")
        assert _needs_range_stats(col)
        # timestamp semantic_type
        col = Column(name="created_at", type="datetime", semantic_type="timestamp")
        assert _needs_range_stats(col)
        # 数值类型
        col = Column(name="count", type="int")
        assert _needs_range_stats(col)
        # 日期类型
        col = Column(name="birth_date", type="date")
        assert _needs_range_stats(col)
        # varchar
        col = Column(name="name", type="varchar")
        assert not _needs_range_stats(col)


# ---- Tests for SchemaProfiler ----

class TestSchemaProfiler:
    def _make_table(self) -> Table:
        return Table(
            name="orders",
            columns=[
                Column(name="order_id", type="BIGINT", is_primary_key=True, semantic_type="id"),
                Column(name="total_amount", type="DECIMAL(10,2)", semantic_type="amount"),
                Column(name="status", type="VARCHAR(20)", semantic_type="category"),
                Column(name="created_at", type="DATETIME", semantic_type="timestamp"),
            ],
        )

    def test_profile_table_row_count(self):
        executor = MockExecutor()
        executor.set_response("count(*)", MockExecutionResult(rows=[[523400]]))
        executor.set_response("sample_rows or limit", MockExecutionResult(rows=[]))
        executor.set_response("count(*) - count", MockExecutionResult(rows=[[10]]))
        executor.set_response("min(", MockExecutionResult(rows=[[0.01, 99999.99]]))
        executor.set_response("count(distinct", MockExecutionResult(rows=[[5]]))
        executor.set_response("group by", MockExecutionResult(
            rows=[["paid", 1000], ["shipped", 400]],
        ))
        executor.set_response("select * from", MockExecutionResult(
            rows=[[1, 299.00, "paid", "2026-01-01"], [2, 599.00, "shipped", "2026-01-02"]],
        ))

        profiler = SchemaProfiler(executor, sample_row_count=2)
        table = self._make_table()
        result = profiler.profile_table(table)

        assert result.row_count == 523400
        assert len(result.sample_rows) == 2
        assert result.sample_rows[0]["order_id"] == 1

        # 列统计
        amount_col = result.get_column("total_amount")
        assert amount_col.value_min == "0.01"
        assert amount_col.value_max == "99999.99"
        assert amount_col.null_rate == 10 / 523400

        status_col = result.get_column("status")
        assert status_col.distinct_count == 5
        assert len(status_col.top_values) == 2
        assert status_col.top_values[0]["value"] == "paid"
        assert status_col.top_values[0]["count"] == 1000

        created_col = result.get_column("created_at")
        assert created_col.value_min is not None
        assert created_col.value_max is not None

    def test_profile_table_large_table_skips_top_values(self):
        executor = MockExecutor()
        # 200 万行，超过默认 100 万阈值
        executor.set_response("count(*)", MockExecutionResult(rows=[[2000000]]))
        executor.set_response("select * from", MockExecutionResult(rows=[]))
        executor.set_response("count(*) - count", MockExecutionResult(rows=[[100]]))
        executor.set_response("min(", MockExecutionResult(rows=[[0, 1000]]))
        executor.set_response("count(distinct", MockExecutionResult(rows=[[50]]))

        profiler = SchemaProfiler(executor)
        table = Table(
            name="big_table",
            columns=[
                Column(name="id", type="BIGINT", is_primary_key=True),
                Column(name="category", type="VARCHAR(50)", semantic_type="category"),
                Column(name="amount", type="DECIMAL", semantic_type="amount"),
            ],
        )
        result = profiler.profile_table(table)

        assert result.row_count == 2_000_000
        # 大表跳过 top_values
        cat_col = result.get_column("category")
        assert cat_col.distinct_count == 50  # distinct_count 仍统计
        assert cat_col.top_values == []  # top_values 跳过
        # 数值范围仍统计
        amount_col = result.get_column("amount")
        assert amount_col.value_min is not None

    def test_high_cardinality_skips_top_values(self):
        executor = MockExecutor()
        executor.set_response("count(*)", MockExecutionResult(rows=[[10000]]))
        executor.set_response("select * from", MockExecutionResult(rows=[]))
        executor.set_response("count(*) - count", MockExecutionResult(rows=[[0]]))
        # 200 个不同值，超过 100 阈值
        executor.set_response("count(distinct", MockExecutionResult(rows=[[200]]))

        profiler = SchemaProfiler(executor)
        table = Table(
            name="t",
            columns=[Column(name="high_card", type="VARCHAR", semantic_type="category")],
        )
        result = profiler.profile_table(table)

        col = result.get_column("high_card")
        assert col.distinct_count == 200
        assert col.top_values == []  # 高基数跳过

    def test_execution_failure_does_not_crash(self):
        class FailingExecutor:
            def execute(self, sql):
                raise Exception("DB error")

        profiler = SchemaProfiler(FailingExecutor())
        table = self._make_table()
        # 不应抛出异常
        result = profiler.profile_table(table)
        assert result.row_count is None
        assert result.sample_rows == []

    def test_profile_datasource(self):
        executor = MockExecutor()
        executor.set_response("count(*)", MockExecutionResult(rows=[[100]]))
        executor.set_response("select * from", MockExecutionResult(rows=[]))
        executor.set_response("count(*) - count", MockExecutionResult(rows=[[0]]))
        executor.set_response("min(", MockExecutionResult(rows=[[0, 100]]))
        executor.set_response("count(distinct", MockExecutionResult(rows=[[3]]))
        executor.set_response("group by", MockExecutionResult(rows=[]))

        profiler = SchemaProfiler(executor)
        ds = DatasourceSchema(
            datasource_id="test",
            datasource_name="test",
            datasource_type="mysql",
            db_schema=Schema(
                tables=[
                    Table(name="t1", columns=[Column(name="id", type="int")]),
                    Table(name="t2", columns=[Column(name="id", type="int")]),
                ]
            ),
        )
        result = profiler.profile_datasource(ds)
        assert result.db_schema.get_table("t1").row_count == 100
        assert result.db_schema.get_table("t2").row_count == 100
```

### Step 4: 运行 Profiler 测试

Run: `cd backend && python -m pytest tests/test_schema/test_profiler.py -v`
Expected: All tests PASS

### Step 5: 添加 YAML 写回功能

在 `profiler.py` 中添加一个工具函数，将探测结果写回 YAML 文件：

```python
import os
import yaml


def write_profile_to_yaml(ds_schema: DatasourceSchema, filepath: str) -> None:
    """将包含探测数据的 schema 写回 YAML 文件。

    只写入有值的探测字段，保持 YAML 整洁。
    """
    # 构建 YAML 数据结构
    tables_data = []
    for table in ds_schema.db_schema.tables:
        table_dict = {"name": table.name}
        if table.description:
            table_dict["description"] = table.description
        if table.aliases:
            table_dict["aliases"] = table.aliases
        if table.business_domain:
            table_dict["business_domain"] = table.business_domain
        if table.update_frequency:
            table_dict["update_frequency"] = table.update_frequency
        if table.row_count is not None:
            table_dict["row_count"] = table.row_count
        if table.common_dimensions:
            table_dict["common_dimensions"] = table.common_dimensions
        if table.common_metrics:
            table_dict["common_metrics"] = table.common_metrics
        if table.sample_rows:
            table_dict["sample_rows"] = table.sample_rows
        if table.examples:
            table_dict["examples"] = table.examples

        columns_data = []
        for col in table.columns:
            col_dict = {
                "name": col.name,
                "type": col.type,
            }
            if col.description:
                col_dict["description"] = col.description
            if col.business_name:
                col_dict["business_name"] = col.business_name
            if col.is_primary_key:
                col_dict["is_primary_key"] = True
            if col.is_foreign_key:
                col_dict["is_foreign_key"] = True
                col_dict["foreign_key_table"] = col.foreign_key_table
                col_dict["foreign_key_column"] = col.foreign_key_column
            if col.semantic_type:
                col_dict["semantic_type"] = col.semantic_type
            if col.enum_values:
                col_dict["enum_values"] = col.enum_values
            if col.calc_formula:
                col_dict["calc_formula"] = col.calc_formula
            if col.distinct_count is not None:
                col_dict["distinct_count"] = col.distinct_count
            if col.top_values:
                col_dict["top_values"] = col.top_values
            if col.value_min is not None:
                col_dict["value_min"] = col.value_min
            if col.value_max is not None:
                col_dict["value_max"] = col.value_max
            if col.null_count is not None:
                col_dict["null_count"] = col.null_count
            if col.null_rate is not None:
                col_dict["null_rate"] = col.null_rate

            columns_data.append(col_dict)

        table_dict["columns"] = columns_data
        tables_data.append(table_dict)

    yaml_data = {
        "datasource": {
            "id": ds_schema.datasource_id,
            "name": ds_schema.datasource_name,
            "type": ds_schema.datasource_type,
        },
        "profiling": {
            "enabled": ds_schema.db_schema.profiling_enabled,
            "sample_row_count": ds_schema.db_schema.sample_row_count,
            "max_rows_for_full_profiling": ds_schema.db_schema.max_rows_for_full_profiling,
        },
        "tables": tables_data,
    }

    # 确保目录存在
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
```

添加测试：

```python
    def test_write_profile_to_yaml(self):
        import os
        import tempfile

        table = Table(
            name="orders",
            description="订单表",
            row_count=1000,
            aliases=["交易表"],
            sample_rows=[{"id": 1, "amount": 100}],
            columns=[
                Column(
                    name="id", type="INT", is_primary_key=True,
                    semantic_type="id", null_rate=0.0,
                ),
                Column(
                    name="amount", type="DECIMAL", semantic_type="amount",
                    value_min="1", value_max="999", null_rate=0.01,
                ),
            ],
        )
        ds = DatasourceSchema(
            datasource_id="test",
            datasource_name="Test DB",
            datasource_type="mysql",
            db_schema=Schema(tables=[table]),
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            tmp_path = f.name

        try:
            from nl2sql.schema.profiler import write_profile_to_yaml
            write_profile_to_yaml(ds, tmp_path)

            # 读回来验证
            from nl2sql.schema.loader import SchemaLoader
            loader = SchemaLoader()
            loaded = loader.load_from_yaml(tmp_path)

            assert loaded.datasource_id == "test"
            orders = loaded.db_schema.get_table("orders")
            assert orders.row_count == 1000
            assert orders.aliases == ["交易表"]
            assert len(orders.sample_rows) == 1
            assert orders.get_column("amount").value_min == "1"
            assert orders.get_column("amount").value_max == "999"
        finally:
            os.unlink(tmp_path)
```

### Step 6: 运行所有 schema 测试

Run: `cd backend && python -m pytest tests/test_schema/ -v`
Expected: All tests PASS

### Step 7: Commit

```bash
git add backend/nl2sql/schema/profiler.py backend/nl2sql/schema/__init__.py \
        backend/tests/test_schema/test_profiler.py
git commit -m "feat(schema): add SchemaProfiler for automatic data profiling"
```

---

## Task 1.3: Schema Context 输出改造

**Files:**
- Modify: `backend/nl2sql/agent/nodes/generate.py`
- Modify: `backend/nl2sql/agent/nodes/intent.py`
- Create: `backend/nl2sql/agent/nodes/_schema_context.py`
- Create: `backend/tests/test_agent/test_schema_context.py`

### Step 1: 抽取 schema context 构建为独立模块

创建 `backend/nl2sql/agent/nodes/_schema_context.py`：

```python
"""Schema Context 构建工具：将 schema 对象格式化为 LLM 可读的文本。"""

from __future__ import annotations

from nl2sql.schema import SchemaMatcher, TableMatch
from nl2sql.schema.models import Column, Table


def _format_column_line(col: Column) -> str:
    """格式化单列信息为紧凑的一行。"""
    parts = [f"  · {col.name}: {col.type}"]

    # 标记
    markers = []
    if col.is_primary_key:
        markers.append("PK")
    if col.is_foreign_key:
        markers.append(f"FK→{col.foreign_key_table}.{col.foreign_key_column}")
    if markers:
        parts.append(f" [{', '.join(markers)}]")

    # 业务名称 / 描述
    desc = col.business_name or col.description
    if desc:
        parts.append(f" {desc}")

    # 语义类型
    if col.semantic_type:
        parts.append(f" [{col.semantic_type}]")

    # 统计信息
    stats = []
    if col.value_min is not None and col.value_max is not None:
        stats.append(f"范围: {col.value_min} ~ {col.value_max}")
    if col.enum_values:
        stats.append(f"枚举: {', '.join(col.enum_values[:5])}")
    if col.distinct_count is not None and col.top_values:
        top3 = ", ".join(
            f"{tv['value']}({tv['ratio']*100:.0f}%)"
            for tv in col.top_values[:3]
        )
        stats.append(f"{col.distinct_count} 个值, Top 3: {top3}")
    if col.null_rate is not None:
        non_null_pct = (1 - col.null_rate) * 100
        stats.append(f"非空 {non_null_pct:.1f}%")

    if stats:
        parts.append(" → " + ", ".join(stats))

    if col.calc_formula:
        parts.append(f" [口径: {col.calc_formula}]")

    return "".join(parts)


def _format_sample_rows(table: Table, max_rows: int = 3) -> list[str]:
    """格式化样例数据为表格形式。"""
    if not table.sample_rows:
        return []

    rows = table.sample_rows[:max_rows]
    if not rows:
        return []

    # 取前 5 列展示，避免太宽
    col_names = list(rows[0].keys())[:5]

    # 计算每列宽度
    col_widths = {c: len(c) for c in col_names}
    for row in rows:
        for c in col_names:
            val_str = str(row.get(c, ""))[:20]
            col_widths[c] = max(col_widths[c], len(val_str))

    lines = [f"样例数据（前 {len(rows)} 行）:"]

    # 表头
    header = "  " + " | ".join(c.ljust(col_widths[c]) for c in col_names)
    lines.append(header)
    lines.append("  " + "-+-".join("-" * col_widths[c] for c in col_names))

    # 数据行
    for row in rows:
        row_str = "  " + " | ".join(
            str(row.get(c, ""))[:20].ljust(col_widths[c]) for c in col_names
        )
        lines.append(row_str)

    return lines


def format_table_context(table: Table, max_columns: int | None = None) -> str:
    """格式化单表的详细 schema context。

    Args:
        table: 表对象
        max_columns: 最多显示多少列，None 表示全部显示

    Returns:
        格式化后的文本
    """
    lines = []

    # 表标题
    title = f"=== 表: {table.name}"
    if table.aliases:
        title += f"（别名: {', '.join(table.aliases)}）"
    title += " ==="
    lines.append(title)

    # 描述
    if table.description:
        lines.append(f"描述: {table.description}")

    # 业务域
    if table.business_domain:
        lines.append(f"业务域: {table.business_domain}")

    # 数据量级
    if table.row_count is not None:
        lines.append(f"数据量级: 约 {table.row_count:,} 行")

    # 常用维度
    if table.common_dimensions:
        lines.append(f"常用维度: {', '.join(table.common_dimensions)}")

    # 常用指标
    if table.common_metrics:
        metric_strs = [
            f"{m['name']}={m['expression']}" for m in table.common_metrics
        ]
        lines.append(f"常用指标: {', '.join(metric_strs)}")

    # 更新频率
    if table.update_frequency:
        lines.append(f"更新频率: {table.update_frequency}")

    # 列
    columns = table.columns
    if max_columns is not None and len(columns) > max_columns:
        columns = columns[:max_columns]
        truncated = True
    else:
        truncated = False

    lines.append("")
    lines.append(f"列（共 {len(table.columns)} 列）:")
    for col in columns:
        lines.append(_format_column_line(col))

    if truncated:
        lines.append(f"  ... 还有 {len(table.columns) - max_columns} 列已省略")

    # 样例数据
    sample_lines = _format_sample_rows(table, max_rows=3)
    if sample_lines:
        lines.append("")
        lines.extend(sample_lines)

    return "\n".join(lines)


def build_detailed_schema_context(
    state: dict,
    max_columns_per_table: int = 15,
) -> tuple[str, str]:
    """构建详细的 schema context（用于 generate 节点）。

    Returns:
        (schema_text, db_type)
    """
    # 确定哪些表需要展示
    intent_tables = []
    if state.get("intent") and state.get("intent").tables:
        intent_tables = [
            t.get("name", "") for t in state.get("intent").tables
            if isinstance(t, dict)
        ]

    matcher = SchemaMatcher(state["datasources"])

    selected_matches: list[TableMatch] = []
    if intent_tables:
        for ds in state["datasources"]:
            for tname in intent_tables:
                table = ds.db_schema.get_table(tname)
                if table:
                    from nl2sql.schema.matcher import TableMatch
                    selected_matches.append(
                        TableMatch(
                            datasource_id=ds.datasource_id,
                            table=table,
                            score=10.0,
                        )
                    )
    if not selected_matches:
        selected_matches = matcher.match_tables(state["user_query"], top_k=5)

    # 确定 db_type
    db_type = "mysql"
    if state["datasources"]:
        db_type = state["datasources"][0].datasource_type

    if not selected_matches:
        return "（无可用的表）", db_type

    lines = []
    current_ds = None
    for m in selected_matches:
        if m.datasource_id != current_ds:
            ds = next(
                (d for d in state["datasources"] if d.datasource_id == m.datasource_id),
                None,
            )
            if ds:
                lines.append(f"数据源: {ds.datasource_name} ({ds.datasource_id})")
                lines.append(f"类型: {ds.datasource_type}")
                lines.append("")
                current_ds = m.datasource_id

        tbl = m.table
        lines.append(format_table_context(tbl, max_columns=max_columns_per_table))
        lines.append("")

    return "\n".join(lines), db_type


def build_compact_schema_context(state: dict) -> str:
    """构建紧凑的 schema context（用于 intent 节点）。

    包含表名、别名、描述、列名列表。
    """
    matcher = SchemaMatcher(state["datasources"])
    matches = matcher.match_tables(state["user_query"], top_k=10)

    if not matches:
        return "（无匹配的表）"

    lines = []
    current_ds = None
    for m in matches:
        if m.datasource_id != current_ds:
            ds = next(
                (d for d in state["datasources"] if d.datasource_id == m.datasource_id),
                None,
            )
            if ds:
                lines.append(f"数据源: {ds.datasource_name} ({ds.datasource_id})")
                current_ds = m.datasource_id

        tbl = m.table
        alias_str = f"（别名: {', '.join(tbl.aliases)}）" if tbl.aliases else ""
        row_count_str = f" [约 {tbl.row_count:,} 行]" if tbl.row_count else ""
        lines.append(
            f"  表: {tbl.name}{alias_str}{row_count_str} - {tbl.description} "
            f"(score: {m.score:.1f})"
        )
        # 只显示前 10 个列名
        col_names = [col.name for col in tbl.columns[:10]]
        more = f" 等 {len(tbl.columns)} 列" if len(tbl.columns) > 10 else ""
        lines.append(f"    列: {', '.join(col_names)}{more}")

    return "\n".join(lines)
```

### Step 2: 重构 generate.py 使用新模块

修改 `backend/nl2sql/agent/nodes/generate.py`：

将 `_build_detailed_schema_context` 函数替换为从新模块导入：

```python
from ._schema_context import build_detailed_schema_context
```

删除原有 `_build_detailed_schema_context` 函数定义。
在 `generate_sql_node` 中调用 `build_detailed_schema_context(state)`。

### Step 3: 重构 intent.py 使用新模块

修改 `backend/nl2sql/agent/nodes/intent.py`：

将 `_build_schema_context` 替换为从新模块导入：

```python
from ._schema_context import build_compact_schema_context
```

删除原有 `_build_schema_context` 函数定义。
在 `intent_analyze_node` 中调用 `build_compact_schema_context(state)`。

### Step 4: 编写 schema context 格式化测试

创建 `backend/tests/test_agent/test_schema_context.py`：

```python
"""测试 Schema Context 格式化。"""

from nl2sql.agent.nodes._schema_context import (
    format_table_context,
    _format_column_line,
)
from nl2sql.schema.models import Column, Table


class TestFormatColumnLine:
    def test_basic_column(self):
        col = Column(name="id", type="BIGINT", is_primary_key=True)
        line = _format_column_line(col)
        assert "id" in line
        assert "BIGINT" in line
        assert "[PK]" in line

    def test_column_with_stats(self):
        col = Column(
            name="total_amount",
            type="DECIMAL(10,2)",
            business_name="商品原价",
            semantic_type="amount",
            value_min="0.01",
            value_max="99999.99",
            null_rate=0.005,
        )
        line = _format_column_line(col)
        assert "商品原价" in line
        assert "amount" in line
        assert "0.01 ~ 99999.99" in line
        assert "非空" in line

    def test_category_column_with_top_values(self):
        col = Column(
            name="status",
            type="VARCHAR(20)",
            semantic_type="category",
            distinct_count=5,
            top_values=[
                {"value": "paid", "count": 600, "ratio": 0.6},
                {"value": "shipped", "count": 200, "ratio": 0.2},
                {"value": "pending", "count": 150, "ratio": 0.15},
            ],
        )
        line = _format_column_line(col)
        assert "5 个值" in line
        assert "paid(60%)" in line
        assert "shipped(20%)" in line

    def test_foreign_key_column(self):
        col = Column(
            name="user_id",
            type="BIGINT",
            is_foreign_key=True,
            foreign_key_table="users",
            foreign_key_column="id",
        )
        line = _format_column_line(col)
        assert "FK→users.id" in line


class TestFormatTableContext:
    def test_full_table(self):
        table = Table(
            name="orders",
            description="记录用户下单信息",
            aliases=["交易表", "下单表"],
            business_domain="交易域",
            row_count=523400,
            update_frequency="实时",
            common_dimensions=["user_id", "channel", "created_at"],
            common_metrics=[
                {"name": "GMV", "expression": "SUM(total_amount)"},
                {"name": "订单量", "expression": "COUNT(*)"},
            ],
            sample_rows=[
                {"order_id": 10001, "total_amount": 299.0, "status": "paid"},
                {"order_id": 10002, "total_amount": 599.0, "status": "shipped"},
            ],
            columns=[
                Column(name="order_id", type="BIGINT", is_primary_key=True),
                Column(
                    name="total_amount", type="DECIMAL(10,2)",
                    business_name="商品原价", semantic_type="amount",
                    value_min="0.01", value_max="99999.99", null_rate=0.005,
                ),
                Column(
                    name="status", type="VARCHAR(20)",
                    semantic_type="category", distinct_count=5,
                    top_values=[
                        {"value": "paid", "count": 600, "ratio": 0.6},
                    ],
                ),
            ],
        )

        text = format_table_context(table)

        # 包含表信息
        assert "orders" in text
        assert "交易表" in text  # 别名
        assert "交易域" in text  # 业务域
        assert "523,400" in text  # 行数（带千分位）
        assert "实时" in text  # 更新频率

        # 常用维度/指标
        assert "常用维度" in text
        assert "GMV" in text
        assert "SUM(total_amount)" in text

        # 列信息
        assert "共 3 列" in text
        assert "商品原价" in text

        # 样例数据
        assert "样例数据" in text
        assert "10001" in text

    def test_truncated_columns(self):
        cols = [Column(name=f"col_{i}", type="INT") for i in range(20)]
        table = Table(name="wide_table", columns=cols)

        text = format_table_context(table, max_columns=5)
        assert "共 20 列" in text
        assert "还有 15 列已省略" in text

    def test_minimal_table(self):
        table = Table(name="simple", columns=[Column(name="id", type="INT")])
        text = format_table_context(table)
        assert "simple" in text
        assert "共 1 列" in text
```

### Step 5: 运行测试

Run: `cd backend && python -m pytest tests/test_agent/test_schema_context.py -v`
Expected: All tests PASS

Run: `cd backend && python -m pytest tests/test_agent/test_nodes_intent.py tests/test_agent/ -k "intent" -v`
Expected: Existing intent tests still pass

### Step 6: Commit

```bash
git add backend/nl2sql/agent/nodes/_schema_context.py \
        backend/nl2sql/agent/nodes/generate.py \
        backend/nl2sql/agent/nodes/intent.py \
        backend/tests/test_agent/test_schema_context.py
git commit -m "feat(schema): enrich schema context format with stats and metadata"
```

---

## Task 1.4: 集成到服务层（异步探测 + API）

**Files:**
- Modify: `backend/app/services/schema_import.py`
- Modify: `backend/app/services/schema_service.py`
- Modify: `backend/app/api/schema.py`
- Modify: `backend/app/core/config.py`
- Create: `backend/app/services/profiling_service.py`

### Step 1: 创建 profiling_service.py 管理异步探测状态

创建 `backend/app/services/profiling_service.py`：

```python
"""Schema 探测服务：管理异步探测任务和状态。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from app.core.database import get_connection
from app.services.datasource_service import build_db_url, get_datasource
from nl2sql.executor.factory import create_executor
from nl2sql.schema.loader import SchemaLoader
from nl2sql.schema.profiler import SchemaProfiler, write_profile_to_yaml


# 内存中的探测状态（进程级，重启丢失，但探测可重跑）
_profiling_status: dict[str, dict] = {}
_profiling_lock = threading.Lock()


def _set_status(datasource_id: str, status: str, **kwargs) -> None:
    with _profiling_lock:
        entry = _profiling_status.setdefault(datasource_id, {
            "status": status,
            "progress": 0,
            "total_tables": 0,
            "current_table": "",
            "started_at": None,
            "finished_at": None,
            "error": None,
        })
        entry["status"] = status
        for k, v in kwargs.items():
            entry[k] = v


def get_profiling_status(datasource_id: str) -> dict:
    """获取指定数据源的探测状态。"""
    with _profiling_lock:
        return dict(_profiling_status.get(datasource_id, {
            "status": "not_started",
            "progress": 0,
            "total_tables": 0,
            "current_table": "",
            "started_at": None,
            "finished_at": None,
            "error": None,
        }))


def start_profiling(datasource_id: str) -> dict:
    """启动异步探测任务。

    Returns:
        启动时的状态信息
    """
    status = get_profiling_status(datasource_id)
    if status["status"] in ("running", "pending"):
        return {"status": status["status"], "message": "Profiling already in progress"}

    _set_status(datasource_id, "pending", started_at=time.time())

    # 在新线程中运行探测
    t = threading.Thread(
        target=_run_profiling,
        args=(datasource_id,),
        daemon=True,
        name=f"profiling-{datasource_id}",
    )
    t.start()

    return {"status": "pending", "message": "Profiling started"}


def _run_profiling(datasource_id: str) -> None:
    """在后台线程中执行探测。"""
    try:
        _set_status(datasource_id, "running")

        # 1. 获取数据源信息
        ds = get_datasource(datasource_id, include_password=True)
        if ds is None:
            _set_status(datasource_id, "failed", error="Datasource not found",
                        finished_at=time.time())
            return

        schema_file = ds.get("schema_file", "")
        if not schema_file:
            _set_status(datasource_id, "failed", error="No schema file, import schema first",
                        finished_at=time.time())
            return

        # 2. 加载当前 schema
        loader = SchemaLoader()
        ds_schema = loader.load_from_yaml(schema_file)

        total_tables = len(ds_schema.db_schema.tables)
        _set_status(datasource_id, "running", total_tables=total_tables, progress=0)

        # 3. 创建执行器
        db_url = build_db_url(ds)
        executor = create_executor(
            datasource_id=datasource_id,
            datasource_type=ds["type"],
            db_url=db_url,
            timeout_seconds=30,
        )

        # 4. 创建 profiler
        profiler = SchemaProfiler(
            executor=executor,
            sample_row_count=ds_schema.db_schema.sample_row_count,
            max_rows_for_full_profiling=ds_schema.db_schema.max_rows_for_full_profiling,
        )

        # 5. 逐表探测（更新进度）
        for i, table in enumerate(ds_schema.db_schema.tables):
            _set_status(datasource_id, "running",
                        current_table=table.name,
                        progress=i)
            try:
                profiler.profile_table(table)
            except Exception as e:
                # 单表失败不终止整体
                import logging
                logger = logging.getLogger(__name__)
                logger.warning("Profiling table %s failed: %s", table.name, e)

        # 6. 写回 YAML
        write_profile_to_yaml(ds_schema, schema_file)

        _set_status(datasource_id, "completed",
                    progress=total_tables,
                    finished_at=time.time())

    except Exception as e:
        import traceback
        _set_status(datasource_id, "failed",
                    error=str(e),
                    finished_at=time.time())
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Profiling failed for datasource %s: %s\n%s",
                     datasource_id, e, traceback.format_exc())
```

### Step 2: 修改 schema_import.py 导入后触发探测

修改 `backend/app/services/schema_import.py` 中的 `import_schema_from_database`：

在函数返回成功之前（return 之前），添加：

```python
        # 启动异步探测
        from app.services.profiling_service import start_profiling
        start_profiling(datasource_id)

        return {
            "success": True,
            "table_count": len(tables_info),
            "tables": tables_info,
        }
```

### Step 3: 添加探测 API 端点

修改 `backend/app/api/schema.py`：

```python
from fastapi import APIRouter, HTTPException, Query
from app.services import schema_service
from app.services import profiling_service

router = APIRouter(prefix="/schema", tags=["schema"])


# ... （保留原有端点）


@router.post("/profile/{datasource_id}")
def start_schema_profiling(datasource_id: str):
    """启动指定数据源的 schema 探测。"""
    result = profiling_service.start_profiling(datasource_id)
    return result


@router.get("/profile/{datasource_id}/status")
def get_profiling_status(datasource_id: str):
    """获取 schema 探测状态。"""
    status = profiling_service.get_profiling_status(datasource_id)
    return status
```

### Step 4: 更新 schema_service 中的返回字段

修改 `backend/app/services/schema_service.py` 的 `get_project_schemas`：

在每个 schema 结果中添加探测状态：

```python
            from app.services.profiling_service import get_profiling_status
            prof_status = get_profiling_status(ds_id)

            results.append({
                "datasource_id": ds_schema.datasource_id or ds_id,
                "datasource_name": ds_schema.datasource_name or ds_name,
                "datasource_type": ds_schema.datasource_type or ds_type,
                "host": ds_host,
                "port": ds_port,
                "database": ds_database,
                "tables": tables,
                "profiling_status": prof_status["status"],
                "row_count_total": sum(
                    t.row_count or 0 for t in ds_schema.db_schema.tables
                ),
            })
```

修改 `get_table_detail` 方法，返回更多字段：

```python
    columns = [
        {
            "name": col.name,
            "type": col.type,
            "description": col.description,
            "business_name": col.business_name,
            "is_primary_key": col.is_primary_key,
            "is_foreign_key": col.is_foreign_key,
            "semantic_type": col.semantic_type,
            "enum_values": col.enum_values,
            "calc_formula": col.calc_formula,
            "distinct_count": col.distinct_count,
            "top_values": col.top_values,
            "value_min": col.value_min,
            "value_max": col.value_max,
            "null_rate": col.null_rate,
        }
        for col in table.columns
    ]

    return {
        "name": table.name,
        "description": table.description,
        "aliases": table.aliases,
        "business_domain": table.business_domain,
        "row_count": table.row_count,
        "update_frequency": table.update_frequency,
        "common_dimensions": table.common_dimensions,
        "common_metrics": table.common_metrics,
        "columns": columns,
        "sample_rows": table.sample_rows,
        "examples": table.examples,
    }
```

### Step 5: 编写服务层测试

创建 `backend/tests/test_services/test_profiling_service.py`：

```python
"""测试 profiling service。"""

from app.services.profiling_service import (
    get_profiling_status,
    _set_status,
    _profiling_status,
)


class TestProfilingService:
    def test_get_status_not_started(self):
        # 用一个不存在的 datasource_id
        status = get_profiling_status("nonexistent_ds")
        assert status["status"] == "not_started"
        assert status["progress"] == 0

    def test_set_and_get_status(self):
        _set_status("test_ds_123", "running", progress=5, total_tables=10, current_table="orders")
        status = get_profiling_status("test_ds_123")
        assert status["status"] == "running"
        assert status["progress"] == 5
        assert status["total_tables"] == 10
        assert status["current_table"] == "orders"

        # 清理
        _profiling_status.pop("test_ds_123", None)
```

### Step 6: 运行相关测试

Run: `cd backend && python -m pytest tests/test_services/test_profiling_service.py tests/test_schema/ -v`
Expected: All tests PASS

### Step 7: Commit

```bash
git add backend/app/services/profiling_service.py \
        backend/app/services/schema_import.py \
        backend/app/services/schema_service.py \
        backend/app/api/schema.py \
        backend/tests/test_services/test_profiling_service.py
git commit -m "feat(service): add async schema profiling with status API"
```

---

# Phase 2: 用户纠错记忆系统

## Task 2.1: 数据模型与基础服务

**Files:**
- Modify: `backend/app/core/database.py`
- Create: `backend/app/services/memory_service.py`
- Create: `backend/tests/test_services/test_memory_service.py`

### Step 1: 在 database.py 中创建 schema_memories 表

在 `backend/app/core/database.py` 的 `init_db()` 函数末尾（`conn.commit()` 之前）添加：

```python
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_memories (
                id TEXT PRIMARY KEY,
                datasource_id TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                entity_type TEXT,
                entity_name TEXT,
                content TEXT NOT NULL,
                raw_content TEXT,
                source TEXT NOT NULL,
                source_session_id TEXT,
                source_message_id TEXT,
                confidence REAL DEFAULT 0.8,
                access_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_datasource
            ON schema_memories(datasource_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_entity
            ON schema_memories(datasource_id, entity_type, entity_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_active
            ON schema_memories(datasource_id, is_active)
        """)
```

### Step 2: 创建 MemoryService

创建 `backend/app/services/memory_service.py`：

```python
"""Schema 记忆服务：管理用户纠错记忆的 CRUD 和召回。"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.database import get_connection


MEMORY_TYPES = {
    "column_description": "column",
    "table_description": "table",
    "metric_definition": "metric",
    "term_mapping": "term",
    "join_hint": "table",
}


def _generate_id() -> str:
    return f"mem_{uuid.uuid4().hex[:12]}"


def add_memory(
    datasource_id: str,
    memory_type: str,
    entity_type: str | None,
    entity_name: str | None,
    content: str,
    *,
    raw_content: str | None = None,
    source: str = "user_correction",
    source_session_id: str | None = None,
    source_message_id: str | None = None,
    confidence: float = 0.8,
) -> dict:
    """添加一条记忆。

    Returns:
        新建的记忆记录 dict
    """
    mem_id = _generate_id()

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO schema_memories
            (id, datasource_id, memory_type, entity_type, entity_name,
             content, raw_content, source, source_session_id, source_message_id,
             confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (mem_id, datasource_id, memory_type, entity_type, entity_name,
             content, raw_content, source, source_session_id, source_message_id,
             confidence),
        )
        conn.commit()
    finally:
        conn.close()

    return get_memory(mem_id) or {}


def get_memory(memory_id: str) -> dict | None:
    """根据 ID 获取单条记忆。"""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM schema_memories WHERE id = ?",
            (memory_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_memories_for_table(datasource_id: str, table_name: str) -> list[dict]:
    """获取某张表的所有相关记忆（表级 + 列级 + 关联表的 join_hint）。"""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT * FROM schema_memories
            WHERE datasource_id = ?
              AND is_active = 1
              AND (
                  (entity_type = 'table' AND entity_name = ?)
                  OR (entity_type = 'column' AND entity_name LIKE ?)
              )
            ORDER BY confidence DESC, access_count DESC, created_at DESC
            """,
            (datasource_id, table_name, f"{table_name}.%"),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_memories_for_query(
    datasource_id: str,
    query: str,
    related_tables: list[str] | None = None,
    related_columns: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """根据查询和相关表召回相关记忆。

    Args:
        datasource_id: 数据源 ID
        query: 用户查询文本
        related_tables: 相关表名列表
        related_columns: 相关列名列表（格式: table.column）
        limit: 最多返回条数

    Returns:
        按相关性排序的记忆列表
    """
    conn = get_connection()
    try:
        # 1. 表级 + 列级精确匹配
        memories: dict[str, dict] = {}

        if related_tables:
            placeholders = ",".join("?" * len(related_tables))
            params = [datasource_id] + related_tables + related_tables
            cursor = conn.execute(
                f"""
                SELECT * FROM schema_memories
                WHERE datasource_id = ?
                  AND is_active = 1
                  AND (
                      (entity_type = 'table' AND entity_name IN ({placeholders}))
                      OR (entity_type = 'column' AND entity_name IN ({placeholders}))
                      OR (memory_type = 'join_hint' AND entity_name IN ({placeholders}))
                  )
                """,
                params + related_tables,
            )
            for row in cursor.fetchall():
                mem = dict(row)
                memories[mem["id"]] = mem

        # 2. 术语型记忆：关键词匹配
        if query:
            query_lower = query.lower()
            cursor = conn.execute(
                """
                SELECT * FROM schema_memories
                WHERE datasource_id = ?
                  AND is_active = 1
                  AND memory_type = 'term_mapping'
                """,
                (datasource_id,),
            )
            for row in cursor.fetchall():
                mem = dict(row)
                entity_name = mem.get("entity_name") or ""
                content = mem.get("content") or ""
                # 简单关键词匹配
                if entity_name and entity_name.lower() in query_lower:
                    memories[mem["id"]] = mem
                elif any(kw in query_lower for kw in content.lower().split()):
                    memories[mem["id"]] = mem

        # 3. 指标型记忆：关键词匹配
        if query:
            query_lower = query.lower()
            cursor = conn.execute(
                """
                SELECT * FROM schema_memories
                WHERE datasource_id = ?
                  AND is_active = 1
                  AND memory_type = 'metric_definition'
                """,
                (datasource_id,),
            )
            for row in cursor.fetchall():
                mem = dict(row)
                entity_name = mem.get("entity_name") or ""
                if entity_name and entity_name.lower() in query_lower:
                    memories[mem["id"]] = mem

        # 4. 排序：confidence 高的在前，access_count 多的在前，新的在前
        result = sorted(
            memories.values(),
            key=lambda m: (m.get("confidence", 0), m.get("access_count", 0),
                           m.get("created_at", "")),
            reverse=True,
        )

        return result[:limit]
    finally:
        conn.close()


def update_memory(memory_id: str, updates: dict) -> dict | None:
    """更新记忆内容。

    Args:
        memory_id: 记忆 ID
        updates: 要更新的字段 dict（content, confidence, entity_name 等）

    Returns:
        更新后的记忆记录
    """
    allowed_fields = {
        "content", "memory_type", "entity_type", "entity_name",
        "confidence", "raw_content",
    }
    update_parts = []
    params = []
    for key, value in updates.items():
        if key in allowed_fields:
            update_parts.append(f"{key} = ?")
            params.append(value)

    if not update_parts:
        return get_memory(memory_id)

    update_parts.append("updated_at = CURRENT_TIMESTAMP")
    params.append(memory_id)

    conn = get_connection()
    try:
        conn.execute(
            f"UPDATE schema_memories SET {', '.join(update_parts)} WHERE id = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()

    return get_memory(memory_id)


def delete_memory(memory_id: str) -> bool:
    """删除记忆（软删除，is_active=0）。"""
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE schema_memories SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (memory_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def list_memories(
    datasource_id: str,
    *,
    memory_type: str | None = None,
    entity_type: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
    include_inactive: bool = False,
) -> dict:
    """列出某数据源的记忆（分页、筛选）。

    Returns:
        {items, total, page, page_size, has_more}
    """
    conn = get_connection()
    try:
        conditions = ["datasource_id = ?"]
        params: list[Any] = [datasource_id]

        if not include_inactive:
            conditions.append("is_active = 1")

        if memory_type:
            conditions.append("memory_type = ?")
            params.append(memory_type)

        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)

        if search:
            conditions.append("(content LIKE ? OR entity_name LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where_clause = " AND ".join(conditions)

        # 总数
        cursor = conn.execute(
            f"SELECT COUNT(*) as total FROM schema_memories WHERE {where_clause}",
            params,
        )
        total = cursor.fetchone()["total"]

        # 分页数据
        offset = (page - 1) * page_size
        cursor = conn.execute(
            f"""
            SELECT * FROM schema_memories
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        )
        items = [dict(row) for row in cursor.fetchall()]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": offset + len(items) < total,
        }
    finally:
        conn.close()


def increment_access(memory_id: str) -> None:
    """增加记忆的访问计数。"""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE schema_memories SET access_count = access_count + 1 WHERE id = ?",
            (memory_id,),
        )
        conn.commit()
    finally:
        conn.close()
```

### Step 3: 编写 MemoryService 单元测试

创建 `backend/tests/test_services/test_memory_service.py`：

```python
"""测试 MemoryService。"""

import os
import tempfile

import pytest

# 用临时数据库
@pytest.fixture(autouse=True)
def use_temp_db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    monkeypatch.setenv("APP_DATABASE_URL", f"sqlite:///{db_path}")

    # 重新初始化数据库
    from app.core.database import init_db
    import importlib
    import app.core.database as db_module
    importlib.reload(db_module)
    init_db()

    yield

    os.unlink(db_path)


class TestAddMemory:
    def test_add_basic_memory(self):
        from app.services import memory_service

        mem = memory_service.add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.total_amount",
            content="amount 是商品原价，不是实付金额",
            source="user_correction",
            source_session_id="sess_1",
            confidence=0.8,
        )

        assert mem["id"].startswith("mem_")
        assert mem["datasource_id"] == "ds_1"
        assert mem["memory_type"] == "column_description"
        assert mem["entity_name"] == "orders.total_amount"
        assert mem["confidence"] == 0.8
        assert mem["is_active"] == 1
        assert mem["access_count"] == 0

    def test_add_term_mapping(self):
        from app.services import memory_service

        mem = memory_service.add_memory(
            datasource_id="ds_1",
            memory_type="term_mapping",
            entity_type="term",
            entity_name="流水",
            content="流水就是 GMV，即订单总金额",
            source="manual_add",
            confidence=1.0,
        )
        assert mem["memory_type"] == "term_mapping"
        assert mem["entity_name"] == "流水"
        assert mem["confidence"] == 1.0


class TestGetMemoriesForQuery:
    def test_table_level_memory_recalled(self):
        from app.services import memory_service

        memory_service.add_memory(
            datasource_id="ds_1",
            memory_type="table_description",
            entity_type="table",
            entity_name="orders",
            content="orders 表只存主站订单",
        )

        result = memory_service.get_memories_for_query(
            datasource_id="ds_1",
            query="订单总数",
            related_tables=["orders"],
        )
        assert len(result) == 1
        assert result[0]["entity_name"] == "orders"

    def test_term_memory_recalled_by_keyword(self):
        from app.services import memory_service

        memory_service.add_memory(
            datasource_id="ds_1",
            memory_type="term_mapping",
            entity_type="term",
            entity_name="流水",
            content="流水就是 GMV",
        )

        result = memory_service.get_memories_for_query(
            datasource_id="ds_1",
            query="上个月的流水是多少",
        )
        assert len(result) == 1
        assert "流水" in result[0]["entity_name"]

    def test_memory_isolated_by_datasource(self):
        from app.services import memory_service

        memory_service.add_memory(
            datasource_id="ds_1",
            memory_type="table_description",
            entity_type="table",
            entity_name="orders",
            content="orders in ds1",
        )

        result = memory_service.get_memories_for_query(
            datasource_id="ds_2",  # 不同的数据源
            query="订单",
            related_tables=["orders"],
        )
        assert len(result) == 0


class TestUpdateAndDelete:
    def test_update_memory(self):
        from app.services import memory_service

        mem = memory_service.add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="old content",
        )
        updated = memory_service.update_memory(
            mem["id"], {"content": "new content", "confidence": 0.95}
        )
        assert updated is not None
        assert updated["content"] == "new content"
        assert updated["confidence"] == 0.95

    def test_delete_memory_soft(self):
        from app.services import memory_service

        mem = memory_service.add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="test",
        )
        result = memory_service.delete_memory(mem["id"])
        assert result is True

        # 软删除后列表中不应出现
        listed = memory_service.list_memories("ds_1")
        assert listed["total"] == 0

        # 但 include_inactive 可以看到
        listed_all = memory_service.list_memories("ds_1", include_inactive=True)
        assert listed_all["total"] == 1


class TestListMemories:
    def test_pagination(self):
        from app.services import memory_service

        for i in range(5):
            memory_service.add_memory(
                datasource_id="ds_1",
                memory_type="column_description",
                entity_type="column",
                entity_name=f"col_{i}",
                content=f"memory {i}",
            )

        page1 = memory_service.list_memories("ds_1", page=1, page_size=2)
        assert page1["total"] == 5
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True

        page3 = memory_service.list_memories("ds_1", page=3, page_size=2)
        assert len(page3["items"]) == 1
        assert page3["has_more"] is False

    def test_filter_by_type(self):
        from app.services import memory_service

        memory_service.add_memory(
            datasource_id="ds_1", memory_type="column_description",
            entity_type="column", entity_name="c1", content="col mem",
        )
        memory_service.add_memory(
            datasource_id="ds_1", memory_type="term_mapping",
            entity_type="term", entity_name="t1", content="term mem",
        )

        result = memory_service.list_memories("ds_1", memory_type="term_mapping")
        assert result["total"] == 1
        assert result["items"][0]["memory_type"] == "term_mapping"

    def test_search(self):
        from app.services import memory_service

        memory_service.add_memory(
            datasource_id="ds_1", memory_type="column_description",
            entity_type="column", entity_name="amount",
            content="这是金额字段",
        )
        memory_service.add_memory(
            datasource_id="ds_1", memory_type="column_description",
            entity_type="column", entity_name="status",
            content="订单状态",
        )

        result = memory_service.list_memories("ds_1", search="金额")
        assert result["total"] == 1
        assert "amount" in result["items"][0]["entity_name"]


class TestIncrementAccess:
    def test_increment(self):
        from app.services import memory_service

        mem = memory_service.add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="test",
        )
        assert mem["access_count"] == 0

        memory_service.increment_access(mem["id"])
        updated = memory_service.get_memory(mem["id"])
        assert updated and updated["access_count"] == 1
```

### Step 4: 运行测试

Run: `cd backend && python -m pytest tests/test_services/test_memory_service.py -v`
Expected: All tests PASS

### Step 5: Commit

```bash
git add backend/app/core/database.py \
        backend/app/services/memory_service.py \
        backend/tests/test_services/test_memory_service.py
git commit -m "feat(memory): add schema_memories table and MemoryService"
```

---

## Task 2.2: 记忆管理 API + 前端类型

**Files:**
- Create: `backend/app/api/memories.py`
- Modify: `backend/app/main.py` (注册 router)
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`

### Step 1: 创建 memories API

创建 `backend/app/api/memories.py`：

```python
"""Schema 记忆管理 API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services import memory_service

router = APIRouter(prefix="/memories", tags=["memories"])


class MemoryCreateRequest(BaseModel):
    datasource_id: str
    memory_type: str
    entity_type: str | None = None
    entity_name: str | None = None
    content: str


class MemoryUpdateRequest(BaseModel):
    content: str | None = None
    memory_type: str | None = None
    entity_type: str | None = None
    entity_name: str | None = None
    confidence: float | None = None


@router.get("")
def list_memories(
    datasource_id: str = Query(..., description="数据源ID"),
    memory_type: str | None = Query(None, description="记忆类型筛选"),
    entity_type: str | None = Query(None, description="实体类型筛选"),
    search: str | None = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """列出指定数据源的记忆列表。"""
    result = memory_service.list_memories(
        datasource_id,
        memory_type=memory_type,
        entity_type=entity_type,
        search=search,
        page=page,
        page_size=page_size,
    )
    return result


@router.post("")
def create_memory(req: MemoryCreateRequest):
    """手动添加一条记忆。"""
    mem = memory_service.add_memory(
        datasource_id=req.datasource_id,
        memory_type=req.memory_type,
        entity_type=req.entity_type,
        entity_name=req.entity_name,
        content=req.content,
        source="manual_add",
        confidence=1.0,
    )
    return mem


@router.get("/{memory_id}")
def get_memory(memory_id: str):
    """获取单条记忆详情。"""
    mem = memory_service.get_memory(memory_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return mem


@router.put("/{memory_id}")
def update_memory(memory_id: str, req: MemoryUpdateRequest):
    """更新记忆内容。"""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    mem = memory_service.update_memory(memory_id, updates)
    if mem is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return mem


@router.delete("/{memory_id}")
def delete_memory(memory_id: str):
    """删除记忆（软删除）。"""
    success = memory_service.delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True}
```

### Step 2: 在 main.py 中注册 router

修改 `backend/app/main.py`，添加：

```python
from app.api.memories import router as memories_router
# ...
app.include_router(memories_router, prefix="/api")
```

### Step 3: 添加前端类型

修改 `frontend/src/lib/types.ts`，添加：

```typescript
// ---------- Schema 记忆 ----------
export type MemoryType = 'column_description' | 'table_description' | 'metric_definition' | 'term_mapping' | 'join_hint'
export type EntityType = 'table' | 'column' | 'metric' | 'term'

export interface SchemaMemory {
  id: string
  datasource_id: string
  memory_type: MemoryType
  entity_type: EntityType | null
  entity_name: string | null
  content: string
  raw_content: string | null
  source: string
  source_session_id: string | null
  source_message_id: string | null
  confidence: number
  access_count: number
  created_at: string
  updated_at: string
  is_active: number
}

export interface MemoryListResult {
  items: SchemaMemory[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}
```

### Step 4: 添加前端 API 调用

修改 `frontend/src/lib/api.ts`，在 Schema 部分之后添加：

```typescript
// ---------- Schema 记忆 ----------
export function listMemories(
  datasourceId: string,
  params: {
    memory_type?: MemoryType
    entity_type?: EntityType
    search?: string
    page?: number
    page_size?: number
  } = {},
): Promise<MemoryListResult> {
  const searchParams = new URLSearchParams()
  searchParams.set('datasource_id', datasourceId)
  if (params.memory_type) searchParams.set('memory_type', params.memory_type)
  if (params.entity_type) searchParams.set('entity_type', params.entity_type)
  if (params.search) searchParams.set('search', params.search)
  if (params.page) searchParams.set('page', String(params.page))
  if (params.page_size) searchParams.set('page_size', String(params.page_size))
  return request<MemoryListResult>(`/memories?${searchParams.toString()}`)
}

export function createMemory(data: {
  datasource_id: string
  memory_type: MemoryType
  entity_type?: EntityType
  entity_name?: string
  content: string
}): Promise<SchemaMemory> {
  return request<SchemaMemory>('/memories', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateMemory(
  memoryId: string,
  data: Partial<{
    content: string
    memory_type: MemoryType
    entity_type: EntityType
    entity_name: string
    confidence: number
  }>,
): Promise<SchemaMemory> {
  return request<SchemaMemory>(`/memories/${encodeURIComponent(memoryId)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteMemory(memoryId: string): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(`/memories/${encodeURIComponent(memoryId)}`, {
    method: 'DELETE',
  })
}
```

需要在顶部 import 中添加类型：

```typescript
import type {
  // ... existing types
  SchemaMemory,
  MemoryType,
  EntityType,
  MemoryListResult,
} from './types'
```

### Step 5: Commit

```bash
git add backend/app/api/memories.py backend/app/main.py \
        frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat(memory): add memory management API and frontend types"
```

---

## Task 2.3: 记忆注入 Schema Context

**Files:**
- Modify: `backend/nl2sql/agent/nodes/_schema_context.py`
- Modify: `backend/nl2sql/agent/nodes/generate.py`
- Modify: `backend/nl2sql/agent/state.py`
- Create: `backend/tests/test_agent/test_memory_injection.py`

### Step 1: 在 AgentState 中添加记忆字段

修改 `backend/nl2sql/agent/state.py`，在 `AgentState` 类中添加：

```python
    # Schema 记忆（从记忆库召回的相关记忆）
    schema_memories: list[dict] = Field(default_factory=list)
```

### Step 2: 在 schema_context 模块中添加记忆注入函数

在 `backend/nl2sql/agent/nodes/_schema_context.py` 末尾添加：

```python
def inject_memories_into_context(
    schema_text: str,
    memories: list[dict],
) -> str:
    """将用户记忆注入到 schema context 文本中。

    - 术语/指标记忆 → 放在最前面作为"业务术语说明"区块
    - 表级记忆 → 追加在对应表描述后面
    - 列级记忆 → 追加在对应列行后面

    Args:
        schema_text: 原始 schema context 文本
        memories: 记忆列表

    Returns:
        注入记忆后的 schema context 文本
    """
    if not memories:
        return schema_text

    lines = schema_text.split("\n")
    result_lines = list(lines)

    # 分类记忆
    term_memories = [m for m in memories if m.get("memory_type") == "term_mapping"]
    metric_memories = [m for m in memories if m.get("memory_type") == "metric_definition"]
    table_memories = [m for m in memories if m.get("memory_type") == "table_description"]
    join_memories = [m for m in memories if m.get("memory_type") == "join_hint"]
    column_memories = [m for m in memories if m.get("memory_type") == "column_description"]

    # 1. 术语/指标记忆：放在最前面
    preamble_lines = []
    if term_memories or metric_memories:
        preamble_lines.append("业务术语说明（来自用户备注）：")
        for m in term_memories:
            date_str = _format_date(m.get("created_at", ""))
            preamble_lines.append(f"  · \"{m.get('entity_name', '')}\" = {m.get('content', '')} ({date_str})")
        for m in metric_memories:
            date_str = _format_date(m.get("created_at", ""))
            preamble_lines.append(f"  · 指标「{m.get('entity_name', '')}」: {m.get('content', '')} ({date_str})")
        preamble_lines.append("")

    # 2. 表级 + join 记忆：在对应表的描述行后注入
    if table_memories or join_memories:
        table_mem_map: dict[str, list[dict]] = {}
        for m in table_memories + join_memories:
            entity_name = m.get("entity_name", "")
            if entity_name:
                table_mem_map.setdefault(entity_name, []).append(m)

        i = 0
        while i < len(result_lines):
            line = result_lines[i]
            # 匹配 "=== 表: table_name（别名: ...）===" 行
            for table_name, mems in table_mem_map.items():
                if f"=== 表: {table_name}" in line or line.startswith(f"表: {table_name}"):
                    # 找到下一个"描述:"行
                    j = i + 1
                    while j < len(result_lines) and "描述:" not in result_lines[j]:
                        j += 1
                    if j < len(result_lines):
                        date_str = _format_date(mems[0].get("created_at", ""))
                        for mem in mems:
                            mem_date = _format_date(mem.get("created_at", ""))
                            result_lines.insert(
                                j + 1,
                                f"📝 用户备注: {mem.get('content', '')}（{mem_date}）",
                            )
                    break
            i += 1

    # 3. 列级记忆：在对应列行后注入
    if column_memories:
        col_mem_map: dict[str, list[dict]] = {}
        for m in column_memories:
            entity_name = m.get("entity_name", "")
            if entity_name:
                # entity_name 格式可能是 table.column 或 column
                if "." in entity_name:
                    col_part = entity_name.split(".")[-1]
                else:
                    col_part = entity_name
                col_mem_map.setdefault(col_part, []).append(m)

        new_lines = []
        for line in result_lines:
            new_lines.append(line)
            # 匹配 "  · col_name: ..." 格式的列行
            stripped = line.lstrip()
            if stripped.startswith("· "):
                # 提取列名（到冒号为止）
                col_part = stripped[2:].split(":")[0].strip()
                if col_part in col_mem_map:
                    for mem in col_mem_map[col_part]:
                        date_str = _format_date(mem.get("created_at", ""))
                        new_lines.append(
                            f"      📝 用户备注: {mem.get('content', '')}（{date_str}）"
                        )
        result_lines = new_lines

    # 组合：术语区块 + 原内容
    if preamble_lines:
        final_lines = preamble_lines + result_lines
    else:
        final_lines = result_lines

    return "\n".join(final_lines)


def _format_date(date_str: str) -> str:
    """格式化日期为简短形式。"""
    if not date_str:
        return ""
    # 2026-08-20 10:30:00 → 2026-08-20
    if " " in date_str:
        return date_str.split(" ")[0]
    if len(date_str) >= 10:
        return date_str[:10]
    return date_str
```

### Step 3: 修改 generate 节点集成记忆

修改 `backend/nl2sql/agent/nodes/generate.py`：

在 `generate_sql_node` 函数中，调用 `build_detailed_schema_context` 后，注入记忆：

```python
        schema_context, db_type = build_detailed_schema_context(state)

        # 注入用户记忆
        if state.get("schema_memories"):
            from ._schema_context import inject_memories_into_context
            schema_context = inject_memories_into_context(
                schema_context, state["schema_memories"]
            )
```

### Step 4: 修改聊天流程：在构建 agent 前召回记忆

修改 `backend/app/services/chat_service.py` 的 `_build_dispatcher_sync` 函数，
在构建 dispatcher 之前，为每个数据源召回相关记忆。

但由于记忆召回需要用户查询，而查询是每次不同的，我们需要在 agent 运行前设置。

改为：在 `_run_chat_sync` 中，构建完 dispatcher 后、运行前，
调用记忆召回并将结果存入 agent 的 state 中。

更简单的方式：修改 `_build_detailed_schema_context` / `build_detailed_schema_context`
让它接收 datasource_id 和 query，然后从 memory_service 中召回。

由于 `build_detailed_schema_context` 在 nl2sql 核心库中，不应该依赖 app 层的 service。
我们通过 state 传递记忆列表。

修改 `nl2sql/agent/dispatcher.py` 或 `graph.py` 在构建 state 时加入记忆。

最简洁的方案：在 `_run_chat_sync` 中，在运行 dispatcher 之前，
先召回记忆，然后在 dispatcher 初始化时传入。

由于 dispatcher 的 `run()` 方法已经存在，我们可以通过修改 dispatcher 的 state 初始化来传入。

让我们在 DispatcherAgent（或 NL2SQLAgent）中增加 `schema_memories` 参数：

修改 `backend/nl2sql/agent/dispatcher.py` 中的 `run` 方法，
增加 `schema_memories` 参数，并传递到子 agent 的 state 中。

为简化，直接在 `_run_chat_sync` 中完成记忆召回，
然后通过修改 dispatcher 的 `datasources` 上下文传递——更简单的方式：
在 chat_service 中召回记忆，存入一个全局/线程局部变量，
agent 节点从 state 中取，state 在初始化时传入。

最佳方式：扩展 `DispatcherAgent.run()` 接收 `extra_state` 参数，
或者直接让 `chat_service` 在构建 state 时包含记忆。

由于现有的 dispatcher.run 接口简洁，我们选择：在 `_build_detailed_schema_context`
中不直接依赖 memory_service，而是由调用方（chat_service）
在 agent 运行前调用 memory_service 召回记忆，然后传递给 state。

具体修改：

1. `_run_chat_sync` 中，在 `dispatcher.run(...)` 之前，
   根据 user_query + 相关表召回记忆
2. 通过修改 dispatcher 的 state 初始化方式传递

最简单且侵入性最小的方式：在 NL2SQLAgent 的 graph 中，
在第一个节点之前设置 state 时传入。

但更简单的是：我们在 chat_service 中计算 schema_memories，
然后将它们附加到 DatasourceSchema 对象上（作为一个新属性），
在 build_detailed_schema_context 中读取。

**最终方案（最简）：**
- 在 `AgentState` 中添加 `schema_memories: list[dict]` 字段
- 在 `_run_chat_sync` 中，运行 dispatcher 前，先用 memory_service 召回记忆
- 通过修改 dispatcher 的初始化让它把记忆放入 state

由于 DispatcherAgent 比较复杂，我们用一个更简洁的实现：
在 `build_detailed_schema_context` 中，如果 state 有 `datasource_executors`
（或有 datasource_id），就从 memory_service 召回。

但是 nl2sql 库不应该依赖 app 层。所以我们用回调函数的方式。

**最终决定的方案：**
- 给 `build_detailed_schema_context` 增加一个可选参数 `memories: list[dict] = []`
- 在 generate 节点中，从 state 读取 `schema_memories` 并传入
- 在 chat_service 中，构建 dispatcher 后、运行前，
  调用 memory_service 召回记忆，将其设置到某个地方

实际上，让我们采用最简单直接的方式：
在 `DispatcherAgent.run()` 中接受 `extra_state` 参数，
然后 NL2SQLAgent 的 initial state 包含这些额外字段。

但这改动较大。

**更简洁的方案：**
将记忆召回放在 `generate_sql_node` 节点内部——
但这样 generate 节点需要调用 memory_service，产生了 nl2sql → app 的反向依赖。

**最终选择（最务实）：**
在 chat_service 的 `_build_dispatcher_sync` 中，
我们构建一个 `memory_retriever` 回调函数，
然后通过 event_callback 类似的方式传递到 state 中。

不，还是复杂了。

**最终方案：**
直接在 state 中增加 `schema_memories` 字段。
在 `_run_chat_sync` 中，dispatcher.run() 调用之前，
我们无法直接设置 state，因为 state 是在 agent 内部创建的。

让我们修改 `DispatcherAgent.run()` 方法，增加可选参数：

```python
def run(self, user_query, history=None, datasource_id=None, schema_memories=None):
```

然后在构建 NL2SQLAgent 的初始 state 时传入。

这是一个相对合理的改动。先查看 dispatcher 的 run 方法签名。

由于这是计划文档，我们在此明确修改点：

修改 `backend/nl2sql/agent/dispatcher.py`：
- `DispatcherAgent.run()` 增加 `schema_memories: list[dict] | None = None` 参数
- 将 schema_memories 传递给 NL2SQLAgent 的初始 state

修改 `backend/nl2sql/agent/graph.py`（或 NL2SQLAgent 定义处）：
- 初始 state 包含 `schema_memories` 字段

修改 `backend/app/services/chat_service.py` 的 `_run_chat_sync`：
- 在调用 `dispatcher.run()` 前，调用 `memory_service.get_memories_for_query()`
- 将记忆列表传入 `dispatcher.run(user_query, history, datasource_id, schema_memories=memories)`

记忆召回需要知道相关的表——但在 intent 分析之前我们不知道哪些表相关。
第一轮的记忆召回只能用关键词匹配（术语、指标）+ 所有表级记忆的轻量召回。
后续轮次（intent 之后）可以更精确地召回。

**简化方案（v1）：**
- 在对话开始时，召回所有术语记忆 + 指标记忆（通常数量少）
- 在 generate 节点，根据 intent 的相关表，精确召回表级和列级记忆
- generate 节点调用记忆召回函数（通过 state 中的回调）

为了避免 nl2sql 依赖 app，我们采用 **state 中传入记忆召回函数** 的方式：

在 state 中增加：
```python
memory_retriever: Any = None  # 可选的记忆召回回调函数
```

在 chat_service 中设置这个回调。
generate 节点如果发现有 memory_retriever，就调用它获取记忆并注入。

但 Pydantic 序列化问题... 好在 state 有 `arbitrary_types_allowed = True`。

**好，最终确定方案：**

1. `AgentState` 添加 `schema_memories: list[dict] = []` 字段
2. `AgentState` 添加 `memory_retriever: Any = None` 字段（回调函数）
3. 在 chat_service 的 `_build_dispatcher_sync` 中，设置 `memory_retriever` 回调
4. generate 节点中：如果有 `memory_retriever`，调用它获取相关记忆，注入 schema context

这个方案最灵活，且 nl2sql 不依赖 app 层。

让我们在 generate 节点实现记忆召回和注入：

```python
# 在 generate_sql_node 中
schema_context, db_type = build_detailed_schema_context(state)

# 召回用户记忆并注入
memory_retriever = state.get("memory_retriever")
if memory_retriever and callable(memory_retriever):
    related_table_names = []
    if state.get("intent") and state.get("intent").tables:
        related_table_names = [
            t.get("name", "") for t in state["intent"].tables
            if isinstance(t, dict)
        ]
    memories = memory_retriever(
        query=state["user_query"],
        related_tables=related_table_names,
    )
    if memories:
        schema_context = inject_memories_into_context(schema_context, memories)
```

在 chat_service 中设置回调：

```python
# 在 _build_dispatcher_sync 的 event_callback 附近
def memory_retriever(query: str, related_tables: list[str]) -> list[dict]:
    from app.services.memory_service import get_memories_for_query
    all_memories = []
    for ds_id in [ds.datasource_id for ds in datasources]:
        mems = get_memories_for_query(ds_id, query, related_tables)
        all_memories.extend(mems)
    return all_memories

# 把回调放到 dispatcher 的 state 中
# 由于 dispatcher 使用 state，我们通过修改 graph 的 initial state 来传入
```

要让这个回调进入 state，需要修改 graph 的构建。
让我们修改 `DispatcherAgent` 以接受额外的 state 字段。

为了减少改动范围，我们用一种更简单的方式：
**通过 `datasource_executors` dict 附加一个特殊 key，
或者通过 event_callback 的特殊事件类型传递。**

不，这些都不优雅。

**最简方案：在 chat_service 中直接在运行前召回记忆，
然后通过修改 dispatcher 的内部 state 来设置。**

但 dispatcher 内部 state 是在 run() 中创建的。

**OK，最终选择：修改 dispatcher.run() 签名。**
增加一个 `extra_state: dict | None = None` 参数，
在构建初始 state 时合并进去。

这是一个通用的、低侵入的改动，对未来扩展也有用。

好的，计划中正式确定此方案。

### Step 5: 修改 DispatcherAgent 支持 extra_state

修改 `backend/nl2sql/agent/dispatcher.py` 中的 `run` 方法：

```python
def run(self, user_query: str, history=None, datasource_id=None, extra_state=None):
```

在构建子 agent state 时，将 `extra_state` 合并进去。

NL2SQLAgent / SchemaExplorerAgent / DatasourceConnectorAgent 各自的
初始 state 构建都需要支持 extra_state。

具体修改：每个子 agent 的 `build_initial_state` 或初始化方法
接受 `**kwargs` 或 `extra_state` 参数。

由于各 agent 的 state 构建方式不同，我们采用：
在 dispatcher.run() 中，将 extra_state 传递给子 agent 的构造或 run 方法。

具体到代码层面，这需要查看各 agent 的实现。
为了计划的可执行性，我们约定：

- `DispatcherAgent.run(user_query, history=None, datasource_id=None, extra_state=None)`
- 当 extra_state 不为 None 时，在构建子 agent 的 state 时合并这些字段
- 合并方式：`initial_state = {**base_state, **extra_state}`

### Step 6: 在 chat_service 中设置记忆召回

修改 `backend/app/services/chat_service.py` 的 `_run_chat_sync`：

```python
        # 构建 dispatcher
        dispatcher = _build_dispatcher_sync(project_id, session_id, loop)

        # 记忆召回回调
        def memory_retriever(query: str, related_tables: list[str]) -> list[dict]:
            from app.services.memory_service import get_memories_for_query
            all_memories = []
            # 获取所有数据源的记忆
            conn = get_connection()
            try:
                cursor = conn.execute(
                    "SELECT id FROM datasources WHERE project_id = ?",
                    (project_id,),
                )
                ds_ids = [row["id"] for row in cursor.fetchall()]
            finally:
                conn.close()

            for ds_id in ds_ids:
                try:
                    mems = get_memories_for_query(ds_id, query, related_tables)
                    all_memories.extend(mems)
                except Exception:
                    pass
            return all_memories

        # 加载历史消息
        history = _load_history_messages_sync(session_id)

        # 运行 dispatcher
        result = dispatcher.run(
            user_query, history, datasource_id,
            extra_state={"memory_retriever": memory_retriever},
        )
```

### Step 7: 编写记忆注入测试

创建 `backend/tests/test_agent/test_memory_injection.py`：

```python
"""测试记忆注入 Schema Context。"""

from nl2sql.agent.nodes._schema_context import (
    format_table_context,
    inject_memories_into_context,
)
from nl2sql.schema.models import Column, Table


def _make_sample_text() -> str:
    table = Table(
        name="orders",
        description="订单表",
        row_count=1000,
        columns=[
            Column(name="order_id", type="BIGINT", is_primary_key=True),
            Column(name="total_amount", type="DECIMAL(10,2)", semantic_type="amount"),
            Column(name="status", type="VARCHAR", semantic_type="category"),
        ],
        sample_rows=[{"order_id": 1, "total_amount": 100, "status": "paid"}],
    )
    return format_table_context(table)


class TestInjectMemories:
    def test_no_memories_returns_original(self):
        text = _make_sample_text()
        result = inject_memories_into_context(text, [])
        assert result == text

    def test_term_memory_added_at_top(self):
        text = _make_sample_text()
        memories = [
            {
                "memory_type": "term_mapping",
                "entity_name": "流水",
                "content": "流水就是 GMV",
                "created_at": "2026-08-20 10:00:00",
            }
        ]
        result = inject_memories_into_context(text, memories)
        assert "业务术语说明" in result
        assert "流水" in result
        assert "GMV" in result
        assert "2026-08-20" in result

    def test_table_level_memory_injected(self):
        text = _make_sample_text()
        memories = [
            {
                "memory_type": "table_description",
                "entity_name": "orders",
                "content": "只存主站订单",
                "created_at": "2026-08-20",
            }
        ]
        result = inject_memories_into_context(text, memories)
        assert "📝 用户备注" in result
        assert "只存主站订单" in result
        # 出现在表描述附近
        lines = result.split("\n")
        desc_idx = next(i for i, l in enumerate(lines) if l.startswith("描述:"))
        note_idx = next(i for i, l in enumerate(lines) if "📝 用户备注" in l)
        assert note_idx == desc_idx + 1

    def test_column_level_memory_injected(self):
        text = _make_sample_text()
        memories = [
            {
                "memory_type": "column_description",
                "entity_name": "orders.total_amount",
                "content": "这是商品原价不是实付",
                "created_at": "2026-08-20",
            }
        ]
        result = inject_memories_into_context(text, memories)
        # 列级记忆用缩进更多的 📝
        assert "用户备注: 这是商品原价不是实付" in result

    def test_metric_definition_memory(self):
        text = _make_sample_text()
        memories = [
            {
                "memory_type": "metric_definition",
                "entity_name": "GMV",
                "content": "total_amount + shipping_fee",
                "created_at": "2026-08-20",
            }
        ]
        result = inject_memories_into_context(text, memories)
        assert "GMV" in result
        assert "指标" in result

    def test_join_hint_memory(self):
        text = _make_sample_text()
        memories = [
            {
                "memory_type": "join_hint",
                "entity_name": "orders",
                "content": "注意游客下单时 user_id 为 NULL",
                "created_at": "2026-08-20",
            }
        ]
        result = inject_memories_into_context(text, memories)
        assert "游客下单" in result
```

### Step 8: 运行测试

Run: `cd backend && python -m pytest tests/test_agent/test_memory_injection.py -v`
Expected: All tests PASS

Run: `cd backend && python -m pytest tests/test_agent/test_schema_context.py -v`
Expected: All tests PASS

### Step 9: Commit

```bash
git add backend/nl2sql/agent/nodes/_schema_context.py \
        backend/nl2sql/agent/nodes/generate.py \
        backend/nl2sql/agent/state.py \
        backend/nl2sql/agent/dispatcher.py \
        backend/app/services/chat_service.py \
        backend/tests/test_agent/test_memory_injection.py
git commit -m "feat(memory): inject user memories into schema context"
```

---

## Task 2.4: 纠错检测服务

**Files:**
- Create: `backend/app/services/correction_detector.py`
- Create: `backend/tests/test_services/test_correction_detector.py`

### Step 1: 创建纠错检测服务

创建 `backend/app/services/correction_detector.py`：

```python
"""纠错检测服务：从用户消息中检测是否为纠错/补充，并提取结构化记忆。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from nl2sql.llm import Message, MessageRole
from nl2sql.llm.factory import create_llm_client

logger = logging.getLogger(__name__)


# 纠错关键词列表（用于预筛）
CORRECTION_KEYWORDS = [
    "不对", "不是", "错了", "纠正", "补充", "说明", "解释一下",
    "其实", "应该是", "指的是", "实际上", "搞错了", "更正",
    "注意", "提醒你", "告诉你", "不是的", "不对的",
    "说错了", "讲错了", "不对哦", "no,", "not ", "wrong",
    "actually", "correction", "wait,",
]


def _has_correction_keyword(text: str) -> bool:
    """检查文本是否包含纠错关键词（快速预筛）。"""
    text_lower = text.lower()
    for kw in CORRECTION_KEYWORDS:
        if kw.lower() in text_lower:
            return True
    return False


DETECTION_SYSTEM_PROMPT = """你是一位数据库 schema 知识抽取专家。

任务：判断用户的消息是否在纠正或补充数据库 schema 的业务含义。

什么算纠错/补充（is_correction = true）：
1. 纠正字段的业务含义（如："amount 不是实付金额，是原价"）
2. 补充表的业务范围（如："这个表只存主站订单"）
3. 解释业务术语（如："流水就是 GMV"）
4. 说明指标计算口径（如："转化率 = 下单用户数 / 访问用户数"）
5. 指出表关联的注意事项（如："关联时注意 NULL 值"）
6. 补充列的枚举值或业务含义

什么不算纠错（is_correction = false）：
1. 普通的追问或换维度（"再看看上个月的"）
2. 数据本身的疑问（"这个数不对吧" 但没说为什么不对）
3. 请求重新查询（"重新查一下"）
4. 表达满意/感谢（"好的，谢谢"）
5. 纯技术问题（"SQL 报错了"）

输出格式：严格的 JSON 格式，包含以下字段：
- is_correction: boolean，是否为纠错/补充
- memory_type: string，记忆类型（仅 is_correction=true 时有效）
  - column_description（列的业务含义补充）
  - table_description（表的业务含义补充）
  - metric_definition（业务指标计算口径）
  - term_mapping（业务术语映射）
  - join_hint（表关联提示）
- entity_type: string，实体类型（column / table / metric / term）
- entity_name: string，实体名称（列名用 table.column 格式，或直接列名）
- content: string，整理后的规范表述（简洁明了的一句话）

如果 is_correction = false，其余字段可以为 null 或空字符串。

请仔细判断，宁缺毋滥，不要误判。"""


@dataclass
class CorrectionResult:
    """纠错检测结果。"""
    is_correction: bool
    memory_type: str | None = None
    entity_type: str | None = None
    entity_name: str | None = None
    content: str = ""
    raw_content: str = ""


def _parse_json_response(text: str) -> dict | None:
    """从 LLM 响应中解析 JSON。"""
    text = text.strip()
    # 去掉 markdown 代码块
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def detect_correction(
    user_message: str,
    context: list[dict] | None = None,
) -> CorrectionResult:
    """检测用户消息是否为纠错/补充。

    Args:
        user_message: 用户消息文本
        context: 上下文消息列表（可选，[{role, content}, ...]）

    Returns:
        CorrectionResult
    """
    # 1. 关键词预筛：没有关键词直接跳过
    if not _has_correction_keyword(user_message):
        return CorrectionResult(is_correction=False, raw_content=user_message)

    # 2. 太短的消息跳过
    if len(user_message.strip()) < 4:
        return CorrectionResult(is_correction=False, raw_content=user_message)

    # 3. LLM 检测
    try:
        # 构建上下文
        context_text = ""
        if context:
            context_lines = []
            for msg in context[-6:]:  # 最近 6 条
                role = "用户" if msg.get("role") == "user" else "助手"
                context_lines.append(f"{role}: {msg.get('content', '')}")
            context_text = "对话上下文：\n" + "\n".join(context_lines) + "\n\n"

        user_msg = f"""{context_text}当前用户消息：
{user_message}

请判断这条用户消息是否在纠正或补充数据库 schema 的业务含义。
输出 JSON。"""

        messages = [
            Message(role=MessageRole.SYSTEM, content=DETECTION_SYSTEM_PROMPT),
            Message(role=MessageRole.USER, content=user_msg),
        ]

        llm = create_llm_client()
        response = llm.chat(messages, temperature=0.0)

        parsed = _parse_json_response(response.content)
        if parsed is None:
            logger.warning("Failed to parse correction detection response: %s", response.content)
            return CorrectionResult(is_correction=False, raw_content=user_message)

        is_correction = bool(parsed.get("is_correction", False))

        if not is_correction:
            return CorrectionResult(is_correction=False, raw_content=user_message)

        memory_type = parsed.get("memory_type") or ""
        entity_type = parsed.get("entity_type") or ""
        entity_name = parsed.get("entity_name") or ""
        content = parsed.get("content") or ""

        # 校验 memory_type 是否合法
        valid_types = {"column_description", "table_description",
                       "metric_definition", "term_mapping", "join_hint"}
        if memory_type not in valid_types:
            # 不合法则视为非纠错
            return CorrectionResult(is_correction=False, raw_content=user_message)

        if not content:
            return CorrectionResult(is_correction=False, raw_content=user_message)

        return CorrectionResult(
            is_correction=True,
            memory_type=memory_type,
            entity_type=entity_type or None,
            entity_name=entity_name or None,
            content=content.strip(),
            raw_content=user_message,
        )

    except Exception as e:
        logger.warning("Correction detection failed: %s", e)
        return CorrectionResult(is_correction=False, raw_content=user_message)


def validate_memory_against_schema(
    correction: CorrectionResult,
    tables: list[Any],
) -> CorrectionResult:
    """验证提取的记忆是否与 schema 中的实体匹配。

    对于 table_description / column_description / join_hint，
    检查 entity_name 对应的表/列是否真实存在。

    对于 term_mapping / metric_definition，不需要验证。
    """
    if not correction.is_correction:
        return correction

    mem_type = correction.memory_type
    entity_name = correction.entity_name or ""

    # 术语/指标不需要验证
    if mem_type in ("term_mapping", "metric_definition"):
        return correction

    # 表级验证
    if mem_type in ("table_description", "join_hint"):
        table_names = {t.name for t in tables}
        if entity_name in table_names:
            return correction
        # 模糊匹配：表名包含 entity_name 或反之
        for t in tables:
            if entity_name.lower() in t.name.lower() or t.name.lower() in entity_name.lower():
                # 修正为正确的表名
                correction.entity_name = t.name
                return correction
        # 找不到对应的表，取消纠错判定
        correction.is_correction = False
        return correction

    # 列级验证
    if mem_type == "column_description":
        # entity_name 可能是 table.column 或 column
        if "." in entity_name:
            table_name, col_name = entity_name.rsplit(".", 1)
        else:
            table_name = ""
            col_name = entity_name

        # 找表
        matching_tables = []
        if table_name:
            for t in tables:
                if table_name.lower() in t.name.lower() or t.name.lower() in table_name.lower():
                    matching_tables.append(t)
        else:
            matching_tables = list(tables)

        # 在匹配的表中找列
        for t in matching_tables:
            for col in t.columns:
                if col.name.lower() == col_name.lower():
                    correction.entity_name = f"{t.name}.{col.name}"
                    return correction

        # 找不到对应的列，取消纠错判定
        correction.is_correction = False
        return correction

    return correction
```

### Step 2: 编写纠错检测测试

创建 `backend/tests/test_services/test_correction_detector.py`：

```python
"""测试纠错检测服务。"""

from nl2sql.schema.models import Column, Table
from app.services.correction_detector import (
    CorrectionResult,
    _has_correction_keyword,
    validate_memory_against_schema,
)


class TestKeywordPreFilter:
    def test_has_correction_keyword(self):
        assert _has_correction_keyword("不对，这个字段是原价")
        assert _has_correction_keyword("纠正一下，应该是这样")
        assert _has_correction_keyword("补充说明，这是流水")
        assert _has_correction_keyword("其实不是的")

    def test_no_correction_keyword(self):
        assert not _has_correction_keyword("帮我查一下订单数据")
        assert not _has_correction_keyword("上个月的数据怎么样")
        assert not _has_correction_keyword("好的谢谢")


class TestValidateAgainstSchema:
    def setup_method(self):
        self.tables = [
            Table(
                name="orders",
                columns=[
                    Column(name="order_id", type="INT"),
                    Column(name="total_amount", type="DECIMAL"),
                    Column(name="status", type="VARCHAR"),
                ],
            ),
            Table(
                name="users",
                columns=[
                    Column(name="user_id", type="INT"),
                    Column(name="name", type="VARCHAR"),
                ],
            ),
        ]

    def test_table_description_valid(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="table_description",
            entity_type="table",
            entity_name="orders",
            content="只存主站订单",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True
        assert result.entity_name == "orders"

    def test_table_description_fuzzy_match(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="table_description",
            entity_type="table",
            entity_name="order表",
            content="主站订单",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True
        assert result.entity_name == "orders"  # 修正为正确表名

    def test_table_description_not_found(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="table_description",
            entity_type="table",
            entity_name="nonexistent",
            content="...",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is False

    def test_column_description_valid(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.total_amount",
            content="商品原价",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True
        assert result.entity_name == "orders.total_amount"

    def test_column_description_fuzzy_table(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="column_description",
            entity_type="column",
            entity_name="order.status",
            content="订单状态",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True
        assert result.entity_name == "orders.status"

    def test_column_description_not_found(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.nonexistent",
            content="...",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is False

    def test_term_mapping_no_validation_needed(self):
        corr = CorrectionResult(
            is_correction=True,
            memory_type="term_mapping",
            entity_type="term",
            entity_name="流水",
            content="就是 GMV",
        )
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is True  # 不需要验证

    def test_non_correction_passthrough(self):
        corr = CorrectionResult(is_correction=False)
        result = validate_memory_against_schema(corr, self.tables)
        assert result.is_correction is False
```

### Step 3: 运行测试

Run: `cd backend && python -m pytest tests/test_services/test_correction_detector.py -v`
Expected: All tests PASS

### Step 4: Commit

```bash
git add backend/app/services/correction_detector.py \
        backend/tests/test_services/test_correction_detector.py
git commit -m "feat(memory): add correction detection service with keyword pre-filter"
```

---

## Task 2.5: 集成到对话流程（异步检测 + 隐式确认）

**Files:**
- Modify: `backend/app/services/chat_service.py`
- Modify: `backend/nl2sql/agent/nodes/summarize.py`
- Modify: `backend/nl2sql/agent/state.py`

### Step 1: 添加待确认记忆队列机制

修改 `backend/app/services/chat_service.py`：

添加模块级的待确认记忆队列：

```python
# 待确认记忆队列：session_id -> [memory1, memory2, ...]
_pending_confirmations: dict[str, list[dict]] = {}
_pending_lock = threading.Lock()  # 需要 import threading


def add_pending_confirmation(session_id: str, memory: dict) -> None:
    """添加一条待确认的记忆。"""
    with _pending_lock:
        if session_id not in _pending_confirmations:
            _pending_confirmations[session_id] = []
        _pending_confirmations[session_id].append(memory)


def get_pending_confirmations(session_id: str) -> list[dict]:
    """获取并清空待确认的记忆列表。"""
    with _pending_lock:
        mems = _pending_confirmations.pop(session_id, [])
        return mems


def peek_pending_confirmations(session_id: str) -> list[dict]:
    """查看待确认记忆（不清空）。"""
    with _pending_lock:
        return list(_pending_confirmations.get(session_id, []))
```

### Step 2: 在对话中加入异步纠错检测

修改 `_run_chat_sync` 函数，在保存用户消息后、构建 dispatcher 前，
启动异步纠错检测：

```python
    # 保存用户消息
    session_service.add_message(session_id, "user", user_query)
    msg_result = session_service.get_messages(session_id)
    user_msg_id = msg_result[-1]["id"] if msg_result else ""

    # 异步纠错检测（不阻塞主流程）
    _start_async_correction_detection(
        session_id=session_id,
        user_query=user_query,
        project_id=project_id,
        user_msg_id=user_msg_id,
    )
```

添加 `_start_async_correction_detection` 函数：

```python
def _start_async_correction_detection(
    session_id: str,
    user_query: str,
    project_id: str,
    user_msg_id: str,
) -> None:
    """启动异步纠错检测。"""
    import threading

    def _detect():
        try:
            from app.services.correction_detector import detect_correction
            from app.services.memory_service import add_memory
            from app.services.session_service import get_messages
            from nl2sql.schema.loader import SchemaLoader

            # 获取上下文消息
            messages = get_messages(session_id)
            context = [
                {"role": m.get("role", ""), "content": m.get("content", "")}
                for m in messages[-10:]  # 最近 10 条
            ]

            # 检测
            correction = detect_correction(user_query, context=context)
            if not correction.is_correction:
                return

            # 获取项目的数据源和 schema，用于验证
            from app.core.database import get_connection
            conn = get_connection()
            try:
                cursor = conn.execute(
                    "SELECT id, schema_file FROM datasources WHERE project_id = ?",
                    (project_id,),
                )
                ds_rows = cursor.fetchall()
            finally:
                conn.close()

            # 收集所有表用于验证
            all_tables = []
            datasource_id_for_memory = None
            loader = SchemaLoader()
            for ds_row in ds_rows:
                schema_file = ds_row["schema_file"]
                if not schema_file:
                    continue
                try:
                    ds = loader.load_from_yaml(schema_file)
                    all_tables.extend(ds.db_schema.tables)
                    if datasource_id_for_memory is None:
                        datasource_id_for_memory = ds_row["id"]
                except Exception:
                    continue

            if not all_tables:
                return

            # 验证
            from app.services.correction_detector import validate_memory_against_schema
            correction = validate_memory_against_schema(correction, all_tables)
            if not correction.is_correction:
                return

            if not datasource_id_for_memory:
                return

            # 存储记忆
            memory = add_memory(
                datasource_id=datasource_id_for_memory,
                memory_type=correction.memory_type,
                entity_type=correction.entity_type,
                entity_name=correction.entity_name,
                content=correction.content,
                raw_content=correction.raw_content,
                source="user_correction",
                source_session_id=session_id,
                source_message_id=user_msg_id,
                confidence=0.8,
            )

            # 加入待确认队列
            add_pending_confirmation(session_id, memory)

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Async correction detection failed: %s", e)

    t = threading.Thread(
        target=_detect,
        daemon=True,
        name=f"correction-detect-{session_id}",
    )
    t.start()
```

### Step 3: 在 summarize 节点中加入隐式确认

修改 `backend/nl2sql/agent/nodes/summarize.py`：

在 state 中读取待确认记忆，在总结回复末尾加入确认语句。

修改 `summarize_node` 函数：

```python
def summarize_node(state: dict) -> dict:
    """Summarize the execution result into a natural language answer.

    Returns:
        dict with final_answer and status
    """
    t0 = step_start(state, "summarize", "总结回答")

    try:
        exec_result = state.get("execution_result")

        # ... (保留原有逻辑) ...

        # 获取待确认的记忆
        pending_memories = state.get("pending_memories", []) or []

        if pending_memories:
            # 在 final_answer 末尾追加确认语句
            confirm_lines = ["\n"]
            if len(pending_memories) == 1:
                mem = pending_memories[0]
                confirm_lines.append(
                    f"另外，我记下了：{mem.get('content', '')}。"
                )
            else:
                confirm_lines.append("另外，我记下了几点：")
                for i, mem in enumerate(pending_memories):
                    confirm_lines.append(f"{i+1}. {mem.get('content', '')}")
            confirm_lines.append("以后我会注意这些区别 👌")

            final_answer += "\n".join(confirm_lines)

        # 发送 final_result 事件（保持原有逻辑，附加确认标记）
        _send_event(state, "final_result", {
            "answer": final_answer,
            "success": success,
            "sql": state.get("sql") or "",
            "row_count": exec_result.row_count if exec_result and success else 0,
            "viz": state.get("viz_spec"),
            "query_assumptions": query_assumptions,
            "rewritten_query": state.get("rewritten_query"),
            "pending_memories": pending_memories,  # 标记有待确认记忆
            "result": {
                # ... 原有 result 数据 ...
            } if exec_result and success else None,
        })
```

### Step 4: 将待确认记忆传入 agent state

修改 `chat_service.py` 中 `_build_dispatcher_sync` 或 `_run_chat_sync`，
在 dispatcher.run() 之前，将待确认记忆传入 extra_state：

```python
        # 获取待确认记忆（上一轮检测到的，本轮确认）
        pending_mems = get_pending_confirmations(session_id)

        # 运行 dispatcher
        result = dispatcher.run(
            user_query, history, datasource_id,
            extra_state={
                "memory_retriever": memory_retriever,
                "pending_memories": pending_mems,
            },
        )
```

确认记忆的时机说明：
- 用户发送消息 → 异步检测到纠错 → 加入待确认队列
- 下一条消息时（可能是用户继续说什么），待确认记忆被取出
- 在 summarize 节点输出确认语句

这样用户在纠正后，下一轮回复中会自然地确认。

但有个问题：如果用户只是纠正一句，没有继续提问，那确认语句就永远不会发出。
更好的方式是：在当前轮的 summarize 中就确认——但纠错检测是异步的，
可能 summarize 已经执行完了。

**改进方案：**
- 纠错检测启动后，等待一小段时间（比如 500ms）看是否已经完成
- 如果完成了，就在当前轮确认
- 如果还在进行中，就下一轮确认

或者：**把纠错检测和当前对话并行处理**，
在 `_run_chat_sync` 中，启动检测线程后继续主流程，
在 summarize 之前检查一下检测是否完成。

但 agent 是同步运行的，不好在节点间插入等待。

**最务实的方案：**
- 异步检测在后台运行
- 检测完成后，如果当前会话还在活跃（还没发送 chat_done），
  就追加一条 confirmation 事件
- 前端收到 confirmation 事件后，在聊天中显示"已记住"的提示
- 记忆立即生效（存入 DB，下一次查询就能召回）

这样不依赖下一轮对话。

**最终方案：**

1. 异步检测 → 存入记忆 → 发送 `memory_saved` SSE 事件
2. 前端收到事件后，在聊天底部显示轻量提示（"已记下：xxx"）
3. 记忆立即生效

修改 `_detect` 函数末尾：

```python
            # 加入待确认队列（供下一轮 summarize 使用）
            add_pending_confirmation(session_id, memory)

            # 同时发送 SSE 事件，让前端立即展示
            loop.call_soon_threadsafe(
                _send_event_sync, session_id, "memory_saved",
                {
                    "memory_id": memory["id"],
                    "content": memory["content"],
                    "entity_name": memory.get("entity_name"),
                    "memory_type": memory.get("memory_type"),
                },
            )
```

注意：需要把 `loop` 传入 `_start_async_correction_detection`。

### Step 5: 更新前端 SSE 类型

修改 `frontend/src/lib/types.ts` 中的 `SseEventType`：

```typescript
export type SseEventType =
  | 'start'
  // ... 原有类型 ...
  | 'memory_saved'  // 新增
  | 'step_detail'
```

### Step 6: 单元测试

在 `backend/tests/test_services/test_chat_service_queue.py` 中添加待确认队列测试，
或新建测试文件：

```python
"""测试待确认记忆队列。"""

from app.services.chat_service import (
    add_pending_confirmation,
    get_pending_confirmations,
    peek_pending_confirmations,
    _pending_confirmations,
)


class TestPendingConfirmations:
    def test_add_and_get(self):
        session_id = "test_sess_123"
        # 清理
        _pending_confirmations.pop(session_id, None)

        mem = {"id": "mem_1", "content": "test"}
        add_pending_confirmation(session_id, mem)

        assert len(peek_pending_confirmations(session_id)) == 1

        retrieved = get_pending_confirmations(session_id)
        assert len(retrieved) == 1
        assert retrieved[0]["id"] == "mem_1"

        # 获取后清空
        assert len(get_pending_confirmations(session_id)) == 0
```

### Step 7: 运行测试

Run: `cd backend && python -m pytest tests/test_services/ -v`
Expected: All tests PASS

### Step 8: Commit

```bash
git add backend/app/services/chat_service.py \
        backend/nl2sql/agent/nodes/summarize.py \
        backend/nl2sql/agent/state.py \
        frontend/src/lib/types.ts
git commit -m "feat(memory): integrate async correction detection into chat flow"
```

---

## Task 2.6: 前端记忆管理页面

**Files:**
- Create: `frontend/src/components/settings/SchemaMemoryPanel.tsx`
- Modify: `frontend/src/components/schema/SchemaPanel.tsx` 或相关设置页

### Step 1: 创建记忆管理组件

创建 `frontend/src/components/settings/SchemaMemoryPanel.tsx`：

```tsx
import { useEffect, useState } from 'react'
import {
  listMemories,
  createMemory,
  updateMemory,
  deleteMemory,
} from '../../lib/api'
import type { SchemaMemory, MemoryType, EntityType } from '../../lib/types'

interface Props {
  datasourceId: string
  tableNames: string[]
}

const MEMORY_TYPE_OPTIONS: { value: MemoryType; label: string }[] = [
  { value: 'column_description', label: '列描述' },
  { value: 'table_description', label: '表描述' },
  { value: 'metric_definition', label: '指标定义' },
  { value: 'term_mapping', label: '术语映射' },
  { value: 'join_hint', label: '关联提示' },
]

const ENTITY_TYPE_MAP: Record<MemoryType, EntityType | ''> = {
  column_description: 'column',
  table_description: 'table',
  metric_definition: 'metric',
  term_mapping: 'term',
  join_hint: 'table',
}

export default function SchemaMemoryPanel({ datasourceId, tableNames }: Props) {
  const [memories, setMemories] = useState<SchemaMemory[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [filter, setFilter] = useState<MemoryType | ''>('')
  const [search, setSearch] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const loadMemories = async () => {
    setLoading(true)
    try {
      const result = await listMemories(datasourceId, {
        memory_type: filter || undefined,
        search: search || undefined,
        page,
        page_size: pageSize,
      })
      setMemories(result.items)
      setTotal(result.total)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (datasourceId) {
      loadMemories()
    }
  }, [datasourceId, page, filter, search])

  const handleDelete = async (id: string) => {
    if (!confirm('确定删除这条记忆吗？')) return
    await deleteMemory(id)
    loadMemories()
  }

  const handleSave = async (data: {
    memory_type: MemoryType
    entity_name?: string
    content: string
  }) => {
    await createMemory({
      datasource_id: datasourceId,
      ...data,
      entity_type: ENTITY_TYPE_MAP[data.memory_type] || undefined,
    })
    setShowAddForm(false)
    loadMemories()
  }

  const handleUpdate = async (id: string, content: string) => {
    await updateMemory(id, { content })
    setEditingId(null)
    loadMemories()
  }

  const typeLabel = (type: string) =>
    MEMORY_TYPE_OPTIONS.find(o => o.value === type)?.label || type

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Schema 记忆</h3>
        <button
          onClick={() => setShowAddForm(true)}
          className="px-3 py-1.5 bg-primary text-white rounded-lg text-sm"
        >
          + 添加记忆
        </button>
      </div>

      {/* 筛选和搜索 */}
      <div className="flex gap-3">
        <select
          value={filter}
          onChange={e => { setFilter(e.target.value as MemoryType | ''); setPage(1) }}
          className="px-3 py-2 border rounded-lg text-sm"
        >
          <option value="">全部类型</option>
          {MEMORY_TYPE_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="搜索内容..."
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1) }}
          className="flex-1 px-3 py-2 border rounded-lg text-sm"
        />
      </div>

      {/* 记忆列表 */}
      {loading ? (
        <div className="text-center py-8 text-gray-400">加载中...</div>
      ) : memories.length === 0 ? (
        <div className="text-center py-8 text-gray-400">
          暂无记忆记录。添加手动记忆，或在对话中纠正时自动生成。
        </div>
      ) : (
        <div className="space-y-2">
          {memories.map(mem => (
            <div
              key={mem.id}
              className="p-3 border rounded-lg bg-white dark:bg-gray-800 dark:border-gray-700"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1">
                  <div className="flex items-center gap-2 text-xs text-gray-500 mb-1">
                    <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-700 rounded">
                      {typeLabel(mem.memory_type)}
                    </span>
                    {mem.entity_name && (
                      <span className="font-mono">{mem.entity_name}</span>
                    )}
                    <span>{mem.created_at?.split('T')[0] || mem.created_at?.split(' ')[0]}</span>
                    <span>访问 {mem.access_count} 次</span>
                  </div>
                  {editingId === mem.id ? (
                    <div className="space-y-2">
                      <textarea
                        defaultValue={mem.content}
                        id={`edit-${mem.id}`}
                        className="w-full px-2 py-1 border rounded text-sm"
                        rows={2}
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={() => {
                            const el = document.getElementById(`edit-${mem.id}`) as HTMLTextAreaElement
                            handleUpdate(mem.id, el.value)
                          }}
                          className="px-2 py-1 text-xs bg-primary text-white rounded"
                        >
                          保存
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="px-2 py-1 text-xs border rounded"
                        >
                          取消
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm">{mem.content}</p>
                  )}
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => setEditingId(mem.id)}
                    className="px-2 py-1 text-xs text-gray-500 hover:text-gray-700"
                  >
                    编辑
                  </button>
                  <button
                    onClick={() => handleDelete(mem.id)}
                    className="px-2 py-1 text-xs text-red-500 hover:text-red-700"
                  >
                    删除
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 分页 */}
      {total > pageSize && (
        <div className="flex justify-center gap-2 pt-2">
          <button
            disabled={page === 1}
            onClick={() => setPage(p => Math.max(1, p - 1))}
            className="px-3 py-1 border rounded text-sm disabled:opacity-50"
          >
            上一页
          </button>
          <span className="px-3 py-1 text-sm text-gray-500">
            {page} / {Math.ceil(total / pageSize)}
          </span>
          <button
            disabled={page * pageSize >= total}
            onClick={() => setPage(p => p + 1)}
            className="px-3 py-1 border rounded text-sm disabled:opacity-50"
          >
            下一页
          </button>
        </div>
      )}

      {/* 添加记忆弹窗 */}
      {showAddForm && (
        <AddMemoryForm
          tableNames={tableNames}
          onSave={handleSave}
          onCancel={() => setShowAddForm(false)}
        />
      )}
    </div>
  )
}

// ---------- 添加记忆表单 ----------

function AddMemoryForm({
  tableNames,
  onSave,
  onCancel,
}: {
  tableNames: string[]
  onSave: (data: { memory_type: MemoryType; entity_name?: string; content: string }) => void
  onCancel: () => void
}) {
  const [memoryType, setMemoryType] = useState<MemoryType>('column_description')
  const [entityName, setEntityName] = useState('')
  const [content, setContent] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave({
      memory_type: memoryType,
      entity_name: entityName || undefined,
      content,
    })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 w-full max-w-md mx-4">
        <h4 className="text-lg font-semibold mb-4">添加记忆</h4>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">记忆类型</label>
            <select
              value={memoryType}
              onChange={e => setMemoryType(e.target.value as MemoryType)}
              className="w-full px-3 py-2 border rounded-lg"
            >
              {MEMORY_TYPE_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {(memoryType === 'table_description' || memoryType === 'join_hint') && (
            <div>
              <label className="block text-sm font-medium mb-1">关联表</label>
              <select
                value={entityName}
                onChange={e => setEntityName(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg"
              >
                <option value="">请选择表</option>
                {tableNames.map(name => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
            </div>
          )}

          {memoryType === 'column_description' && (
            <div>
              <label className="block text-sm font-medium mb-1">
                列名（格式：表名.列名，如 orders.amount）
              </label>
              <input
                type="text"
                value={entityName}
                onChange={e => setEntityName(e.target.value)}
                placeholder="orders.amount"
                className="w-full px-3 py-2 border rounded-lg"
              />
            </div>
          )}

          {(memoryType === 'term_mapping' || memoryType === 'metric_definition') && (
            <div>
              <label className="block text-sm font-medium mb-1">术语/指标名称</label>
              <input
                type="text"
                value={entityName}
                onChange={e => setEntityName(e.target.value)}
                placeholder="如：流水、GMV"
                className="w-full px-3 py-2 border rounded-lg"
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium mb-1">记忆内容</label>
            <textarea
              value={content}
              onChange={e => setContent(e.target.value)}
              placeholder="描述这条记忆的内容..."
              className="w-full px-3 py-2 border rounded-lg"
              rows={3}
              required
            />
          </div>

          <div className="flex gap-3 justify-end pt-2">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 border rounded-lg"
            >
              取消
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-primary text-white rounded-lg"
            >
              添加
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
```

### Step 2: 集成到设置页或 SchemaPanel

在 SchemaPanel 或数据源设置页中添加"记忆"标签页。
具体集成位置取决于现有设置页结构。假设在 SchemaPanel 中添加：

修改 `frontend/src/components/schema/SchemaPanel.tsx`，添加 tab 切换：

```tsx
// 新增 state
const [activeTab, setActiveTab] = useState<'tables' | 'memories'>('tables')

// 渲染
<div>
  <div className="flex border-b mb-4">
    <button
      className={`px-4 py-2 ${activeTab === 'tables' ? 'border-b-2 border-primary' : ''}`}
      onClick={() => setActiveTab('tables')}
    >
      表结构
    </button>
    <button
      className={`px-4 py-2 ${activeTab === 'memories' ? 'border-b-2 border-primary' : ''}`}
      onClick={() => setActiveTab('memories')}
    >
      Schema 记忆
    </button>
  </div>

  {activeTab === 'tables' && (
    // ...原有表结构内容...
  )}

  {activeTab === 'memories' && (
    <SchemaMemoryPanel
      datasourceId={selectedDatasourceId}
      tableNames={tableNames}
    />
  )}
</div>
```

具体集成细节根据现有 SchemaPanel 的实际结构调整。

### Step 3: 聊天中记忆保存提示

在前端聊天组件（useChat hook）中，处理 `memory_saved` 事件，
在消息流中插入一条轻量提示。

修改 `frontend/src/hooks/useChat.ts`（或对应的 hook）：

```typescript
// 在 SSE 事件处理中添加
case 'memory_saved':
  // 在消息列表中追加一条系统提示消息
  addSystemMessage({
    type: 'memory_saved',
    content: `已记下：${data.content}`,
    memory_id: data.memory_id,
  })
  break
```

在聊天消息组件中添加记忆保存提示的渲染样式：
一个带 📝 图标的浅色提示条。

### Step 4: Commit

```bash
git add frontend/src/components/settings/SchemaMemoryPanel.tsx \
        frontend/src/components/schema/SchemaPanel.tsx
git commit -m "feat(frontend): add schema memory management UI"
```

---

## Task 2.7: 联调与测试

**Files:**
- 所有相关文件

### Step 1: 端到端测试计划

手动测试以下场景：

1. **Schema 探测**：
   - 连接一个测试数据库
   - 导入 schema
   - 检查探测状态 API 返回 running
   - 等待后检查 completed
   - 验证 YAML 文件中包含 row_count、top_values、sample_rows 等字段

2. **Schema context 增肥**：
   - 发起查询
   - 在日志中查看传给 LLM 的 schema context
   - 验证包含别名、数据量级、列统计信息、样例数据

3. **手动添加记忆**：
   - 在设置页添加一条术语记忆
   - 添加一条列描述记忆
   - 列表展示、筛选、搜索正常
   - 编辑、删除正常

4. **记忆注入生效**：
   - 添加一条"amount 是原价"的记忆
   - 查询涉及 amount 的问题
   - 验证生成的 SQL 正确（或在 schema context 中能看到记忆）

5. **自动纠错检测**：
   - 正常查询后回复"不对，amount 是商品原价不是实付"
   - 检查是否生成了 memory_saved 事件
   - 检查记忆列表中是否有新记录

6. **多数据源隔离**：
   - 两个数据源各添加一条记忆
   - 验证互不影响

7. **边界情况**：
   - 没有纠错关键词的消息不触发检测
   - 实体不存在的纠错被拒绝
   - 大表探测降级正常

### Step 2: 运行所有测试

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

### Step 3: Bug 修复

根据测试结果修复发现的问题。

### Step 4: 更新文档

在 README 或相关文档中添加功能说明。

### Step 5: 最终 Commit

```bash
git commit -m "feat: schema enrichment and memory system complete"
```

---

## 附录：新增文件总览

### 后端新增
- `backend/nl2sql/schema/profiler.py` — Schema 自动探测服务
- `backend/nl2sql/agent/nodes/_schema_context.py` — Schema context 格式化工具
- `backend/app/services/profiling_service.py` — 异步探测状态管理
- `backend/app/services/memory_service.py` — 记忆 CRUD + 召回服务
- `backend/app/services/correction_detector.py` — 纠错检测服务
- `backend/app/api/memories.py` — 记忆管理 API

### 后端修改
- `backend/nl2sql/schema/models.py` — 新增字段
- `backend/nl2sql/schema/loader.py` — 兼容新字段
- `backend/nl2sql/schema/__init__.py` — 导出 Profiler
- `backend/nl2sql/agent/nodes/generate.py` — 使用新的 context 构建 + 记忆注入
- `backend/nl2sql/agent/nodes/intent.py` — 使用新的紧凑 context
- `backend/nl2sql/agent/state.py` — 新增 schema_memories、memory_retriever、pending_memories
- `backend/nl2sql/agent/dispatcher.py` — 支持 extra_state
- `backend/app/core/database.py` — 新增 schema_memories 表
- `backend/app/services/schema_service.py` — 返回更多 schema 字段
- `backend/app/services/schema_import.py` — 导入后触发探测
- `backend/app/services/chat_service.py` — 异步纠错检测 + 待确认队列
- `backend/app/api/schema.py` — 新增探测 API
- `backend/app/main.py` — 注册 memories router

### 前端新增
- `frontend/src/components/settings/SchemaMemoryPanel.tsx` — 记忆管理页面

### 前端修改
- `frontend/src/lib/types.ts` — 新增记忆相关类型 + SSE 事件
- `frontend/src/lib/api.ts` — 新增记忆 API 调用
- `frontend/src/components/schema/SchemaPanel.tsx` — 集成记忆标签页
- 聊天 hook — 处理 memory_saved 事件

### 测试新增
- `backend/tests/test_schema/test_profiler.py`
- `backend/tests/test_agent/test_schema_context.py`
- `backend/tests/test_agent/test_memory_injection.py`
- `backend/tests/test_services/test_profiling_service.py`
- `backend/tests/test_services/test_memory_service.py`
- `backend/tests/test_services/test_correction_detector.py`
