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

    # ---- 增肥字段 ----
    business_name: str = ""          # 业务名称（YAML 配置）
    distinct_count: int | None = None  # 去重值数量（自动探测）
    top_values: list[dict] = []      # 高频值及占比 [{value, count, ratio}]
    value_min: str | None = None     # 最小值（数值/时间/字符串通用，存字符串方便序列化）
    value_max: str | None = None     # 最大值
    null_count: int | None = None    # NULL 行数
    null_rate: float | None = None   # NULL 率（0.0 ~ 1.0）
    calc_formula: str = ""           # 计算口径说明（衍生字段，YAML 配置）


class Table(BaseModel):
    """表定义。"""

    name: str
    description: str = ""
    columns: list[Column] = []
    examples: list[dict] = []

    # ---- 增肥字段 ----
    aliases: list[str] = []          # 业务别名列表（YAML 配置）
    business_domain: str = ""        # 所属业务域（YAML 配置）
    row_count: int | None = None     # 数据行数（自动探测）
    common_dimensions: list[str] = []  # 常用维度列名（YAML + 推断）
    common_metrics: list[dict] = []    # 常用指标 [{name, expression}]（YAML + 推断）
    sample_rows: list[dict] = []     # 样例数据（前 N 行，列名→值）
    update_frequency: str = ""       # 更新频率描述（YAML 配置）

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

    def has_profiling_data(self) -> bool:
        """是否包含自动探测的数据。"""
        return self.row_count is not None or any(
            col.null_rate is not None or col.value_min is not None
            for col in self.columns
        )


class Schema(BaseModel):
    """Schema 定义：包含多张表。"""

    tables: list[Table] = []
    profiling_enabled: bool = True
    sample_row_count: int = 5
    max_rows_for_full_profiling: int = 1_000_000

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
