from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str = "dev-secret-change-me"
    DATABASE_URL: str = "sqlite:///./competition.db"
    DB_PATH: str = "./competition.db"
    AUTH_COOKIE_SECURE: bool = False
    # 机器人令牌：插件 .ts start 开局前自动随机选边时使用（请求头 X-Bot-Token）。
    # 留空则机器人随机选边接口返回 503（人工裁判选边不受影响）。
    BOT_API_TOKEN: str = ""

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
