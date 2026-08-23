"""Schema YAML 加载器。"""

from __future__ import annotations

import os
from typing import Any

import yaml

from .models import Column, DatasourceSchema, Schema, Table


class SchemaLoader:
    """从 YAML 文件加载 Schema 定义。"""

    YAML_EXTENSIONS = (".yaml", ".yml")

    def load_from_yaml(self, filepath: str) -> DatasourceSchema:
        """从单个 YAML 文件加载 DatasourceSchema。"""
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"Schema 文件不存在: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return self._parse_datasource(data)

    def load_from_directory(self, dirpath: str) -> list[DatasourceSchema]:
        """从目录加载所有 YAML 文件，返回 DatasourceSchema 列表。"""
        if not os.path.isdir(dirpath):
            raise FileNotFoundError(f"目录不存在: {dirpath}")

        results: list[DatasourceSchema] = []
        for filename in sorted(os.listdir(dirpath)):
            if not filename.lower().endswith(self.YAML_EXTENSIONS):
                continue
            filepath = os.path.join(dirpath, filename)
            if not os.path.isfile(filepath):
                continue
            results.append(self.load_from_yaml(filepath))

        return results

    def _parse_datasource(self, data: dict[str, Any]) -> DatasourceSchema:
        ds_info = data.get("datasource", {})
        tables_data = data.get("tables", [])

        tables = [self._parse_table(t) for t in tables_data]

        # profiling 配置（schema 级别）
        profiling = data.get("profiling", {})

        schema_kwargs: dict[str, Any] = {"tables": tables}
        if isinstance(profiling, dict):
            if "enabled" in profiling:
                schema_kwargs["profiling_enabled"] = profiling["enabled"]
            if "sample_row_count" in profiling:
                schema_kwargs["sample_row_count"] = profiling["sample_row_count"]
            if "max_rows_for_full_profiling" in profiling:
                schema_kwargs["max_rows_for_full_profiling"] = profiling["max_rows_for_full_profiling"]

        return DatasourceSchema(
            datasource_id=ds_info.get("id", ""),
            datasource_name=ds_info.get("name", ""),
            datasource_type=ds_info.get("type", "mysql"),
            db_schema=Schema(**schema_kwargs),
        )

    def _parse_table(self, table_data: dict[str, Any]) -> Table:
        columns_data = table_data.get("columns", [])
        columns = [Column(**col) for col in columns_data]

        # 透传所有 Table 模型支持的字段
        valid_fields = set(Table.model_fields.keys())
        table_kwargs = {k: v for k, v in table_data.items() if k in valid_fields}
        table_kwargs["columns"] = columns

        return Table(**table_kwargs)
