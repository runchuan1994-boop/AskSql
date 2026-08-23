"""测试 chat_service 的事件队列复用机制.

关键验证：start_chat 不能替换队列对象，否则 SSE 端先拿到的引用会失效。
前端的调用顺序是：先建立 SSE 连接（获取队列引用），再发送消息（start_chat）。
如果 start_chat 创建了新队列，事件会全部丢失。
"""
from __future__ import annotations

import asyncio
import importlib
import os
import tempfile

import pytest


def _reload_for_test(tmpdir: str):
    """设置环境并重新加载 chat_service 模块（清空模块级状态）."""
    os.environ["APP_DATA_DIR"] = os.path.join(tmpdir, "data")
    os.environ["APP_DATABASE_URL"] = f"sqlite:///{tmpdir}/data/test.db"
    os.environ["APP_SCHEMAS_DIR"] = os.path.join(tmpdir, "config", "schemas")

    from app.core import config as config_mod

    importlib.reload(config_mod)
    from app.core import database as db_mod

    importlib.reload(db_mod)
    db_mod.init_db()

    from app.services import chat_service as chat_mod

    importlib.reload(chat_mod)
    return chat_mod


class TestEventQueueReuse:
    """验证 start_chat 复用同一个队列对象，不会替换失效 SSE 端引用."""

    def test_start_chat_reuses_same_queue_object(self):
        """start_chat 不应创建新队列替换旧队列，SSE 端持有旧引用会收不到事件."""
        with tempfile.TemporaryDirectory() as tmpdir:
            chat_mod = _reload_for_test(tmpdir)
            session_id = "test-session-1"

            # 模拟 SSE 先连接：获取队列引用
            q_before = chat_mod._get_event_queue(session_id)

            async def _run():
                # 调用 start_chat
                await chat_mod.start_chat(session_id, "hello")
                # start_chat 后再取一次
                q_after = chat_mod._get_event_queue(session_id)
                # 必须是同一个队列对象
                assert q_before is q_after, (
                    "start_chat 替换了队列对象！"
                    "SSE 端持有的旧引用会收不到后续事件，导致前端无内容返回。"
                )

            asyncio.run(_run())

    def test_start_chat_clears_existing_events(self):
        """start_chat 应该清空队列中遗留的旧事件，但不替换队列对象."""
        with tempfile.TemporaryDirectory() as tmpdir:
            chat_mod = _reload_for_test(tmpdir)
            session_id = "test-session-2"

            # 先放一些旧事件（模拟上一轮遗留）
            q = chat_mod._get_event_queue(session_id)
            q.put_nowait(("old_event", {"foo": "bar"}))
            q.put_nowait(("another_old", {}))
            assert q.qsize() == 2

            async def _run():
                await chat_mod.start_chat(session_id, "new query")
                # 队列应该被清空
                assert q.qsize() == 0, "start_chat 应该清空旧事件"

            asyncio.run(_run())

    def test_event_stream_uses_same_queue_as_start_chat(self):
        """event_stream 获取的队列和 start_chat 操作的队列必须是同一个."""
        with tempfile.TemporaryDirectory() as tmpdir:
            chat_mod = _reload_for_test(tmpdir)
            session_id = "test-session-3"

            # event_stream 里调 _get_event_queue 拿到的队列
            q_stream = chat_mod._get_event_queue(session_id)

            async def _run():
                await chat_mod.start_chat(session_id, "test")
                # start_chat 通过 _get_event_queue / _send_event_sync 操作的也是同一个
                q_send = chat_mod._get_event_queue(session_id)
                assert q_stream is q_send

            asyncio.run(_run())
