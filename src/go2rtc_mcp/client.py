"""Async HTTP client for interacting with a go2rtc server with enforced credential redaction."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, urlparse

import httpx
import yaml

from go2rtc_mcp.config import Go2RtcSettings
from go2rtc_mcp.security import (
    redact_sensitive_data,
    redact_uri_credentials,
    validate_stream_source,
)


class Go2RtcClientError(RuntimeError):
    """Exception raised when communicating with the go2rtc server fails."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        safe_message = redact_uri_credentials(str(message))
        super().__init__(safe_message)
        self.status_code = status_code


class Go2RtcClient:
    """Asynchronous client for the go2rtc HTTP API with automatic credential redaction."""

    def __init__(
        self,
        settings: Go2RtcSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or Go2RtcSettings.from_env()
        self._external_client = http_client

    def _build_client(self) -> httpx.AsyncClient:
        auth: httpx.BasicAuth | None = None
        if self.settings.username and self.settings.password is not None:
            auth = httpx.BasicAuth(self.settings.username, self.settings.password)
        return httpx.AsyncClient(
            base_url=self.settings.url,
            auth=auth,
            timeout=httpx.Timeout(self.settings.timeout),
            follow_redirects=True,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        if self._external_client is not None:
            return await self._send(self._external_client, method, path, params=params, timeout=timeout)

        async with self._build_client() as client:
            return await self._send(client, method, path, params=params, timeout=timeout)

    async def _send(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        try:
            kwargs: dict[str, Any] = {}
            if params is not None:
                kwargs["params"] = params
            if timeout is not None:
                kwargs["timeout"] = timeout
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            body_preview = redact_uri_credentials(exc.response.text[:300])
            raise Go2RtcClientError(
                f"go2rtc API returned HTTP {exc.response.status_code} for {method} {path}: {body_preview}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise Go2RtcClientError(
                f"Failed to connect to go2rtc at {self.settings.url} ({method} {path}): {exc}"
            ) from exc

    async def get_server_info(self) -> dict[str, Any]:
        """Fetch server metadata (`GET /api`)."""
        response = await self._request("GET", "/api")
        data = response.json()
        return redact_sensitive_data(data)

    async def list_streams(self) -> dict[str, Any]:
        """Fetch all configured and active streams (`GET /api/streams`) with credentials redacted."""
        response = await self._request("GET", "/api/streams")
        data = response.json()
        return redact_sensitive_data(data)

    async def get_stream(self, stream_name: str, *, probe: bool = False) -> dict[str, Any]:
        """Fetch information for a single stream (`GET /api/streams?src=<stream_name>`).

        If `probe=True`, queries `video=all&audio=all&microphone` to actively inspect codecs and SDP.
        """
        name = stream_name.strip()
        if not name:
            raise ValueError("stream_name must not be empty.")

        params: dict[str, Any] = {"src": name}
        if probe:
            params["video"] = "all"
            params["audio"] = "all"

        response = await self._request("GET", "/api/streams", params=params)
        data = response.json()
        return redact_sensitive_data(data)

    async def probe_stream(self, stream_name: str) -> dict[str, Any]:
        """Actively probe a stream (`GET /api/streams?src=<stream_name>&video=all&audio=all`)."""
        return await self.get_stream(stream_name, probe=True)

    async def add_stream(self, stream_name: str, source: str | list[str]) -> dict[str, Any]:
        """Register or overwrite a stream dynamically (`PUT /api/streams`)."""
        return await self._upsert_stream("PUT", stream_name, source)

    async def update_stream(self, stream_name: str, source: str | list[str]) -> dict[str, Any]:
        """Update an existing stream dynamically (`PATCH /api/streams`)."""
        return await self._upsert_stream("PATCH", stream_name, source)

    async def _upsert_stream(
        self, method: str, stream_name: str, source: str | list[str]
    ) -> dict[str, Any]:
        name = stream_name.strip()
        if not name:
            raise ValueError("stream_name must not be empty.")

        sources = [source] if isinstance(source, str) else list(source)
        if not sources:
            raise ValueError("At least one stream source URL is required.")

        validated_sources = [
            validate_stream_source(src, allow_exec=self.settings.allow_exec_streams)
            for src in sources
        ]

        params: list[tuple[str, str]] = [("name", name)]
        for src in validated_sources:
            params.append(("src", src))

        await self._request(method, "/api/streams", params=params)
        return redact_sensitive_data(
            {
                "status": "ok",
                "action": "added" if method == "PUT" else "updated",
                "stream": name,
                "sources": validated_sources,
            }
        )

    async def delete_stream(self, stream_name: str) -> dict[str, Any]:
        """Delete a stream (`DELETE /api/streams?src=<stream_name>`)."""
        name = stream_name.strip()
        if not name:
            raise ValueError("stream_name must not be empty.")

        await self._request("DELETE", "/api/streams", params={"src": name})
        return redact_sensitive_data(
            {
                "status": "ok",
                "action": "deleted",
                "stream": name,
            }
        )

    async def get_snapshot(
        self,
        stream_name: str,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes:
        """Capture a JPEG snapshot frame from a stream (`GET /api/frame.jpeg?src=<stream_name>`)."""
        name = stream_name.strip()
        if not name:
            raise ValueError("stream_name must not be empty.")

        params: dict[str, Any] = {"src": name}
        if width is not None:
            if width <= 0:
                raise ValueError("width must be a positive integer.")
            params["width"] = width
        if height is not None:
            if height <= 0:
                raise ValueError("height must be a positive integer.")
            params["height"] = height

        response = await self._request("GET", "/api/frame.jpeg", params=params)
        return response.content

    async def get_config(self) -> str:
        """Fetch `go2rtc.yaml` (`GET /api/config`) and sanitize all embedded credentials."""
        response = await self._request("GET", "/api/config")
        raw_yaml = response.text

        # First sanitize structurally via PyYAML if valid YAML, then also run text sanitizer
        try:
            parsed = yaml.safe_load(raw_yaml)
            if isinstance(parsed, (dict, list)):
                redacted_obj = redact_sensitive_data(parsed)
                dumped = yaml.safe_dump(redacted_obj, sort_keys=False, allow_unicode=True)
                return redact_uri_credentials(dumped)
        except yaml.YAMLError:
            pass

        return redact_uri_credentials(raw_yaml)

    async def get_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch and sanitize recent server log entries (`GET /api/log`)."""
        if limit <= 0:
            raise ValueError("limit must be a positive integer.")

        response = await self._request("GET", "/api/log")
        lines = [line.strip() for line in response.text.splitlines() if line.strip()]
        entries: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    entries.append(redact_sensitive_data(parsed))
                else:
                    entries.append({"message": redact_sensitive_data(str(parsed))})
            except json.JSONDecodeError:
                entries.append({"message": redact_uri_credentials(line)})
        return entries

    async def discover_sources(self, provider: str = "hass") -> Any:
        """Query a go2rtc discovery provider endpoint (e.g. `hass`, `onvif`, `dvrip`, `homekit`)."""
        allowed_providers = {
            "hass",
            "onvif",
            "dvrip",
            "homekit",
            "roborock",
            "webtorrent",
            "alsa",
            "v4l2",
        }
        clean_provider = provider.strip().lower().lstrip("/")
        if clean_provider not in allowed_providers:
            raise ValueError(
                f"Unsupported discovery provider '{provider}'. "
                f"Allowed providers: {', '.join(sorted(allowed_providers))}"
            )

        response = await self._request("GET", f"/api/{clean_provider}")
        try:
            data = response.json()
            return redact_sensitive_data(data)
        except ValueError:
            return redact_uri_credentials(response.text)

    async def get_stream_urls(self, stream_name: str) -> dict[str, str]:
        """Build safe playback & snapshot URLs for a stream (HTTP, WebRTC, HLS, MP4, MJPEG, RTSP)."""
        name = stream_name.strip()
        if not name:
            raise ValueError("stream_name must not be empty.")

        encoded = quote(name, safe="")
        base_http = self.settings.url.rstrip("/")
        parsed = urlparse(base_http)
        hostname = parsed.hostname or "localhost"
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_netloc = parsed.netloc or hostname

        rtsp_port = "8554"
        try:
            info = await self.get_server_info()
            rtsp_info = info.get("rtsp")
            if isinstance(rtsp_info, dict):
                listen = str(rtsp_info.get("listen", ""))
                if ":" in listen:
                    port_candidate = listen.rsplit(":", 1)[-1].strip()
                    if port_candidate.isdigit():
                        rtsp_port = port_candidate
        except Exception:
            pass

        return redact_sensitive_data(
            {
                "stream": name,
                "webrtc_viewer": f"{base_http}/stream.html?src={encoded}&mode=webrtc",
                "mse_viewer": f"{base_http}/stream.html?src={encoded}&mode=mse",
                "websocket_url": f"{ws_scheme}://{ws_netloc}/api/ws?src={encoded}",
                "hls_m3u8": f"{base_http}/api/stream.m3u8?src={encoded}",
                "mp4_stream": f"{base_http}/api/stream.mp4?src={encoded}",
                "mjpeg_stream": f"{base_http}/api/stream.mjpeg?src={encoded}",
                "snapshot_jpeg": f"{base_http}/api/frame.jpeg?src={encoded}",
                "rtsp_url": f"rtsp://{hostname}:{rtsp_port}/{encoded}",
            }
        )
