from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "dev-secret-change-me"
    DATABASE_URL: str = "sqlite:///./competition.db"
    DB_PATH: str = "./competition.db"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
