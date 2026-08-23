"""测试沙盒配置."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


class TestSandboxConfig:
    def test_default_values(self):
        from sandbox.config import SandboxConfig

        config = SandboxConfig()
        assert config.enabled is False
        assert config.runtime == "runc"
        assert config.image == "nl2sql-sandbox:latest"
        assert config.memory_limit == "256m"
        assert config.cpu_limit == 0.5
        assert config.pids_limit == 64
        assert config.execution_timeout_seconds == 30
        assert config.pool_min_size == 0
        assert config.pool_max_size == 4
        assert config.network_enabled is False

    def test_from_env_with_overrides(self):
        from sandbox.config import SandboxConfig

        env_vars = {
            "SANDBOX_ENABLED": "true",
            "SANDBOX_RUNTIME": "runsc",
            "SANDBOX_IMAGE": "my-sandbox:v1",
            "SANDBOX_MEMORY": "512m",
            "SANDBOX_CPU": "1.0",
            "SANDBOX_TIMEOUT": "60",
            "SANDBOX_POOL_MAX": "8",
            "SANDBOX_NETWORK": "true",
        }

        with patch.dict(os.environ, env_vars):
            config = SandboxConfig.from_env()

        assert config.enabled is True
        assert config.runtime == "runsc"
        assert config.image == "my-sandbox:v1"
        assert config.memory_limit == "512m"
        assert config.cpu_limit == 1.0
        assert config.execution_timeout_seconds == 60
        assert config.pool_max_size == 8
        assert config.network_enabled is True

    def test_from_env_disabled_by_default(self):
        from sandbox.config import SandboxConfig

        with patch.dict(os.environ, {}, clear=True):
            config = SandboxConfig.from_env()
        assert config.enabled is False

    @pytest.mark.parametrize("value,expected", [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("True", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("", False),
    ])
    def test_enabled_env_parsing(self, value, expected):
        from sandbox.config import SandboxConfig

        with patch.dict(os.environ, {"SANDBOX_ENABLED": value}):
            config = SandboxConfig.from_env()
        assert config.enabled is expected
