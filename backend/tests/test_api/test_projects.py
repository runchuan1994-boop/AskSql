import importlib
import os
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
    from app.api import projects as projects_mod

    importlib.reload(projects_mod)
    import app.api as api_mod

    importlib.reload(api_mod)
    from app import main as main_mod

    importlib.reload(main_mod)
    return main_mod


def test_create_project_returns_200_with_id():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)

        response = client.post("/api/projects", json={"name": "Test Project"})
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["name"] == "Test Project"
        assert data["description"] == ""
        assert len(data["id"]) == 8


def test_create_project_with_description():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)

        response = client.post(
            "/api/projects",
            json={"name": "Proj", "description": "A test project"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "A test project"


def test_list_projects():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)

        # Create two projects
        client.post("/api/projects", json={"name": "Project A"})
        client.post("/api/projects", json={"name": "Project B"})

        response = client.get("/api/projects")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        names = [p["name"] for p in data]
        assert "Project A" in names
        assert "Project B" in names


def test_get_project_by_id():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)

        create_resp = client.post("/api/projects", json={"name": "Detail Project"})
        project_id = create_resp.json()["id"]

        response = client.get(f"/api/projects/{project_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == "Detail Project"


def test_get_nonexistent_project_returns_404():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)

        response = client.get("/api/projects/nonexistent")
        assert response.status_code == 404


def test_update_project_name():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)

        create_resp = client.post("/api/projects", json={"name": "Old Name"})
        project_id = create_resp.json()["id"]

        response = client.patch(
            f"/api/projects/{project_id}",
            json={"name": "New Name"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["id"] == project_id


def test_update_project_description():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)

        create_resp = client.post("/api/projects", json={"name": "P1"})
        project_id = create_resp.json()["id"]

        response = client.patch(
            f"/api/projects/{project_id}",
            json={"description": "New desc"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "New desc"
        assert data["name"] == "P1"


def test_update_nonexistent_project_returns_404():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)

        response = client.patch(
            "/api/projects/nonexistent",
            json={"name": "anything"},
        )
        assert response.status_code == 404


def test_delete_project():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)

        create_resp = client.post("/api/projects", json={"name": "To Delete"})
        project_id = create_resp.json()["id"]

        response = client.delete(f"/api/projects/{project_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify it's gone
        get_resp = client.get(f"/api/projects/{project_id}")
        assert get_resp.status_code == 404


def test_delete_nonexistent_project_returns_404():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)

        response = client.delete("/api/projects/nonexistent")
        assert response.status_code == 404


def test_create_project_creates_schema_directory():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)

        create_resp = client.post("/api/projects", json={"name": "Schema Dir Test"})
        project_id = create_resp.json()["id"]

        schema_dir = os.path.join(tmpdir, "schemas", project_id)
        assert os.path.isdir(schema_dir), f"Schema dir not created at {schema_dir}"
