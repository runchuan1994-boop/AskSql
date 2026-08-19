"""测试配置模块。"""
import pytest


def test_settings_import():
    """测试可以从 nl2sql 导入 settings。"""
    from nl2sql import settings
    assert settings is not None


def test_settings_default_llm_provider():
    """测试默认 LLM provider 为 claude。"""
    from nl2sql import settings
    assert settings.llm_provider == "claude"


def test_settings_default_anthropic_model():
    """测试默认 anthropic 模型。"""
    from nl2sql import settings
    assert settings.anthropic_model == "claude-sonnet-4-20250514"


def test_settings_agent_defaults():
    """测试 Agent 相关默认配置。"""
    from nl2sql import settings
    assert settings.max_iterations == 5
    assert settings.max_probe_iterations == 3
    assert settings.sql_timeout_seconds == 30
    assert settings.sql_max_rows == 1000
    assert settings.agent_timeout_seconds == 300


def test_version():
    """测试 __version__ 存在。"""
    import nl2sql
    assert nl2sql.__version__ == "0.1.0"
