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
            schema=Schema(
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
        assert len(ds.schema.tables) == 2
        assert ds.schema.table_names == ["users", "orders"]

        users = ds.schema.get_table("users")
        assert users is not None
        assert len(users.columns) == 3
        assert users.get_column("id").is_primary_key is True
        assert users.get_column("status").enum_values == ["active", "inactive"]

        orders = ds.schema.get_table("orders")
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
            schema=Schema(tables=[]),
        )
        assert ds.datasource_type == "mysql"
        assert ds.datasource_name == ""
