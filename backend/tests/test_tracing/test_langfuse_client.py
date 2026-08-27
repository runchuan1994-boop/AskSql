"""Tests for Langfuse client singleton management."""
from __future__ import annotations

import pytest


def test_get_client_disabled_by_default():
    """默认配置下 langfuse_enabled=false，get_langfuse() 返回 None。"""
    from nl2sql.tracing.langfuse_client import get_langfuse, reset_client_for_tests
    reset_client_for_tests()
    client = get_langfuse()
    assert client is None


def test_get_client_no_public_key():
    """enabled=true 但没有 key，仍然返回 None（降级）。"""
    from unittest.mock import patch
    from nl2sql.tracing.langfuse_client import get_langfuse, reset_client_for_tests

    mock_settings = type(
        "Settings",
        (),
        {
            "langfuse_enabled": True,
            "langfuse_public_key": "",
            "langfuse_secret_key": "",
            "langfuse_host": "http://localhost:3030",
        },
    )()

    with patch("nl2sql.tracing.langfuse_client.Settings", return_value=mock_settings):
        reset_client_for_tests()
        client = get_langfuse()
        assert client is None
