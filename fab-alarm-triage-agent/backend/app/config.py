"""Application settings, loaded from environment."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Database
    postgres_user: str = "fab"
    postgres_password: str = "fab"
    postgres_db: str = "fab_mes"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Services
    backend_url: str = "http://localhost:8000"
    mcp_url: str = "http://localhost:9000/mcp"

    # Agent
    max_tool_calls: int = 12
    structured_output_retries: int = 2

    # Where eval reports are written and read. The runner and the metrics endpoint must
    # agree, and the default resolves differently inside the image than in the repo, so
    # deployments set it explicitly.
    eval_reports_dir: str = ""

    # Seeding
    seed_demo: int = 42
    seed_eval: int = 1337

    @property
    def async_dsn(self) -> str:
        """SQLAlchemy async URL (psycopg3 driver)."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_dsn(self) -> str:
        """Plain libpq URL — what LangGraph's Postgres checkpointer expects."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
