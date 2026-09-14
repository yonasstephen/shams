"""Application configuration."""

import os
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode

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
    # Comma-separated in .env, as documented in .env.example. NoDecode is
    # required: without it pydantic-settings JSON-decodes any list-typed field
    # inside the env source itself, which raises on "a@b.com,c@d.com" before any
    # validator can run — and that stops the whole backend from starting.
    allowed_yahoo_emails: Annotated[list[str], NoDecode] = []

    @field_validator("allowed_yahoo_emails", mode="before")
    @classmethod
    def _split_emails(cls, value: object) -> list[str]:
        """Accept either a comma-separated string or an already-parsed list."""
        if value is None:
            return []
        if isinstance(value, str):
            value = value.split(",")
        return [str(email).strip().lower() for email in value if str(email).strip()]
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "False").lower() == "true"

    # Yahoo OAuth
    yahoo_consumer_key: str = os.getenv("YAHOO_CONSUMER_KEY", "")
    yahoo_consumer_secret: str = os.getenv("YAHOO_CONSUMER_SECRET", "")
    yahoo_token_dir: Path = Path(
        os.getenv("SHAMS_YAHOO_TOKEN_DIR", "~/.shams/yahoo")
    ).expanduser()

    # Cache settings
    cache_dir: Path = Path.home() / ".shams"

    # Draft assistant Chrome extension. An unpacked extension's id is assigned by
    # Chrome, so it is configured rather than hardcoded. Set DRAFT_EXTENSION_ID to
    # the id shown on chrome://extensions to allow it as a CORS origin; leaving it
    # unset allows any extension origin in debug mode only.
    draft_extension_id: str = os.getenv("DRAFT_EXTENSION_ID", "")

    # API settings
    waiver_batch_size: int = int(os.getenv("WAIVER_BATCH_SIZE", "25"))  # Yahoo API caps at 25
    nba_api_timeout: int = int(os.getenv("NBA_API_TIMEOUT", "60"))
    nba_api_requests_per_second: float = float(
        os.getenv("NBA_API_REQUESTS_PER_SECOND", "2.0")
    )

    class Config:
        env_file = ".env"
        case_sensitive = False
        # Most settings above are read through os.getenv under a different name
        # than the field (SESSION_SECRET -> secret_key, SHAMS_YAHOO_TOKEN_DIR ->
        # yahoo_token_dir). Without this, pydantic-settings treats those .env
        # keys as unknown fields and refuses to construct Settings at all.
        extra = "ignore"


settings = Settings()
