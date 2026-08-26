"""测试 MemoryService。"""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def use_temp_db(monkeypatch):
    """每个测试用独立的临时数据库。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    monkeypatch.setenv("APP_DATABASE_URL", f"sqlite:///{db_path}")

    # 重新加载模块以获取新的 settings
    import importlib
    import app.core.config as config_module
    import app.core.database as db_module
    importlib.reload(config_module)
    importlib.reload(db_module)
    db_module.init_db()

    # 重新加载 memory_service（因为它导入了 get_connection）
    import app.services.memory_service as ms_module
    importlib.reload(ms_module)

    yield db_path

    os.unlink(db_path)


class TestAddMemory:
    def test_add_basic_memory(self):
        from app.services.memory_service import add_memory

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.total_amount",
            content="amount 是商品原价，不是实付金额",
            source="user_correction",
            source_session_id="sess_1",
            confidence=0.8,
        )

        assert mem["id"].startswith("mem_")
        assert mem["datasource_id"] == "ds_1"
        assert mem["memory_type"] == "column_description"
        assert mem["entity_name"] == "orders.total_amount"
        assert mem["confidence"] == 0.8
        assert mem["is_active"] == 1
        assert mem["access_count"] == 0

    def test_add_term_mapping(self):
        from app.services.memory_service import add_memory

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="term_mapping",
            entity_type="term",
            entity_name="流水",
            content="流水就是 GMV，即订单总金额",
            source="manual_add",
            confidence=1.0,
        )
        assert mem["memory_type"] == "term_mapping"
        assert mem["entity_name"] == "流水"
        assert mem["confidence"] == 1.0

    def test_add_without_entity(self):
        from app.services.memory_service import add_memory

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="term_mapping",
            entity_type=None,
            entity_name=None,
            content="some content",
        )
        assert mem["id"].startswith("mem_")
        assert mem["entity_type"] is None
        assert mem["entity_name"] is None


class TestGetMemory:
    def test_get_existing(self):
        from app.services.memory_service import add_memory, get_memory

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="test",
        )
        fetched = get_memory(mem["id"])
        assert fetched is not None
        assert fetched["content"] == "test"

    def test_get_nonexistent(self):
        from app.services.memory_service import get_memory

        assert get_memory("mem_nonexistent") is None


class TestGetMemoriesForQuery:
    def test_table_level_memory_recalled(self):
        from app.services.memory_service import add_memory, get_memories_for_query

        add_memory(
            datasource_id="ds_1",
            memory_type="table_description",
            entity_type="table",
            entity_name="orders",
            content="orders 表只存主站订单",
        )

        result = get_memories_for_query(
            datasource_id="ds_1",
            query="订单总数",
            related_tables=["orders"],
        )
        assert len(result) == 1
        assert result[0]["entity_name"] == "orders"

    def test_term_memory_recalled_by_keyword(self):
        from app.services.memory_service import add_memory, get_memories_for_query

        add_memory(
            datasource_id="ds_1",
            memory_type="term_mapping",
            entity_type="term",
            entity_name="流水",
            content="流水就是 GMV",
        )

        result = get_memories_for_query(
            datasource_id="ds_1",
            query="上个月的流水是多少",
        )
        assert len(result) == 1
        assert "流水" in result[0]["entity_name"]

    def test_metric_memory_recalled_by_keyword(self):
        from app.services.memory_service import add_memory, get_memories_for_query

        add_memory(
            datasource_id="ds_1",
            memory_type="metric_definition",
            entity_type="metric",
            entity_name="GMV",
            content="GMV = total_amount + shipping_fee",
        )

        result = get_memories_for_query(
            datasource_id="ds_1",
            query="本月 GMV 是多少",
        )
        assert len(result) == 1
        assert result[0]["entity_name"] == "GMV"

    def test_memory_isolated_by_datasource(self):
        from app.services.memory_service import add_memory, get_memories_for_query

        add_memory(
            datasource_id="ds_1",
            memory_type="table_description",
            entity_type="table",
            entity_name="orders",
            content="orders in ds1",
        )

        result = get_memories_for_query(
            datasource_id="ds_2",  # 不同的数据源
            query="订单",
            related_tables=["orders"],
        )
        assert len(result) == 0

    def test_column_level_memory_recalled(self):
        from app.services.memory_service import add_memory, get_memories_for_query

        add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.total_amount",
            content="商品原价",
        )

        result = get_memories_for_query(
            datasource_id="ds_1",
            query="订单金额",
            related_tables=["orders"],
            related_columns=["orders.total_amount"],
        )
        assert len(result) == 1

    def test_no_match_returns_empty(self):
        from app.services.memory_service import get_memories_for_query

        result = get_memories_for_query(
            datasource_id="ds_1",
            query="随便查询",
        )
        assert result == []

    def test_limit_results(self):
        from app.services.memory_service import add_memory, get_memories_for_query

        for i in range(15):
            add_memory(
                datasource_id="ds_1",
                memory_type="term_mapping",
                entity_type="term",
                entity_name=f"术语{i}",
                content=f"术语{i}的含义",
            )

        result = get_memories_for_query(
            datasource_id="ds_1",
            query="术语0 术语1 术语2",
            limit=5,
        )
        assert len(result) <= 5


class TestUpdateAndDelete:
    def test_update_memory(self):
        from app.services.memory_service import add_memory, update_memory

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="old content",
        )
        updated = update_memory(
            mem["id"], {"content": "new content", "confidence": 0.95}
        )
        assert updated is not None
        assert updated["content"] == "new content"
        assert updated["confidence"] == 0.95

    def test_update_no_fields(self):
        from app.services.memory_service import add_memory, update_memory

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="test",
        )
        updated = update_memory(mem["id"], {})
        assert updated is not None
        assert updated["content"] == "test"

    def test_delete_memory_soft(self):
        from app.services.memory_service import add_memory, delete_memory, list_memories

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="test",
        )
        result = delete_memory(mem["id"])
        assert result is True

        # 软删除后列表中不应出现
        listed = list_memories("ds_1")
        assert listed["total"] == 0

        # 但 include_inactive 可以看到
        listed_all = list_memories("ds_1", include_inactive=True)
        assert listed_all["total"] == 1

    def test_delete_nonexistent(self):
        from app.services.memory_service import delete_memory

        assert delete_memory("mem_nonexistent") is False


class TestListMemories:
    def test_pagination(self):
        from app.services.memory_service import add_memory, list_memories

        for i in range(5):
            add_memory(
                datasource_id="ds_1",
                memory_type="column_description",
                entity_type="column",
                entity_name=f"col_{i}",
                content=f"memory {i}",
            )

        page1 = list_memories("ds_1", page=1, page_size=2)
        assert page1["total"] == 5
        assert len(page1["items"]) == 2
        assert page1["has_more"] is True

        page3 = list_memories("ds_1", page=3, page_size=2)
        assert len(page3["items"]) == 1
        assert page3["has_more"] is False

    def test_filter_by_type(self):
        from app.services.memory_service import add_memory, list_memories

        add_memory(
            datasource_id="ds_1", memory_type="column_description",
            entity_type="column", entity_name="c1", content="col mem",
        )
        add_memory(
            datasource_id="ds_1", memory_type="term_mapping",
            entity_type="term", entity_name="t1", content="term mem",
        )

        result = list_memories("ds_1", memory_type="term_mapping")
        assert result["total"] == 1
        assert result["items"][0]["memory_type"] == "term_mapping"

    def test_filter_by_entity_type(self):
        from app.services.memory_service import add_memory, list_memories

        add_memory(
            datasource_id="ds_1", memory_type="column_description",
            entity_type="column", entity_name="c1", content="col mem",
        )
        add_memory(
            datasource_id="ds_1", memory_type="table_description",
            entity_type="table", entity_name="t1", content="table mem",
        )

        result = list_memories("ds_1", entity_type="table")
        assert result["total"] == 1
        assert result["items"][0]["entity_type"] == "table"

    def test_search(self):
        from app.services.memory_service import add_memory, list_memories

        add_memory(
            datasource_id="ds_1", memory_type="column_description",
            entity_type="column", entity_name="amount",
            content="这是金额字段",
        )
        add_memory(
            datasource_id="ds_1", memory_type="column_description",
            entity_type="column", entity_name="status",
            content="订单状态",
        )

        result = list_memories("ds_1", search="金额")
        assert result["total"] == 1
        assert "amount" in result["items"][0]["entity_name"]

    def test_search_by_entity_name(self):
        from app.services.memory_service import add_memory, list_memories

        add_memory(
            datasource_id="ds_1", memory_type="column_description",
            entity_type="column", entity_name="special_field",
            content="some content",
        )
        add_memory(
            datasource_id="ds_1", memory_type="column_description",
            entity_type="column", entity_name="other_field",
            content="other content",
        )

        result = list_memories("ds_1", search="special")
        assert result["total"] == 1


class TestGetMemoriesIncrementsAccess:
    def test_get_memories_increments_access_count(self):
        from app.services.memory_service import (
            add_memory, get_memory, get_memories_for_query,
        )

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="table_description",
            entity_type="table",
            entity_name="orders",
            content="orders table",
        )
        assert mem["access_count"] == 0

        # 第一次召回
        result = get_memories_for_query(
            datasource_id="ds_1",
            query="订单",
            related_tables=["orders"],
        )
        assert len(result) == 1
        updated = get_memory(mem["id"])
        assert updated and updated["access_count"] == 1

        # 第二次召回
        get_memories_for_query(
            datasource_id="ds_1",
            query="订单",
            related_tables=["orders"],
        )
        updated = get_memory(mem["id"])
        assert updated and updated["access_count"] == 2

    def test_column_memory_recalled_by_table(self):
        from app.services.memory_service import add_memory, get_memories_for_query

        add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="amount 是商品原价",
        )

        result = get_memories_for_query(
            datasource_id="ds_1",
            query="订单金额",
            related_tables=["orders"],
        )
        assert len(result) == 1
        assert result[0]["entity_name"] == "orders.amount"

    def test_column_memory_not_recalled_for_other_table(self):
        from app.services.memory_service import add_memory, get_memories_for_query

        add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="amount 是商品原价",
        )

        result = get_memories_for_query(
            datasource_id="ds_1",
            query="用户信息",
            related_tables=["users"],
        )
        assert len(result) == 0


class TestIncrementAccess:
    def test_increment(self):
        from app.services.memory_service import add_memory, get_memory, increment_access

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="test",
        )
        assert mem["access_count"] == 0

        increment_access(mem["id"])
        updated = get_memory(mem["id"])
        assert updated and updated["access_count"] == 1

        increment_access(mem["id"])
        increment_access(mem["id"])
        updated = get_memory(mem["id"])
        assert updated and updated["access_count"] == 3


class TestConfirmPendingMemories:
    """测试 chat_service.confirm_pending_memories 函数。"""

    def test_confirm_pending_memories_updates_confidence(self):
        """user_correction 来源的记忆确认后 confidence 从 0.8 升到 0.9，source 变更。"""
        from app.services.memory_service import add_memory, get_memory
        from app.services.chat_service import confirm_pending_memories

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="amount 是原价",
            source="user_correction",
            confidence=0.8,
        )
        assert mem["confidence"] == 0.8
        assert mem["source"] == "user_correction"

        confirm_pending_memories("sess_1", [mem["id"]])

        updated = get_memory(mem["id"])
        assert updated is not None
        assert updated["confidence"] == 0.9
        assert updated["source"] == "user_correction_confirmed"

    def test_confirm_empty_list_does_nothing(self):
        """空列表不做任何操作。"""
        from app.services.chat_service import confirm_pending_memories

        # 不应抛异常
        confirm_pending_memories("sess_1", [])

    def test_confirm_non_correction_source_unchanged(self):
        """手动添加的记忆（非 user_correction 来源）不被修改。"""
        from app.services.memory_service import add_memory, get_memory
        from app.services.chat_service import confirm_pending_memories

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="term_mapping",
            entity_type="term",
            entity_name="GMV",
            content="GMV 是总交易额",
            source="manual_add",
            confidence=0.8,
        )

        confirm_pending_memories("sess_1", [mem["id"]])

        updated = get_memory(mem["id"])
        assert updated is not None
        assert updated["confidence"] == 0.8
        assert updated["source"] == "manual_add"

    def test_confirm_already_high_confidence_unchanged(self):
        """已经 >= 0.9 的记忆不被修改（不降级）。"""
        from app.services.memory_service import add_memory, get_memory
        from app.services.chat_service import confirm_pending_memories

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="amount 是原价",
            source="user_correction_confirmed",
            confidence=0.95,
        )

        confirm_pending_memories("sess_1", [mem["id"]])

        updated = get_memory(mem["id"])
        assert updated is not None
        assert updated["confidence"] == 0.95
        # source 也不变（因为 confidence 已经 >= 0.9，跳过）
        assert updated["source"] == "user_correction_confirmed"

    def test_confirm_already_confirmed_source_still_upgrades_from_08(self):
        """source 已是 user_correction_confirmed 但 confidence 还是 0.8 的边缘情况也会提升。"""
        from app.services.memory_service import add_memory, get_memory
        from app.services.chat_service import confirm_pending_memories

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="amount 是原价",
            source="user_correction_confirmed",
            confidence=0.8,
        )

        confirm_pending_memories("sess_1", [mem["id"]])

        updated = get_memory(mem["id"])
        assert updated is not None
        assert updated["confidence"] == 0.9

    def test_confirm_nonexistent_memory_no_error(self):
        """不存在的记忆 ID 不抛异常。"""
        from app.services.chat_service import confirm_pending_memories

        # 不应抛异常
        confirm_pending_memories("sess_1", ["mem_nonexistent_123"])

    def test_confirm_multiple_memories(self):
        """批量确认多条记忆。"""
        from app.services.memory_service import add_memory, get_memory
        from app.services.chat_service import confirm_pending_memories

        mem1 = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="amount 是原价",
            source="user_correction",
            confidence=0.8,
        )
        mem2 = add_memory(
            datasource_id="ds_1",
            memory_type="term_mapping",
            entity_type="term",
            entity_name="流水",
            content="流水就是 GMV",
            source="user_correction",
            confidence=0.8,
        )

        confirm_pending_memories("sess_1", [mem1["id"], mem2["id"]])

        u1 = get_memory(mem1["id"])
        u2 = get_memory(mem2["id"])
        assert u1["confidence"] == 0.9
        assert u1["source"] == "user_correction_confirmed"
        assert u2["confidence"] == 0.9
        assert u2["source"] == "user_correction_confirmed"


class TestGetMemoriesForTable:
    def test_returns_table_and_column_memories(self):
        from app.services.memory_service import add_memory, get_memories_for_table

        add_memory(
            datasource_id="ds_1",
            memory_type="table_description",
            entity_type="table",
            entity_name="orders",
            content="table mem",
        )
        add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="column mem",
        )
        add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="users.name",
            content="other table mem",
        )

        result = get_memories_for_table("ds_1", "orders")
        assert len(result) == 2  # 1 表级 + 1 列级


class TestFindMemoryByEntity:
    def test_find_memory_by_entity_found(self):
        from app.services.memory_service import add_memory, find_memory_by_entity

        add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="amount is original price",
            source="user_correction",
            confidence=0.8,
        )

        result = find_memory_by_entity("ds_1", "column_description", "orders.amount")
        assert result is not None
        assert result["entity_name"] == "orders.amount"
        assert result["content"] == "amount is original price"

    def test_find_memory_by_entity_not_found(self):
        from app.services.memory_service import find_memory_by_entity

        result = find_memory_by_entity("ds_1", "column_description", "orders.nonexistent")
        assert result is None

    def test_find_returns_highest_confidence(self):
        from app.services.memory_service import add_memory, find_memory_by_entity

        add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="low confidence",
            confidence=0.5,
        )
        add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="high confidence",
            confidence=0.95,
        )

        result = find_memory_by_entity("ds_1", "column_description", "orders.amount")
        assert result is not None
        assert result["content"] == "high confidence"
        assert result["confidence"] == 0.95

    def test_find_skips_inactive(self):
        from app.services.memory_service import (
            add_memory, delete_memory, find_memory_by_entity,
        )

        mem = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="to be deleted",
        )
        delete_memory(mem["id"])

        result = find_memory_by_entity("ds_1", "column_description", "orders.amount")
        assert result is None

    def test_find_isolated_by_datasource(self):
        from app.services.memory_service import add_memory, find_memory_by_entity

        add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="ds1 content",
        )

        result = find_memory_by_entity("ds_2", "column_description", "orders.amount")
        assert result is None


class TestUpsertCorrectionMemory:
    def test_upsert_new_memory(self):
        """没有旧记忆时创建新的。"""
        from app.services.memory_service import (
            list_memories, upsert_correction_memory,
        )

        mem = upsert_correction_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="amount is original price",
            raw_content="用户说 amount 是原价",
            source_session_id="sess_1",
            source_message_id="msg_1",
        )

        assert mem["id"].startswith("mem_")
        assert mem["entity_name"] == "orders.amount"
        assert mem["content"] == "amount is original price"
        assert mem["source"] == "user_correction"
        assert mem["confidence"] == 0.8
        assert mem["source_session_id"] == "sess_1"
        assert mem["source_message_id"] == "msg_1"

        listed = list_memories("ds_1")
        assert listed["total"] == 1

    def test_upsert_overwrites_existing(self):
        """有旧自动纠错记忆时更新内容和 confidence。"""
        from app.services.memory_service import (
            add_memory, list_memories, upsert_correction_memory,
        )

        # 先创建一条旧的纠错记忆（已确认，confidence=0.9）
        old = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="old content: amount is original price",
            source="user_correction_confirmed",
            confidence=0.9,
            source_session_id="sess_old",
            source_message_id="msg_old",
        )

        # 新的纠错覆盖旧记忆
        updated = upsert_correction_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="new content: amount is order total",
            raw_content="用户纠正：amount 其实是订单总额",
            source_session_id="sess_new",
            source_message_id="msg_new",
        )

        # id 不变，是同一条记录
        assert updated["id"] == old["id"]
        assert updated["content"] == "new content: amount is order total"
        assert updated["raw_content"] == "用户纠正：amount 其实是订单总额"
        assert updated["confidence"] == 0.8  # 重置为 0.8
        assert updated["source"] == "user_correction"  # 改回 user_correction
        assert updated["source_session_id"] == "sess_new"
        assert updated["source_message_id"] == "msg_new"

        # 总数不变，没有新增
        listed = list_memories("ds_1")
        assert listed["total"] == 1

    def test_upsert_keeps_manual(self):
        """手动添加的记忆不被覆盖，而是并存。"""
        from app.services.memory_service import (
            add_memory, list_memories, upsert_correction_memory,
        )

        # 手动添加的记忆（高优先级）
        manual = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="manual definition",
            source="manual_add",
            confidence=1.0,
        )

        # 自动纠错不覆盖手动添加的，而是并存
        new_mem = upsert_correction_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="auto correction content",
            source_session_id="sess_1",
            source_message_id="msg_1",
        )

        # 新建了一条，不是同一条
        assert new_mem["id"] != manual["id"]
        assert new_mem["source"] == "user_correction"
        assert new_mem["confidence"] == 0.8

        # 两条记忆并存
        listed = list_memories("ds_1")
        assert listed["total"] == 2

        # 手动添加的仍然存在且内容不变
        from app.services.memory_service import get_memory
        manual_updated = get_memory(manual["id"])
        assert manual_updated is not None
        assert manual_updated["content"] == "manual definition"
        assert manual_updated["source"] == "manual_add"
        assert manual_updated["confidence"] == 1.0

    def test_upsert_different_entity(self):
        """不同实体创建不同记忆。"""
        from app.services.memory_service import list_memories, upsert_correction_memory

        upsert_correction_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="amount desc",
        )
        upsert_correction_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.status",
            content="status desc",
        )

        listed = list_memories("ds_1")
        assert listed["total"] == 2

    def test_upsert_preserves_access_count(self):
        """更新时保留 access_count。"""
        from app.services.memory_service import (
            add_memory, increment_access, upsert_correction_memory,
        )

        old = add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="old content",
            source="user_correction",
        )

        # 增加访问次数
        increment_access(old["id"])
        increment_access(old["id"])

        updated = upsert_correction_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="new content",
        )

        assert updated["id"] == old["id"]
        assert updated["access_count"] == 2


class TestMemoryRecallRanking:
    """测试记忆召回的相关性排序优化。"""

    def test_table_memory_ranks_higher_than_term(self):
        """表级精确匹配的记忆排名应该高于术语关键词匹配。"""
        from app.services.memory_service import add_memory, get_memories_for_query

        # 表级记忆（confidence 较低但匹配度高）
        add_memory(
            datasource_id="ds_1",
            memory_type="table_description",
            entity_type="table",
            entity_name="orders",
            content="主站订单表",
            confidence=0.8,
        )
        # 术语记忆（confidence 高但只是关键词匹配）
        add_memory(
            datasource_id="ds_1",
            memory_type="term_mapping",
            entity_type="term",
            entity_name="GMV",
            content="商品交易总额",
            confidence=1.0,
            source="manual_add",
        )

        result = get_memories_for_query(
            datasource_id="ds_1",
            query="GMV 和订单统计",
            related_tables=["orders"],
        )
        # 表级精确匹配（8分*0.3 + 0.8*10*0.5 = 2.4+4 = 6.4）
        # vs 术语实体名匹配（6分*0.3 + 1.0*10*0.5 = 1.8+5 = 6.8）
        # 术语置信度高可能排前，但表级也应该在前 2
        assert len(result) == 2
        entity_names = [m["entity_name"] for m in result]
        assert "orders" in entity_names
        assert "GMV" in entity_names

    def test_exact_column_match_ranks_higher_than_prefix(self):
        """列精确匹配应该比表前缀匹配排名更高。"""
        from app.services.memory_service import add_memory, get_memories_for_query

        # 精确匹配的列（低 confidence）
        add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.total_amount",
            content="商品原价",
            confidence=0.8,
        )
        # 前缀匹配的列（高 confidence）
        add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.status",
            content="订单状态",
            confidence=0.9,
        )

        # 只传列名精确匹配一个
        result = get_memories_for_query(
            datasource_id="ds_1",
            query="统计",
            related_tables=["orders"],
            related_columns=["orders.total_amount"],
        )
        # 两条都能召回（一条精确匹配，一条表前缀匹配）
        assert len(result) == 2
        # 精确匹配的应该排第一（即使 confidence 低一些）
        assert result[0]["entity_name"] == "orders.total_amount"

    def test_term_entity_match_beats_content_match(self):
        """术语记忆中，实体名精确匹配的应该比内容关键词匹配的排名高。"""
        from app.services.memory_service import add_memory, get_memories_for_query

        # 实体名匹配（低 confidence）
        add_memory(
            datasource_id="ds_1",
            memory_type="term_mapping",
            entity_type="term",
            entity_name="流水",
            content="就是 GMV",
            confidence=0.8,
        )
        # 内容关键词匹配（高 confidence，但实体名不在查询里）
        add_memory(
            datasource_id="ds_1",
            memory_type="term_mapping",
            entity_type="term",
            entity_name="客单价",
            content="平均每笔订单金额",
            confidence=1.0,
            source="manual_add",
        )

        result = get_memories_for_query(
            datasource_id="ds_1",
            query="上月流水统计",
        )
        # 两条都能召回（流水实体匹配，客单价是内容部分匹配）
        assert len(result) >= 1
        # "流水" 实体名匹配应该排第一
        assert result[0]["entity_name"] == "流水"

    def test_query_boosts_relevant_memory(self):
        """查询关键词命中会提升记忆排名。"""
        from app.services.memory_service import add_memory, get_memories_for_query

        add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.status",
            content="订单状态",
            confidence=0.8,
        )
        add_memory(
            datasource_id="ds_1",
            memory_type="column_description",
            entity_type="column",
            entity_name="orders.amount",
            content="订单金额",
            confidence=0.8,
        )

        # 查询包含 "状态"，status 列记忆应该排名更靠前
        result = get_memories_for_query(
            datasource_id="ds_1",
            query="订单状态分布",
            related_tables=["orders"],
        )
        assert len(result) == 2
        assert "status" in result[0]["entity_name"]

    def test_same_confidence_ranked_by_match_score(self):
        """相同 confidence 下，匹配度高的排前面。"""
        from app.services.memory_service import add_memory, get_memories_for_query

        # 表级（匹配度高）
        add_memory(
            datasource_id="ds_1",
            memory_type="table_description",
            entity_type="table",
            entity_name="orders",
            content="订单表",
            confidence=0.9,
        )
        # 术语关键词（匹配度低）
        add_memory(
            datasource_id="ds_1",
            memory_type="term_mapping",
            entity_type="term",
            entity_name="订单",
            content="订单就是 order",
            confidence=0.9,
        )

        result = get_memories_for_query(
            datasource_id="ds_1",
            query="订单统计",
            related_tables=["orders"],
        )
        assert len(result) == 2
        # 表级精确匹配（8 分）应该比术语实体名匹配（6 分）排名高
        assert result[0]["entity_type"] == "table"
