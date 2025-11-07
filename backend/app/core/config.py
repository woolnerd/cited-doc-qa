"""Application configuration using Pydantic settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "RAG Chatbot API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # CORS
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    # File Upload
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_FILE_TYPES: list[str] = ["pdf", "docx", "txt"]

    # Rate Limiting
    UPLOAD_RATE_LIMIT: str = "10/hour"
    QUERY_RATE_LIMIT: str = "30/hour"

    # Database (Supabase - legacy)
    SUPABASE_URL: str = "https://test.supabase.co"
    SUPABASE_KEY: str = "test-key"

    # Database (PostgreSQL - preferred)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "rag_db"
    POSTGRES_USER: str = "rag_user"
    POSTGRES_PASSWORD: str = "changeme123"

    # Database connection URL (constructed from above)
    @property
    def DATABASE_URL(self) -> str:
        """PostgreSQL connection URL for asyncpg."""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # AI Services
    GOOGLE_API_KEY: str = "test-google-key"  # Gemini embeddings
    COHERE_API_KEY: str = "test-cohere-key"  # Reranking
    OPENROUTER_API_KEY: str = "test-openrouter-key"  # Claude LLM via Openrouter

    # Embedding Configuration
    EMBEDDING_MODEL: str = "models/text-embedding-004"
    EMBEDDING_DIMENSIONS: int = 768

    # Chunking Configuration
    CHUNK_SIZE_MIN: int = 400
    CHUNK_SIZE_MAX: int = 600
    CHUNK_SIZE_TARGET: int = 500

    # Search Configuration
    SEARCH_TOP_K: int = 10  # Number of top results to return
    SEARCH_SIMILARITY_THRESHOLD: float = (
        0.5  # Minimum similarity score (0-1) - Lowered for better semantic recall
    )
    VECTOR_SEARCH_LIMIT: int = 30
    FULL_TEXT_SEARCH_LIMIT: int = 30
    RERANK_TOP_K: int = 5
    RRF_K: int = 60

    # Reranking Configuration
    RERANK_MODEL: str = "rerank-english-v3.0"
    RERANK_MAX_RETRIES: int = 3
    RERANK_RETRY_DELAY: float = 1.0  # seconds

    # LLM Configuration (via Openrouter)
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_MODEL: str = "anthropic/claude-3.5-sonnet"  # Openrouter format
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 2048

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Global settings instance
settings = Settings()
