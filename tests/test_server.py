"""Unit tests for go2rtc-mcp tools, resources, and prompts."""

from __future__ import annotations

import httpx
import pytest
import respx

from go2rtc_mcp import server

MOCK_BASE_URL = "http://192.0.2.1:1984"
MOCK_RTSP_URL = "rtsp://admin:mockpass%2A@192.0.2.10:554/stream1"


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GO2RTC_URL", MOCK_BASE_URL)
    monkeypatch.setenv("GO2RTC_USERNAME", "")
    monkeypatch.setenv("GO2RTC_PASSWORD", "")
    monkeypatch.setenv("GO2RTC_TIMEOUT", "5.0")
    monkeypatch.setenv("GO2RTC_ALLOW_EXEC_STREAMS", "false")


async def test_mcp_registers_expected_tools_and_resources() -> None:
    tools = await server.mcp.list_tools()
    tool_names = {t.name for t in tools}
    expected_tools = {
        "get_server_info",
        "list_streams",
        "get_stream_info",
        "probe_stream",
        "get_stream_snapshot",
        "get_stream_urls",
        "add_stream",
        "update_stream",
        "delete_stream",
        "get_config",
        "get_server_logs",
        "discover_sources",
    }
    assert expected_tools.issubset(tool_names)

    resources = await server.mcp.list_resources()
    resource_uris = {str(r.uri) for r in resources}
    assert "go2rtc://server/info" in resource_uris
    assert "go2rtc://streams" in resource_uris
    assert "go2rtc://config" in resource_uris


@respx.mock
async def test_server_tools_and_resources_redact_credentials() -> None:
    respx.get(f"{MOCK_BASE_URL}/api").mock(
        return_value=httpx.Response(
            200,
            json={
                "version": "1.9.14",
                "host": "192.0.2.1:1984",
                "rtsp": {"listen": ":554"},
            },
        )
    )
    respx.get(f"{MOCK_BASE_URL}/api/streams").mock(
        return_value=httpx.Response(
            200,
            json={
                "door_camera": {
                    "producers": [{"url": MOCK_RTSP_URL}],
                    "consumers": None,
                }
            },
        )
    )
    respx.get(f"{MOCK_BASE_URL}/api/config").mock(
        return_value=httpx.Response(
            200,
            text=f"streams:\n  door_camera: {MOCK_RTSP_URL}\n",
        )
    )
    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\xff\xd9"
    respx.get(f"{MOCK_BASE_URL}/api/frame.jpeg").mock(
        return_value=httpx.Response(200, content=fake_jpeg)
    )

    streams = await server.list_streams()
    assert (
        streams["door_camera"]["producers"][0]["url"]
        == "rtsp://***:***@192.0.2.10:554/stream1"
    )
    assert "mockpass" not in str(streams)

    urls = await server.get_stream_urls("door_camera")
    assert urls["rtsp_url"] == "rtsp://192.0.2.1:554/door_camera"
    assert urls["snapshot_jpeg"] == f"{MOCK_BASE_URL}/api/frame.jpeg?src=door_camera"

    snap = await server.get_stream_snapshot("door_camera")
    img_content = snap.to_image_content()
    assert img_content.mime_type == "image/jpeg"

    res_streams = await server.resource_streams()
    assert "mockpass" not in res_streams
    assert "rtsp://***:***@192.0.2.10:554/stream1" in res_streams

    res_config = await server.resource_config()
    assert "mockpass" not in res_config
    assert "rtsp://***:***@192.0.2.10:554/stream1" in res_config

    prompt_text = server.diagnose_stream("door_camera")
    assert "door_camera" in prompt_text
