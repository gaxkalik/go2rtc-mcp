"""Environment configuration loader for go2rtc-mcp."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


def _parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Go2RtcSettings(BaseModel):
    """Runtime settings for connecting to a go2rtc instance."""

    url: str = Field(default="http://localhost:1984", description="Base URL of the go2rtc server")
    username: str | None = Field(default=None, description="Optional HTTP Basic Auth username")
    password: str | None = Field(default=None, description="Optional HTTP Basic Auth password")
    timeout: float = Field(default=15.0, gt=0.0, description="HTTP request timeout in seconds")
    allow_exec_streams: bool = Field(
        default=False,
        description="Whether to allow adding/updating exec:, echo:, or expr: streams",
    )

    @field_validator("url")
    @classmethod
    def _normalize_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("GO2RTC_URL must start with http:// or https://")
        return cleaned

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> Go2RtcSettings:
        """Load settings from environment variables (and `.env` if present)."""
        if env_file is not None:
            load_dotenv(dotenv_path=env_file, override=False)
        else:
            load_dotenv(override=False)

        raw_url = os.getenv("GO2RTC_URL", "http://localhost:1984").strip() or "http://localhost:1984"
        raw_user = os.getenv("GO2RTC_USERNAME", "").strip() or None
        raw_pass = os.getenv("GO2RTC_PASSWORD", "").strip() or None
        raw_timeout = os.getenv("GO2RTC_TIMEOUT", "15.0").strip() or "15.0"
        raw_allow_exec = os.getenv("GO2RTC_ALLOW_EXEC_STREAMS", "false")

        return cls(
            url=raw_url,
            username=raw_user,
            password=raw_pass,
            timeout=float(raw_timeout),
            allow_exec_streams=_parse_bool(raw_allow_exec, default=False),
        )
