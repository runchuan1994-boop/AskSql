"""测试 Schema API."""

import importlib
import os
import tempfile


def _reload_app_modules(tmpdir: str):
    """Set env vars and reload app modules so settings pick up the temp data dir."""
    os.environ["APP_DATA_DIR"] = os.path.join(tmpdir, "data")
    os.environ["APP_DATABASE_URL"] = f"sqlite:///{tmpdir}/data/test.db"

    from app.core import config as config_mod

    importlib.reload(config_mod)
    from app.core import database as db_mod

    importlib.reload(db_mod)
    from app import main as main_mod

    importlib.reload(main_mod)
    return main_mod


def _create_test_project(conn, project_id="proj-001", name="Test Project"):
    conn.execute(
        "INSERT INTO projects (id, name, description) VALUES (?, ?, ?)",
        (project_id, name, "A test project"),
    )
    conn.commit()


def _create_datasource(
    conn,
    datasource_id="ds-001",
    project_id="proj-001",
    name="测试数据源",
    dtype="mysql",
    schema_file=None,
):
    conn.execute(
        """INSERT INTO datasources (id, project_id, name, type, schema_file)
           VALUES (?, ?, ?, ?, ?)""",
        (datasource_id, project_id, name, dtype, schema_file),
    )
    conn.commit()


SAMPLE_SCHEMA_YAML = """
datasource:
  id: ds-001
  name: 电商 MySQL 库
  type: mysql

tables:
  - name: users
    description: 用户表，存储平台注册用户的基本信息
    columns:
      - name: id
        type: bigint
        description: 用户ID
        is_primary_key: true
        semantic_type: id
      - name: username
        type: varchar
        description: 用户名
        semantic_type: dimension
      - name: email
        type: varchar
        description: 邮箱地址
      - name: status
        type: varchar
        description: 用户状态
        enum_values:
          - active
          - inactive
          - banned
        semantic_type: category
    examples:
      - question: 上个月新增用户数
        sql: SELECT COUNT(*) FROM users
  - name: orders
    description: 订单表，存储用户的订单信息
    columns:
      - name: id
        type: bigint
        description: 订单ID
        is_primary_key: true
        semantic_type: id
      - name: user_id
        type: bigint
        description: 下单用户ID
        is_foreign_key: true
        foreign_key_table: users
        foreign_key_column: id
        semantic_type: id
"""


class TestGetProjectSchemas:
    def test_returns_schema_overview_for_project(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)

            # 写入 schema yaml 文件
            schemas_dir = os.path.join(tmpdir, "config", "schemas")
            os.makedirs(schemas_dir, exist_ok=True)
            schema_path = os.path.join(schemas_dir, "ecommerce.yaml")
            with open(schema_path, "w", encoding="utf-8") as f:
                f.write(SAMPLE_SCHEMA_YAML)

            _create_datasource(conn, schema_file=schema_path)
            conn.close()

            client = TestClient(main_mod.app)
            response = client.get("/api/schema?project_id=proj-001")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 1

            ds = data[0]
            assert ds["datasource_id"] == "ds-001"
            assert ds["datasource_name"] == "电商 MySQL 库"
            assert ds["datasource_type"] == "mysql"

            tables = ds["tables"]
            assert len(tables) == 2
            assert tables[0]["name"] == "users"
            assert "用户表" in tables[0]["description"]
            assert tables[0]["column_count"] == 4
            assert tables[1]["name"] == "orders"
            assert tables[1]["column_count"] == 2

    def test_datasource_without_schema_file_returns_note(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            _create_datasource(conn, datasource_id="ds-no-schema", schema_file=None)
            conn.close()

            client = TestClient(main_mod.app)
            response = client.get("/api/schema?project_id=proj-001")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["note"] == "尚未导入 schema"
            assert data[0]["datasource_id"] == "ds-no-schema"

    def test_datasource_with_missing_schema_file_returns_note(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            _create_datasource(
                conn,
                datasource_id="ds-bad-path",
                schema_file="/nonexistent/schema.yaml",
            )
            conn.close()

            client = TestClient(main_mod.app)
            response = client.get("/api/schema?project_id=proj-001")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["note"] == "尚未导入 schema"

    def test_multiple_datasources(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)

            schemas_dir = os.path.join(tmpdir, "config", "schemas")
            os.makedirs(schemas_dir, exist_ok=True)
            schema_path = os.path.join(schemas_dir, "ecommerce.yaml")
            with open(schema_path, "w", encoding="utf-8") as f:
                f.write(SAMPLE_SCHEMA_YAML)

            _create_datasource(conn, datasource_id="ds-001", name="第一个", schema_file=schema_path)
            _create_datasource(conn, datasource_id="ds-002", name="第二个", schema_file=None)
            conn.close()

            client = TestClient(main_mod.app)
            response = client.get("/api/schema?project_id=proj-001")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2


class TestGetTableDetail:
    def test_get_table_detail_success(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)

            schemas_dir = os.path.join(tmpdir, "config", "schemas")
            os.makedirs(schemas_dir, exist_ok=True)
            schema_path = os.path.join(schemas_dir, "ecommerce.yaml")
            with open(schema_path, "w", encoding="utf-8") as f:
                f.write(SAMPLE_SCHEMA_YAML)

            _create_datasource(conn, schema_file=schema_path)
            conn.close()

            client = TestClient(main_mod.app)
            response = client.get("/api/schema/table/ds-001/users")
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "users"
            assert "用户表" in data["description"]
            assert len(data["columns"]) == 4

            # 检查列详情
            id_col = next(c for c in data["columns"] if c["name"] == "id")
            assert id_col["type"] == "bigint"
            assert id_col["is_primary_key"] is True
            assert id_col["semantic_type"] == "id"

            status_col = next(c for c in data["columns"] if c["name"] == "status")
            assert status_col["is_primary_key"] is False
            assert status_col["is_foreign_key"] is False
            assert status_col["semantic_type"] == "category"
            assert status_col["enum_values"] == ["active", "inactive", "banned"]

            # 检查 examples
            assert len(data["examples"]) == 1
            assert data["examples"][0]["question"] == "上个月新增用户数"

    def test_get_table_with_foreign_key(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)

            schemas_dir = os.path.join(tmpdir, "config", "schemas")
            os.makedirs(schemas_dir, exist_ok=True)
            schema_path = os.path.join(schemas_dir, "ecommerce.yaml")
            with open(schema_path, "w", encoding="utf-8") as f:
                f.write(SAMPLE_SCHEMA_YAML)

            _create_datasource(conn, schema_file=schema_path)
            conn.close()

            client = TestClient(main_mod.app)
            response = client.get("/api/schema/table/ds-001/orders")
            assert response.status_code == 200
            data = response.json()

            user_id_col = next(c for c in data["columns"] if c["name"] == "user_id")
            assert user_id_col["is_foreign_key"] is True
            assert user_id_col["semantic_type"] == "id"

    def test_table_not_found_returns_404(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)

            schemas_dir = os.path.join(tmpdir, "config", "schemas")
            os.makedirs(schemas_dir, exist_ok=True)
            schema_path = os.path.join(schemas_dir, "ecommerce.yaml")
            with open(schema_path, "w", encoding="utf-8") as f:
                f.write(SAMPLE_SCHEMA_YAML)

            _create_datasource(conn, schema_file=schema_path)
            conn.close()

            client = TestClient(main_mod.app)
            response = client.get("/api/schema/table/ds-001/nonexistent_table")
            assert response.status_code == 404

    def test_datasource_not_found_returns_404(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            client = TestClient(main_mod.app)
            response = client.get("/api/schema/table/nonexistent-ds/users")
            assert response.status_code == 404

    def test_datasource_without_schema_returns_404(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            _create_datasource(conn, datasource_id="ds-no-schema", schema_file=None)
            conn.close()

            client = TestClient(main_mod.app)
            response = client.get("/api/schema/table/ds-no-schema/users")
            assert response.status_code == 404
