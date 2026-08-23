"""测试 Schema 数据模型。"""

import pytest

from nl2sql.schema.models import Column, Table, Schema, DatasourceSchema


class TestColumn:
    def test_basic_creation(self):
        col = Column(name="id", type="bigint")
        assert col.name == "id"
        assert col.type == "bigint"
        assert col.description == ""
        assert col.is_primary_key is False
        assert col.is_foreign_key is False
        assert col.foreign_key_table is None
        assert col.foreign_key_column is None
        assert col.enum_values == []
        assert col.semantic_type is None

    def test_with_description_and_pk(self):
        col = Column(name="user_id", type="bigint", description="用户ID", is_primary_key=True)
        assert col.description == "用户ID"
        assert col.is_primary_key is True

    def test_foreign_key(self):
        col = Column(
            name="order_id",
            type="bigint",
            is_foreign_key=True,
            foreign_key_table="orders",
            foreign_key_column="id",
        )
        assert col.is_foreign_key is True
        assert col.foreign_key_table == "orders"
        assert col.foreign_key_column == "id"

    def test_enum_values(self):
        col = Column(name="status", type="varchar", enum_values=["active", "inactive", "pending"])
        assert col.enum_values == ["active", "inactive", "pending"]

    def test_semantic_type(self):
        col = Column(name="amount", type="decimal", semantic_type="amount")
        assert col.semantic_type == "amount"

    def test_all_semantic_types_allowed(self):
        for st in ["timestamp", "amount", "dimension", "category", "id"]:
            col = Column(name="x", type="varchar", semantic_type=st)
            assert col.semantic_type == st


class TestTable:
    def test_basic_creation(self):
        table = Table(name="users")
        assert table.name == "users"
        assert table.description == ""
        assert table.columns == []
        assert table.examples == []

    def test_with_columns(self):
        cols = [
            Column(name="id", type="bigint", is_primary_key=True),
            Column(name="name", type="varchar"),
            Column(name="email", type="varchar"),
        ]
        table = Table(name="users", description="用户表", columns=cols)
        assert table.description == "用户表"
        assert len(table.columns) == 3

    def test_column_names(self):
        cols = [
            Column(name="id", type="bigint"),
            Column(name="name", type="varchar"),
        ]
        table = Table(name="users", columns=cols)
        assert table.column_names == ["id", "name"]

    def test_get_column_found(self):
        cols = [
            Column(name="id", type="bigint"),
            Column(name="name", type="varchar"),
        ]
        table = Table(name="users", columns=cols)
        col = table.get_column("name")
        assert col is not None
        assert col.name == "name"
        assert col.type == "varchar"

    def test_get_column_not_found(self):
        table = Table(name="users", columns=[Column(name="id", type="bigint")])
        assert table.get_column("nonexistent") is None

    def test_with_examples(self):
        examples = [{"question": "用户总数", "sql": "SELECT COUNT(*) FROM users"}]
        table = Table(name="users", examples=examples)
        assert len(table.examples) == 1
        assert table.examples[0]["question"] == "用户总数"


class TestSchema:
    def test_basic_creation(self):
        schema = Schema()
        assert schema.tables == []

    def test_with_tables(self):
        tables = [Table(name="users"), Table(name="orders")]
        schema = Schema(tables=tables)
        assert len(schema.tables) == 2

    def test_table_names(self):
        schema = Schema(tables=[Table(name="users"), Table(name="orders")])
        assert schema.table_names == ["users", "orders"]

    def test_get_table_found(self):
        schema = Schema(tables=[Table(name="users"), Table(name="orders")])
        table = schema.get_table("orders")
        assert table is not None
        assert table.name == "orders"

    def test_get_table_not_found(self):
        schema = Schema(tables=[Table(name="users")])
        assert schema.get_table("products") is None


class TestDatasourceSchema:
    def test_full_structure(self):
        ds = DatasourceSchema(
            datasource_id="ecommerce_mysql",
            datasource_name="电商 MySQL 库",
            datasource_type="mysql",
            db_schema=Schema(
                tables=[
                    Table(
                        name="users",
                        description="用户表",
                        columns=[
                            Column(name="id", type="bigint", is_primary_key=True, semantic_type="id"),
                            Column(name="name", type="varchar", description="用户名", semantic_type="dimension"),
                            Column(name="status", type="varchar", enum_values=["active", "inactive"], semantic_type="category"),
                        ],
                    ),
                    Table(
                        name="orders",
                        description="订单表",
                        columns=[
                            Column(name="id", type="bigint", is_primary_key=True, semantic_type="id"),
                            Column(name="user_id", type="bigint", is_foreign_key=True,
                                   foreign_key_table="users", foreign_key_column="id", semantic_type="id"),
                            Column(name="amount", type="decimal", semantic_type="amount"),
                            Column(name="created_at", type="datetime", semantic_type="timestamp"),
                        ],
                    ),
                ]
            ),
        )

        assert ds.datasource_id == "ecommerce_mysql"
        assert ds.datasource_name == "电商 MySQL 库"
        assert ds.datasource_type == "mysql"
        assert len(ds.db_schema.tables) == 2
        assert ds.db_schema.table_names == ["users", "orders"]

        users = ds.db_schema.get_table("users")
        assert users is not None
        assert len(users.columns) == 3
        assert users.get_column("id").is_primary_key is True
        assert users.get_column("status").enum_values == ["active", "inactive"]

        orders = ds.db_schema.get_table("orders")
        assert orders is not None
        fk_col = orders.get_column("user_id")
        assert fk_col.is_foreign_key is True
        assert fk_col.foreign_key_table == "users"
        assert fk_col.foreign_key_column == "id"
        assert orders.get_column("amount").semantic_type == "amount"
        assert orders.get_column("created_at").semantic_type == "timestamp"

    def test_default_datasource_type(self):
        ds = DatasourceSchema(
            datasource_id="test",
            db_schema=Schema(tables=[]),
        )
        assert ds.datasource_type == "mysql"
        assert ds.datasource_name == ""


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


class TestSchemaProfilingConfig:
    def test_default_values(self):
        schema = Schema(tables=[])
        assert schema.profiling_enabled is True
        assert schema.sample_row_count == 5
        assert schema.max_rows_for_full_profiling == 1_000_000

    def test_custom_values(self):
        schema = Schema(
            tables=[],
            profiling_enabled=False,
            sample_row_count=3,
            max_rows_for_full_profiling=500_000,
        )
        assert schema.profiling_enabled is False
        assert schema.sample_row_count == 3
        assert schema.max_rows_for_full_profiling == 500_000
