"""测试 Schema 自动探测服务。"""

from __future__ import annotations

import os
import tempfile
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
    write_profile_to_yaml,
)


# ---- Mock executor ----

@dataclass
class MockExecutionResult:
    success: bool = True
    rows: list[list[Any]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    row_count: int = 0


class MockExecutor:
    """Mock SQL executor.

    用回调函数匹配 SQL 并返回结果。按注册顺序匹配，第一个匹配的生效。
    """

    def __init__(self):
        self._handlers: list[tuple[str, callable]] = []
        self._keyword_responses: list[tuple[str, MockExecutionResult]] = []

    def set_response(self, sql_keyword: str, result: MockExecutionResult):
        """设置一个关键字匹配的响应。按注册顺序匹配，先注册的优先级高。"""
        self._keyword_responses.append((sql_keyword.lower(), result))

    def set_handler(self, predicate: str, handler: callable):
        """设置一个回调处理器，predicate 是关键字，handler(sql) -> result。"""
        self._handlers.append((predicate.lower(), handler))

    def execute(self, sql: str) -> MockExecutionResult:
        sql_lower = sql.strip().lower()

        # 先检查回调处理器
        for predicate, handler in self._handlers:
            if predicate in sql_lower:
                return handler(sql)

        # 再检查关键字响应（后注册的先匹配，因为 append 在后面，更具体的应该后注册）
        # 其实应该反过来：先注册的（更通用的）后匹配
        # 我们按逆序匹配，后注册的（更具体的）优先
        for keyword, result in reversed(self._keyword_responses):
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
        # 注意：MockExecutor 用关键字子串匹配，后注册的优先级高
        # 因此要把更具体的（更长的）关键字后注册

        # NULL 统计（最具体，先注册 = 最低优先级）
        executor.set_response("count(*) - count(`", MockExecutionResult(rows=[[10]]))
        # 表行数统计（注意用 "select count(*) from" 避免和 count(*)-count(...) 混淆）
        executor.set_response("select count(*) from", MockExecutionResult(rows=[[523400]]))
        # 采样数据
        executor.set_response("limit 2", MockExecutionResult(
            rows=[[1, 299.00, "paid", "2026-01-01 00:00:00"], [2, 599.00, "shipped", "2026-01-02 00:00:00"]],
        ))
        # MIN/MAX - 为不同列设置不同的 mock
        executor.set_response("min(`order_id`)", MockExecutionResult(rows=[[1, 100000]]))
        executor.set_response("min(`total_amount`)", MockExecutionResult(rows=[[0.01, 99999.99]]))
        executor.set_response("min(`created_at`)", MockExecutionResult(rows=[["2023-01-01", "2026-08-23"]]))
        # distinct count
        executor.set_response("count(distinct", MockExecutionResult(rows=[[5]]))
        # top values（最具体，最后注册 = 最高优先级）
        executor.set_response("`status` is not null", MockExecutionResult(
            rows=[["paid", 1000], ["shipped", 400]],
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
        executor.set_response("limit 5", MockExecutionResult(rows=[]))
        executor.set_response("count(*) - count", MockExecutionResult(rows=[[100]]))
        executor.set_response("min(`amount`)", MockExecutionResult(rows=[[0, 1000]]))
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
        executor.set_response("limit 5", MockExecutionResult(rows=[]))
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
        executor.set_response("limit 5", MockExecutionResult(rows=[]))
        executor.set_response("count(*) - count", MockExecutionResult(rows=[[0]]))
        executor.set_response("min(`id`)", MockExecutionResult(rows=[[0, 100]]))
        executor.set_response("count(distinct", MockExecutionResult(rows=[[3]]))
        executor.set_response("order by cnt desc", MockExecutionResult(rows=[]))

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

    def test_null_rate_with_zero_row_count(self):
        executor = MockExecutor()
        executor.set_response("count(*)", MockExecutionResult(rows=[[0]]))
        executor.set_response("limit 5", MockExecutionResult(rows=[]))
        executor.set_response("count(*) - count", MockExecutionResult(rows=[[0]]))

        profiler = SchemaProfiler(executor)
        table = Table(name="empty", columns=[Column(name="col", type="INT")])
        result = profiler.profile_table(table)
        assert result.row_count == 0
        # 0 行时 null_rate 应为 None（避免除以 0）
        assert result.get_column("col").null_rate is None


class TestWriteProfileToYaml:
    def test_write_and_reload(self):
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
            assert loaded.db_schema.profiling_enabled is True
        finally:
            os.unlink(tmp_path)
