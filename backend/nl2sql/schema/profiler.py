"""Schema 自动探测服务：从数据库中统计信息并填充到 schema 对象中。"""

from __future__ import annotations

import logging
import os
from typing import Any

import yaml

from .models import Column, DatasourceSchema, Table

logger = logging.getLogger(__name__)

# 数值型类型关键字
_NUMERIC_TYPES = {"int", "bigint", "smallint", "tinyint", "decimal", "float", "double", "numeric", "real"}
# 日期时间型类型关键字
_DATETIME_TYPES = {"datetime", "date", "timestamp", "time", "year"}
# 类别型判断阈值：distinct_count 小于此值视为低基数类别列
_LOW_CARDINALITY_THRESHOLD = 100


def _is_numeric(col_type: str) -> bool:
    """判断列类型是否为数值型。"""
    t = col_type.lower()
    return any(kw in t for kw in _NUMERIC_TYPES)


def _is_datetime(col_type: str) -> bool:
    """判断列类型是否为日期时间型。"""
    t = col_type.lower()
    return any(kw in t for kw in _DATETIME_TYPES)


def _is_category_column(col: Column) -> bool:
    """判断列是否为类别型（需要统计 top_values）。"""
    if col.semantic_type == "category":
        return True
    if col.enum_values:
        return True
    t = col.type.lower()
    if "varchar" in t or "char" in t or "text" in t or "enum" in t:
        return True
    return False


def _needs_range_stats(col: Column) -> bool:
    """判断列是否需要统计数值/时间范围。"""
    if col.semantic_type in ("amount", "timestamp"):
        return True
    return _is_numeric(col.type) or _is_datetime(col.type)


class SchemaProfiler:
    """Schema 自动探测器。

    通过执行 SQL 查询从数据库中收集统计信息，填充到 Table/Column 对象中。
    """

    def __init__(
        self,
        executor: Any,
        sample_row_count: int = 5,
        max_rows_for_full_profiling: int = 1_000_000,
    ):
        """
        Args:
            executor: SQL 执行器（需要有 execute(sql) -> ExecutionResult 方法）
            sample_row_count: 采样行数
            max_rows_for_full_profiling: 超过此行数的表不做全量 top_values 统计
        """
        self.executor = executor
        self.sample_row_count = sample_row_count
        self.max_rows_for_full_profiling = max_rows_for_full_profiling

    def profile_datasource(self, ds_schema: DatasourceSchema) -> DatasourceSchema:
        """对整个数据源的所有表进行探测。

        Args:
            ds_schema: 数据源 schema 对象

        Returns:
            填充了探测数据的 DatasourceSchema（原地修改后返回）
        """
        for table in ds_schema.db_schema.tables:
            try:
                self.profile_table(table)
            except Exception as e:
                logger.warning("Profiling table %s failed: %s", table.name, e)
        return ds_schema

    def profile_table(self, table: Table) -> Table:
        """对单张表进行探测。

        Args:
            table: 表对象（原地修改）

        Returns:
            填充了探测数据的 Table
        """
        table_name = table.name

        # 1. 表行数
        row_count = self._get_row_count(table_name)
        table.row_count = row_count

        # 2. 样例数据
        if self.sample_row_count > 0:
            table.sample_rows = self._get_sample_rows(
                table_name, table.columns, self.sample_row_count
            )

        # 判断是否为大表
        is_large_table = (
            row_count is not None and row_count > self.max_rows_for_full_profiling
        )

        # 3. 逐列统计
        for col in table.columns:
            try:
                self._profile_column(table_name, col, row_count, is_large_table)
            except Exception as e:
                logger.warning(
                    "Profiling column %s.%s failed: %s", table_name, col.name, e
                )

        return table

    def _get_row_count(self, table_name: str) -> int | None:
        """获取表行数。"""
        try:
            result = self.executor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
            if result.success and result.rows:
                return int(result.rows[0][0])
        except Exception as e:
            logger.warning("Failed to get row count for %s: %s", table_name, e)
        return None

    def _get_sample_rows(
        self, table_name: str, columns: list[Column], limit: int
    ) -> list[dict]:
        """获取样例数据。"""
        try:
            col_names = ", ".join(f"`{c.name}`" for c in columns)
            result = self.executor.execute(
                f"SELECT {col_names} FROM `{table_name}` LIMIT {limit}"
            )
            if not result.success or not result.rows:
                return []

            sample_rows = []
            for row in result.rows:
                row_dict = {}
                for i, col in enumerate(columns):
                    row_dict[col.name] = row[i]
                sample_rows.append(row_dict)
            return sample_rows
        except Exception as e:
            logger.warning("Failed to get sample rows for %s: %s", table_name, e)
            return []

    def _profile_column(
        self,
        table_name: str,
        col: Column,
        row_count: int | None,
        is_large_table: bool,
    ) -> None:
        """对单列进行统计。"""
        col_name = col.name

        # NULL 统计（所有列都做）
        null_count, null_rate = self._get_null_stats(table_name, col_name, row_count)
        col.null_count = null_count
        col.null_rate = null_rate

        # 数值/时间范围统计
        if _needs_range_stats(col):
            value_min, value_max = self._get_value_range(table_name, col_name)
            col.value_min = str(value_min) if value_min is not None else None
            col.value_max = str(value_max) if value_max is not None else None

        # 类别型列：distinct_count + top_values
        if _is_category_column(col):
            distinct_count = self._get_distinct_count(table_name, col_name)
            col.distinct_count = distinct_count

            # 高基数列跳过 top_values，避免性能问题
            if distinct_count is not None and distinct_count > _LOW_CARDINALITY_THRESHOLD:
                return
            # 大表降级：跳过 top_values
            if is_large_table:
                return

            top_values = self._get_top_values(table_name, col_name, row_count, limit=10)
            col.top_values = top_values

    def _get_null_stats(
        self, table_name: str, col_name: str, row_count: int | None
    ) -> tuple[int | None, float | None]:
        """获取 NULL 数量和比率。"""
        try:
            result = self.executor.execute(
                f"SELECT COUNT(*) - COUNT(`{col_name}`) FROM `{table_name}`"
            )
            if result.success and result.rows:
                null_count = int(result.rows[0][0])
                null_rate = (
                    null_count / row_count if row_count and row_count > 0 else None
                )
                return null_count, null_rate
        except Exception as e:
            logger.warning(
                "Failed to get null stats for %s.%s: %s", table_name, col_name, e
            )
        return None, None

    def _get_value_range(
        self, table_name: str, col_name: str
    ) -> tuple[Any | None, Any | None]:
        """获取列的最小值和最大值。"""
        try:
            result = self.executor.execute(
                f"SELECT MIN(`{col_name}`), MAX(`{col_name}`) FROM `{table_name}`"
            )
            if result.success and result.rows:
                return result.rows[0][0], result.rows[0][1]
        except Exception as e:
            logger.warning(
                "Failed to get value range for %s.%s: %s", table_name, col_name, e
            )
        return None, None

    def _get_distinct_count(self, table_name: str, col_name: str) -> int | None:
        """获取去重值数量。"""
        try:
            result = self.executor.execute(
                f"SELECT COUNT(DISTINCT `{col_name}`) FROM `{table_name}`"
            )
            if result.success and result.rows:
                return int(result.rows[0][0])
        except Exception as e:
            logger.warning(
                "Failed to get distinct count for %s.%s: %s", table_name, col_name, e
            )
        return None

    def _get_top_values(
        self,
        table_name: str,
        col_name: str,
        row_count: int | None,
        limit: int = 10,
    ) -> list[dict]:
        """获取高频值及其占比。"""
        try:
            result = self.executor.execute(
                f"SELECT `{col_name}`, COUNT(*) as cnt "
                f"FROM `{table_name}` "
                f"WHERE `{col_name}` IS NOT NULL "
                f"GROUP BY `{col_name}` "
                f"ORDER BY cnt DESC "
                f"LIMIT {limit}"
            )
            if not result.success or not result.rows:
                return []

            top_values = []
            for row in result.rows:
                value = row[0]
                count = int(row[1])
                ratio = count / row_count if row_count and row_count > 0 else 0.0
                top_values.append({
                    "value": str(value) if value is not None else None,
                    "count": count,
                    "ratio": round(ratio, 4),
                })
            return top_values
        except Exception as e:
            logger.warning(
                "Failed to get top values for %s.%s: %s", table_name, col_name, e
            )
            return []


def write_profile_to_yaml(ds_schema: DatasourceSchema, filepath: str) -> None:
    """将包含探测数据的 schema 写回 YAML 文件。

    只写入有值的探测字段，保持 YAML 整洁。
    """
    # 构建 YAML 数据结构
    tables_data = []
    for table in ds_schema.db_schema.tables:
        table_dict: dict[str, Any] = {"name": table.name}
        if table.description:
            table_dict["description"] = table.description
        if table.aliases:
            table_dict["aliases"] = table.aliases
        if table.business_domain:
            table_dict["business_domain"] = table.business_domain
        if table.update_frequency:
            table_dict["update_frequency"] = table.update_frequency
        if table.row_count is not None:
            table_dict["row_count"] = table.row_count
        if table.common_dimensions:
            table_dict["common_dimensions"] = table.common_dimensions
        if table.common_metrics:
            table_dict["common_metrics"] = table.common_metrics
        if table.sample_rows:
            table_dict["sample_rows"] = table.sample_rows
        if table.examples:
            table_dict["examples"] = table.examples

        columns_data = []
        for col in table.columns:
            col_dict: dict[str, Any] = {
                "name": col.name,
                "type": col.type,
            }
            if col.description:
                col_dict["description"] = col.description
            if col.business_name:
                col_dict["business_name"] = col.business_name
            if col.is_primary_key:
                col_dict["is_primary_key"] = True
            if col.is_foreign_key:
                col_dict["is_foreign_key"] = True
                col_dict["foreign_key_table"] = col.foreign_key_table
                col_dict["foreign_key_column"] = col.foreign_key_column
            if col.semantic_type:
                col_dict["semantic_type"] = col.semantic_type
            if col.enum_values:
                col_dict["enum_values"] = col.enum_values
            if col.calc_formula:
                col_dict["calc_formula"] = col.calc_formula
            if col.distinct_count is not None:
                col_dict["distinct_count"] = col.distinct_count
            if col.top_values:
                col_dict["top_values"] = col.top_values
            if col.value_min is not None:
                col_dict["value_min"] = col.value_min
            if col.value_max is not None:
                col_dict["value_max"] = col.value_max
            if col.null_count is not None:
                col_dict["null_count"] = col.null_count
            if col.null_rate is not None:
                col_dict["null_rate"] = col.null_rate

            columns_data.append(col_dict)

        table_dict["columns"] = columns_data
        tables_data.append(table_dict)

    yaml_data: dict[str, Any] = {
        "datasource": {
            "id": ds_schema.datasource_id,
            "name": ds_schema.datasource_name,
            "type": ds_schema.datasource_type,
        },
        "profiling": {
            "enabled": ds_schema.db_schema.profiling_enabled,
            "sample_row_count": ds_schema.db_schema.sample_row_count,
            "max_rows_for_full_profiling": ds_schema.db_schema.max_rows_for_full_profiling,
        },
        "tables": tables_data,
    }

    # 确保目录存在
    dirname = os.path.dirname(filepath)
    if dirname:
        os.makedirs(dirname, exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
