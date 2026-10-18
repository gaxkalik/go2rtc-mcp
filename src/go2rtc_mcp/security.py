"""Centralized security guardrails and recursive credential redaction for go2rtc-mcp."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import unquote

from pydantic import BaseModel

# Matches any URI starting with scheme:// up to whitespace or quote/angle-bracket delimiters.
_URI_PATTERN = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://)([^\s\"'<>`]+)")

# Matches URL-encoded scheme%3A%2F%2Fuser%3Apass%40host in query parameters (e.g., httpx logs)
_ENCODED_URI_CREDENTIALS_PATTERN = re.compile(
    r"(?i)([a-zA-Z][a-zA-Z0-9+.-]*%3A%2F%2F)([^/&?#\s\"'<>]+?)(%40)"
)

# Matches sensitive query parameters in URLs (e.g., ?token=..., &password=..., &auth=...)
_SENSITIVE_QUERY_PARAM_PATTERN = re.compile(
    r"(?i)([?&](?:token|access_token|refresh_token|auth|password|pass|pwd|secret|api_key|apikey|key|jwt)=)([^&#\s\"'<>`]+)"
)

# Matches YAML/INI style sensitive key-value lines (e.g. "  password: mysecretpassword")
_YAML_SENSITIVE_LINE_PATTERN = re.compile(
    r"(?im)^(\s*(?:password|passwd|pass|secret|token|api_key|apikey|access_token|client_secret)\s*:\s*)(?!['\"]?\*\*\*['\"]?\s*$)([^\r\n#]+)"
)

_SENSITIVE_DICT_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pass",
        "pwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "client_secret",
        "authorization",
    }
)

_DANGEROUS_STREAM_PREFIXES = ("exec:", "echo:", "expr:")


class SecurityPolicyError(ValueError):
    """Raised when a stream source or operation violates security policy."""


def _redact_single_uri(match: re.Match[str]) -> str:
    scheme_prefix = match.group(1)
    rest = match.group(2)

    # Split authority from path/query/fragment at the first '/', '?', or '#'
    split_idx = len(rest)
    for sep in ("/", "?", "#"):
        idx = rest.find(sep)
        if idx != -1 and idx < split_idx:
            split_idx = idx

    authority = rest[:split_idx]
    tail = rest[split_idx:]

    # Also check if URL-encoded '@' (%40) is present when literal '@' is not
    if "@" in authority:
        _, host_part = authority.rsplit("@", 1)
        authority = f"***:***@{host_part}"
    elif "%40" in authority.upper():
        decoded_auth = unquote(authority)
        if "@" in decoded_auth:
            _, host_part = decoded_auth.rsplit("@", 1)
            authority = f"***:***@{host_part}"

    tail = _SENSITIVE_QUERY_PARAM_PATTERN.sub(r"\1***", tail)
    return f"{scheme_prefix}{authority}{tail}"


def redact_uri_credentials(text: str) -> str:
    """Mask embedded credentials in any URI scheme into `scheme://***:***@host...`."""
    if not text:
        return text

    redacted = _URI_PATTERN.sub(_redact_single_uri, text)
    redacted = _ENCODED_URI_CREDENTIALS_PATTERN.sub(r"\1***%3A***\3", redacted)
    redacted = _SENSITIVE_QUERY_PARAM_PATTERN.sub(r"\1***", redacted)
    redacted = _YAML_SENSITIVE_LINE_PATTERN.sub(r'\1"***"', redacted)
    return redacted


def redact_sensitive_data(data: Any) -> Any:
    """Recursively sanitize credentials from strings, dicts (keys & values), lists, and models.

    Ensures that any URI with credentials (`rtsp://`, `rtsps://`, `http://`, `https://`,
    `rtmp://`, `onvif://`, `dvrip://`, etc.) is converted to `scheme://***:***@host...`
    before returning data to the LLM or logging.
    """
    if data is None or isinstance(data, (bool, int, float)):
        return data

    if isinstance(data, str):
        return redact_uri_credentials(data)

    if isinstance(data, BaseModel):
        return redact_sensitive_data(data.model_dump())

    if isinstance(data, dict):
        sanitized_dict: dict[Any, Any] = {}
        for key, value in data.items():
            safe_key = redact_sensitive_data(key) if isinstance(key, str) else key
            if isinstance(key, str) and key.strip().lower() in _SENSITIVE_DICT_KEYS:
                if value is None or value == "":
                    sanitized_dict[safe_key] = value
                else:
                    sanitized_dict[safe_key] = "***"
            else:
                sanitized_dict[safe_key] = redact_sensitive_data(value)
        return sanitized_dict

    if isinstance(data, list):
        return [redact_sensitive_data(item) for item in data]

    if isinstance(data, tuple):
        return tuple(redact_sensitive_data(item) for item in data)

    if isinstance(data, set):
        return {redact_sensitive_data(item) for item in data}

    return data


def validate_stream_source(source: str, *, allow_exec: bool = False) -> str:
    """Validate a stream source URL/definition against command-execution security guardrails.

    Blocks `exec:`, `echo:`, and `expr:` stream sources (including chained prefixes like
    `ffmpeg:exec:...`) unless `allow_exec=True` (`GO2RTC_ALLOW_EXEC_STREAMS=true`).
    """
    cleaned = source.strip()
    if not cleaned:
        raise ValueError("Stream source URL cannot be empty.")

    if not allow_exec:
        pre_scheme = cleaned.split("://", 1)[0].lower()
        segments = [seg.strip() for seg in pre_scheme.split(":") if seg.strip()]
        for prefix in _DANGEROUS_STREAM_PREFIXES:
            prefix_name = prefix.rstrip(":")
            if cleaned.lower().startswith(prefix) or prefix_name in segments:
                raise SecurityPolicyError(
                    f"Stream source using '{prefix}' is blocked by security policy "
                    "(GO2RTC_ALLOW_EXEC_STREAMS=false)."
                )

    return cleaned


class RedactingLoggingFilter(logging.Filter):
    """Logging filter that masks any URI credentials in log messages and arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_uri_credentials(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_uri_credentials(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_uri_credentials(str(arg)) if not isinstance(arg, (int, float)) else arg
                    for arg in record.args
                )
        return True


def install_log_redaction_filter() -> None:
    """Attach RedactingLoggingFilter to root, httpx, httpcore, and go2rtc_mcp loggers."""
    redacting_filter = RedactingLoggingFilter()
    for logger_name in ("", "httpx", "httpcore", "go2rtc_mcp", "mcp"):
        target_logger = logging.getLogger(logger_name)
        if not any(isinstance(f, RedactingLoggingFilter) for f in target_logger.filters):
            target_logger.addFilter(redacting_filter)
