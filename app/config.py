from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Environment variables override the defaults."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    chat_provider: str = "dictionary"
    request_timeout_seconds: float = 60
    app_api_key: str = ""

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"

    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-5"
    claude_max_tokens: int = 1024

    ibm_bob_api_key: str = ""
    bob_api_key: str = ""
    ibm_bob_base_url: str = "https://api.us-east.bob.ibm.com/inference/v1"
    ibm_bob_model: str = "premium"
    ibm_bob_auth_scheme: str = "Apikey"
    ibm_bob_instance_id: str = ""
    ibm_bob_team_id: str = ""

    cursor_api_key: str = ""
    cursor_model: str = "composer-2.5"
    cursor_cwd: str = ""

    @property
    def resolved_bob_api_key(self) -> str:
        return self.ibm_bob_api_key.strip() or self.bob_api_key.strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
