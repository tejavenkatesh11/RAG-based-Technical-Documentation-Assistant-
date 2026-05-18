from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Groq ---
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_model_fast: str = "llama-3.1-8b-instant"

    # --- Postgres: either DATABASE_URL or split parts ---
    database_url: str = ""
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "rag_assistant"

    # --- Vector store ---
    chroma_persist_dir: str = "./data/chroma"
    chroma_collection: str = "tech_docs"

    # --- Embeddings ---
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Retrieval / workflow ---
    top_k: int = 4
    max_retries: int = 2

    # --- Logging ---
    log_level: str = "INFO"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
