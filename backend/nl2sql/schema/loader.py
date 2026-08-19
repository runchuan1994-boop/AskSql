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

        return DatasourceSchema(
            datasource_id=ds_info.get("id", ""),
            datasource_name=ds_info.get("name", ""),
            datasource_type=ds_info.get("type", "mysql"),
            schema=Schema(tables=tables),
        )

    def _parse_table(self, table_data: dict[str, Any]) -> Table:
        columns_data = table_data.get("columns", [])
        columns = [Column(**col) for col in columns_data]
        return Table(
            name=table_data.get("name", ""),
            description=table_data.get("description", ""),
            columns=columns,
            examples=table_data.get("examples", []),
        )
