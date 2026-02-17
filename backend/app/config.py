"""Application configuration."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables
load_dotenv()


class Settings(BaseSettings):
    """Application settings."""

    # App settings
    app_name: str = "Shams Fantasy Basketball API"
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"

    # Server settings
    backend_url: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # Security
    secret_key: str = os.getenv("SESSION_SECRET", "dev-secret-key-change-in-production")
    allowed_yahoo_emails: list[str] = [
        email.strip().lower()
        for email in os.getenv("ALLOWED_YAHOO_EMAILS", "").split(",")
        if email.strip()
    ]
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "False").lower() == "true"

    # Yahoo OAuth
    yahoo_consumer_key: str = os.getenv("YAHOO_CONSUMER_KEY", "")
    yahoo_consumer_secret: str = os.getenv("YAHOO_CONSUMER_SECRET", "")
    yahoo_token_dir: Path = Path(
        os.getenv("SHAMS_YAHOO_TOKEN_DIR", "~/.shams/yahoo")
    ).expanduser()

    # Cache settings
    cache_dir: Path = Path.home() / ".shams"

    # API settings
    waiver_batch_size: int = int(os.getenv("WAIVER_BATCH_SIZE", "25"))  # Yahoo API caps at 25
    nba_api_timeout: int = int(os.getenv("NBA_API_TIMEOUT", "60"))
    nba_api_requests_per_second: float = float(
        os.getenv("NBA_API_REQUESTS_PER_SECOND", "2.0")
    )

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
