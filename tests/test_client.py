"""Unit tests for Go2RtcClient using synthetic RFC 5737 test fixtures and respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from go2rtc_mcp.client import Go2RtcClient, Go2RtcClientError
from go2rtc_mcp.config import Go2RtcSettings
from go2rtc_mcp.security import SecurityPolicyError

MOCK_BASE_URL = "http://192.0.2.1:1984"
MOCK_RTSP_DOOR = "rtsp://admin:mockpass%2A@192.0.2.10:554/stream1"
MOCK_RTSP_GARAGE = "rtsp://admin:mockgarage%26@192.0.2.11:554/stream1"


@pytest.fixture
def settings() -> Go2RtcSettings:
    return Go2RtcSettings(
        url=MOCK_BASE_URL,
        username=None,
        password=None,
        timeout=5.0,
        allow_exec_streams=False,
    )


@pytest.fixture
def client(settings: Go2RtcSettings) -> Go2RtcClient:
    return Go2RtcClient(settings=settings)


@respx.mock
async def test_get_server_info(client: Go2RtcClient) -> None:
    respx.get(f"{MOCK_BASE_URL}/api").mock(
        return_value=httpx.Response(
            200,
            json={
                "version": "1.9.14",
                "revision": "b5948cf",
                "host": "192.0.2.1:1984",
                "config_path": "/config/go2rtc.yaml",
                "rtsp": {"listen": ":554", "default_query": "video&audio"},
            },
        )
    )
    info = await client.get_server_info()
    assert info["version"] == "1.9.14"
    assert info["rtsp"]["listen"] == ":554"


@respx.mock
async def test_list_streams_redacts_credentials(client: Go2RtcClient) -> None:
    respx.get(f"{MOCK_BASE_URL}/api/streams").mock(
        return_value=httpx.Response(
            200,
            json={
                "door_camera": {
                    "producers": [{"url": MOCK_RTSP_DOOR}],
                    "consumers": None,
                },
                "garage_camera": {
                    "producers": [{"url": MOCK_RTSP_GARAGE}],
                    "consumers": [],
                },
                MOCK_RTSP_DOOR: {
                    "producers": [{"url": MOCK_RTSP_DOOR}],
                    "consumers": [],
                },
            },
        )
    )

    streams = await client.list_streams()
    serialized = str(streams)
    assert "mockpass" not in serialized
    assert "mockgarage" not in serialized
    assert (
        streams["door_camera"]["producers"][0]["url"]
        == "rtsp://***:***@192.0.2.10:554/stream1"
    )
    assert (
        streams["garage_camera"]["producers"][0]["url"]
        == "rtsp://***:***@192.0.2.11:554/stream1"
    )
    assert "rtsp://***:***@192.0.2.10:554/stream1" in streams


@respx.mock
async def test_probe_stream(client: Go2RtcClient) -> None:
    route = respx.get(
        f"{MOCK_BASE_URL}/api/streams",
        params={"src": "door_camera", "video": "all", "audio": "all"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "producers": [
                    {
                        "id": 1,
                        "format_name": "rtsp",
                        "protocol": "rtsp+tcp",
                        "url": MOCK_RTSP_DOOR,
                        "medias": ["video, sendonly, H264"],
                    }
                ],
                "consumers": [],
            },
        )
    )

    probed = await client.probe_stream("door_camera")
    assert route.called
    assert probed["producers"][0]["url"] == "rtsp://***:***@192.0.2.10:554/stream1"
    assert "mockpass" not in str(probed)


@respx.mock
async def test_add_update_delete_stream_lifecycle(client: Go2RtcClient) -> None:
    put_route = respx.put(f"{MOCK_BASE_URL}/api/streams").mock(return_value=httpx.Response(200))
    patch_route = respx.patch(f"{MOCK_BASE_URL}/api/streams").mock(
        return_value=httpx.Response(200)
    )
    delete_route = respx.delete(f"{MOCK_BASE_URL}/api/streams").mock(
        return_value=httpx.Response(200)
    )

    added = await client.add_stream("test_cam", MOCK_RTSP_DOOR)
    assert put_route.called
    assert added["action"] == "added"
    assert added["sources"] == ["rtsp://***:***@192.0.2.10:554/stream1"]
    assert "mockpass" not in str(added)

    updated = await client.update_stream("test_cam", MOCK_RTSP_GARAGE)
    assert patch_route.called
    assert updated["action"] == "updated"
    assert updated["sources"] == ["rtsp://***:***@192.0.2.11:554/stream1"]

    deleted = await client.delete_stream("test_cam")
    assert delete_route.called
    assert deleted == {"status": "ok", "action": "deleted", "stream": "test_cam"}


async def test_add_stream_blocks_exec_without_network_call(client: Go2RtcClient) -> None:
    with pytest.raises(SecurityPolicyError):
        await client.add_stream("evil_cam", "exec:ffmpeg -i input.mp4")


@respx.mock
async def test_get_snapshot(client: Go2RtcClient) -> None:
    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    respx.get(
        f"{MOCK_BASE_URL}/api/frame.jpeg",
        params={"src": "door_camera", "width": 640, "height": 360},
    ).mock(
        return_value=httpx.Response(
            200, content=fake_jpeg, headers={"content-type": "image/jpeg"}
        )
    )

    data = await client.get_snapshot("door_camera", width=640, height=360)
    assert data == fake_jpeg


@respx.mock
async def test_get_config_redacts_yaml_secrets(client: Go2RtcClient) -> None:
    raw_yaml = (
        "rtsp:\n"
        '  listen: ":554"\n'
        "streams:\n"
        f"  door_camera: {MOCK_RTSP_DOOR}\n"
        "  cloud_camera: rtsp://cloud.example.com/live?token=secretToken999\n"
    )
    respx.get(f"{MOCK_BASE_URL}/api/config").mock(
        return_value=httpx.Response(200, text=raw_yaml)
    )

    sanitized_yaml = await client.get_config()
    assert "mockpass" not in sanitized_yaml
    assert "secretToken999" not in sanitized_yaml
    assert "rtsp://***:***@192.0.2.10:554/stream1" in sanitized_yaml
    assert "token=***" in sanitized_yaml


@respx.mock
async def test_get_logs_and_discover_sources(client: Go2RtcClient) -> None:
    ndjson_logs = (
        '{"level":"info","message":"connected to rtsp://admin:mockpass%2A@192.0.2.10:554/stream1"}\n'
        '{"level":"warn","message":"retrying http://user:pass123@192.0.2.12/stream"}\n'
    )
    respx.get(f"{MOCK_BASE_URL}/api/log").mock(
        return_value=httpx.Response(200, text=ndjson_logs)
    )
    logs = await client.get_logs(limit=10)
    assert len(logs) == 2
    assert "mockpass" not in str(logs)
    assert "pass123" not in str(logs)
    assert "rtsp://***:***@192.0.2.10:554/stream1" in logs[0]["message"]

    respx.get(f"{MOCK_BASE_URL}/api/hass").mock(
        return_value=httpx.Response(
            200,
            json={
                "sources": [
                    {
                        "name": "door_cam",
                        "url": "hass:door_cam",
                        "location": MOCK_RTSP_DOOR,
                    }
                ]
            },
        )
    )
    discovered = await client.discover_sources("hass")
    assert (
        discovered["sources"][0]["location"]
        == "rtsp://***:***@192.0.2.10:554/stream1"
    )


@respx.mock
async def test_client_error_redacts_leaked_url_in_response(client: Go2RtcClient) -> None:
    respx.get(f"{MOCK_BASE_URL}/api/streams").mock(
        return_value=httpx.Response(
            500,
            text=f"Upstream failure connecting to {MOCK_RTSP_DOOR}",
        )
    )
    with pytest.raises(Go2RtcClientError) as exc_info:
        await client.list_streams()

    assert "mockpass" not in str(exc_info.value)
    assert "rtsp://***:***@192.0.2.10:554/stream1" in str(exc_info.value)
