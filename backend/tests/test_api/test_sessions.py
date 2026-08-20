"""测试会话管理 API."""

import importlib
import json
import tempfile


def _reload_app_modules(tmpdir: str):
    """Set env vars and reload app modules so settings pick up the temp data dir."""
    import os

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


class TestCreateSession:
    def test_create_session_success(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            client = TestClient(main_mod.app)
            response = client.post(
                "/api/sessions",
                json={"project_id": "proj-001", "title": "我的对话"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["project_id"] == "proj-001"
            assert data["title"] == "我的对话"
            assert "id" in data
            assert len(data["id"]) > 10  # uuid long id

    def test_create_session_default_title(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            client = TestClient(main_mod.app)
            response = client.post(
                "/api/sessions",
                json={"project_id": "proj-001"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "新对话"


class TestListSessions:
    def test_list_sessions_returns_empty(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            client = TestClient(main_mod.app)
            response = client.get("/api/sessions?project_id=proj-001")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 0

    def test_list_sessions_ordered_by_updated_desc(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            client = TestClient(main_mod.app)
            client.post("/api/sessions", json={"project_id": "proj-001", "title": "第一个"})
            client.post("/api/sessions", json={"project_id": "proj-001", "title": "第二个"})

            response = client.get("/api/sessions?project_id=proj-001")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            # 按更新时间倒序，第二个（后创建的）应该在前
            assert data[0]["title"] == "第二个"
            assert data[1]["title"] == "第一个"


class TestGetSession:
    def test_get_session_success(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            client = TestClient(main_mod.app)
            create_resp = client.post(
                "/api/sessions",
                json={"project_id": "proj-001", "title": "测试会话"},
            )
            session_id = create_resp.json()["id"]

            response = client.get(f"/api/sessions/{session_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == session_id
            assert data["title"] == "测试会话"
            assert data["project_id"] == "proj-001"
            assert "created_at" in data
            assert "updated_at" in data

    def test_get_session_not_found(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            client = TestClient(main_mod.app)
            response = client.get("/api/sessions/nonexistent-id")
            assert response.status_code == 404


class TestUpdateSession:
    def test_update_session_title(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            client = TestClient(main_mod.app)
            create_resp = client.post(
                "/api/sessions",
                json={"project_id": "proj-001", "title": "旧标题"},
            )
            session_id = create_resp.json()["id"]

            response = client.patch(
                f"/api/sessions/{session_id}",
                json={"title": "新标题"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["title"] == "新标题"

    def test_update_session_not_found(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            client = TestClient(main_mod.app)
            response = client.patch(
                "/api/sessions/nonexistent-id",
                json={"title": "新标题"},
            )
            assert response.status_code == 404


class TestMessages:
    def test_get_messages_empty(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            client = TestClient(main_mod.app)
            create_resp = client.post(
                "/api/sessions",
                json={"project_id": "proj-001"},
            )
            session_id = create_resp.json()["id"]

            response = client.get(f"/api/sessions/{session_id}/messages")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 0

    def test_add_and_get_messages_in_order(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            client = TestClient(main_mod.app)
            create_resp = client.post(
                "/api/sessions",
                json={"project_id": "proj-001"},
            )
            session_id = create_resp.json()["id"]

            # 添加用户消息
            from app.services.session_service import add_message

            msg1 = add_message(session_id, "user", "你好")
            msg2 = add_message(session_id, "assistant", "你好！我可以帮你查询数据", sql_text="SELECT 1", result={"rows": [{"1": 1}]})

            assert msg1["role"] == "user"
            assert msg2["role"] == "assistant"
            assert msg2["sql_text"] == "SELECT 1"

            response = client.get(f"/api/sessions/{session_id}/messages")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["role"] == "user"
            assert data[1]["role"] == "assistant"
            assert data[1]["result"] is not None
            assert data[1]["result"]["rows"] == [{"1": 1}]


class TestDeleteSession:
    def test_delete_session_success(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            client = TestClient(main_mod.app)
            create_resp = client.post(
                "/api/sessions",
                json={"project_id": "proj-001"},
            )
            session_id = create_resp.json()["id"]

            response = client.delete(f"/api/sessions/{session_id}")
            assert response.status_code == 200
            assert response.json()["deleted"] is True

            # 确认已删除
            get_resp = client.get(f"/api/sessions/{session_id}")
            assert get_resp.status_code == 404

    def test_delete_nonexistent_session_returns_404(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            main_mod = _reload_app_modules(tmpdir)
            client = TestClient(main_mod.app)
            response = client.delete("/api/sessions/nonexistent-id")
            assert response.status_code == 404


class TestUpdateTitleFromQuery:
    def test_update_title_when_default(self):
        from app.services.session_service import (
            create_session,
            get_session,
            update_session_title_from_query,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            session = create_session("proj-001")
            assert session["title"] == "新对话"

            update_session_title_from_query(session["id"], "查询上个月的订单总金额有多少")
            updated = get_session(session["id"])
            assert updated["title"] == "查询上个月的订单总金额有多少"

    def test_update_title_truncates_long_query(self):
        from app.services.session_service import (
            create_session,
            get_session,
            update_session_title_from_query,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            session = create_session("proj-001")
            long_query = "这是一个非常非常非常非常非常非常非常非常非常非常长的查询问题超过30个字"
            update_session_title_from_query(session["id"], long_query)
            updated = get_session(session["id"])
            assert len(updated["title"]) == 30

    def test_do_not_update_if_title_not_default(self):
        from app.services.session_service import (
            create_session,
            get_session,
            update_session_title_from_query,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            from app.core.database import get_connection

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            session = create_session("proj-001", title="自定义标题")
            update_session_title_from_query(session["id"], "查询订单数据")
            updated = get_session(session["id"])
            assert updated["title"] == "自定义标题"
