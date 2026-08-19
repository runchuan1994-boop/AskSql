"""Schema 模块：数据模型、加载器、匹配器。"""

from .models import Column, Table, Schema, DatasourceSchema
from .loader import SchemaLoader
from .matcher import SchemaMatcher, TableMatch, ColumnMatch

__all__ = [
    "Column",
    "Table",
    "Schema",
    "DatasourceSchema",
    "SchemaLoader",
    "SchemaMatcher",
    "TableMatch",
    "ColumnMatch",
]
