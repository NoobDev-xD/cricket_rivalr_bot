from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    bot_token: str
    database_url: str

    bowling_video_file_id: str = ""
    bowling_video_url: str = ""

    four_gif_url: str = ""
    four_mp3_url: str = ""

    six_gif_url: str = ""
    six_mp3_url: str = ""

    fifty_gif_url: str = ""
    fifty_mp3_url: str = ""

    hundred_gif_url: str = ""
    hundred_mp3_url: str = ""

    partnership_fifty_gif_url: str = ""
    partnership_fifty_mp3_url: str = ""

    partnership_hundred_gif_url: str = ""
    partnership_hundred_mp3_url: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = Settings()

# Railway PostgreSQL URL compatibility
if settings.database_url.startswith("postgres://"):
    settings.database_url = settings.database_url.replace(
        "postgres://",
        "postgresql+asyncpg://",
        1
    )

elif settings.database_url.startswith("postgresql://"):
    settings.database_url = settings.database_url.replace(
        "postgresql://",
        "postgresql+asyncpg://",
        1
    )
    
