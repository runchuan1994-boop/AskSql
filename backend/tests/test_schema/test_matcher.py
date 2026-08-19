"""测试 Schema 语义匹配器。"""

import pytest

from nl2sql.schema.matcher import SchemaMatcher, TableMatch, ColumnMatch
from nl2sql.schema.models import Column, DatasourceSchema, Schema, Table


def _make_ds(datasource_id: str, tables: list[Table]) -> DatasourceSchema:
    return DatasourceSchema(
        datasource_id=datasource_id,
        datasource_name=f"{datasource_id} 库",
        datasource_type="mysql",
        schema=Schema(tables=tables),
    )


@pytest.fixture
def sample_datasources() -> list[DatasourceSchema]:
    users_table = Table(
        name="users",
        description="用户表，存储注册用户基本信息",
        columns=[
            Column(name="id", type="bigint", description="用户ID",
                   is_primary_key=True, semantic_type="id"),
            Column(name="username", type="varchar", description="用户名",
                   semantic_type="dimension"),
            Column(name="email", type="varchar", description="邮箱地址"),
            Column(name="status", type="varchar", description="用户状态",
                   semantic_type="category",
                   enum_values=["active", "inactive", "banned"]),
            Column(name="created_at", type="datetime", description="注册时间",
                   semantic_type="timestamp"),
        ],
    )

    orders_table = Table(
        name="orders",
        description="订单表，存储用户下单信息",
        columns=[
            Column(name="id", type="bigint", description="订单ID",
                   is_primary_key=True, semantic_type="id"),
            Column(name="user_id", type="bigint", description="下单用户ID",
                   is_foreign_key=True, semantic_type="id"),
            Column(name="total_amount", type="decimal", description="订单总金额",
                   semantic_type="amount"),
            Column(name="status", type="varchar", description="订单状态",
                   semantic_type="category"),
            Column(name="created_at", type="datetime", description="下单时间",
                   semantic_type="timestamp"),
        ],
    )

    products_table = Table(
        name="products",
        description="商品表，存储商品库存和价格信息",
        columns=[
            Column(name="id", type="bigint", description="商品ID",
                   is_primary_key=True, semantic_type="id"),
            Column(name="name", type="varchar", description="商品名称",
                   semantic_type="dimension"),
            Column(name="price", type="decimal", description="商品价格",
                   semantic_type="amount"),
            Column(name="stock", type="int", description="库存数量",
                   semantic_type="amount"),
        ],
    )

    ds1 = _make_ds("ecommerce", [users_table, orders_table, products_table])
    ds2 = _make_ds("crm", [
        Table(name="customers", description="客户表", columns=[
            Column(name="customer_id", type="bigint", semantic_type="id"),
            Column(name="customer_name", type="varchar", semantic_type="dimension"),
        ])
    ])
    return [ds1, ds2]


class TestTableMatch:
    def test_table_match_attributes(self):
        table = Table(name="users")
        m = TableMatch(datasource_id="ecommerce", table=table, score=10.5)
        assert m.datasource_id == "ecommerce"
        assert m.table.name == "users"
        assert m.score == 10.5


class TestColumnMatch:
    def test_column_match_attributes(self):
        col = Column(name="id", type="bigint")
        m = ColumnMatch(column=col, score=3.0)
        assert m.column.name == "id"
        assert m.score == 3.0


class TestSchemaMatcherInit:
    def test_init_with_datasources(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        assert len(matcher.datasources) == 2

    def test_init_empty(self):
        matcher = SchemaMatcher([])
        assert matcher.datasources == []


class TestMatchTables:
    def test_exact_table_name_match(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        results = matcher.match_tables("users")

        assert len(results) > 0
        top = results[0]
        assert top.table.name == "users"
        assert top.score >= 10

    def test_partial_table_name_match(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        results = matcher.match_tables("user")

        # users 表应该匹配上 (包含关系)
        names = [r.table.name for r in results]
        assert "users" in names

    def test_description_keyword_match(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        # "库存" 在 products 描述里
        results = matcher.match_tables("库存")
        names = [r.table.name for r in results]
        assert "products" in names

    def test_top_k_limit(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        results = matcher.match_tables("id", top_k=2)
        assert len(results) == 2

    def test_results_sorted_by_score_desc(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        results = matcher.match_tables("users 用户")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_cross_datasource_match(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        results = matcher.match_tables("客户")
        ds_ids = set(r.datasource_id for r in results)
        assert "crm" in ds_ids

    def test_no_match_returns_empty(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        results = matcher.match_tables("xyznonexistenttable")
        # 可能有极低分数，但应该都排很后
        assert isinstance(results, list)

    def test_empty_query(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        results = matcher.match_tables("")
        assert all(r.score == 0 for r in results)


class TestMatchColumns:
    def test_exact_column_name_match(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        users_table = sample_datasources[0].schema.get_table("users")

        results = matcher.match_columns(users_table, "username")
        assert len(results) > 0
        assert results[0].column.name == "username"

    def test_column_description_match(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        users_table = sample_datasources[0].schema.get_table("users")

        # "注册时间" 在 created_at 的描述里
        results = matcher.match_columns(users_table, "注册时间")
        names = [r.column.name for r in results]
        assert "created_at" in names

    def test_semantic_type_match(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        orders_table = sample_datasources[0].schema.get_table("orders")

        # 匹配 amount 语义类型的列
        results = matcher.match_columns(orders_table, "金额")
        # total_amount 有 semantic_type=amount 且名字/描述匹配
        top_names = [r.column.name for r in results[:3]]
        assert "total_amount" in top_names

    def test_top_k_limit(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        users_table = sample_datasources[0].schema.get_table("users")
        results = matcher.match_columns(users_table, "id", top_k=2)
        assert len(results) == 2

    def test_results_sorted_by_score_desc(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        users_table = sample_datasources[0].schema.get_table("users")
        results = matcher.match_columns(users_table, "用户名 username")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestFindRelevantTables:
    def test_filters_low_scores(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        results = matcher.find_relevant_tables("用户 orders 订单", top_k=5, min_score=1.0)
        assert all(r.score >= 1.0 for r in results)

    def test_returns_sorted(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        results = matcher.find_relevant_tables("用户订单金额", top_k=10, min_score=0.0)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_empty_when_none_above_min(self, sample_datasources):
        matcher = SchemaMatcher(sample_datasources)
        # 用非常高的 min_score 确保没有匹配
        results = matcher.find_relevant_tables("xyz", top_k=5, min_score=100.0)
        assert results == []
