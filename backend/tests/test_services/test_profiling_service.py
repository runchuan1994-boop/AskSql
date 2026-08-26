"""测试 profiling service。"""

from app.services.profiling_service import (
    get_profiling_status,
    _set_status,
    _profiling_status,
)


class TestProfilingService:
    def test_get_status_not_started(self):
        # 用一个不存在的 datasource_id
        status = get_profiling_status("nonexistent_ds")
        assert status["status"] == "not_started"
        assert status["progress"] == 0
        assert status["total_tables"] == 0

    def test_set_and_get_status(self):
        _set_status("test_ds_123", "running", progress=5, total_tables=10, current_table="orders")
        status = get_profiling_status("test_ds_123")
        assert status["status"] == "running"
        assert status["progress"] == 5
        assert status["total_tables"] == 10
        assert status["current_table"] == "orders"

        # 清理
        _profiling_status.pop("test_ds_123", None)

    def test_status_is_copy_not_reference(self):
        _set_status("test_ds_copy", "running", progress=1)
        status = get_profiling_status("test_ds_copy")
        status["progress"] = 999  # 修改返回值
        # 原始值不应改变
        status2 = get_profiling_status("test_ds_copy")
        assert status2["progress"] == 1

        _profiling_status.pop("test_ds_copy", None)

    def test_start_profiling_returns_status(self):
        from app.services.profiling_service import start_profiling
        # 用一个不存在的数据源，应该能启动但很快失败
        result = start_profiling("nonexistent_ds_for_test")
        assert "status" in result
        assert result["status"] in ("pending",)

        # 清理
        _profiling_status.pop("nonexistent_ds_for_test", None)

    def test_start_profiling_idempotent(self):
        from app.services.profiling_service import start_profiling
        ds_id = "test_idempotent_ds"
        _set_status(ds_id, "running", progress=0, total_tables=5)

        result = start_profiling(ds_id)
        # 已经在运行，不应重复启动
        assert "already in progress" in result.get("message", "").lower()

        _profiling_status.pop(ds_id, None)
