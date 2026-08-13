from __future__ import annotations

from functools import lru_cache
from typing import Literal

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
    llm_reason_then_format: bool = False
    llm_context_tokens: int = Field(8192, ge=2048, le=262144)
    llm_max_output_tokens: int = Field(2048, ge=128, le=32768)
    llm_reasoning_output_tokens: int = Field(20480, ge=512, le=131072)
    llm_timeout_s: float = Field(180.0, ge=10.0, le=3600.0)
    llm_temperature: float = Field(0.0, ge=0.0, le=2.0)
    llm_top_p: float | None = Field(None, gt=0.0, le=1.0)
    llm_top_k: int | None = Field(None, ge=0, le=1000)
    llm_min_p: float | None = Field(None, ge=0.0, le=1.0)
    llm_repeat_penalty: float | None = Field(None, ge=0.0, le=2.0)
    llm_presence_penalty: float | None = Field(None, ge=-2.0, le=2.0)
    embedding_model: str = "embeddinggemma:300m-qat-q4_0"
    figure_analysis_enabled: bool = True
    vision_model: str = "qwen3.5:4b"
    figure_max_candidates: int = Field(8, ge=0, le=40)
    figure_max_pages_per_source: int = Field(3, ge=1, le=12)
    figure_min_relevance: float = Field(0.55, ge=0.0, le=1.0)
    figure_analysis_timeout_s: float = Field(180.0, ge=10.0, le=900.0)
    figure_source_embedding_enabled: bool = True
    figure_source_max_exports: int = Field(5, ge=0, le=12)
    figure_source_min_confidence: float = Field(0.70, ge=0.0, le=1.0)
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
    openalex_api_key: str | None = None
    openalex_mailto: str | None = None
    crossref_mailto: str | None = None
    crossref_rps: float = Field(1.0, gt=0, le=50)
    semantic_scholar_api_key: str | None = None
    semantic_scholar_rps: float = Field(1.0, gt=0, le=100)
    semantic_scholar_citation_limit: int = Field(20, ge=0, le=500)
    zotero_local_url: str = "http://localhost:23119/api"
    zotero_local_enabled: bool = True
    zotero_api_key: str | None = None
    zotero_user_id: str | None = None
    zotero_group_id: str | None = None
    zotero_include_notes: bool = True
    zotero_include_attachments: bool = True
    paperqa2_enabled: bool = False
    paperqa2_shadow_mode: bool = True
    paperqa2_max_documents: int = Field(20, ge=1, le=100)
    api_token: str = "change-me-local-token"
    api_host: str = "127.0.0.1"
    api_port: int = Field(8000, ge=1, le=65535)
    control_panel_host: str = "127.0.0.1"
    control_panel_port: int = Field(8020, ge=1, le=65535)
    control_panel_allowed_networks: list[str] = Field(default_factory=list)
    # Whether the panel supervises native processes started by the office scripts or
    # the compose project. Left at "native" so existing office servers keep working.
    control_panel_deployment: Literal["native", "docker"] = "native"
    research_api_url: str = "http://localhost:8000"
    gateway_download_dir: str = "./data/deliveries"
    mcp_transport: str = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = Field(8010, ge=1, le=65535)
    mcp_bearer_token: str | None = None
    mcp_allowed_origins: list[str] = Field(default_factory=list)
    mcp_allowed_networks: list[str] = Field(default_factory=list)
    telegram_bot_token: str | None = None
    telegram_api_url: str = "https://api.telegram.org"
    telegram_allowed_user_ids: list[int] = Field(default_factory=list)
    telegram_allowed_chat_ids: list[int] = Field(default_factory=list)
    telegram_allow_group_chats: bool = False
    telegram_allow_all_users: bool = False
    telegram_default_max_wall_minutes: int = Field(20, ge=1, le=180)
    telegram_max_wall_minutes: int = Field(180, ge=1, le=1440)
    telegram_default_max_sources: int | None = Field(None, ge=1)
    telegram_default_max_rounds: int = Field(3, ge=1, le=12)
    user_agent: str = "ResearchPlatform/0.1 (local research; contact=local)"

    max_download_bytes: int = 25 * 1024 * 1024
    request_timeout_s: float = 25.0
    pipeline_control_poll_s: float = Field(1.0, ge=0.1, le=10.0)
    search_stage_timeout_s: float = Field(600.0, ge=10.0, le=3600.0)
    acquisition_stage_timeout_s: float = Field(900.0, ge=10.0, le=3600.0)
    acquisition_concurrency: int = Field(4, ge=1, le=16)
    domain_delay_s: float = Field(0.5, ge=0)
    allow_private_networks: bool = False
    testing: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
