from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://judge:judgepass@postgres:5432/judgedb"

    # ── Celery / Redis ────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"

    # ── Docker — points to the socket-proxy, NOT the raw daemon socket ────────
    DOCKER_HOST: str = "tcp://docker-socket-proxy:2375"

    # ── Ollama ────────────────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder"

    # ── Sandbox constraints ───────────────────────────────────────────────────
    # 5 s to accommodate C++ compile + execute phases separately
    SANDBOX_TIMEOUT: int = 5
    # Must match the bind-mount path declared in docker-compose.yml for the worker
    SANDBOX_BASE_DIR: str = "/tmp/judge_sandboxes"


settings = Settings()
