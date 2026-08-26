"""纠错记忆流程集成测试。

测试完整链路：用户纠错 → 检测 → schema 验证 → 存储 → 召回 → 注入 context。
所有 LLM 调用均 mock，不依赖外部服务。
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from nl2sql.schema.models import Column, Table
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


# 测试用的表结构
TEST_TABLES = [
    Table(
        name="orders",
        columns=[
            Column(name="order_id", type="INT"),
            Column(name="total_amount", type="DECIMAL"),
            Column(name="status", type="VARCHAR"),
            Column(name="user_id", type="INT"),
        ],
    ),
    Table(
        name="users",
        columns=[
            Column(name="user_id", type="INT"),
            Column(name="name", type="VARCHAR"),
            Column(name="level", type="INT"),
        ],
    ),
]


def _mock_llm(json_content: str) -> MagicMock:
    mock_client = MagicMock()
    mock_client.chat.return_value = ChatResponse(content=json_content)
    return mock_client


class TestCorrectionToMemoryFlow:
    """纠错检测 → 记忆存储 → 召回 → 注入 完整流程。"""

    def test_full_flow_column_correction(self):
        """完整流程：列含义纠错 → 检测 → 验证 → 存储 → 召回 → 注入。"""
        from app.services.correction_detector import (
            detect_correction,
            validate_memory_against_schema,
        )
        from app.services.memory_service import (
            add_memory,
            get_memories_for_query,
        )
        from nl2sql.agent.nodes._schema_context import inject_memories_into_context

        # Step 1: 模拟 LLM 检测纠错
        fake_response = '''{
  "is_correction": true,
  "memory_type": "column_description",
  "entity_type": "column",
  "entity_name": "orders.total_amount",
  "content": "total_amount 是商品原价，不是实付金额"
}'''
        mock_client = _mock_llm(fake_response)
        with patch("app.services.correction_detector.create_llm_client",
                   return_value=mock_client):
            correction = detect_correction("不对，amount 不是实付金额，是原价")

        assert correction.is_correction is True
        assert correction.memory_type == "column_description"

        # Step 2: schema 验证
        correction = validate_memory_against_schema(correction, TEST_TABLES)
        assert correction.is_correction is True
        assert correction.entity_name == "orders.total_amount"

        # Step 3: 存储记忆
        mem = add_memory(
            datasource_id="ds_test",
            memory_type=correction.memory_type,
            entity_type=correction.entity_type,
            entity_name=correction.entity_name,
            content=correction.content,
            raw_content=correction.raw_content,
            source="user_correction",
            confidence=0.8,
        )
        assert mem["id"].startswith("mem_")
        assert mem["confidence"] == 0.8

        # Step 4: 召回记忆
        memories = get_memories_for_query(
            datasource_id="ds_test",
            query="订单金额统计",
            related_tables=["orders"],
        )
        assert len(memories) >= 1
        found = [m for m in memories if m["entity_name"] == "orders.total_amount"]
        assert len(found) == 1
        assert "原价" in found[0]["content"]

        # Step 5: 注入 schema context（使用与 format_table_context 一致的格式）
        schema_context = """表: orders
描述: 订单表
  · order_id: INT [PK]
  · total_amount: DECIMAL (金额)
  · status: VARCHAR"""

        result = inject_memories_into_context(schema_context, memories)
        # 列记忆应该注入到对应列后面
        assert "📝 用户备注" in result
        assert "原价" in result
        assert "total_amount" in result

    def test_full_flow_term_mapping(self):
        """完整流程：术语映射纠错 → 检测 → 存储 → 召回 → 注入（顶部）。"""
        from app.services.correction_detector import (
            detect_correction,
            validate_memory_against_schema,
        )
        from app.services.memory_service import (
            add_memory,
            get_memories_for_query,
        )
        from nl2sql.agent.nodes._schema_context import inject_memories_into_context

        fake_response = '''{
  "is_correction": true,
  "memory_type": "term_mapping",
  "entity_type": "term",
  "entity_name": "流水",
  "content": "流水就是 GMV（商品交易总额）"
}'''
        mock_client = _mock_llm(fake_response)
        with patch("app.services.correction_detector.create_llm_client",
                   return_value=mock_client):
            correction = detect_correction("其实流水指的是 GMV")

        assert correction.is_correction is True

        # 术语映射不需要 schema 验证
        correction = validate_memory_against_schema(correction, TEST_TABLES)
        assert correction.is_correction is True

        mem = add_memory(
            datasource_id="ds_test",
            memory_type=correction.memory_type,
            entity_type=correction.entity_type,
            entity_name=correction.entity_name,
            content=correction.content,
            raw_content=correction.raw_content,
            source="user_correction",
            confidence=0.8,
        )
        assert mem["id"].startswith("mem_")

        # 召回：用包含"流水"关键词的查询
        memories = get_memories_for_query(
            datasource_id="ds_test",
            query="上个月的流水是多少",
            related_tables=["orders"],
        )
        assert len(memories) >= 1
        found = [m for m in memories if m["memory_type"] == "term_mapping"]
        assert len(found) >= 1

        # 注入到 context 顶部
        schema_context = """表：orders
描述：订单表
  - order_id INT
  - total_amount DECIMAL"""

        result = inject_memories_into_context(schema_context, memories)
        assert "业务术语说明" in result
        assert "GMV" in result
        # 术语说明应该在表描述之前
        term_pos = result.index("业务术语说明")
        table_pos = result.index("表：orders")
        assert term_pos < table_pos

    def test_full_flow_not_correction_no_memory(self):
        """非纠错消息不会创建记忆。"""
        from app.services.correction_detector import detect_correction
        from app.services.memory_service import list_memories

        fake_response = '{"is_correction": false}'
        mock_client = _mock_llm(fake_response)
        with patch("app.services.correction_detector.create_llm_client",
                   return_value=mock_client):
            correction = detect_correction("不对，再看看上个月的数据")

        assert correction.is_correction is False

        # 数据库中应该没有记忆
        result = list_memories("ds_test")
        assert result["total"] == 0

    def test_full_flow_entity_not_found_no_memory(self):
        """实体不存在时，schema 验证取消纠错，不存记忆。"""
        from app.services.correction_detector import (
            detect_correction,
            validate_memory_against_schema,
        )
        from app.services.memory_service import list_memories

        fake_response = '''{
  "is_correction": true,
  "memory_type": "column_description",
  "entity_type": "column",
  "entity_name": "orders.nonexistent_col",
  "content": "不存在的列"
}'''
        mock_client = _mock_llm(fake_response)
        with patch("app.services.correction_detector.create_llm_client",
                   return_value=mock_client):
            correction = detect_correction("不对，nonexistent_col 有错")

        assert correction.is_correction is True  # LLM 认为是纠错

        # schema 验证后应该取消
        correction = validate_memory_against_schema(correction, TEST_TABLES)
        assert correction.is_correction is False

        # 没有记忆被创建
        result = list_memories("ds_test")
        assert result["total"] == 0

    def test_full_flow_table_correction(self):
        """表范围补充完整流程。"""
        from app.services.correction_detector import (
            detect_correction,
            validate_memory_against_schema,
        )
        from app.services.memory_service import (
            add_memory,
            get_memories_for_query,
        )
        from nl2sql.agent.nodes._schema_context import inject_memories_into_context

        fake_response = '''{
  "is_correction": true,
  "memory_type": "table_description",
  "entity_type": "table",
  "entity_name": "orders",
  "content": "orders 表只存储主站订单，不包含第三方渠道订单"
}'''
        mock_client = _mock_llm(fake_response)
        with patch("app.services.correction_detector.create_llm_client",
                   return_value=mock_client):
            correction = detect_correction("补充一下，orders 表只存主站订单")

        assert correction.is_correction is True

        correction = validate_memory_against_schema(correction, TEST_TABLES)
        assert correction.is_correction is True
        assert correction.entity_name == "orders"

        mem = add_memory(
            datasource_id="ds_test",
            memory_type=correction.memory_type,
            entity_type=correction.entity_type,
            entity_name=correction.entity_name,
            content=correction.content,
            raw_content=correction.raw_content,
            source="user_correction",
            confidence=0.8,
        )

        memories = get_memories_for_query(
            datasource_id="ds_test",
            query="订单统计",
            related_tables=["orders"],
        )
        assert any(m["entity_name"] == "orders" and m["memory_type"] == "table_description"
                   for m in memories)

        schema_context = """表: orders
描述: 订单表
  · order_id: INT [PK]"""

        result = inject_memories_into_context(schema_context, memories)
        assert "📝 用户备注" in result
        assert "主站订单" in result

    def test_full_flow_invalid_json_handled(self):
        """LLM 返回格式异常时，降级为非纠错，不创建记忆。"""
        from app.services.correction_detector import detect_correction
        from app.services.memory_service import list_memories

        # LLM 返回了完全无法解析的内容
        mock_client = _mock_llm("我需要更多信息才能判断。")
        with patch("app.services.correction_detector.create_llm_client",
                   return_value=mock_client):
            correction = detect_correction("不对，这有问题")

        assert correction.is_correction is False

        result = list_memories("ds_test")
        assert result["total"] == 0

    def test_full_flow_metric_definition(self):
        """指标定义完整流程。"""
        from app.services.correction_detector import (
            detect_correction,
            validate_memory_against_schema,
        )
        from app.services.memory_service import (
            add_memory,
            get_memories_for_query,
        )
        from nl2sql.agent.nodes._schema_context import inject_memories_into_context

        fake_response = '''{
  "is_correction": true,
  "memory_type": "metric_definition",
  "entity_type": "metric",
  "entity_name": "转化率",
  "content": "转化率 = 下单用户数 / 访问用户数"
}'''
        mock_client = _mock_llm(fake_response)
        with patch("app.services.correction_detector.create_llm_client",
                   return_value=mock_client):
            correction = detect_correction("纠正一下，转化率应该是下单用户数除以访问用户数")

        assert correction.is_correction is True
        assert correction.memory_type == "metric_definition"

        # 指标定义不需要 schema 验证
        correction = validate_memory_against_schema(correction, TEST_TABLES)
        assert correction.is_correction is True

        mem = add_memory(
            datasource_id="ds_test",
            memory_type=correction.memory_type,
            entity_type=correction.entity_type,
            entity_name=correction.entity_name,
            content=correction.content,
            raw_content=correction.raw_content,
            source="user_correction",
            confidence=0.8,
        )

        # 召回
        memories = get_memories_for_query(
            datasource_id="ds_test",
            query="转化率统计",
            related_tables=["orders", "users"],
        )
        assert any(m["memory_type"] == "metric_definition" for m in memories)

        # 注入顶部
        schema_context = "表: orders\n描述: 订单表\n  · order_id: INT [PK]"
        result = inject_memories_into_context(schema_context, memories)
        assert "业务术语说明" in result or "转化率" in result


class TestCorrectionEdgeCases:
    """边界情况集成测试。"""

    def test_keyword_filter_skips_llm(self):
        """无纠错关键词时，不调用 LLM，直接返回 False。"""
        from app.services.correction_detector import detect_correction

        mock_client = _mock_llm('{"is_correction": true}')
        with patch("app.services.correction_detector.create_llm_client",
                   return_value=mock_client):
            result = detect_correction("帮我查一下订单数据")

        assert result.is_correction is False
        mock_client.chat.assert_not_called()

    def test_llm_exception_fails_closed(self):
        """LLM 调用异常时 fail-closed（不判定为纠错）。"""
        from app.services.correction_detector import detect_correction
        from app.services.memory_service import list_memories

        mock_client = MagicMock()
        mock_client.chat.side_effect = Exception("API 调用失败")
        with patch("app.services.correction_detector.create_llm_client",
                   return_value=mock_client):
            correction = detect_correction("不对，这个字段错了")

        assert correction.is_correction is False
        result = list_memories("ds_test")
        assert result["total"] == 0

    def test_fuzzy_table_name_in_validation(self):
        """schema 验证时表名模糊匹配。"""
        from app.services.correction_detector import (
            CorrectionResult,
            validate_memory_against_schema,
        )

        corr = CorrectionResult(
            is_correction=True,
            memory_type="table_description",
            entity_type="table",
            entity_name="order",  # 少了 s
            content="主站订单",
        )
        result = validate_memory_against_schema(corr, TEST_TABLES)
        assert result.is_correction is True
        assert result.entity_name == "orders"  # 被修正为正确表名

    def test_re_correction_overwrites_old_memory(self):
        """用户再次纠正同一实体时，覆盖旧记忆而不是创建第二条。"""
        from app.services.memory_service import (
            add_memory,
            upsert_correction_memory,
            list_memories,
            find_memory_by_entity,
        )

        # 第一次纠错
        upsert_correction_memory(
            datasource_id="ds_test",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.total_amount",
            content="amount 是原价",
            raw_content="不对，amount 是原价",
            source_session_id="sess_1",
            source_message_id="msg_1",
        )

        # 验证只有一条
        result = list_memories("ds_test")
        assert result["total"] == 1
        assert "原价" in result["items"][0]["content"]
        assert result["items"][0]["confidence"] == 0.8

        # 第二次纠错（同一实体，不同内容）
        upsert_correction_memory(
            datasource_id="ds_test",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.total_amount",
            content="amount 是订单总额，包含运费",
            raw_content="不对，应该是订单总额",
            source_session_id="sess_1",
            source_message_id="msg_2",
        )

        # 仍然只有一条，但内容更新了
        result = list_memories("ds_test")
        assert result["total"] == 1
        assert "订单总额" in result["items"][0]["content"]
        assert result["items"][0]["confidence"] == 0.8  # 重置为待确认

    def test_confirmation_boosts_confidence(self):
        """确认后记忆 confidence 从 0.8 提升到 0.9。"""
        from app.services.memory_service import (
            add_memory,
            get_memory,
        )
        from app.services.chat_service import confirm_pending_memories

        # 创建一条待确认的纠错记忆
        mem = add_memory(
            datasource_id="ds_test",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="amount 是原价",
            source="user_correction",
            confidence=0.8,
        )
        assert mem["confidence"] == 0.8

        # 确认
        confirm_pending_memories("sess_test", [mem["id"]])

        # 验证提升
        updated = get_memory(mem["id"])
        assert updated is not None
        assert updated["confidence"] == 0.9
        assert updated["source"] == "user_correction_confirmed"

    def test_memory_datasource_isolation(self):
        """不同数据源的记忆互相隔离。"""
        from app.services.memory_service import (
            add_memory,
            get_memories_for_query,
        )

        # 在 ds_1 中创建记忆
        add_memory(
            datasource_id="ds_1",
            memory_type="term_mapping",
            entity_type="term",
            entity_name="流水",
            content="流水 = GMV",
            source="user_correction",
            confidence=0.8,
        )
        # 在 ds_2 中创建记忆
        add_memory(
            datasource_id="ds_2",
            memory_type="term_mapping",
            entity_type="term",
            entity_name="流水",
            content="流水 = 现金流",
            source="user_correction",
            confidence=0.8,
        )

        # 查 ds_1 只能看到 ds_1 的记忆
        mems_1 = get_memories_for_query(
            datasource_id="ds_1",
            query="流水",
            related_tables=[],
        )
        assert all(m["datasource_id"] == "ds_1" for m in mems_1)
        assert any("GMV" in m["content"] for m in mems_1)

        # 查 ds_2 只能看到 ds_2 的记忆
        mems_2 = get_memories_for_query(
            datasource_id="ds_2",
            query="流水",
            related_tables=[],
        )
        assert all(m["datasource_id"] == "ds_2" for m in mems_2)
        assert any("现金流" in m["content"] for m in mems_2)
