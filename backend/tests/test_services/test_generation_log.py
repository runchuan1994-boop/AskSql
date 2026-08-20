"""测试生成日志服务."""

from __future__ import annotations

import importlib
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
    # re-init db tables
    db_mod.init_db()
    return db_mod


def _create_test_project(conn, project_id="proj-001", name="Test Project"):
    conn.execute(
        "INSERT INTO projects (id, name, description) VALUES (?, ?, ?)",
        (project_id, name, "A test project"),
    )
    conn.commit()


class TestLogGeneration:
    def test_log_generation_returns_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            from app.core.database import get_connection
            from app.services.generation_log import log_generation

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            log_id = log_generation(
                project_id="proj-001",
                datasource_id="ds-001",
                session_id="sess-001",
                user_query="查询用户总数",
                generated_sql="SELECT COUNT(*) FROM users",
                intent_summary="统计用户数量",
                execution_success=True,
                execution_time_ms=120,
                row_count=1,
                error_message=None,
                iteration=1,
                reflection_notes="结果满意",
                model="test-model",
                final_selected=True,
            )

            assert isinstance(log_id, str)
            assert len(log_id) > 0

            # Verify stored in DB
            conn = get_connection()
            row = conn.execute(
                "SELECT * FROM generation_logs WHERE id = ?",
                (log_id,),
            ).fetchone()
            conn.close()

            assert row is not None
            assert row["project_id"] == "proj-001"
            assert row["datasource_id"] == "ds-001"
            assert row["session_id"] == "sess-001"
            assert row["user_query"] == "查询用户总数"
            assert row["generated_sql"] == "SELECT COUNT(*) FROM users"
            assert row["intent_summary"] == "统计用户数量"
            assert row["execution_success"] == 1
            assert row["execution_time_ms"] == 120
            assert row["row_count"] == 1
            assert row["error_message"] is None
            assert row["iteration"] == 1
            assert row["reflection_notes"] == "结果满意"
            assert row["model"] == "test-model"
            assert row["final_selected"] == 1

    def test_log_generation_with_optional_fields_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            from app.core.database import get_connection
            from app.services.generation_log import log_generation

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            log_id = log_generation(
                project_id="proj-001",
                datasource_id=None,
                session_id=None,
                user_query="test",
                generated_sql=None,
                intent_summary=None,
                execution_success=False,
                execution_time_ms=0,
                row_count=0,
                error_message="something went wrong",
                iteration=0,
                reflection_notes=None,
                model=None,
                final_selected=False,
            )

            assert isinstance(log_id, str)

            conn = get_connection()
            row = conn.execute(
                "SELECT * FROM generation_logs WHERE id = ?",
                (log_id,),
            ).fetchone()
            conn.close()

            assert row is not None
            assert row["datasource_id"] is None
            assert row["session_id"] is None
            assert row["generated_sql"] is None
            assert row["execution_success"] == 0
            assert row["error_message"] == "something went wrong"
            assert row["final_selected"] == 0


class TestListGenerationLogs:
    def test_list_logs_ordered_by_time_desc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            from app.core.database import get_connection
            from app.services.generation_log import list_generation_logs, log_generation

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            log_id1 = log_generation(
                project_id="proj-001",
                datasource_id="ds-1",
                session_id="sess-1",
                user_query="第一个查询",
                generated_sql="SELECT 1",
                intent_summary="",
                execution_success=True,
                execution_time_ms=10,
                row_count=1,
                error_message=None,
                iteration=1,
                reflection_notes=None,
                model="m1",
                final_selected=True,
            )

            log_id2 = log_generation(
                project_id="proj-001",
                datasource_id="ds-2",
                session_id="sess-2",
                user_query="第二个查询",
                generated_sql="SELECT 2",
                intent_summary="",
                execution_success=True,
                execution_time_ms=20,
                row_count=1,
                error_message=None,
                iteration=1,
                reflection_notes=None,
                model="m2",
                final_selected=True,
            )

            logs = list_generation_logs("proj-001")

            assert isinstance(logs, list)
            assert len(logs) == 2
            # 按时间倒序，第二个应该在前
            assert logs[0]["id"] == log_id2
            assert logs[1]["id"] == log_id1

    def test_list_logs_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            from app.core.database import get_connection
            from app.services.generation_log import list_generation_logs, log_generation

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            for i in range(5):
                log_generation(
                    project_id="proj-001",
                    datasource_id=f"ds-{i}",
                    session_id=f"sess-{i}",
                    user_query=f"查询{i}",
                    generated_sql=f"SELECT {i}",
                    intent_summary="",
                    execution_success=True,
                    execution_time_ms=10,
                    row_count=1,
                    error_message=None,
                    iteration=1,
                    reflection_notes=None,
                    model="m",
                    final_selected=True,
                )

            logs = list_generation_logs("proj-001", limit=3)
            assert len(logs) == 3

    def test_list_logs_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _reload_app_modules(tmpdir)
            from app.core.database import get_connection
            from app.services.generation_log import list_generation_logs

            conn = get_connection()
            _create_test_project(conn)
            conn.close()

            logs = list_generation_logs("proj-001")
            assert logs == []
