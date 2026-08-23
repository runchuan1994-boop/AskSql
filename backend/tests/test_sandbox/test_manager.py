"""测试 SandboxManager（用 mock 容器，不需要真实 Docker）."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sandbox.config import SandboxConfig
from sandbox.manager import SandboxManager


@pytest.fixture
def config():
    return SandboxConfig(
        enabled=True,
        pool_max_size=4,
        sandbox_idle_timeout_seconds=60,
    )


@pytest.fixture
def mock_sandbox():
    sb = MagicMock()
    sb.id = "sb-test"
    sb._last_used_at = 0
    sb.is_alive.return_value = True
    sb.ping.return_value = True
    return sb


class TestSandboxManagerAcquireRelease:
    def test_acquire_creates_new_when_pool_empty(self, config, mock_sandbox):
        """空闲池为空时应该新建沙盒."""
        manager = SandboxManager(config)

        with patch.object(SandboxManager, "docker_client"), \
             patch("sandbox.manager.Sandbox.create", return_value=mock_sandbox):
            sb = manager.acquire()

        assert sb is mock_sandbox
        assert len(manager._active_pool) == 1
        assert len(manager._idle_pool) == 0

    def test_release_returns_to_idle_pool(self, config, mock_sandbox):
        """归还沙盒应该进入空闲池."""
        manager = SandboxManager(config)

        with patch.object(SandboxManager, "docker_client"), \
             patch("sandbox.manager.Sandbox.create", return_value=mock_sandbox):
            sb = manager.acquire()
            manager.release(sb)

        assert len(manager._active_pool) == 0
        assert len(manager._idle_pool) == 1
        assert manager._idle_pool[0] is mock_sandbox

    def test_acquire_reuses_idle_sandbox(self, config, mock_sandbox):
        """有空闲沙盒时应该复用."""
        manager = SandboxManager(config)

        with patch.object(SandboxManager, "docker_client"), \
             patch("sandbox.manager.Sandbox.create") as mock_create:
            # 先放一个到空闲池
            manager._idle_pool.append(mock_sandbox)

            sb = manager.acquire()

            # 应该复用空闲的，而不是新建
            assert sb is mock_sandbox
            mock_create.assert_not_called()
            assert len(manager._idle_pool) == 0
            assert len(manager._active_pool) == 1

    def test_acquire_rejects_unhealthy_idle(self, config, mock_sandbox):
        """不健康的空闲沙盒应该被销毁而不是复用."""
        manager = SandboxManager(config)
        mock_sandbox.ping.return_value = False  # 不健康

        with patch.object(SandboxManager, "docker_client"), \
             patch("sandbox.manager.Sandbox.create") as mock_create:
            mock_create.return_value = MagicMock(is_alive=lambda: True, ping=lambda timeout=2: True)
            manager._idle_pool.append(mock_sandbox)

            sb = manager.acquire()

            # 旧的被销毁了，新建了一个
            mock_sandbox.destroy.assert_called_once()
            mock_create.assert_called_once()
            assert sb is not mock_sandbox

    def test_pool_max_size(self, config):
        """达到最大池大小时应该报错."""
        manager = SandboxManager(config)
        config.pool_max_size = 2

        # 占满池
        for _ in range(2):
            sb = MagicMock()
            sb.id = "sb-x"
            sb._last_used_at = 0
            manager._active_pool.add(sb)

        with patch.object(SandboxManager, "docker_client"):
            with pytest.raises(RuntimeError, match="full"):
                manager.acquire()


class TestSandboxManagerShutdown:
    def test_shutdown_destroys_all(self, config, mock_sandbox):
        """关闭时应该销毁所有沙盒."""
        manager = SandboxManager(config)
        manager._idle_pool.append(mock_sandbox)
        active_sb = MagicMock()
        active_sb._last_used_at = 0
        manager._active_pool.add(active_sb)

        with patch.object(SandboxManager, "docker_client"):
            manager.shutdown()

        mock_sandbox.destroy.assert_called_once()
        active_sb.destroy.assert_called_once()
        assert len(manager._idle_pool) == 0
        assert len(manager._active_pool) == 0
        assert manager._running is False


class TestSandboxManagerStats:
    def test_stats(self, config):
        """统计信息应该正确."""
        manager = SandboxManager(config)
        s1 = MagicMock(); s1._last_used_at = 0
        s2 = MagicMock(); s2._last_used_at = 0
        s3 = MagicMock(); s3._last_used_at = 0

        manager._idle_pool = [s1]
        manager._active_pool = {s2, s3}

        stats = manager.stats
        assert stats["idle"] == 1
        assert stats["active"] == 2
        assert stats["total"] == 3
        assert stats["max_size"] == 4
