"""从数据库自动导入 Schema。"""
from __future__ import annotations

import os

import yaml
from sqlalchemy import create_engine, inspect

from app.core.config import settings
from app.core.database import get_connection
from app.services.datasource_service import (
    build_db_url,
    decrypt_password,
    get_datasource,
)


def _infer_semantic_type(col_name: str, col_type: str) -> str | None:
    """根据列名和类型推断 semantic_type。"""
    name_lower = col_name.lower()

    # ID 类
    if name_lower in ("id", "uuid") or name_lower.endswith("_id"):
        return "id"

    # 时间戳类
    if "time" in name_lower or "date" in name_lower or "created_at" in name_lower or "updated_at" in name_lower:
        return "timestamp"

    # 金额类
    if "amount" in name_lower or "price" in name_lower or "total" in name_lower or "cost" in name_lower:
        return "amount"

    # 类别类
    if "type" in name_lower or "category" in name_lower or "status" in name_lower or "role" in name_lower:
        return "category"

    return None


def _get_datasource_full(datasource_id: str) -> dict | None:
    """获取完整的数据源信息（含密码）。"""
    ds = get_datasource(datasource_id, include_password=True)
    return ds


def import_schema_from_database(datasource_id: str, use_llm: bool = False) -> dict:
    """从数据库导入 schema，生成 YAML 文件并更新 datasource 记录。

    Returns:
        {success, table_count, tables: [{name, column_count}]}
    """
    ds = _get_datasource_full(datasource_id)
    if ds is None:
        return {"success": False, "table_count": 0, "tables": [], "error": "Datasource not found"}

    db_url = build_db_url(ds)

    try:
        engine = create_engine(db_url)
        inspector = inspect(engine)

        table_names = inspector.get_table_names()

        tables_info = []
        yaml_tables = []

        for table_name in table_names:
            columns_info = inspector.get_columns(table_name)
            pk_info = inspector.get_pk_constraint(table_name)
            fk_info = inspector.get_foreign_keys(table_name)
            try:
                table_comment = inspector.get_table_comment(table_name)
            except (NotImplementedError, Exception):
                table_comment = {"text": ""}

            pk_columns = set(pk_info.get("constrained_columns", []))

            # 建立外键映射: column -> (referred_table, referred_column)
            fk_map: dict[str, tuple[str, str]] = {}
            for fk in fk_info:
                constrained_cols = fk.get("constrained_columns", [])
                referred_cols = fk.get("referred_columns", [])
                referred_table = fk.get("referred_table", "")
                for col, ref_col in zip(constrained_cols, referred_cols):
                    fk_map[col] = (referred_table, ref_col)

            columns_yaml = []
            for col in columns_info:
                col_name = col["name"]
                col_type = str(col["type"])
                is_pk = col_name in pk_columns
                is_fk = col_name in fk_map

                col_entry = {
                    "name": col_name,
                    "type": col_type,
                    "description": col.get("comment", "") or "",
                    "is_primary_key": is_pk,
                    "is_foreign_key": is_fk,
                }

                if is_fk:
                    ref_table, ref_col = fk_map[col_name]
                    col_entry["foreign_key_table"] = ref_table
                    col_entry["foreign_key_column"] = ref_col

                # 推断 semantic_type
                semantic = _infer_semantic_type(col_name, col_type)
                if semantic:
                    col_entry["semantic_type"] = semantic

                columns_yaml.append(col_entry)

            table_yaml = {
                "name": table_name,
                "description": table_comment.get("text", "") or "",
                "columns": columns_yaml,
                "examples": [],
            }
            yaml_tables.append(table_yaml)
            tables_info.append({"name": table_name, "column_count": len(columns_yaml)})

        # 构建 YAML 数据结构
        yaml_data = {
            "datasource": {
                "id": ds["id"],
                "name": ds["name"],
                "type": ds["type"],
            },
            "tables": yaml_tables,
        }

        # 确保 schema 目录存在
        schema_dir = os.path.join(settings.schemas_dir, ds["project_id"])
        os.makedirs(schema_dir, exist_ok=True)

        # 写入 YAML 文件
        schema_file = os.path.join(schema_dir, f"{ds['id']}.yaml")
        with open(schema_file, "w", encoding="utf-8") as f:
            yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        # 更新 datasource 记录的 schema_file
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE datasources SET schema_file = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (schema_file, datasource_id),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "success": True,
            "table_count": len(tables_info),
            "tables": tables_info,
        }

    except Exception as e:
        return {"success": False, "table_count": 0, "tables": [], "error": str(e)}
