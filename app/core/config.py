from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Support Workflow Platform"
    app_env: str = "dev"
    database_url: str = "sqlite:///./support_workflow.db"
    max_review_iterations: int = 2
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8501
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.3
    chroma_persist_dir: str = "./chroma_data"
    embedding_model: str = "all-MiniLM-L6-v2"
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    rag_top_k: int = 5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
