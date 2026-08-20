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


def test_health_endpoint_returns_200():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        client = TestClient(main_mod.app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "app_name" in data


def test_api_root_returns_200():
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        # Add a simple root route to the api router for testing
        from app.api import router

        @router.get("/")
        async def api_root():
            return {"message": "API root"}

        client = TestClient(main_mod.app)
        response = client.get("/api/")
        assert response.status_code == 200


def test_app_title_is_nl2sql_agent():
    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        assert main_mod.app.title == "NL2SQL Agent"


def test_db_file_is_created():
    with tempfile.TemporaryDirectory() as tmpdir:
        main_mod = _reload_app_modules(tmpdir)
        db_path = os.path.join(tmpdir, "data", "test.db")
        assert os.path.exists(db_path), f"Database file not created at {db_path}"
