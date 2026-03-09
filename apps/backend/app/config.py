from pydantic import BaseModel
import os


class Settings(BaseModel):
    port: int = int(os.getenv("PORT", "3003"))
    postgres_dsn: str = os.getenv(
        "POSTGRES_DSN",
        "postgresql://avaclaw_user:avaclaw_pw@localhost:5432/avaclaw_db"
    )
    redis_url: str = os.getenv(
        "REDIS_URL",
        "redis://:avaclaw_redis_pw@localhost:56379/0"
    )
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3-coder")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))
    openalex_base: str = "https://api.openalex.org"


settings = Settings()
