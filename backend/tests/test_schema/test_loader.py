"""测试 Schema YAML 加载器。"""

import os
import tempfile

import pytest

from nl2sql.schema.loader import SchemaLoader
from nl2sql.schema.models import DatasourceSchema, Column, Table, Schema

SAMPLE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "schemas", "sample"
)
ECOMMERCE_YAML = os.path.join(SAMPLE_DIR, "ecommerce.yaml")


class TestSchemaLoaderLoadFromYaml:
    def test_load_ecommerce_sample(self):
        loader = SchemaLoader()
        ds = loader.load_from_yaml(ECOMMERCE_YAML)

        assert isinstance(ds, DatasourceSchema)
        assert ds.datasource_id == "ecommerce_mysql"
        assert ds.datasource_name == "电商 MySQL 库"
        assert ds.datasource_type == "mysql"

        schema = ds.db_schema
        assert isinstance(schema, Schema)
        assert len(schema.tables) == 2
        assert schema.table_names == ["users", "orders"]

    def test_users_table_structure(self):
        loader = SchemaLoader()
        ds = loader.load_from_yaml(ECOMMERCE_YAML)
        users = ds.db_schema.get_table("users")

        assert users is not None
        assert users.name == "users"
        assert "用户表" in users.description
        assert len(users.columns) == 5

        id_col = users.get_column("id")
        assert id_col is not None
        assert id_col.type == "bigint"
        assert id_col.is_primary_key is True
        assert id_col.semantic_type == "id"

        status_col = users.get_column("status")
        assert status_col is not None
        assert status_col.semantic_type == "category"
        assert status_col.enum_values == ["active", "inactive", "banned"]

        created_col = users.get_column("created_at")
        assert created_col is not None
        assert created_col.semantic_type == "timestamp"

        assert len(users.examples) == 2
        assert users.examples[0]["question"] == "上个月新增用户数"

    def test_orders_table_foreign_key(self):
        loader = SchemaLoader()
        ds = loader.load_from_yaml(ECOMMERCE_YAML)
        orders = ds.db_schema.get_table("orders")

        assert orders is not None
        user_id_col = orders.get_column("user_id")
        assert user_id_col is not None
        assert user_id_col.is_foreign_key is True
        assert user_id_col.foreign_key_table == "users"
        assert user_id_col.foreign_key_column == "id"

        total_amount = orders.get_column("total_amount")
        assert total_amount is not None
        assert total_amount.semantic_type == "amount"

    def test_minimal_yaml(self):
        yaml_content = """
datasource:
  id: test_db
tables:
  - name: items
    columns:
      - name: id
        type: int
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            tmp_path = f.name

        try:
            loader = SchemaLoader()
            ds = loader.load_from_yaml(tmp_path)
            assert ds.datasource_id == "test_db"
            assert ds.datasource_name == ""
            assert ds.datasource_type == "mysql"
            assert len(ds.db_schema.tables) == 1
            assert ds.db_schema.get_table("items").columns[0].name == "id"
        finally:
            os.unlink(tmp_path)

    def test_file_not_found_raises(self):
        loader = SchemaLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_from_yaml("/nonexistent/path/schema.yaml")

    def test_enriched_yaml_fields(self):
        yaml_content = """
datasource:
  id: test_db
  name: test
  type: mysql
profiling:
  enabled: true
  sample_row_count: 3
  max_rows_for_full_profiling: 500000
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

            # profiling 配置
            assert ds.db_schema.profiling_enabled is True
            assert ds.db_schema.sample_row_count == 3
            assert ds.db_schema.max_rows_for_full_profiling == 500000

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
            assert ds.db_schema.profiling_enabled is True  # 默认开启

            id_col = items.get_column("id")
            assert id_col.business_name == ""
            assert id_col.distinct_count is None
            assert id_col.top_values == []
            assert id_col.null_rate is None
        finally:
            os.unlink(tmp_path)


class TestSchemaLoaderLoadFromDirectory:
    def test_load_sample_directory(self):
        loader = SchemaLoader()
        dses = loader.load_from_directory(SAMPLE_DIR)

        assert isinstance(dses, list)
        assert len(dses) >= 1
        assert all(isinstance(ds, DatasourceSchema) for ds in dses)

        ids = [ds.datasource_id for ds in dses]
        assert "ecommerce_mysql" in ids

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = SchemaLoader()
            dses = loader.load_from_directory(tmpdir)
            assert dses == []

    def test_directory_not_found_raises(self):
        loader = SchemaLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_from_directory("/nonexistent/dir/")

    def test_only_yaml_files_loaded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a yaml file
            with open(os.path.join(tmpdir, "a.yaml"), "w") as f:
                f.write("datasource:\n  id: a\ntables: []\n")
            # Write a yml file
            with open(os.path.join(tmpdir, "b.yml"), "w") as f:
                f.write("datasource:\n  id: b\ntables: []\n")
            # Write a non-yaml file
            with open(os.path.join(tmpdir, "c.txt"), "w") as f:
                f.write("not yaml")

            loader = SchemaLoader()
            dses = loader.load_from_directory(tmpdir)
            assert len(dses) == 2
            ids = sorted(ds.datasource_id for ds in dses)
            assert ids == ["a", "b"]
