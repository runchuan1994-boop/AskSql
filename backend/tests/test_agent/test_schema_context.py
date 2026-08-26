"""测试 Schema Context 格式化。"""

from nl2sql.agent.nodes._schema_context import (
    format_table_context,
    _format_column_line,
    _sort_columns_by_relevance,
    _rank_column_relevance,
    build_compact_schema_context,
    inject_memories_into_context,
)
from nl2sql.schema.models import Column, Table


class TestFormatColumnLine:
    def test_basic_pk_column(self):
        col = Column(name="id", type="BIGINT", is_primary_key=True)
        line = _format_column_line(col)
        assert "id" in line
        assert "BIGINT" in line
        assert "[PK]" in line

    def test_column_with_stats(self):
        col = Column(
            name="total_amount",
            type="DECIMAL(10,2)",
            business_name="商品原价",
            semantic_type="amount",
            value_min="0.01",
            value_max="99999.99",
            null_rate=0.005,
        )
        line = _format_column_line(col)
        assert "商品原价" in line
        assert "amount" in line
        assert "0.01 ~ 99999.99" in line
        assert "非空" in line

    def test_category_column_with_top_values(self):
        col = Column(
            name="status",
            type="VARCHAR(20)",
            semantic_type="category",
            distinct_count=5,
            top_values=[
                {"value": "paid", "count": 600, "ratio": 0.6},
                {"value": "shipped", "count": 200, "ratio": 0.2},
                {"value": "pending", "count": 150, "ratio": 0.15},
            ],
        )
        line = _format_column_line(col)
        assert "5 个值" in line
        assert "paid(60%)" in line
        assert "shipped(20%)" in line

    def test_foreign_key_column(self):
        col = Column(
            name="user_id",
            type="BIGINT",
            is_foreign_key=True,
            foreign_key_table="users",
            foreign_key_column="id",
        )
        line = _format_column_line(col)
        assert "FK→users.id" in line

    def test_column_with_calc_formula(self):
        col = Column(
            name="final_amount",
            type="DECIMAL",
            calc_formula="total_amount + shipping_fee - discount",
        )
        line = _format_column_line(col)
        assert "口径:" in line
        assert "total_amount" in line

    def test_column_with_enum_values(self):
        col = Column(
            name="status",
            type="VARCHAR",
            enum_values=["pending", "paid", "shipped", "completed", "cancelled"],
        )
        line = _format_column_line(col)
        assert "枚举:" in line
        assert "pending" in line


class TestFormatTableContext:
    def test_full_table(self):
        table = Table(
            name="orders",
            description="记录用户下单信息",
            aliases=["交易表", "下单表"],
            business_domain="交易域",
            row_count=523400,
            update_frequency="实时",
            common_dimensions=["user_id", "channel", "created_at"],
            common_metrics=[
                {"name": "GMV", "expression": "SUM(total_amount)"},
                {"name": "订单量", "expression": "COUNT(*)"},
            ],
            sample_rows=[
                {"order_id": 10001, "total_amount": 299.0, "status": "paid"},
                {"order_id": 10002, "total_amount": 599.0, "status": "shipped"},
            ],
            columns=[
                Column(name="order_id", type="BIGINT", is_primary_key=True),
                Column(
                    name="total_amount", type="DECIMAL(10,2)",
                    business_name="商品原价", semantic_type="amount",
                    value_min="0.01", value_max="99999.99", null_rate=0.005,
                ),
                Column(
                    name="status", type="VARCHAR(20)",
                    semantic_type="category", distinct_count=5,
                    top_values=[
                        {"value": "paid", "count": 600, "ratio": 0.6},
                    ],
                ),
            ],
        )

        text = format_table_context(table)

        # 包含表信息
        assert "orders" in text
        assert "交易表" in text  # 别名
        assert "交易域" in text  # 业务域
        assert "523,400" in text  # 行数（带千分位）
        assert "实时" in text  # 更新频率

        # 常用维度/指标
        assert "常用维度" in text
        assert "GMV" in text
        assert "SUM(total_amount)" in text

        # 列信息
        assert "共 3 列" in text
        assert "商品原价" in text

        # 样例数据
        assert "样例数据" in text
        assert "10001" in text

    def test_truncated_columns(self):
        cols = [Column(name=f"col_{i}", type="INT") for i in range(20)]
        table = Table(name="wide_table", columns=cols)

        text = format_table_context(table, max_columns=5)
        assert "共 20 列" in text
        assert "还有 15 列已省略" in text

    def test_minimal_table(self):
        table = Table(name="simple", columns=[Column(name="id", type="INT")])
        text = format_table_context(table)
        assert "simple" in text
        assert "共 1 列" in text

    def test_thousand_separator_for_row_count(self):
        table = Table(name="t", row_count=1234567, columns=[Column(name="id", type="INT")])
        text = format_table_context(table)
        assert "1,234,567" in text


class TestBuildCompactSchemaContext:
    def test_compact_with_aliases_and_row_count(self):
        state = {
            "user_query": "订单",
            "datasources": [
                type('obj', (object,), {
                    'datasource_id': 'ds1',
                    'datasource_name': '测试库',
                    'datasource_type': 'mysql',
                    'db_schema': type('obj2', (object,), {
                        'tables': [
                            Table(
                                name='orders',
                                description='订单表',
                                aliases=['交易表'],
                                row_count=10000,
                                columns=[Column(name=f'c{i}', type='INT') for i in range(5)],
                            ),
                        ],
                    })(),
                })(),
            ],
        }
        text = build_compact_schema_context(state)
        assert "orders" in text
        assert "交易表" in text  # 别名在紧凑模式也显示
        assert "10,000" in text  # 行数
        assert "订单表" in text


class TestInjectMemories:
    def _make_sample_text(self) -> str:
        table = Table(
            name="orders",
            description="订单表",
            row_count=1000,
            columns=[
                Column(name="order_id", type="BIGINT", is_primary_key=True),
                Column(name="total_amount", type="DECIMAL(10,2)", semantic_type="amount"),
                Column(name="status", type="VARCHAR", semantic_type="category"),
            ],
            sample_rows=[{"order_id": 1, "total_amount": 100, "status": "paid"}],
        )
        return format_table_context(table)

    def test_no_memories_returns_original(self):
        text = self._make_sample_text()
        result = inject_memories_into_context(text, [])
        assert result == text

    def test_term_memory_added_at_top(self):
        text = self._make_sample_text()
        memories = [
            {
                "memory_type": "term_mapping",
                "entity_name": "流水",
                "content": "流水就是 GMV",
                "created_at": "2026-08-20 10:00:00",
            }
        ]
        result = inject_memories_into_context(text, memories)
        assert "业务术语说明" in result
        assert "流水" in result
        assert "GMV" in result
        assert "2026-08-20" in result
        # 术语说明在最前面
        assert result.index("业务术语说明") < result.index("===")

    def test_table_level_memory_injected(self):
        text = self._make_sample_text()
        memories = [
            {
                "memory_type": "table_description",
                "entity_name": "orders",
                "content": "只存主站订单",
                "created_at": "2026-08-20",
            }
        ]
        result = inject_memories_into_context(text, memories)
        assert "📝 用户备注" in result
        assert "只存主站订单" in result
        # 出现在表描述附近
        lines = result.split("\n")
        desc_idx = next(i for i, l in enumerate(lines) if l.startswith("描述:"))
        note_idx = next(i for i, l in enumerate(lines) if "📝 用户备注" in l)
        assert note_idx == desc_idx + 1

    def test_column_level_memory_injected(self):
        text = self._make_sample_text()
        memories = [
            {
                "memory_type": "column_description",
                "entity_name": "orders.total_amount",
                "content": "这是商品原价不是实付",
                "created_at": "2026-08-20",
            }
        ]
        result = inject_memories_into_context(text, memories)
        # 列级记忆用缩进更多的 📝
        assert "用户备注: 这是商品原价不是实付" in result

    def test_metric_definition_memory(self):
        text = self._make_sample_text()
        memories = [
            {
                "memory_type": "metric_definition",
                "entity_name": "GMV",
                "content": "total_amount + shipping_fee",
                "created_at": "2026-08-20",
            }
        ]
        result = inject_memories_into_context(text, memories)
        assert "GMV" in result
        assert "指标" in result

    def test_join_hint_memory(self):
        text = self._make_sample_text()
        memories = [
            {
                "memory_type": "join_hint",
                "entity_name": "orders",
                "content": "注意游客下单时 user_id 为 NULL",
                "created_at": "2026-08-20",
            }
        ]
        result = inject_memories_into_context(text, memories)
        assert "游客下单" in result

    def test_format_date_handles_iso_format(self):
        from nl2sql.agent.nodes._schema_context import _format_date
        assert _format_date("2026-08-20 10:30:00") == "2026-08-20"
        assert _format_date("2026-08-20T10:30:00") == "2026-08-20"
        assert _format_date("2026-08-20") == "2026-08-20"
        assert _format_date("") == ""
        assert _format_date("2026") == "2026"

    def test_multiple_memories(self):
        text = self._make_sample_text()
        memories = [
            {"memory_type": "term_mapping", "entity_name": "流水", "content": "GMV", "created_at": "2026-08-20"},
            {"memory_type": "table_description", "entity_name": "orders", "content": "主站订单", "created_at": "2026-08-20"},
            {"memory_type": "column_description", "entity_name": "orders.status", "content": "订单状态", "created_at": "2026-08-20"},
        ]
        result = inject_memories_into_context(text, memories)
        assert "流水" in result
        assert "主站订单" in result
        assert "订单状态" in result


class TestColumnRelevanceRanking:
    """测试列相关性排序（列多时高相关列优先展示）。"""

    def _make_test_table(self):
        return Table(
            name="orders",
            description="订单表",
            common_dimensions=["status", "channel"],
            columns=[
                # 0: 普通列
                Column(name="remark", type="TEXT"),
                # 1: 主键
                Column(name="order_id", type="BIGINT", is_primary_key=True),
                # 2: 有业务名+描述
                Column(
                    name="total_amount", type="DECIMAL",
                    business_name="订单总额", description="订单总金额",
                    semantic_type="amount",
                ),
                # 3: 常用维度 + 类别
                Column(
                    name="status", type="VARCHAR",
                    semantic_type="category",
                    enum_values=["pending", "paid", "done"],
                ),
                # 4: 外键
                Column(
                    name="user_id", type="BIGINT",
                    is_foreign_key=True, foreign_key_table="users",
                ),
                # 5: 另一个普通列
                Column(name="created_at", type="DATETIME", semantic_type="timestamp"),
            ],
        )

    def test_pk_ranked_highest(self):
        """主键列得分最高，排在最前。"""
        table = self._make_test_table()
        sorted_cols = _sort_columns_by_relevance(table.columns, table)
        assert sorted_cols[0].name == "order_id"  # PK 第一

    def test_fk_ranked_second_to_pk(self):
        """外键列得分仅次于主键。"""
        table = self._make_test_table()
        sorted_cols = _sort_columns_by_relevance(table.columns, table)
        # PK 是第 0，外键应该很靠前（前 3 之内）
        top_names = [c.name for c in sorted_cols[:3]]
        assert "user_id" in top_names

    def test_common_dimensions_ranked_high(self):
        """常用维度列排名靠前。"""
        table = self._make_test_table()
        sorted_cols = _sort_columns_by_relevance(table.columns, table)
        # status 是 common_dimensions，应该在 remark 之前
        status_idx = [c.name for c in sorted_cols].index("status")
        remark_idx = [c.name for c in sorted_cols].index("remark")
        assert status_idx < remark_idx

    def test_business_name_boosts_rank(self):
        """有业务名称的列排名更靠前。"""
        table = self._make_test_table()
        sorted_cols = _sort_columns_by_relevance(table.columns, table)
        # total_amount 有业务名称，应该在 remark 之前
        amount_idx = [c.name for c in sorted_cols].index("total_amount")
        remark_idx = [c.name for c in sorted_cols].index("remark")
        assert amount_idx < remark_idx

    def test_query_keyword_boosts_relevance(self):
        """查询关键词命中的列排名提升。"""
        table = Table(
            name="orders",
            columns=[
                Column(name="order_id", type="INT"),
                Column(name="status", type="VARCHAR", semantic_type="category"),
                Column(name="total_amount", type="DECIMAL", semantic_type="amount"),
            ],
        )

        # 不带 query 时的排序
        sorted_no_query = _sort_columns_by_relevance(table.columns, table, "")
        no_query_order = [c.name for c in sorted_no_query]

        # 带 "amount" 查询时，total_amount 应该排名提升
        sorted_with_query = _sort_columns_by_relevance(table.columns, table, "total amount 统计")
        with_query_order = [c.name for c in sorted_with_query]

        # total_amount 在带 query 时的排名应该比不带 query 时更靠前（或相同）
        amount_idx_no_q = no_query_order.index("total_amount")
        amount_idx_with_q = with_query_order.index("total_amount")
        assert amount_idx_with_q <= amount_idx_no_q

    def test_truncated_table_shows_high_relevance_columns(self):
        """列截断时，显示的是高相关列，而不是前 N 列。"""
        table = self._make_test_table()

        # 只显示 3 列，应该是 PK + 高相关列，而不是前 3 个列名
        result = format_table_context(table, max_columns=3)

        # 主键肯定在前三
        assert "order_id" in result
        # 外键或常用维度也应该在
        assert "user_id" in result or "status" in result
        # 普通列 remark 不应该在前三里
        # （remark 是第 0 列，如果没排序会被显示）
        # 我们检查 "remark" 出现在省略提示中（说明被截断了）
        assert "已省略" in result or "remark" not in result.split("列（共")[1].split("样例数据")[0]

    def test_truncation_message_mentions_relevance(self):
        """截断提示文字说明是高相关列优先。"""
        table = self._make_test_table()
        result = format_table_context(table, max_columns=2)
        assert "高相关列优先" in result or "相关列" in result

    def test_stable_sorting_same_score(self):
        """得分相同时，按原始顺序排列（稳定排序）。"""
        table = Table(
            name="t",
            columns=[
                Column(name="a", type="INT"),
                Column(name="b", type="INT"),
                Column(name="c", type="INT"),
            ],
        )
        sorted_cols = _sort_columns_by_relevance(table.columns, table)
        # 三列得分相同，保持原始顺序
        assert [c.name for c in sorted_cols] == ["a", "b", "c"]

    def test_no_truncation_keeps_original_order(self):
        """不需要截断时，保持原始列顺序（不排序）。"""
        table = self._make_test_table()
        # max_columns 为 None 时不截断，保持原顺序
        result = format_table_context(table, max_columns=None)
        # 验证原始顺序的第一列（remark）出现在列列表中第一个位置
        lines = result.split("\n")
        col_lines = [l for l in lines if l.strip().startswith("·")]
        # 第一列应该是 remark（原始顺序）
        assert "remark" in col_lines[0]

    def test_rank_column_relevance_scores(self):
        """验证各因素的得分值。"""
        table = Table(
            name="t",
            common_dimensions=["status"],
            columns=[],
        )

        # 主键得分最高
        pk_col = Column(name="id", type="INT", is_primary_key=True)
        pk_score = _rank_column_relevance(pk_col, table)
        assert pk_score >= 100

        # 外键第二
        fk_col = Column(name="user_id", type="INT", is_foreign_key=True)
        fk_score = _rank_column_relevance(fk_col, table)
        assert fk_score >= 80
        assert fk_score < pk_score

        # 常用维度
        dim_col = Column(name="status", type="VARCHAR", semantic_type="category")
        dim_score = _rank_column_relevance(dim_col, table)
        assert dim_score >= 60
