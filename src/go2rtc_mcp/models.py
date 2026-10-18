"""Pydantic data models for go2rtc API responses and stream metadata."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RtspConfigInfo(BaseModel):
    """RTSP listener configuration reported by `/api`."""

    model_config = ConfigDict(extra="allow")

    listen: str | None = None
    default_query: str | None = None


class ServerInfo(BaseModel):
    """Server metadata returned by `GET /api`."""

    model_config = ConfigDict(extra="allow")

    version: str | None = None
    revision: str | None = None
    host: str | None = None
    config_path: str | None = None
    rtsp: RtspConfigInfo | dict[str, Any] | None = None


class StreamProducer(BaseModel):
    """Representation of a stream producer in go2rtc (always redacted)."""

    model_config = ConfigDict(extra="allow")

    id: int | None = None
    url: str | None = None
    format_name: str | None = None
    protocol: str | None = None
    remote_addr: str | None = None
    sdp: str | None = None
    medias: list[str] | None = None
    receivers: list[dict[str, Any]] | None = None
    senders: list[dict[str, Any]] | None = None
    bytes_recv: int | None = None
    bytes_send: int | None = None


class StreamInfo(BaseModel):
    """Representation of a single stream's producers and consumers."""

    model_config = ConfigDict(extra="allow")

    producers: list[StreamProducer | dict[str, Any]] | None = Field(default_factory=list)
    consumers: list[dict[str, Any]] | None = None
