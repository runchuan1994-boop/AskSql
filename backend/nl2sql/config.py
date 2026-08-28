"""全局配置，从环境变量读取。"""
from __future__ import annotations

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    """全局配置，从环境变量读取。"""

    model_config = SettingsConfigDict(env_file=".env")

    # LLM
    llm_provider: str = "claude"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"

    # Agent
    max_iterations: int = 5
    max_probe_iterations: int = 3
    sql_timeout_seconds: int = 30
    sql_max_rows: int = 1000
    agent_timeout_seconds: int = 300

    # Langfuse 可观测性（默认开启，缺 key 时静默降级为 no-op）
    langfuse_enabled: bool = True
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3030"


settings = Settings()
