"""Alias module re-exporting centralized security and credential sanitization utilities."""

from go2rtc_mcp.security import (
    SecurityPolicyError,
    redact_sensitive_data,
    redact_uri_credentials,
    validate_stream_source,
)

__all__ = [
    "SecurityPolicyError",
    "redact_sensitive_data",
    "redact_uri_credentials",
    "validate_stream_source",
]
