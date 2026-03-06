from pydantic import BaseModel
import os


class Settings(BaseModel):
    port: int = int(os.getenv("PORT", "3003"))
    sqlite_path: str = os.getenv("SQLITE_PATH", "./data/avaclaw.db")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3-coder")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))
    semantic_scholar_base: str = "https://api.semanticscholar.org"


settings = Settings()
