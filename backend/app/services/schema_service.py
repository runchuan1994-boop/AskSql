"""Schema 服务 - 提供项目 schema 概览和表详情查询."""

from __future__ import annotations

from app.core.database import get_connection
from nl2sql.schema.loader import SchemaLoader


def get_project_schemas(project_id: str) -> list[dict]:
    """获取项目所有数据源的 schema 概览.

    返回每个数据源的:
      {datasource_id, datasource_name, datasource_type, tables: [{name, description, column_count}]}
    如果 schema_file 不存在或加载失败，返回 note: "尚未导入 schema"
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT id, name, type, host, port, database, schema_file FROM datasources WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    loader = SchemaLoader()
    results = []
    for row in rows:
        ds_id = row["id"]
        ds_name = row["name"]
        ds_type = row["type"]
        ds_host = row["host"] or ""
        ds_port = row["port"]
        ds_database = row["database"] or ""
        schema_file = row["schema_file"]

        if not schema_file:
            results.append({
                "datasource_id": ds_id,
                "datasource_name": ds_name,
                "datasource_type": ds_type,
                "host": ds_host,
                "port": ds_port,
                "database": ds_database,
                "note": "尚未导入 schema",
            })
            continue

        try:
            ds_schema = loader.load_from_yaml(schema_file)
            tables = [
                {
                    "name": t.name,
                    "description": t.description,
                    "column_count": len(t.columns),
                }
                for t in ds_schema.db_schema.tables
            ]
            from app.services.profiling_service import get_profiling_status
            prof_status = get_profiling_status(ds_id)

            results.append({
                "datasource_id": ds_schema.datasource_id or ds_id,
                "datasource_name": ds_schema.datasource_name or ds_name,
                "datasource_type": ds_schema.datasource_type or ds_type,
                "host": ds_host,
                "port": ds_port,
                "database": ds_database,
                "tables": tables,
                "profiling_status": prof_status["status"],
                "row_count_total": sum(
                    t.row_count or 0 for t in ds_schema.db_schema.tables
                ),
            })
        except Exception:
            results.append({
                "datasource_id": ds_id,
                "datasource_name": ds_name,
                "datasource_type": ds_type,
                "host": ds_host,
                "port": ds_port,
                "database": ds_database,
                "note": "尚未导入 schema",
            })

    return results


def get_table_detail(datasource_id: str, table_name: str) -> dict | None:
    """获取指定数据源的单表详情.

    返回表的详细信息:
      {name, description, columns: [...], examples: [...]}
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT schema_file FROM datasources WHERE id = ?",
            (datasource_id,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    schema_file = row["schema_file"]
    if not schema_file:
        return None

    loader = SchemaLoader()
    try:
        ds_schema = loader.load_from_yaml(schema_file)
    except Exception:
        return None

    table = ds_schema.db_schema.get_table(table_name)
    if table is None:
        return None

    columns = [
        {
            "name": col.name,
            "type": col.type,
            "description": col.description,
            "business_name": col.business_name,
            "is_primary_key": col.is_primary_key,
            "is_foreign_key": col.is_foreign_key,
            "semantic_type": col.semantic_type,
            "enum_values": col.enum_values,
            "calc_formula": col.calc_formula,
            "distinct_count": col.distinct_count,
            "top_values": col.top_values,
            "value_min": col.value_min,
            "value_max": col.value_max,
            "null_rate": col.null_rate,
        }
        for col in table.columns
    ]

    return {
        "name": table.name,
        "description": table.description,
        "aliases": table.aliases,
        "business_domain": table.business_domain,
        "row_count": table.row_count,
        "update_frequency": table.update_frequency,
        "common_dimensions": table.common_dimensions,
        "common_metrics": table.common_metrics,
        "columns": columns,
        "sample_rows": table.sample_rows,
        "examples": table.examples,
    }
