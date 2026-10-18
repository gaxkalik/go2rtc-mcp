# go2rtc-mcp

A production-grade **Model Context Protocol (MCP)** server for [go2rtc](https://github.com/AlexxIT/go2rtc) (including Home Assistant's built-in `go2rtc` instance). `go2rtc-mcp` allows AI assistants and MCP clients to inspect camera streams, probe live video/audio codecs, capture JPEG snapshots, generate streaming playback URLs (WebRTC, MSE, HLS, MP4, MJPEG, RTSP), discover camera sources, and manage streams dynamically—with **strict, automatic credential redaction**.

---

## Table of Contents

- [Architecture & Security Guardrails](#architecture--security-guardrails)
- [Installation & Quick Start](#installation--quick-start)
- [Configuration](#configuration)
- [Connecting an MCP Client](#connecting-an-mcp-client)
- [Usage Guide](#usage-guide)
  - [Example Natural-Language Prompts](#example-natural-language-prompts)
  - [MCP Tools Reference & Examples](#mcp-tools-reference--examples)
  - [MCP Resources Reference](#mcp-resources-reference)
  - [MCP Prompts Reference](#mcp-prompts-reference)
  - [Programmatic Python Usage](#programmatic-python-usage)
- [Project Structure](#project-structure)
- [Development & Testing](#development--testing)
- [License](#license)

---

## Architecture & Security Guardrails

Live `go2rtc` API responses (`/api/streams`, `/api/config`, `/api/hass`, `/api/log`) regularly include plaintext or URL-encoded camera credentials and session tokens inside producer URLs. `go2rtc-mcp` is architected to prevent credential leakage and remote command execution:

### 1. Centralized Recursive Credential Redaction (`redact_sensitive_data`)
Every MCP tool output, MCP resource payload, client exception message, and log record passes through [`redact_sensitive_data`](src/go2rtc_mcp/security.py):
- **URI Credential Masking**: Masks credentials in any URI scheme (`rtsp://`, `rtsps://`, `http://`, `https://`, `rtmp://`, `onvif://`, `dvrip://`, including chained prefixes such as `ffmpeg:rtsp://...`).
- **Query Token Masking**: Masks sensitive URL query parameters (`token`, `access_token`, `auth`, `password`, `pass`, `pwd`, `secret`, `api_key`, `jwt`).
- **Recursive Dict Key & Value Sanitization**: Sanitizes both dictionary keys and values (important because `go2rtc` sometimes uses raw RTSP URLs as stream keys), lists, tuples, sets, Pydantic models, and multiline YAML configs.
- **Log Filtering**: Attaches `RedactingLoggingFilter` to `httpx`, `httpcore`, `mcp`, and `go2rtc_mcp` loggers so credentials never appear in console/stderr logs.

**Example Transformation:**
```text
Raw from go2rtc:
  rtsp://admin:mockpass%2A@192.0.2.10:554/Streaming/Channels/101
  rtsp://stream.example.com/live?token=eyJmockToken123&tracks=v1a1

Returned by go2rtc-mcp:
  rtsp://***:***@192.0.2.10:554/Streaming/Channels/101
  rtsp://stream.example.com/live?token=***&tracks=v1a1
```

### 2. Command Execution Guardrail (`GO2RTC_ALLOW_EXEC_STREAMS`)
`go2rtc` supports `exec:`, `echo:`, and `expr:` stream sources that execute shell commands on the host. By default (`GO2RTC_ALLOW_EXEC_STREAMS=false`), `go2rtc-mcp` rejects any `add_stream` or `update_stream` call containing `exec:`, `echo:`, or `expr:` (including chained forms like `ffmpeg:exec:...`) before any network request is made.

---

## Installation & Quick Start

### Prerequisites
- **Python** `>= 3.11`
- **[uv](https://docs.astral.sh/uv/)** package manager
- Access to a running `go2rtc` instance (standalone or Home Assistant port `1984`)

### 1. Clone and Install Dependencies
```powershell
git clone https://github.com/gaxkalik/go2rtc-mcp.git
cd go2rtc-mcp
uv sync
```

### 2. Configure Environment
Copy `.env.example` to `.env` and set your `go2rtc` server URL:
```powershell
Copy-Item .env.example .env
```

Edit `.env`:
```env
GO2RTC_URL=http://localhost:1984
GO2RTC_USERNAME=
GO2RTC_PASSWORD=
GO2RTC_TIMEOUT=15.0
GO2RTC_ALLOW_EXEC_STREAMS=false
```

### 3. Run the MCP Server
```powershell
# Run over stdio transport (default for MCP clients)
uv run go2rtc-mcp
```

To interactively test tools and resources in your browser using the official MCP Inspector:
```powershell
npx @modelcontextprotocol/inspector uv run go2rtc-mcp
```

---

## Configuration

`go2rtc-mcp` reads configuration from environment variables (and automatically loads a local `.env` file if present):

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `GO2RTC_URL` | `http://localhost:1984` | Base HTTP/HTTPS URL of your `go2rtc` server |
| `GO2RTC_USERNAME` | *(empty)* | Optional HTTP Basic Auth username if `go2rtc` API auth is enabled |
| `GO2RTC_PASSWORD` | *(empty)* | Optional HTTP Basic Auth password |
| `GO2RTC_TIMEOUT` | `15.0` | HTTP request timeout in seconds (increase if camera snapshots take longer) |
| `GO2RTC_ALLOW_EXEC_STREAMS` | `false` | Set to `true` only if you explicitly want to allow `exec:` / `echo:` / `expr:` streams |

---

## Connecting an MCP Client

### Claude Desktop / Cursor / Antigravity / Windsurf
Add the following entry to your MCP client configuration file (e.g., `claude_desktop_config.json` or `mcp_config.json`):

```json
{
  "mcpServers": {
    "go2rtc": {
      "command": "uv",
      "args": [
        "--directory",
        "C:/Users/Bart/go2rtc-mcp",
        "run",
        "go2rtc-mcp"
      ],
      "env": {
        "GO2RTC_URL": "http://localhost:1984",
        "GO2RTC_USERNAME": "",
        "GO2RTC_PASSWORD": "",
        "GO2RTC_TIMEOUT": "15.0",
        "GO2RTC_ALLOW_EXEC_STREAMS": "false"
      }
    }
  }
}
```

---

## Usage Guide

### Example Natural-Language Prompts
Once connected to an MCP client, you can ask your AI assistant:
- *"List all cameras configured on my go2rtc server and check which ones have active consumers."*
- *"Capture a live snapshot from `door_camera` and `garage_camera` and describe what you see."*
- *"Probe `door_camera` to check its video/audio codecs, resolution, and RTSP transport protocol."*
- *"Give me the WebRTC viewer URL, HLS `.m3u8` URL, and RTSP URL for `outside_camera`."*
- *"Discover any Home Assistant or ONVIF camera sources available to go2rtc."*
- *"Check the recent go2rtc server logs for any connection or decoding warnings."*

---

### MCP Tools Reference & Examples

#### 1. `get_server_info()`
Fetches `go2rtc` server metadata (`GET /api`).
- **Returns:**
  ```json
  {
    "config_path": "/config/go2rtc.yaml",
    "host": "localhost:1984",
    "revision": "b5948cf",
    "rtsp": {
      "default_query": "video&audio",
      "listen": ":554"
    },
    "version": "1.9.14"
  }
  ```

#### 2. `list_streams()`
Lists all configured and active streams (`GET /api/streams`) with producer credentials automatically masked.
- **Returns:**
  ```json
  {
    "door_camera": {
      "producers": [
        {
          "url": "rtsp://***:***@192.0.2.10:554/Streaming/Channels/101"
        }
      ],
      "consumers": null
    },
    "garage_camera": {
      "producers": [
        {
          "url": "rtsp://***:***@192.0.2.11:554/Streaming/Channels/101"
        }
      ],
      "consumers": null
    }
  }
  ```

#### 3. `get_stream_info(stream_name: str, probe: bool = False)`
Fetches producer and consumer state for a single camera stream (`GET /api/streams?src=<stream_name>`). Pass `probe=True` to actively query video/audio codecs and SDP tracks.

#### 4. `probe_stream(stream_name: str)`
Actively probes a stream (`GET /api/streams?src=<stream_name>&video=all&audio=all`) to inspect active codecs (H264, H265, AAC, PCMA, OPUS), SDP metadata, remote address, protocol (`rtsp+tcp`), and received bytes.

#### 5. `get_stream_snapshot(stream_name: str, width: int | None = None, height: int | None = None)`
Captures a live JPEG frame from `stream_name` (`GET /api/frame.jpeg?src=<stream_name>`) and returns it as a native MCP `Image` (`image/jpeg`) so multimodal LLMs can view the camera feed directly.
- **Arguments:**
  - `stream_name` *(required)*: Camera stream identifier (e.g., `"door_camera"`).
  - `width` *(optional)*: Target width in pixels (e.g., `1280`).
  - `height` *(optional)*: Target height in pixels (e.g., `720`).

#### 6. `get_stream_urls(stream_name: str)`
Generates ready-to-use playback and snapshot URLs for a stream based on the server's HTTP and RTSP listeners.
- **Returns:**
  ```json
  {
    "stream": "door_camera",
    "webrtc_viewer": "http://localhost:1984/stream.html?src=door_camera&mode=webrtc",
    "mse_viewer": "http://localhost:1984/stream.html?src=door_camera&mode=mse",
    "websocket_url": "ws://localhost:1984/api/ws?src=door_camera",
    "hls_m3u8": "http://localhost:1984/api/stream.m3u8?src=door_camera",
    "mp4_stream": "http://localhost:1984/api/stream.mp4?src=door_camera",
    "mjpeg_stream": "http://localhost:1984/api/stream.mjpeg?src=door_camera",
    "snapshot_jpeg": "http://localhost:1984/api/frame.jpeg?src=door_camera",
    "rtsp_url": "rtsp://localhost:554/door_camera"
  }
  ```

#### 7. `add_stream(stream_name: str, source_url: str)`
Dynamically registers or overwrites a stream (`PUT /api/streams?name=<stream_name>&src=<source_url>`). Validates `source_url` against `GO2RTC_ALLOW_EXEC_STREAMS` and redacts credentials in the confirmation payload.

#### 8. `update_stream(stream_name: str, source_url: str)`
Dynamically updates an existing stream (`PATCH /api/streams?name=<stream_name>&src=<source_url>`).

#### 9. `delete_stream(stream_name: str)`
Removes a dynamically registered stream (`DELETE /api/streams?src=<stream_name>`).

#### 10. `get_config()`
Retrieves the server's `go2rtc.yaml` configuration (`GET /api/config`) with all embedded credentials, passwords, and tokens redacted.

#### 11. `get_server_logs(limit: int = 50)`
Fetches the most recent `limit` structured log entries from `GET /api/log` with any embedded credentials masked.

#### 12. `discover_sources(provider: str = "hass")`
Queries a `go2rtc` discovery integration (`GET /api/<provider>`) to list discoverable cameras/streams with credentials redacted.
- **Supported providers:** `hass`, `onvif`, `dvrip`, `homekit`, `roborock`, `webtorrent`, `alsa`, `v4l2`.

---

### MCP Resources Reference

MCP clients that support resource URIs can read these resources directly:

| Resource URI | MIME Type | Description |
| :--- | :--- | :--- |
| `go2rtc://server/info` | `application/json` | Server version, revision, host, and RTSP listener config |
| `go2rtc://streams` | `application/json` | Complete dictionary of streams with redacted producer URLs |
| `go2rtc://streams/{stream_name}` | `application/json` | Producer and consumer details for `{stream_name}` |
| `go2rtc://config` | `text/yaml` | Sanitized `go2rtc.yaml` configuration file |

---

### MCP Prompts Reference

- **`diagnose_stream(stream_name: str)`**: Generates a structured troubleshooting workflow instructing the assistant to probe codecs/SDP, capture a verification snapshot, inspect recent server logs, and summarize stream health for `stream_name`.

---

### Programmatic Python Usage

You can also use `Go2RtcClient` and `redact_sensitive_data` directly in Python scripts:

```python
import asyncio
from go2rtc_mcp import Go2RtcClient, Go2RtcSettings, redact_sensitive_data


async def main() -> None:
    settings = Go2RtcSettings.from_env()
    client = Go2RtcClient(settings=settings)

    # 1. Server info
    info = await client.get_server_info()
    print("Server version:", info.get("version"))

    # 2. List streams (credentials automatically masked as scheme://***:***@host...)
    streams = await client.list_streams()
    for name, data in streams.items():
        print(f"Stream: {name} -> {data}")

    # 3. Capture a live JPEG snapshot
    jpeg_bytes = await client.get_snapshot("door_camera", width=1280)
    print(f"Captured {len(jpeg_bytes)} bytes from door_camera")

    # 4. Standalone sanitizer usage
    safe = redact_sensitive_data("rtsp://admin:mockpass%2A@192.0.2.10:554/stream1")
    assert safe == "rtsp://***:***@192.0.2.10:554/stream1"


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Project Structure

```text
go2rtc-mcp/
├── .env.example                 # Safe template for environment variables
├── .gitignore                   # Excludes .env, snapshots (*.jpg/*.png/*.mp4), and live dumps
├── LICENSE                      # MIT License
├── pyproject.toml               # Package metadata, dependencies, pytest & ruff config
├── README.md                    # Project documentation and usage guide
├── src/
│   └── go2rtc_mcp/
│       ├── __init__.py          # Public package exports
│       ├── client.py            # Async httpx Go2RtcClient with automatic redaction
│       ├── config.py            # Pydantic Go2RtcSettings & dotenv loader
│       ├── models.py            # Pydantic models for server & stream objects
│       ├── sanitizer.py         # Alias module re-exporting security redaction utilities
│       ├── security.py          # redact_sensitive_data, validate_stream_source, log filter
│       └── server.py            # MCPServer tools, resources, prompts, and CLI entry point
└── tests/
    ├── test_client.py           # respx unit tests for Go2RtcClient endpoints & error handling
    ├── test_security.py         # Unit tests for URI schemes, recursive redaction & exec policy
    └── test_server.py           # Unit tests for MCP tools, resources, snapshots & prompts
```

---

## Development & Testing

All unit tests use synthetic RFC 5737 (`192.0.2.0/24`) addresses and mock credentials via `respx` so tests run offline and deterministically.

```powershell
# Run the full test suite
uv run pytest -v

# Run ruff linter
uv run ruff check src/ tests/
```

---

## License

Released under the [MIT License](LICENSE).
