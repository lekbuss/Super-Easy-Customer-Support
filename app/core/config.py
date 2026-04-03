import os

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        app_name: str = "Support Workflow Platform"
        app_env: str = "dev"
        database_url: str = "sqlite:///./support_workflow.db"
        max_review_iterations: int = 2

        model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

except Exception:

    class Settings:
        def __init__(self):
            self.app_name = os.getenv("APP_NAME", "Support Workflow Platform")
            self.app_env = os.getenv("APP_ENV", "dev")
            self.database_url = os.getenv("DATABASE_URL", "sqlite:///./support_workflow.db")
            self.max_review_iterations = int(os.getenv("MAX_REVIEW_ITERATIONS", "2"))


settings = Settings()
