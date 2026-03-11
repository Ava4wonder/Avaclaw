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
    ollama_code_model: str = os.getenv("OLLAMA_CODE_MODEL", "qwen3-coder")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:30b")
    ollama_embedding_model: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding:8b")
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))
    openalex_base: str = "https://api.openalex.org"


settings = Settings()
