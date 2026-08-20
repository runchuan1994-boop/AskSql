from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    app_name: str = "NL2SQL Agent"
    debug: bool = False
    data_dir: str = "data"
    projects_dir: str = "config/projects"
    schemas_dir: str = "config/schemas"
    database_url: str = "sqlite:///data/nl2sql.db"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    agent_max_iterations: int = 5
    agent_max_probe_iterations: int = 3
    agent_timeout_seconds: int = 300
    secret_key: str = "nl2sql-default-secret-key-change-me"

    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env")


settings = AppSettings()
