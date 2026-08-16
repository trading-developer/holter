from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    db_url: str = "sqlite+aiosqlite:///bp_diary.db"
    timezone: str = "Europe/Moscow"

    max_per_day: int = 10
    min_interval_seconds: int = 60

    sys_min: int = 50
    sys_max: int = 300
    dia_min: int = 30
    dia_max: int = 250
    pulse_min: int = 20
    pulse_max: int = 300
    require_sys_gt_dia: bool = True

    stats_days: int = 7
    history_limit: int = 15
    graph_days: int = 14
    max_reminders_per_user: int = 5


settings = Settings()
