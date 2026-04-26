"""Application configuration sourced from environment variables."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default=Path("/app/data"), validation_alias="AUDIO_MCP_DATA_DIR")
    upload_max_bytes: int = Field(default=500 * 1024 * 1024, validation_alias="AUDIO_MCP_UPLOAD_MAX_BYTES")
    inline_base64_max_bytes: int = Field(default=10 * 1024 * 1024, validation_alias="AUDIO_MCP_INLINE_B64_MAX_BYTES")
    upload_ttl_seconds: int = Field(default=86_400, validation_alias="AUDIO_MCP_UPLOAD_TTL_SECONDS")
    global_concurrency: int = Field(default=5, validation_alias="AUDIO_MCP_GLOBAL_CONCURRENCY")
    cpu_backend_concurrency: int = Field(default=1, validation_alias="AUDIO_MCP_CPU_CONCURRENCY")
    host: str = Field(default="0.0.0.0", validation_alias="AUDIO_MCP_HOST")
    port: int = Field(default=8000, validation_alias="AUDIO_MCP_PORT")
    public_base_url: str = Field(default="", validation_alias="AUDIO_MCP_PUBLIC_BASE_URL")

    groq_api_key: str = Field(default="", validation_alias="GROQ_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    google_application_credentials: str = Field(default="", validation_alias="GOOGLE_APPLICATION_CREDENTIALS")

    piper_voice_dir: Path = Field(default=Path("/app/models/piper"), validation_alias="AUDIO_MCP_PIPER_VOICE_DIR")
    piper_binary: str = Field(default="piper", validation_alias="AUDIO_MCP_PIPER_BINARY")

    enable_metrics: bool = Field(default=False, validation_alias="AUDIO_MCP_ENABLE_METRICS")

    default_wait_max_sec: int = Field(default=50, validation_alias="AUDIO_MCP_DEFAULT_WAIT_MAX_SEC")
    stats_window: int = Field(default=20, validation_alias="AUDIO_MCP_STATS_WINDOW")

    def ensure_dirs(self) -> None:
        (self.data_dir / "uploads").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "outputs").mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    return Settings()
