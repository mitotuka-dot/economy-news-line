from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    x_bearer_token: str
    x_user_id: str
    openai_api_key: str
    line_channel_access_token: str
    line_user_id: str
    dry_run: bool = True
    use_openai: bool = False
    db_path: str = "data/x_reply_radar.db"
    openai_model: str = "gpt-4.1-mini"
    watchlist_path: str = "watchlist.txt"
    request_timeout: int = 20
    max_notifications: int = 5


def load_settings(validate: bool = True) -> Settings:
    load_dotenv()
    settings = Settings(
        x_bearer_token=os.getenv("X_BEARER_TOKEN", "").strip(),
        x_user_id=os.getenv("X_USER_ID", "").strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        line_channel_access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip(),
        line_user_id=os.getenv("LINE_USER_ID", "").strip(),
        dry_run=_as_bool(os.getenv("DRY_RUN"), default=True),
        use_openai=_as_bool(os.getenv("USE_OPENAI"), default=False),
        db_path=os.getenv("DB_PATH", "data/x_reply_radar.db").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
        watchlist_path=os.getenv("WATCHLIST_PATH", "watchlist.txt").strip(),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "20")),
        max_notifications=int(os.getenv("MAX_NOTIFICATIONS", "5")),
    )
    if validate:
        missing = []
        required = {"X_BEARER_TOKEN": settings.x_bearer_token}
        if settings.use_openai:
            required["OPENAI_API_KEY"] = settings.openai_api_key
        for key, value in required.items():
            if not value:
                missing.append(key)
        if not settings.dry_run:
            for key, value in {
                "LINE_CHANNEL_ACCESS_TOKEN": settings.line_channel_access_token,
                "LINE_USER_ID": settings.line_user_id,
            }.items():
                if not value:
                    missing.append(key)
        if missing:
            raise RuntimeError(
                "Missing required environment variables: "
                + ", ".join(missing)
                + ". Set them in .env or GitHub Secrets."
            )
    return settings
