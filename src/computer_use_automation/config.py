from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: str = Field(default="ollama", alias="CUA_LLM_PROVIDER")
    model: str = Field(default="qwen3:8b", alias="CUA_MODEL")
    ollama_base_url: str = Field(default="http://127.0.0.1:11434/v1", alias="OLLAMA_BASE_URL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    headless: bool = Field(default=False, alias="CUA_HEADLESS")
    allowed_hosts_csv: str = Field(default="127.0.0.1,localhost", alias="CUA_ALLOWED_HOSTS")
    artifacts_dir: Path = Path("artifacts")
    evidence_dir: Path = Path("evidence")
    max_steps: int = 20
    action_timeout_ms: int = 5_000
    transient_retries: int = 2

    @property
    def allowed_hosts(self) -> set[str]:
        return {item.strip() for item in self.allowed_hosts_csv.split(",") if item.strip()}


settings = Settings()
