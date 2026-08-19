"""Schema 语义匹配器：基于关键词的简单匹配策略。"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Column, DatasourceSchema, Table


@dataclass
class TableMatch:
    """表匹配结果。"""

    datasource_id: str
    table: Table
    score: float


@dataclass
class ColumnMatch:
    """列匹配结果。"""

    column: Column
    score: float


# 语义类型到关键词的映射（中英文常见同义词）
_SEMANTIC_TYPE_KEYWORDS: dict[str, list[str]] = {
    "id": ["id", "编号", "标识"],
    "timestamp": ["时间", "日期", "时刻", "time", "date", "datetime", "timestamp"],
    "amount": ["金额", "数量", "价格", "总数", "总量", "amount", "price", "total", "sum"],
    "dimension": ["名称", "名字", "维度", "name", "dimension"],
    "category": ["状态", "类型", "类别", "分类", "status", "type", "category"],
}


class SchemaMatcher:
    """Schema 语义匹配器。

    采用简单关键词匹配策略，适合表数量较少的场景。
    """

    def __init__(self, datasources: list[DatasourceSchema]):
        self.datasources = datasources

    def match_tables(self, query: str, top_k: int = 5) -> list[TableMatch]:
        """匹配所有数据源中的表，按分数从高到低返回。

        Args:
            query: 查询文本（自然语言问题或关键词）
            top_k: 返回前 k 个结果

        Returns:
            TableMatch 列表，按 score 降序排列
        """
        query_lower = query.lower().strip()
        results: list[TableMatch] = []

        # 空查询直接返回 0 分结果
        if not query_lower:
            for ds in self.datasources:
                for table in ds.schema.tables:
                    results.append(
                        TableMatch(datasource_id=ds.datasource_id, table=table, score=0.0)
                    )
            results.sort(key=lambda m: m.score, reverse=True)
            return results[:top_k]

        for ds in self.datasources:
            for table in ds.schema.tables:
                score = self._score_table(table, query_lower)
                results.append(
                    TableMatch(datasource_id=ds.datasource_id, table=table, score=score)
                )

        results.sort(key=lambda m: m.score, reverse=True)
        return results[:top_k]

    def match_columns(self, table: Table, query: str, top_k: int = 5) -> list[ColumnMatch]:
        """匹配单表中的列，按分数从高到低返回。

        Args:
            table: 要匹配的表
            query: 查询文本
            top_k: 返回前 k 个结果

        Returns:
            ColumnMatch 列表，按 score 降序排列
        """
        query_lower = query.lower().strip()
        results: list[ColumnMatch] = []

        # 空查询直接返回 0 分结果
        if not query_lower:
            for col in table.columns:
                results.append(ColumnMatch(column=col, score=0.0))
            results.sort(key=lambda m: m.score, reverse=True)
            return results[:top_k]

        for col in table.columns:
            score = self._score_column(col, query_lower)
            results.append(ColumnMatch(column=col, score=score))

        results.sort(key=lambda m: m.score, reverse=True)
        return results[:top_k]

    def find_relevant_tables(
        self, query: str, top_k: int = 5, min_score: float = 1.0
    ) -> list[TableMatch]:
        """查找相关表，过滤掉低于 min_score 的结果。

        Args:
            query: 查询文本
            top_k: 最多返回数量
            min_score: 最低分数阈值

        Returns:
            分数 >= min_score 的 TableMatch 列表，按 score 降序排列
        """
        results = self.match_tables(query, top_k=top_k)
        return [r for r in results if r.score >= min_score]

    # ---------- 评分方法 ----------

    def _score_table(self, table: Table, query: str) -> float:
        """计算表与查询的匹配分数。"""
        score = 0.0
        table_name_lower = table.name.lower()

        # 1. 表名精确匹配: +10
        if query == table_name_lower:
            score += 10
        # 2. 表名包含/被包含: +3
        elif table_name_lower and (table_name_lower in query or query in table_name_lower):
            score += 3

        # 3. 描述关键词匹配: +2（每个关键词）
        desc_words = self._tokenize(table.description)
        for word in desc_words:
            if word and word in query:
                score += 2

        # 4. 列名/列描述匹配: 每个 +0.5
        for col in table.columns:
            col_name_lower = col.name.lower()
            if col_name_lower and (col_name_lower in query or query in col_name_lower):
                score += 0.5
            col_desc_words = self._tokenize(col.description)
            for word in col_desc_words:
                if word and word in query:
                    score += 0.5

        # 5. 列语义类型匹配: +1.5
        for col in table.columns:
            if col.semantic_type:
                keywords = _SEMANTIC_TYPE_KEYWORDS.get(col.semantic_type, [])
                for kw in keywords:
                    if kw.lower() in query:
                        score += 1.5
                        break  # 同一列的语义类型只加一次

        return score

    def _score_column(self, col: Column, query: str) -> float:
        """计算列与查询的匹配分数。"""
        score = 0.0
        col_name_lower = col.name.lower()

        # 列名精确匹配
        if query == col_name_lower:
            score += 10
        # 列名包含/被包含
        elif col_name_lower and (col_name_lower in query or query in col_name_lower):
            score += 3

        # 列描述关键词匹配
        desc_words = self._tokenize(col.description)
        for word in desc_words:
            if word and word in query:
                score += 2

        # 语义类型匹配
        if col.semantic_type:
            keywords = _SEMANTIC_TYPE_KEYWORDS.get(col.semantic_type, [])
            for kw in keywords:
                if kw.lower() in query:
                    score += 1.5
                    break

        return score

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """简单分词：按常见分隔符切分，返回小写 token 列表。

        对中文直接返回原文作为整体匹配项，
        对英文按空格、下划线、驼峰等切分。
        """
        if not text:
            return []

        tokens: list[str] = []
        # 原始文本整体作为一个 token（用于中文子串匹配）
        tokens.append(text.lower())

        # 英文/数字部分按常见分隔符切分
        import re

        # 按空格、逗号、句号、分号、下划线、连字符切分
        parts = re.split(r"[\s,.;_\-]+", text)
        for part in parts:
            part_lower = part.lower()
            if part_lower and part_lower not in tokens:
                tokens.append(part_lower)
            # 驼峰切分
            camel_parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+", part)
            for cp in camel_parts:
                cp_lower = cp.lower()
                if cp_lower and cp_lower not in tokens:
                    tokens.append(cp_lower)

        return tokens
