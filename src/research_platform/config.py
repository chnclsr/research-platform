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
    # Which PDF page goes to the heavy engine. The file is the unit of change: its
    # contents are hashed into `esik_version` and written to provenance, so a
    # threshold cannot move without the version moving with it. Read once at import
    # by parsers/smart_router/ayarlar.py, which falls back to embedded defaults on a
    # missing or malformed file rather than failing the pipeline -- a typo in a
    # config file must not take PDF parsing down. Empty means the repository
    # default, config/smart_router.yaml.
    smart_router_config_path: str = ""
    # Where the docling service lives, e.g. http://docling:3941. Empty means the heavy
    # path falls back to a local interpreter (SMART_ROUTER_DOCLING_PYTHON) or, if that
    # is unset too, to no heavy engine at all -- pages keep their fast-path text and the
    # document is marked degraded rather than failing. Mirrored from the environment
    # variable of the same name by parsers/smart_router/engines.py, so a `.env` entry
    # works as well as a container environment.
    smart_router_docling_url: str = ""
    passage_target_tokens: int = Field(700, ge=200, le=1800)
    passage_overlap_tokens: int = Field(100, ge=0, le=400)
    passages_per_question: int = Field(8, ge=1, le=30)
    frontier_max_links_per_document: int = Field(50, ge=0, le=500)
    frontier_max_depth: int = Field(2, ge=0, le=5)
    local_corpus_results: int = Field(8, ge=0, le=50)
    enable_github_repository_handler: bool = True
    github_clone_timeout_s: float = Field(90.0, ge=10.0, le=300.0)
    github_repository_max_bytes: int = Field(100 * 1024 * 1024, ge=1024 * 1024)
    github_repository_max_files: int = Field(200, ge=1, le=2000)
    github_repository_max_file_bytes: int = Field(512 * 1024, ge=4096)
    github_repository_max_chars: int = Field(2_000_000, ge=10_000, le=10_000_000)
    enable_jina_reader_fallback: bool = True
    jina_reader_url: str = "https://r.jina.ai"
    jina_reader_timeout_s: float = Field(90.0, ge=10.0, le=180.0)
    enable_scrapling_fallback: bool = True
    openai_compatible_url: str | None = None
    openai_compatible_api_key: str | None = None
    telegram_preparation_llm_enabled: bool = False
    gemini_api_key: str | None = None
    gemini_api_url: str = "https://generativelanguage.googleapis.com"
    gemini_preparation_model: str = "gemini-3.6-flash"
    gemini_preparation_timeout_s: float = Field(60.0, ge=10.0, le=300.0)
    gemini_preparation_max_retries: int = Field(2, ge=0, le=5)

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
    # Signs panel session cookies. Left unset it is generated per process, which logs
    # everyone out on restart -- fine for a single workstation, wrong for a shared
    # deployment, so a real value belongs in the environment file there.
    session_secret: str | None = None
    session_max_age_seconds: int = Field(12 * 3600, ge=300)
    login_max_attempts: int = Field(8, ge=1, le=100)
    login_lockout_seconds: int = Field(300, ge=1, le=86400)
    # Presented by trusted intermediaries (the panel, the Telegram bot) that
    # authenticate their own users and then declare who they act for via X-Actor-User.
    service_token: str | None = None
    # Passages from finished runs feed later ones. "owner" keeps that pool inside a
    # single user's own history; "global" restores the previous cross-user behaviour
    # as a deliberate, documented choice.
    corpus_scope: Literal["owner", "global"] = "owner"
    control_panel_host: str = "127.0.0.1"
    control_panel_port: int = Field(8020, ge=1, le=65535)
    control_panel_allowed_networks: list[str] = Field(default_factory=list)
    # Extra names accepted in the Host header -- a reverse-proxy hostname, say. The
    # machine's own addresses are added automatically when the panel is not on loopback.
    control_panel_allowed_hosts: list[str] = Field(default_factory=list)
    # Whether the panel supervises native processes started by the office scripts or
    # the compose project. Left at "native" so existing office servers keep working.
    control_panel_deployment: Literal["native", "docker"] = "native"
    # Set when the panel is served over TLS, so the session cookie can carry Secure.
    # Left false on a plain-HTTP workstation, where Secure would make it unusable.
    control_panel_https: bool = False
    research_api_url: str = "http://localhost:8000"
    gateway_download_dir: str = "./data/deliveries"
    gateway_client_timeout_s: float = Field(60.0, gt=0, le=3600.0)
    gateway_artifact_max_chars: int = Field(100_000, ge=1, le=10_000_000)
    mcp_transport: str = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = Field(8010, ge=1, le=65535)
    # MCP_BEARER_TOKEN was removed in v0.10.1. The gateway authenticates callers with their
    # own API key, so a shared token no longer exists; a leftover line in .env is ignored.
    mcp_allowed_origins: list[str] = Field(default_factory=list)
    mcp_allowed_networks: list[str] = Field(default_factory=list)
    telegram_bot_token: str | None = None
    telegram_api_url: str = "https://api.telegram.org"
    # Used to build the t.me deep link the panel shows, without the leading @. Left unset
    # the panel falls back to showing the code for the user to type.
    telegram_bot_username: str | None = None
    telegram_link_code_ttl_seconds: int = Field(300, ge=60, le=3600)
    # Kept for group chats and as an optional extra restriction. It no longer decides who
    # may use the bot in a direct chat -- being linked to an account does.
    telegram_allowed_user_ids: list[int] = Field(default_factory=list)
    telegram_allowed_chat_ids: list[int] = Field(default_factory=list)
    telegram_allow_group_chats: bool = False
    telegram_allow_all_users: bool = False
    telegram_default_max_wall_minutes: int = Field(20, ge=1, le=180)
    telegram_max_wall_minutes: int = Field(180, ge=1, le=1440)
    telegram_default_max_sources: int | None = Field(None, ge=1)
    telegram_default_max_rounds: int = Field(3, ge=1, le=12)
    # How far back the failure notice looks. It also decides what "already known" means:
    # a run that failed before this window is never announced, so switching the feature on
    # does not replay old failures, while a bot that was down for a while still catches the
    # ones it missed.
    telegram_failure_notice_window_h: float = Field(24.0, ge=0.5, le=168.0)
    user_agent: str = "ResearchPlatform/0.1 (local research; contact=local)"

    # The plan gate waits on a person, not on a service: five minutes -- the window the
    # other checkpoints use -- would park most runs before anyone opened the panel.
    hitl_plan_timeout_minutes: int = Field(1440, ge=5, le=20160)
    # How many times a rejected plan may be rebuilt before the run is given up on.
    plan_max_revisions: int = Field(3, ge=1, le=10)

    max_download_bytes: int = 25 * 1024 * 1024
    request_timeout_s: float = 25.0
    http_transport_retries: int = Field(3, ge=0, le=20)
    service_health_timeout_s: float = Field(3.0, gt=0, le=120.0)
    redis_startup_connect_attempts: int = Field(30, ge=1, le=300)
    redis_operation_connect_attempts: int = Field(3, ge=1, le=100)
    redis_probe_connect_attempts: int = Field(1, ge=1, le=20)
    redis_connect_delay_s: float = Field(1.0, ge=0, le=60.0)
    pipeline_control_poll_s: float = Field(1.0, ge=0.1, le=10.0)
    search_stage_timeout_s: float = Field(600.0, ge=10.0, le=3600.0)
    acquisition_stage_timeout_s: float = Field(900.0, ge=10.0, le=3600.0)
    acquisition_concurrency: int = Field(4, ge=1, le=16)
    acquisition_max_redirects: int = Field(5, ge=0, le=50)
    agentsearch_read_max_chars: int = Field(100_000, ge=1, le=10_000_000)
    crawl4ai_timeout_s: float = Field(90.0, gt=0, le=3600.0)
    domain_delay_s: float = Field(0.5, ge=0)
    allow_private_networks: bool = False

    embedding_batch_size: int = Field(32, ge=1, le=1024)
    embedding_timeout_s: float = Field(180.0, gt=0, le=3600.0)

    search_concurrency: int = Field(8, ge=1, le=128)
    citation_seed_min: int = Field(4, ge=0, le=1000)
    citation_seed_max: int = Field(12, ge=0, le=1000)
    evidence_extraction_concurrency: int = Field(2, ge=1, le=128)
    relevance_retry_attempts: int = Field(2, ge=1, le=20)
    graph_recursion_min: int = Field(80, ge=1, le=100_000)
    graph_recursion_max: int = Field(5000, ge=1, le=100_000)
    graph_recursion_per_wall_minute: int = Field(20, ge=0, le=1000)
    first_round_source_fraction: float = Field(0.40, gt=0, le=1)
    later_round_source_fraction: float = Field(0.30, gt=0, le=1)

    checkpoint_max_bytes: int = Field(200 * 1024 * 1024, ge=1024 * 1024)
    db_pool_min_size: int = Field(10, ge=1, le=1000)
    db_pool_per_run: int = Field(5, ge=1, le=100)
    db_overflow_min_size: int = Field(10, ge=0, le=1000)
    db_overflow_per_run: int = Field(3, ge=0, le=100)
    queue_priority_shift_days: int = Field(3650, ge=1, le=36500)
    queue_job_expiry_s: int = Field(86400, ge=1, le=2_592_000)
    worker_job_timeout_s: int = Field(86400, ge=1, le=2_592_000)
    worker_keep_result_s: int = Field(60, ge=0, le=86400)
    worker_health_check_interval_s: int = Field(30, ge=1, le=3600)

    # How many runs may execute at once is measured, not configured -- see capacity.py.
    # What is configured here is the *budget* each run is assumed to need and the headroom
    # the machine keeps for itself. These are safety parameters: raising them lowers
    # concurrency, and none of them is a policy cap on how many runs may start.
    run_memory_budget_gb: float = Field(2.5, gt=0, le=64)
    run_cpu_budget: float = Field(3.0, gt=0, le=32)
    # Never spend the last of the machine: what stays free for the OS, Docker itself and
    # everything that is not this platform.
    ram_reserve_gb: float = Field(4.0, ge=0, le=64)
    cpu_headroom: float = Field(0.2, ge=0.0, le=0.9)
    # The worker container has no nvidia-smi, so the card's size is stated once; what the
    # models actually occupy is read live from Ollama.
    gpu_vram_total_gb: float = Field(8.0, gt=0, le=256)
    gpu_vram_margin_gb: float = Field(0.7, ge=0, le=16)
    # VRAM the docling service holds while it is resident. Subtracted from the headroom
    # the run planner works with, because docling is a GPU consumer the planner cannot
    # see: capacity measures Ollama's resident VRAM, and model_lease() serialises Ollama
    # calls -- neither knows about a second process on the same card. Left at 0.0 until
    # measured on the deployment (nvidia-smi during a conversion); a guessed reservation
    # would either waste the card or fail to protect it.
    docling_vram_reserve_gb: float = Field(0.0, ge=0, le=64)
    capacity_poll_s: float = Field(15.0, ge=1.0, le=300.0)
    capacity_absolute_guard: int = Field(8, ge=1, le=128)
    capacity_probe_timeout_s: float = Field(5.0, gt=0, le=120.0)
    model_max_concurrent_calls: int = Field(1, ge=1, le=32)
    # Shared run-window telemetry. It describes the Docker/WSL environment and total
    # visible GPU load, not one coroutine's share of those resources.
    hardware_telemetry_enabled: bool = True
    hardware_telemetry_interval_s: float = Field(5.0, ge=1.0, le=60.0)
    hardware_telemetry_flush_s: float = Field(60.0, ge=1.0, le=3600.0)
    hardware_telemetry_max_buffered_samples: int = Field(720, ge=1, le=100_000)
    # "csv" keeps the data artifacts and skips the rendered chart; "all" adds the SVG.
    hardware_telemetry_output_type: Literal["csv", "all"] = "all"
    testing: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
