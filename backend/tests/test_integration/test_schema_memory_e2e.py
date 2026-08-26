"""Schema 增肥 + 记忆系统端到端集成测试。

验证完整链路：profiling → YAML 持久化 → schema context 格式化 → 记忆注入 → 召回排序。
全部使用 mock，不依赖外部服务。
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from nl2sql.schema.models import Column, Table
from nl2sql.schema.profiler import write_profile_to_yaml
from nl2sql.schema.loader import SchemaLoader
from nl2sql.llm.base import ChatResponse


@pytest.fixture(autouse=True)
def use_temp_db(monkeypatch):
    """每个测试用独立的临时数据库。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    monkeypatch.setenv("APP_DATABASE_URL", f"sqlite:///{db_path}")

    import importlib
    import app.core.config as config_module
    import app.core.database as db_module
    importlib.reload(config_module)
    importlib.reload(db_module)
    db_module.init_db()

    import app.services.memory_service as ms_module
    importlib.reload(ms_module)

    yield db_path

    os.unlink(db_path)


# 构造带增肥数据的测试表
def _make_enriched_table() -> Table:
    return Table(
        name="orders",
        description="订单主表",
        aliases=["order_table", "交易表"],
        business_domain="交易域",
        row_count=125000,
        update_frequency="每日凌晨更新",
        common_dimensions=["status", "created_date", "channel"],
        common_metrics=[
            {"name": "GMV", "expression": "sum(total_amount)"},
            {"name": "order_count", "expression": "count(*)"},
        ],
        sample_rows=[
            {"order_id": "1001", "total_amount": 99.9, "status": "paid"},
            {"order_id": "1002", "total_amount": 199.0, "status": "pending"},
        ],
        columns=[
            Column(
                name="order_id",
                type="VARCHAR(32)",
                description="订单号",
                business_name="订单编号",
                semantic_type="id",
                distinct_count=125000,
                null_rate=0.0,
            ),
            Column(
                name="total_amount",
                type="DECIMAL(10,2)",
                description="订单金额",
                business_name="订单总额",
                semantic_type="amount",
                value_min="0.01",
                value_max="99999.99",
                null_rate=0.005,  # 0.5% 空值率
                distinct_count=8920,
            ),
            Column(
                name="status",
                type="VARCHAR(16)",
                description="订单状态",
                business_name="订单状态",
                semantic_type="category",
                enum_values=["pending", "paid", "shipped", "done", "cancelled"],
                top_values=[
                    {"value": "paid", "count": 65000, "ratio": 0.52},
                    {"value": "done", "count": 35000, "ratio": 0.28},
                    {"value": "cancelled", "count": 12000, "ratio": 0.096},
                ],
                distinct_count=5,
                null_rate=0.0,
            ),
            Column(
                name="created_at",
                type="DATETIME",
                description="创建时间",
                semantic_type="timestamp",
                value_min="2023-01-01 00:00:00",
                value_max="2026-08-24 23:59:59",
                null_rate=0.0,
            ),
            Column(
                name="discounted_amount",
                type="DECIMAL(10,2)",
                description="优惠后金额",
                business_name="实付金额",
                semantic_type="amount",
                calc_formula="total_amount * (1 - discount_rate)",
                value_min="0.0",
                value_max="99999.99",
                null_rate=0.023,  # 2.3% 空值率
            ),
        ],
    )


class TestEnrichedSchemaContext:
    """增肥 Schema Context 格式验证。"""

    def test_table_metadata_in_context(self):
        """表级增肥信息出现在 schema context 中。"""
        from nl2sql.agent.nodes._schema_context import format_table_context

        table = _make_enriched_table()
        result = format_table_context(table)

        assert "订单主表" in result  # 描述
        assert "125,000" in result or "125000" in result  # 行数（千分位或原始）
        assert "交易域" in result  # 业务域
        assert "每日凌晨更新" in result  # 更新频率

    def test_table_aliases_in_context(self):
        """表别名出现在 schema context 中。"""
        from nl2sql.agent.nodes._schema_context import format_table_context

        table = _make_enriched_table()
        result = format_table_context(table)
        assert "order_table" in result or "交易表" in result or "别名" in result

    def test_column_business_name_in_context(self):
        """列的业务名称出现在 schema context 中。"""
        from nl2sql.agent.nodes._schema_context import format_table_context

        table = _make_enriched_table()
        result = format_table_context(table)

        assert "订单总额" in result  # total_amount 的业务名
        assert "订单状态" in result  # status 的业务名

    def test_column_stats_in_context(self):
        """列的统计信息（top values、范围、非空率等）出现在 context 中。"""
        from nl2sql.agent.nodes._schema_context import format_table_context

        table = _make_enriched_table()
        result = format_table_context(table)

        # 类别列有 top values
        assert "paid" in result
        assert "52%" in result  # 0.52 * 100 = 52%
        # 数值列有范围
        assert "0.01" in result or "99999.99" in result
        # 非空率显示
        assert "非空" in result

    def test_column_calc_formula_in_context(self):
        """计算公式列的公式出现在 context 中。"""
        from nl2sql.agent.nodes._schema_context import format_table_context

        table = _make_enriched_table()
        result = format_table_context(table)

        assert "discount_rate" in result or "公式" in result

    def test_sample_rows_in_context(self):
        """样例数据表格出现在 context 中。"""
        from nl2sql.agent.nodes._schema_context import format_table_context

        table = _make_enriched_table()
        result = format_table_context(table)

        # 样例行中应该有数据
        assert "1001" in result
        assert "99.9" in result

    def test_column_truncation_many_columns(self):
        """列数多时截断，并显示省略提示。"""
        from nl2sql.agent.nodes._schema_context import format_table_context

        table = _make_enriched_table()
        # 用 max_columns=2 测试截断
        result = format_table_context(table, max_columns=2)

        assert "省略" in result or "更多" in result
        # 应该显示了前两列
        assert "order_id" in result
        assert "total_amount" in result


class TestMemoryInjectionWithEnrichment:
    """记忆注入与增肥数据共存验证。"""

    def test_term_memory_plus_enriched_table(self):
        """术语记忆 + 增肥表信息，两者都正确显示。"""
        from nl2sql.agent.nodes._schema_context import (
            format_table_context,
            inject_memories_into_context,
        )

        table = _make_enriched_table()
        context = format_table_context(table)

        memories = [
            {
                "id": "mem_1",
                "memory_type": "term_mapping",
                "entity_type": "term",
                "entity_name": "GMV",
                "content": "GMV = 商品交易总额",
                "created_at": "2026-08-20 10:00:00",
            },
        ]

        result = inject_memories_into_context(context, memories)

        # 术语记忆在顶部
        term_pos = result.index("业务术语说明") if "业务术语说明" in result else -1
        table_pos = result.index("orders")
        assert term_pos < table_pos
        assert "GMV" in result
        # 增肥数据仍然存在
        assert "订单总额" in result
        assert "125,000" in result or "125000" in result

    def test_table_memory_after_description(self):
        """表级记忆在描述行后，增肥数据在其后面。"""
        from nl2sql.agent.nodes._schema_context import (
            format_table_context,
            inject_memories_into_context,
        )

        table = _make_enriched_table()
        context = format_table_context(table)

        memories = [
            {
                "id": "mem_2",
                "memory_type": "table_description",
                "entity_type": "table",
                "entity_name": "orders",
                "content": "只包含主站订单",
                "created_at": "2026-08-20",
            },
        ]

        result = inject_memories_into_context(context, memories)

        assert "📝 用户备注" in result
        assert "只包含主站订单" in result
        # 增肥数据依然在
        assert "125,000" in result or "125000" in result
        assert "交易域" in result

    def test_column_memory_after_stats(self):
        """列级记忆在列行后，列的统计数据也存在。"""
        from nl2sql.agent.nodes._schema_context import (
            format_table_context,
            inject_memories_into_context,
        )

        table = _make_enriched_table()
        context = format_table_context(table)

        memories = [
            {
                "id": "mem_3",
                "memory_type": "column_description",
                "entity_type": "column",
                "entity_name": "orders.status",
                "content": "状态不含退款订单",
                "created_at": "2026-08-20",
            },
        ]

        result = inject_memories_into_context(context, memories)

        assert "状态不含退款订单" in result
        # 列的统计信息仍然在
        assert "paid" in result
        assert "52%" in result  # 0.52 → 52%


class TestProfilerYamlRoundTrip:
    """SchemaProfiler → YAML → 重新加载 往返验证。"""

    def test_write_and_reload_preserves_enrichment(self):
        """增肥数据写回 YAML 后重新加载，数据不丢失。"""
        from nl2sql.schema.models import DatasourceSchema, Schema

        table = _make_enriched_table()
        ds = DatasourceSchema(
            datasource_id="test_id",
            datasource_name="test_ds",
            datasource_type="sqlite",
            db_schema=Schema(tables=[table]),
        )

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            yaml_path = f.name

        try:
            # 写回 YAML
            write_profile_to_yaml(ds, yaml_path)

            # 重新加载
            loader = SchemaLoader()
            loaded = loader.load_from_yaml(yaml_path)

            assert loaded.datasource_name == "test_ds"
            assert len(loaded.db_schema.tables) == 1

            t = loaded.db_schema.tables[0]
            assert t.name == "orders"
            assert t.description == "订单主表"
            assert t.row_count == 125000
            assert t.business_domain == "交易域"
            assert t.update_frequency == "每日凌晨更新"
            assert "order_table" in t.aliases
            assert "交易表" in t.aliases
            assert t.common_dimensions == ["status", "created_date", "channel"]
            assert len(t.common_metrics) == 2
            assert t.common_metrics[0]["name"] == "GMV"
            assert t.common_metrics[0]["expression"] == "sum(total_amount)"
            assert t.common_metrics[1]["name"] == "order_count"
            assert t.common_metrics[1]["expression"] == "count(*)"
            assert len(t.sample_rows) == 2

            # 验证列
            cols = {c.name: c for c in t.columns}
            assert len(cols) == 5

            assert cols["order_id"].business_name == "订单编号"
            assert cols["order_id"].semantic_type == "id"
            assert cols["order_id"].distinct_count == 125000
            assert cols["order_id"].null_rate == 0.0

            assert cols["total_amount"].business_name == "订单总额"
            assert cols["total_amount"].semantic_type == "amount"
            assert cols["total_amount"].value_min == "0.01"
            assert cols["total_amount"].value_max == "99999.99"
            assert cols["total_amount"].null_rate == 0.005

            assert cols["status"].semantic_type == "category"
            assert cols["status"].enum_values == ["pending", "paid", "shipped", "done", "cancelled"]
            assert cols["status"].distinct_count == 5
            assert len(cols["status"].top_values) == 3
            assert cols["status"].top_values[0]["value"] == "paid"
            assert cols["status"].top_values[0]["ratio"] == 0.52  # 52%

            assert cols["discounted_amount"].calc_formula == "total_amount * (1 - discount_rate)"
            assert cols["discounted_amount"].null_rate == 0.023  # 2.3%

        finally:
            os.unlink(yaml_path)

    def test_write_only_non_default_fields(self):
        """YAML 中只写入非默认值的字段，保持整洁。"""
        from nl2sql.schema.models import DatasourceSchema, Schema

        # 没有增肥数据的表
        plain_table = Table(
            name="simple",
            description="简单表",
            columns=[Column(name="id", type="INT", description="ID")],
        )
        ds = DatasourceSchema(
            datasource_id="simple_id",
            datasource_name="simple_ds",
            datasource_type="sqlite",
            db_schema=Schema(tables=[plain_table]),
        )

        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w+") as f:
            yaml_path = f.name

        try:
            write_profile_to_yaml(ds, yaml_path)

            with open(yaml_path) as f:
                content = f.read()

            # 不应该包含增肥数据的具体值（null/0/空列表这些默认值不算）
            # 检查没有业务名称、计算公式等增肥字段内容
            assert "business_name" not in content
            assert "calc_formula" not in content
            # 但应该有基本字段
            assert "simple" in content
            assert "id" in content

        finally:
            os.unlink(yaml_path)


class TestMemoryLifecycle:
    """完整记忆生命周期测试（检测→存储→召回→注入→排名）。"""

    def _mock_llm(self, json_str):
        m = MagicMock()
        m.chat.return_value = ChatResponse(content=json_str)
        return m

    def test_full_lifecycle_column_memory(self):
        """列记忆完整生命周期：检测→验证→存储→召回→注入。"""
        from app.services.correction_detector import (
            detect_correction,
            validate_memory_against_schema,
        )
        from app.services.memory_service import (
            add_memory,
            get_memories_for_query,
        )
        from nl2sql.agent.nodes._schema_context import (
            format_table_context,
            inject_memories_into_context,
        )

        table = _make_enriched_table()
        tables = [table]

        # 1. 检测
        fake_resp = '''{
  "is_correction": true,
  "memory_type": "column_description",
  "entity_type": "column",
  "entity_name": "orders.total_amount",
  "content": "total_amount 是商品原价，不含运费"
}'''
        with patch("app.services.correction_detector.create_llm_client",
                   return_value=self._mock_llm(fake_resp)):
            corr = detect_correction("不对，total_amount 是原价不含运费")

        assert corr.is_correction is True

        # 2. 验证
        corr = validate_memory_against_schema(corr, tables)
        assert corr.is_correction is True
        assert corr.entity_name == "orders.total_amount"

        # 3. 存储
        mem = add_memory(
            datasource_id="ds_1",
            memory_type=corr.memory_type,
            entity_type=corr.entity_type,
            entity_name=corr.entity_name,
            content=corr.content,
            raw_content=corr.raw_content,
            source="user_correction",
            confidence=0.8,
        )
        assert mem["id"].startswith("mem_")

        # 4. 召回
        memories = get_memories_for_query(
            datasource_id="ds_1",
            query="订单金额统计",
            related_tables=["orders"],
        )
        assert len(memories) >= 1
        assert any("原价" in m["content"] for m in memories)

        # 5. 注入
        context = format_table_context(table)
        result = inject_memories_into_context(context, memories)
        assert "原价" in result
        assert "📝 用户备注" in result

    def test_memory_ranking_by_confidence(self):
        """记忆按 confidence 降序排列。"""
        from app.services.memory_service import (
            add_memory,
            get_memories_for_query,
        )

        # 同类型同实体，不同 confidence
        add_memory(
            datasource_id="ds_1", memory_type="term_mapping", entity_type="term",
            entity_name="流水", content="低置信度", source="user_correction", confidence=0.6,
        )
        add_memory(
            datasource_id="ds_1", memory_type="term_mapping", entity_type="term",
            entity_name="流水", content="高置信度", source="manual_add", confidence=1.0,
        )
        add_memory(
            datasource_id="ds_1", memory_type="term_mapping", entity_type="term",
            entity_name="流水", content="中置信度", source="user_correction_confirmed",
            confidence=0.9,
        )

        memories = get_memories_for_query(
            datasource_id="ds_1", query="流水统计", related_tables=[],
        )
        assert len(memories) >= 3
        # 按 confidence 排序
        assert memories[0]["confidence"] >= memories[1]["confidence"]
        assert memories[1]["confidence"] >= memories[2]["confidence"]
        assert "高置信度" in memories[0]["content"]

    def test_memory_ranking_by_access_count(self):
        """同 confidence 下，access_count 高的排前面。"""
        from app.services.memory_service import (
            add_memory,
            get_memories_for_query,
            increment_access,
            get_memory,
        )

        m1 = add_memory(
            datasource_id="ds_1", memory_type="term_mapping", entity_type="term",
            entity_name="流水", content="记忆A", source="user_correction", confidence=0.8,
        )
        m2 = add_memory(
            datasource_id="ds_1", memory_type="term_mapping", entity_type="term",
            entity_name="流水", content="记忆B", source="user_correction", confidence=0.8,
        )

        # 增加 m2 的访问次数
        increment_access(m2["id"])
        increment_access(m2["id"])

        memories = get_memories_for_query(
            datasource_id="ds_1", query="流水", related_tables=[],
        )
        # 同 confidence 下，access_count 高的在前
        m2_in_result = [i for i, m in enumerate(memories) if "记忆B" in m["content"]][0]
        m1_in_result = [i for i, m in enumerate(memories) if "记忆A" in m["content"]][0]
        assert m2_in_result < m1_in_result  # B 在 A 前面

    def test_multi_datasource_isolation(self):
        """多数据源记忆隔离。"""
        from app.services.memory_service import (
            add_memory,
            get_memories_for_query,
        )

        add_memory(
            datasource_id="ds_a", memory_type="table_description", entity_type="table",
            entity_name="orders", content="A数据源的订单表", source="manual_add", confidence=1.0,
        )
        add_memory(
            datasource_id="ds_b", memory_type="table_description", entity_type="table",
            entity_name="orders", content="B数据源的订单表", source="manual_add", confidence=1.0,
        )

        mems_a = get_memories_for_query(datasource_id="ds_a", query="订单", related_tables=["orders"])
        mems_b = get_memories_for_query(datasource_id="ds_b", query="订单", related_tables=["orders"])

        assert all("A数据" in m["content"] for m in mems_a)
        assert all("B数据" in m["content"] for m in mems_b)

    def test_memory_access_increments_on_recall(self):
        """召回时 access_count 会增加。"""
        from app.services.memory_service import (
            add_memory,
            get_memories_for_query,
            get_memory,
        )

        mem = add_memory(
            datasource_id="ds_1", memory_type="term_mapping", entity_type="term",
            entity_name="GMV", content="商品交易总额", source="manual_add", confidence=1.0,
        )
        assert get_memory(mem["id"])["access_count"] == 0

        get_memories_for_query(datasource_id="ds_1", query="GMV 是多少", related_tables=[])
        assert get_memory(mem["id"])["access_count"] == 1

        get_memories_for_query(datasource_id="ds_1", query="GMV 趋势", related_tables=[])
        assert get_memory(mem["id"])["access_count"] == 2


class TestCorrectionDetectionEdgeCases:
    """纠错检测的端到端边界场景。"""

    def _mock_llm(self, json_str):
        m = MagicMock()
        m.chat.return_value = ChatResponse(content=json_str)
        return m

    def test_no_keyword_no_llm_call(self):
        """无纠错关键词时不调用 LLM。"""
        from app.services.correction_detector import detect_correction

        mock = self._mock_llm('{"is_correction": true}')
        with patch("app.services.correction_detector.create_llm_client", return_value=mock):
            result = detect_correction("帮我查一下销售数据")

        assert result.is_correction is False
        mock.chat.assert_not_called()

    def test_llm_exception_fails_closed(self):
        """LLM 异常时 fail-closed。"""
        from app.services.correction_detector import detect_correction
        from app.services.memory_service import list_memories

        mock = MagicMock()
        mock.chat.side_effect = Exception("API 宕机了")
        with patch("app.services.correction_detector.create_llm_client", return_value=mock):
            result = detect_correction("不对，这有问题")

        assert result.is_correction is False
        # 不创建记忆
        result = list_memories("ds_test")
        assert result["total"] == 0

    def test_context_passed_to_detection(self):
        """上下文消息正确传入 LLM。"""
        from app.services.correction_detector import detect_correction

        mock = self._mock_llm('{"is_correction": false}')
        context = [
            {"role": "user", "content": "查订单量"},
            {"role": "assistant", "content": "订单量是 100"},
        ]

        with patch("app.services.correction_detector.create_llm_client", return_value=mock):
            detect_correction("不对，应该按月分组", context=context)

        mock.chat.assert_called_once()
        call_args = mock.chat.call_args
        messages = call_args[0][0] if call_args[0] else call_args.kwargs.get("messages", [])
        user_msg = [m for m in messages if m.role.value == "user"][0]
        assert "订单量是 100" in user_msg.content
        assert "按月分组" in user_msg.content

    def test_markdown_json_with_explanation_parsed(self):
        """LLM 返回 markdown JSON + 解释文字，能正确解析。"""
        from app.services.correction_detector import detect_correction

        response = '''```json
{
  "is_correction": true,
  "memory_type": "column_description",
  "entity_type": "column",
  "entity_name": "orders.status",
  "content": "status 表示订单状态"
}
```

分析：用户明确指出了字段含义，属于列描述纠错。'''
        mock = self._mock_llm(response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock):
            result = detect_correction("不对，status 是订单状态")

        assert result.is_correction is True
        assert result.memory_type == "column_description"

    def test_invalid_memory_type_rejected(self):
        """不合法的 memory_type 被拒绝。"""
        from app.services.correction_detector import detect_correction

        response = '{"is_correction": true, "memory_type": "weird_type", "content": "..."}'
        mock = self._mock_llm(response)
        with patch("app.services.correction_detector.create_llm_client", return_value=mock):
            result = detect_correction("不对，这有问题")

        assert result.is_correction is False
