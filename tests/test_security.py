"""Unit tests for centralized recursive credential redaction and stream security policy."""

from __future__ import annotations

import pytest

from go2rtc_mcp.models import StreamInfo, StreamProducer
from go2rtc_mcp.security import (
    SecurityPolicyError,
    redact_sensitive_data,
    redact_uri_credentials,
    validate_stream_source,
)


@pytest.mark.parametrize(
    ("raw_url", "expected_url"),
    [
        (
            "rtsp://admin:mockpass%2A@192.0.2.10:554/stream1",
            "rtsp://***:***@192.0.2.10:554/stream1",
        ),
        (
            "rtsps://operator:s3cr3t%26%21@192.0.2.11:322/cam/realmonitor",
            "rtsps://***:***@192.0.2.11:322/cam/realmonitor",
        ),
        (
            "http://user:http_pass@192.0.2.12:8080/video.mjpg",
            "http://***:***@192.0.2.12:8080/video.mjpg",
        ),
        (
            "https://apiuser:apipass@camera.example.com/snapshot.jpg",
            "https://***:***@camera.example.com/snapshot.jpg",
        ),
        (
            "rtmp://pub:rtmppass@192.0.2.13:1935/live/stream",
            "rtmp://***:***@192.0.2.13:1935/live/stream",
        ),
        (
            "onvif://admin:onvifpass%40123@192.0.2.14:8000/onvif/device_service",
            "onvif://***:***@192.0.2.14:8000/onvif/device_service",
        ),
        (
            "dvrip://admin:dvrippass@192.0.2.15:34567/channel=1",
            "dvrip://***:***@192.0.2.15:34567/channel=1",
        ),
        (
            "ffmpeg:rtsp://admin:mockpass%2A@192.0.2.10:554/stream1#video=h264",
            "ffmpeg:rtsp://***:***@192.0.2.10:554/stream1#video=h264",
        ),
        (
            "rtsp://stream.example.com/live/cam1?token=eyJmockJwtToken123&tracks=v1a1",
            "rtsp://stream.example.com/live/cam1?token=***&tracks=v1a1",
        ),
    ],
)
def test_redact_uri_credentials_schemes(raw_url: str, expected_url: str) -> None:
    """Verify credentials in all supported URI schemes and query parameters are masked."""
    redacted = redact_uri_credentials(raw_url)
    assert redacted == expected_url
    assert "mockpass" not in redacted
    assert "s3cr3t" not in redacted
    assert "eyJmockJwtToken123" not in redacted


def test_redact_sensitive_data_recursive_structures() -> None:
    """Verify nested dicts, dict keys, lists, tuples, sets, and Pydantic models are redacted."""
    raw_payload = {
        "door_camera": {
            "producers": [
                {"url": "rtsp://admin:mockpass%2A@192.0.2.10:554/stream1"},
                {"url": "onvif://admin:onvifSecret@192.0.2.10:8000"},
            ],
            "consumers": None,
        },
        "rtsp://admin:mockpass%2A@192.0.2.10:554/stream1": {
            "producers": [{"url": "rtsp://admin:mockpass%2A@192.0.2.10:554/stream1"}],
            "consumers": [],
        },
        "auth": {
            "username": "admin",
            "password": "super_secret_yaml_password",
            "token": "secret_bearer_token",
        },
        "tuple_urls": ("dvrip://root:dvrpass@192.0.2.20:34567",),
        "model": StreamInfo(
            producers=[
                StreamProducer(url="rtmp://user:rtmpsecret@192.0.2.30/live"),
            ]
        ),
    }

    sanitized = redact_sensitive_data(raw_payload)

    assert (
        sanitized["door_camera"]["producers"][0]["url"]
        == "rtsp://***:***@192.0.2.10:554/stream1"
    )
    assert (
        sanitized["door_camera"]["producers"][1]["url"]
        == "onvif://***:***@192.0.2.10:8000"
    )
    # Dict keys containing raw RTSP URLs must also be sanitized
    assert "rtsp://admin:mockpass%2A@192.0.2.10:554/stream1" not in sanitized
    assert "rtsp://***:***@192.0.2.10:554/stream1" in sanitized
    assert sanitized["auth"]["username"] == "admin"
    assert sanitized["auth"]["password"] == "***"
    assert sanitized["auth"]["token"] == "***"
    assert sanitized["tuple_urls"] == ("dvrip://***:***@192.0.2.20:34567",)
    assert sanitized["model"]["producers"][0]["url"] == "rtmp://***:***@192.0.2.30/live"


def test_redact_yaml_multiline_config() -> None:
    """Verify multiline YAML strings have both URI credentials and password fields masked."""
    raw_yaml = """
api:
  listen: ":1984"
  username: admin
  password: my_secret_api_password

streams:
  door_camera: rtsp://admin:mockpass%2A@192.0.2.10:554/stream1
  garage_camera:
    - ffmpeg:rtsp://admin:garagepass%26@192.0.2.11:554/stream1
"""
    redacted = redact_uri_credentials(raw_yaml)
    assert "my_secret_api_password" not in redacted
    assert "mockpass" not in redacted
    assert "garagepass" not in redacted
    assert "rtsp://***:***@192.0.2.10:554/stream1" in redacted
    assert "ffmpeg:rtsp://***:***@192.0.2.11:554/stream1" in redacted


@pytest.mark.parametrize(
    "dangerous_src",
    [
        "exec:ffmpeg -re -i input.mp4 -c copy -f rtsp {output}",
        "EXEC:python3 -c 'import os'",
        "echo:rtsp://192.0.2.10/stream",
        "expr:1+1",
        "ffmpeg:exec:sh -c id",
    ],
)
def test_validate_stream_source_blocks_exec_by_default(dangerous_src: str) -> None:
    """Ensure exec:, echo:, and expr: streams are rejected when allow_exec=False."""
    with pytest.raises(SecurityPolicyError, match="blocked by security policy"):
        validate_stream_source(dangerous_src, allow_exec=False)


def test_validate_stream_source_allows_exec_when_enabled() -> None:
    """Ensure exec: streams are permitted only when allow_exec=True."""
    src = "exec:ffmpeg -re -i test.mp4"
    assert validate_stream_source(src, allow_exec=True) == src


def test_validate_stream_source_rejects_empty() -> None:
    """Ensure empty stream sources raise ValueError."""
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_stream_source("   ")


def test_redacting_logging_filter_masks_log_records() -> None:
    """Verify RedactingLoggingFilter masks credentials in log messages and args."""
    import logging

    from go2rtc_mcp.security import RedactingLoggingFilter

    log_filter = RedactingLoggingFilter()
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP Request: PUT http://192.0.2.1:1984/api/streams?src=%s",
        args=("rtsp://admin:mockpass%2A@192.0.2.10:554/stream1",),
        exc_info=None,
    )
    assert log_filter.filter(record) is True
    formatted = record.getMessage()
    assert "mockpass" not in formatted
    assert "rtsp://***:***@192.0.2.10:554/stream1" in formatted

