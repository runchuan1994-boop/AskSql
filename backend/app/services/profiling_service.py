"""Schema 探测服务：管理异步探测任务和状态。"""

from __future__ import annotations

import threading
import time

from app.core.database import get_connection
from app.services.datasource_service import build_db_url, get_datasource
from nl2sql.executor.factory import create_executor
from nl2sql.schema.loader import SchemaLoader
from nl2sql.schema.profiler import SchemaProfiler, write_profile_to_yaml


# 内存中的探测状态（进程级，重启丢失，但探测可重跑）
_profiling_status: dict[str, dict] = {}
_profiling_lock = threading.Lock()


def _set_status(datasource_id: str, status: str, **kwargs) -> None:
    with _profiling_lock:
        entry = _profiling_status.setdefault(datasource_id, {
            "status": status,
            "progress": 0,
            "total_tables": 0,
            "current_table": "",
            "started_at": None,
            "finished_at": None,
            "error": None,
        })
        entry["status"] = status
        for k, v in kwargs.items():
            entry[k] = v


def get_profiling_status(datasource_id: str) -> dict:
    """获取指定数据源的探测状态。"""
    with _profiling_lock:
        status = _profiling_status.get(datasource_id)
        if status is None:
            return {
                "status": "not_started",
                "progress": 0,
                "total_tables": 0,
                "current_table": "",
                "started_at": None,
                "finished_at": None,
                "error": None,
            }
        return dict(status)


def start_profiling(datasource_id: str) -> dict:
    """启动异步探测任务。

    Returns:
        启动时的状态信息
    """
    status = get_profiling_status(datasource_id)
    if status["status"] in ("running", "pending"):
        return {"status": status["status"], "message": "Profiling already in progress"}

    _set_status(datasource_id, "pending", started_at=time.time())

    # 在新线程中运行探测
    t = threading.Thread(
        target=_run_profiling,
        args=(datasource_id,),
        daemon=True,
        name=f"profiling-{datasource_id}",
    )
    t.start()

    return {"status": "pending", "message": "Profiling started"}


def _run_profiling(datasource_id: str) -> None:
    """在后台线程中执行探测。"""
    import logging

    logger = logging.getLogger(__name__)

    try:
        _set_status(datasource_id, "running")

        # 1. 获取数据源信息
        ds = get_datasource(datasource_id, include_password=True)
        if ds is None:
            _set_status(
                datasource_id, "failed",
                error="Datasource not found",
                finished_at=time.time(),
            )
            return

        schema_file = ds.get("schema_file", "")
        if not schema_file:
            _set_status(
                datasource_id, "failed",
                error="No schema file, import schema first",
                finished_at=time.time(),
            )
            return

        # 2. 加载当前 schema
        loader = SchemaLoader()
        ds_schema = loader.load_from_yaml(schema_file)

        total_tables = len(ds_schema.db_schema.tables)
        _set_status(
            datasource_id, "running",
            total_tables=total_tables, progress=0,
        )

        # 3. 检查 profiling 是否启用
        if not ds_schema.db_schema.profiling_enabled:
            _set_status(
                datasource_id, "skipped",
                error="Profiling disabled in schema config",
                finished_at=time.time(),
            )
            return

        # 4. 创建执行器
        db_url = build_db_url(ds)
        executor = create_executor(
            datasource_id=datasource_id,
            datasource_type=ds["type"],
            db_url=db_url,
            timeout_seconds=30,
        )

        # 5. 创建 profiler
        profiler = SchemaProfiler(
            executor=executor,
            sample_row_count=ds_schema.db_schema.sample_row_count,
            max_rows_for_full_profiling=ds_schema.db_schema.max_rows_for_full_profiling,
        )

        # 6. 逐表探测（更新进度）
        for i, table in enumerate(ds_schema.db_schema.tables):
            _set_status(
                datasource_id, "running",
                current_table=table.name,
                progress=i,
            )
            try:
                profiler.profile_table(table)
            except Exception as e:
                logger.warning("Profiling table %s failed: %s", table.name, e)

        # 7. 写回 YAML
        write_profile_to_yaml(ds_schema, schema_file)

        _set_status(
            datasource_id, "completed",
            progress=total_tables,
            finished_at=time.time(),
        )

    except Exception as e:
        import traceback
        _set_status(
            datasource_id, "failed",
            error=str(e),
            finished_at=time.time(),
        )
        logger.error(
            "Profiling failed for datasource %s: %s\n%s",
            datasource_id, e, traceback.format_exc(),
        )
