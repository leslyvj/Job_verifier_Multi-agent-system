"""Application configuration management."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    mistral_api_key: str | None = os.getenv("MISTRAL_API_KEY")
    llm_provider: str = os.getenv("LLM_PROVIDER", "mistral")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "mistral")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    tavily_api_key: str | None = os.getenv("TAVILY_API_KEY")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
