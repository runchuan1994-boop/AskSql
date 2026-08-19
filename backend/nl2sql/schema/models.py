"""Schema 数据模型。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Column(BaseModel):
    """列定义。"""

    name: str
    type: str
    description: str = ""
    is_primary_key: bool = False
    is_foreign_key: bool = False
    foreign_key_table: Optional[str] = None
    foreign_key_column: Optional[str] = None
    enum_values: list[str] = []
    semantic_type: Optional[str] = None  # timestamp / amount / dimension / category / id


class Table(BaseModel):
    """表定义。"""

    name: str
    description: str = ""
    columns: list[Column] = []
    examples: list[dict] = []

    @property
    def column_names(self) -> list[str]:
        """返回所有列名。"""
        return [col.name for col in self.columns]

    def get_column(self, name: str) -> Optional[Column]:
        """按列名查找列，找不到返回 None。"""
        for col in self.columns:
            if col.name == name:
                return col
        return None


class Schema(BaseModel):
    """Schema 定义：包含多张表。"""

    tables: list[Table] = []

    @property
    def table_names(self) -> list[str]:
        """返回所有表名。"""
        return [tbl.name for tbl in self.tables]

    def get_table(self, name: str) -> Optional[Table]:
        """按表名查找表，找不到返回 None。"""
        for tbl in self.tables:
            if tbl.name == name:
                return tbl
        return None


class DatasourceSchema(BaseModel):
    """数据源 Schema：一个数据源对应一个 Schema。"""

    datasource_id: str
    datasource_name: str = ""
    datasource_type: str = "mysql"
    db_schema: Schema
