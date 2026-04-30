from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    bot_token: str

    # PostgreSQL
    postgres_user: str = "study_bot"
    postgres_password: str = "changeme"
    postgres_db: str = "study_tools"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # App
    debug: bool = False
    log_level: str = "INFO"

    # Admin
    admin_username: str = "admin"
    admin_password: str = "change_me"
    admin_secret_key: str = "change_me_too"
    admin_host: str = "0.0.0.0"
    admin_port: int = 8080

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
