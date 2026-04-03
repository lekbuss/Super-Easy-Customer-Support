from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Support Workflow Platform"
    app_env: str = "dev"
    database_url: str = "sqlite:///./support_workflow.db"
    max_review_iterations: int = 2

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
