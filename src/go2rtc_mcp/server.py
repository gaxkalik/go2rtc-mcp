"""Model Context Protocol (MCP) server for go2rtc media streaming instances."""

from __future__ import annotations

import json
from typing import Any

try:
    from mcp.server.mcpserver import Image, MCPServer
except ImportError:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP as MCPServer  # type: ignore[no-redef]
    from mcp.server.fastmcp import Image  # type: ignore[no-redef]

from go2rtc_mcp.client import Go2RtcClient
from go2rtc_mcp.config import Go2RtcSettings
from go2rtc_mcp.security import redact_sensitive_data

mcp = MCPServer(
    "go2rtc-mcp",
    instructions=(
        "Manage and inspect go2rtc camera streams, codecs, snapshots, and configurations. "
        "All credentials in stream URLs and YAML configurations are automatically redacted."
    ),
)

# Alias for callers expecting `server` or `mcp`
server = mcp


def get_client(settings: Go2RtcSettings | None = None) -> Go2RtcClient:
    """Instantiate a Go2RtcClient configured from environment variables or explicit settings."""
    return Go2RtcClient(settings=settings)


@mcp.tool()
async def get_server_info() -> dict[str, Any]:
    """Get go2rtc server metadata including version, revision, host, RTSP port, and config path."""
    client = get_client()
    info = await client.get_server_info()
    return redact_sensitive_data(info)


@mcp.tool()
async def list_streams() -> dict[str, Any]:
    """List all configured and active streams on the go2rtc server with credentials redacted."""
    client = get_client()
    streams = await client.list_streams()
    return redact_sensitive_data(streams)


@mcp.tool()
async def get_stream_info(stream_name: str, probe: bool = False) -> dict[str, Any]:
    """Get producer and consumer details for a specific stream (`stream_name`).

    Set `probe=True` to actively query video/audio codecs, SDP, and byte counters.
    """
    client = get_client()
    stream_data = await client.get_stream(stream_name, probe=probe)
    return redact_sensitive_data(stream_data)


@mcp.tool()
async def probe_stream(stream_name: str) -> dict[str, Any]:
    """Actively probe a camera stream to inspect its video/audio codecs, SDP, and track stats."""
    client = get_client()
    probe_data = await client.probe_stream(stream_name)
    return redact_sensitive_data(probe_data)


@mcp.tool()
async def get_stream_snapshot(
    stream_name: str,
    width: int | None = None,
    height: int | None = None,
) -> Image:
    """Capture a live JPEG snapshot frame from `stream_name` and return it as an MCP Image."""
    client = get_client()
    jpeg_bytes = await client.get_snapshot(stream_name, width=width, height=height)
    return Image(data=jpeg_bytes, format="jpeg")


@mcp.tool()
async def get_stream_urls(stream_name: str) -> dict[str, str]:
    """Generate WebRTC, MSE, HLS (.m3u8), MP4, MJPEG, JPEG snapshot, and RTSP URLs for a stream."""
    client = get_client()
    urls = await client.get_stream_urls(stream_name)
    return redact_sensitive_data(urls)


@mcp.tool()
async def add_stream(stream_name: str, source_url: str) -> dict[str, Any]:
    """Dynamically add or overwrite a stream on go2rtc (`PUT /api/streams`).

    Rejects `exec:`, `echo:`, and `expr:` sources unless `GO2RTC_ALLOW_EXEC_STREAMS=true`.
    """
    client = get_client()
    result = await client.add_stream(stream_name, source_url)
    return redact_sensitive_data(result)


@mcp.tool()
async def update_stream(stream_name: str, source_url: str) -> dict[str, Any]:
    """Dynamically update an existing stream on go2rtc (`PATCH /api/streams`).

    Rejects `exec:`, `echo:`, and `expr:` sources unless `GO2RTC_ALLOW_EXEC_STREAMS=true`.
    """
    client = get_client()
    result = await client.update_stream(stream_name, source_url)
    return redact_sensitive_data(result)


@mcp.tool()
async def delete_stream(stream_name: str) -> dict[str, Any]:
    """Delete a dynamically registered stream from go2rtc (`DELETE /api/streams`)."""
    client = get_client()
    result = await client.delete_stream(stream_name)
    return redact_sensitive_data(result)


@mcp.tool()
async def get_config() -> str:
    """Retrieve the go2rtc YAML configuration (`GET /api/config`) with all credentials redacted."""
    client = get_client()
    yaml_text = await client.get_config()
    return redact_sensitive_data(yaml_text)


@mcp.tool()
async def get_server_logs(limit: int = 50) -> list[dict[str, Any]]:
    """Retrieve the most recent `limit` log entries from go2rtc (`GET /api/log`), sanitized."""
    client = get_client()
    logs = await client.get_logs(limit=limit)
    return redact_sensitive_data(logs)


@mcp.tool()
async def discover_sources(provider: str = "hass") -> Any:
    """Discover stream sources from a go2rtc integration (`hass`, `onvif`, `dvrip`, `homekit`)."""
    client = get_client()
    discovered = await client.discover_sources(provider=provider)
    return redact_sensitive_data(discovered)


@mcp.resource(
    "go2rtc://server/info",
    name="go2rtc_server_info",
    description="Redacted go2rtc server metadata and RTSP configuration",
    mime_type="application/json",
)
async def resource_server_info() -> str:
    """Return JSON-serialized server info with credentials redacted."""
    client = get_client()
    info = redact_sensitive_data(await client.get_server_info())
    return json.dumps(info, indent=2)


@mcp.resource(
    "go2rtc://streams",
    name="go2rtc_streams",
    description="All configured go2rtc streams with producer credentials redacted",
    mime_type="application/json",
)
async def resource_streams() -> str:
    """Return JSON-serialized streams dictionary with credentials redacted."""
    client = get_client()
    streams = redact_sensitive_data(await client.list_streams())
    return json.dumps(streams, indent=2)


@mcp.resource(
    "go2rtc://streams/{stream_name}",
    name="go2rtc_stream_detail",
    description="Detailed producer and consumer state for a single go2rtc stream (redacted)",
    mime_type="application/json",
)
async def resource_stream_detail(stream_name: str) -> str:
    """Return JSON-serialized details for `stream_name` with credentials redacted."""
    client = get_client()
    detail = redact_sensitive_data(await client.get_stream(stream_name))
    return json.dumps(detail, indent=2)


@mcp.resource(
    "go2rtc://config",
    name="go2rtc_config",
    description="Sanitized go2rtc.yaml server configuration",
    mime_type="text/yaml",
)
async def resource_config() -> str:
    """Return sanitized go2rtc.yaml configuration."""
    client = get_client()
    return redact_sensitive_data(await client.get_config())


@mcp.prompt()
def diagnose_stream(stream_name: str) -> str:
    """Generate a step-by-step diagnostic prompt for troubleshooting a go2rtc camera stream."""
    return (
        f"Please diagnose the go2rtc camera stream '{stream_name}':\n"
        f"1. Call `get_stream_info(stream_name='{stream_name}', probe=True)` to inspect "
        "active producers, video/audio codecs, SDP, and packet counters.\n"
        f"2. Call `get_stream_snapshot(stream_name='{stream_name}')` to verify live video "
        "frame decoding.\n"
        "3. Call `get_server_logs(limit=50)` to check for connection, auth, or codec errors.\n"
        "4. Summarize stream health, codecs, and any recommended fixes."
    )


def main() -> None:
    """Run the go2rtc-mcp server over stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
