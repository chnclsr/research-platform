from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str = "sqlite+aiosqlite:///./data/research.db"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "research"
    minio_secret_key: str = "change-me-now"
    minio_secure: bool = False
    minio_bucket: str = "research-artifacts"

    agentsearch_url: str = "http://localhost:3939"
    crawl4ai_url: str = "http://localhost:11235"
    crawl4ai_api_token: str | None = "local-crawl-token"
    ollama_url: str = "http://localhost:11434"
    llm_provider: str = "ollama"
    llm_model: str = "qwen3:4b-instruct-2507-q4_K_M"
    llm_think: bool = False
    llm_context_tokens: int = Field(8192, ge=2048, le=262144)
    llm_max_output_tokens: int = Field(2048, ge=128, le=32768)
    llm_temperature: float = Field(0.0, ge=0.0, le=2.0)
    llm_top_p: float | None = Field(None, gt=0.0, le=1.0)
    llm_top_k: int | None = Field(None, ge=1, le=1000)
    llm_presence_penalty: float | None = Field(None, ge=-2.0, le=2.0)
    embedding_model: str = "embeddinggemma:300m-qat-q4_0"
    passage_target_tokens: int = Field(700, ge=200, le=1800)
    passage_overlap_tokens: int = Field(100, ge=0, le=400)
    passages_per_question: int = Field(8, ge=1, le=30)
    frontier_max_links_per_document: int = Field(50, ge=0, le=500)
    frontier_max_depth: int = Field(2, ge=0, le=5)
    local_corpus_results: int = Field(8, ge=0, le=50)
    enable_scrapling_fallback: bool = True
    openai_compatible_url: str | None = None
    openai_compatible_api_key: str | None = None

    github_token: str | None = None
    epo_ops_key: str | None = None
    epo_ops_secret: str | None = None
    api_token: str = "change-me-local-token"
    user_agent: str = "ResearchPlatform/0.1 (local research; contact=local)"

    max_download_bytes: int = 25 * 1024 * 1024
    request_timeout_s: float = 25.0
    acquisition_concurrency: int = Field(4, ge=1, le=16)
    domain_delay_s: float = Field(0.5, ge=0)
    allow_private_networks: bool = False
    testing: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
