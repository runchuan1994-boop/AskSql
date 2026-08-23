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
