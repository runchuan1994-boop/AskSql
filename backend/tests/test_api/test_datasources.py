import importlib
import os
import sqlite3
import tempfile


def _reload_app_modules(tmpdir: str):
    """Set env vars and reload app modules so settings pick up the temp data dir."""
    os.environ["APP_DATA_DIR"] = os.path.join(tmpdir, "data")
    os.environ["APP_DATABASE_URL"] = f"sqlite:///{tmpdir}/data/test.db"
    os.environ["APP_SCHEMAS_DIR"] = os.path.join(tmpdir, "schemas")

    from app.core import config as config_mod

    importlib.reload(config_mod)
    from app.core import database as db_mod

    importlib.reload(db_mod)
    from app.services import project_service as ps_mod

    importlib.reload(ps_mod)
    from app.services import datasource_service as ds_mod

    importlib.reload(ds_mod)
    from app.services import schema_import as si_mod

    importlib.reload(si_mod)
    from app.api import projects as projects_mod

    importlib.reload(projects_mod)
    from app.api import datasources as datasources_mod

    importlib.reload(datasources_mod)
    import app.api as api_mod

    importlib.reload(api_mod)
    from app import main as main_mod

    importlib.reload(main_mod)
    return main_mod


def _create_project(client):
    resp = client.post("/api/projects", json={"name": "Test Project"})
    assert resp.status_code == 200
    return resp.json()["id"]


def test_create_datasource():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)
        project_id = _create_project(client)

        response = client.post(
            "/api/datasources",
            json={
                "project_id": project_id,
                "name": "Test DS",
                "type": "sqlite",
                "database": ":memory:",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["name"] == "Test DS"
        assert data["type"] == "sqlite"
        assert "password" not in data
        assert "password_encrypted" not in data


def test_list_datasources():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)
        project_id = _create_project(client)

        client.post(
            "/api/datasources",
            json={
                "project_id": project_id,
                "name": "DS1",
                "type": "sqlite",
                "database": ":memory:",
            },
        )
        client.post(
            "/api/datasources",
            json={
                "project_id": project_id,
                "name": "DS2",
                "type": "sqlite",
                "database": ":memory:",
            },
        )

        response = client.get(f"/api/datasources?project_id={project_id}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2


def test_get_datasource():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)
        project_id = _create_project(client)

        create_resp = client.post(
            "/api/datasources",
            json={
                "project_id": project_id,
                "name": "Get DS",
                "type": "sqlite",
                "database": ":memory:",
            },
        )
        ds_id = create_resp.json()["id"]

        response = client.get(f"/api/datasources/{ds_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == ds_id
        assert data["name"] == "Get DS"
        assert "password" not in data


def test_get_nonexistent_datasource_returns_404():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)
        response = client.get("/api/datasources/nonexistent")
        assert response.status_code == 404


def test_update_datasource():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)
        project_id = _create_project(client)

        create_resp = client.post(
            "/api/datasources",
            json={
                "project_id": project_id,
                "name": "Old DS",
                "type": "sqlite",
                "database": ":memory:",
            },
        )
        ds_id = create_resp.json()["id"]

        response = client.patch(
            f"/api/datasources/{ds_id}",
            json={"name": "New DS Name"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New DS Name"


def test_delete_datasource():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)
        project_id = _create_project(client)

        create_resp = client.post(
            "/api/datasources",
            json={
                "project_id": project_id,
                "name": "To Delete",
                "type": "sqlite",
                "database": ":memory:",
            },
        )
        ds_id = create_resp.json()["id"]

        response = client.delete(f"/api/datasources/{ds_id}")
        assert response.status_code == 200
        assert response.json()["success"] is True

        get_resp = client.get(f"/api/datasources/{ds_id}")
        assert get_resp.status_code == 404


def test_test_connection_sqlite_memory():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)
        project_id = _create_project(client)

        create_resp = client.post(
            "/api/datasources",
            json={
                "project_id": project_id,
                "name": "Conn Test",
                "type": "sqlite",
                "database": ":memory:",
            },
        )
        ds_id = create_resp.json()["id"]

        response = client.post(f"/api/datasources/{ds_id}/test-connection")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


def test_import_schema():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)

        # Create a temporary SQLite file database with sample tables
        db_path = os.path.join(tmpdir, "sample.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT, created_at TIMESTAMP)"
        )
        conn.execute(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, status TEXT, FOREIGN KEY (user_id) REFERENCES users(id))"
        )
        conn.commit()
        conn.close()

        client = TestClient(main_mod.app)
        project_id = _create_project(client)

        create_resp = client.post(
            "/api/datasources",
            json={
                "project_id": project_id,
                "name": "Import Test",
                "type": "sqlite",
                "database": db_path,
            },
        )
        ds_id = create_resp.json()["id"]

        response = client.post(f"/api/datasources/{ds_id}/import-schema")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["table_count"] == 2
        assert len(data["tables"]) == 2
        table_names = [t["name"] for t in data["tables"]]
        assert "users" in table_names
        assert "orders" in table_names


def test_import_schema_file_is_created():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)

        db_path = os.path.join(tmpdir, "sample.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()
        conn.close()

        client = TestClient(main_mod.app)
        project_id = _create_project(client)

        create_resp = client.post(
            "/api/datasources",
            json={
                "project_id": project_id,
                "name": "Schema File Test",
                "type": "sqlite",
                "database": db_path,
            },
        )
        ds_id = create_resp.json()["id"]

        client.post(f"/api/datasources/{ds_id}/import-schema")

        # Check that the schema YAML file was created
        schema_dir = os.path.join(tmpdir, "schemas", project_id)
        schema_files = os.listdir(schema_dir)
        assert len(schema_files) >= 1
        yaml_files = [f for f in schema_files if f.endswith(".yaml") or f.endswith(".yml")]
        assert len(yaml_files) >= 1


def test_import_schema_nonexistent_datasource_returns_404():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)

        response = client.post("/api/datasources/nonexistent/import-schema")
        assert response.status_code == 404


def test_password_is_encrypted_in_db():
    """Verify password is stored encrypted, not plaintext."""
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)
        project_id = _create_project(client)

        response = client.post(
            "/api/datasources",
            json={
                "project_id": project_id,
                "name": "Pwd Test",
                "type": "mysql",
                "host": "localhost",
                "port": 3306,
                "database": "db",
                "username": "user",
                "password": "secret123",
            },
        )
        assert response.status_code == 200
        ds_id = response.json()["id"]

        # Directly query the DB to verify password is encrypted
        from app.core.database import get_connection

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT password_encrypted FROM datasources WHERE id = ?",
                (ds_id,),
            )
            row = cursor.fetchone()
            assert row is not None
            encrypted = row["password_encrypted"]
            assert encrypted is not None
            assert encrypted != "secret123"
            assert "secret123" not in encrypted
        finally:
            conn.close()
