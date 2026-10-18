# go2rtc-mcp

[![PyPI version](https://img.shields.io/pypi/v/go2rtc-mcp.svg)](https://pypi.org/project/go2rtc-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/go2rtc-mcp.svg)](https://pypi.org/project/go2rtc-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A production-grade **Model Context Protocol (MCP)** server for [go2rtc](https://github.com/AlexxIT/go2rtc) (including Home Assistant's built-in `go2rtc` service). Designed primarily for **Linux** environments (Home Assistant Supervised/OS, Debian/Ubuntu, Docker, and headless media servers), `go2rtc-mcp` enables AI assistants and MCP clients to inspect camera streams, probe video/audio codecs, capture live JPEG snapshots, generate streaming playback URLs (WebRTC, MSE, HLS, MP4, MJPEG, RTSP), discover camera integrations, and manage streams dynamically—with **strict, automated credential redaction**.

---

## Table of Contents

- [Architecture & Security Guardrails](#architecture--security-guardrails)
- [Linux Installation & Quick Start](#linux-installation--quick-start)
- [Configuration](#configuration)
- [MCP Client Configuration (Linux, macOS, Windows)](#mcp-client-configuration-linux-macos-windows)
- [Running as a Systemd Service (Linux)](#running-as-a-systemd-service-linux)
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

Live `go2rtc` API endpoints (`/api/streams`, `/api/config`, `/api/hass`, `/api/log`) regularly return plaintext or URL-encoded camera credentials and authentication tokens in RTSP producer URLs. `go2rtc-mcp` enforces defense-in-depth security:

### 1. Centralized Recursive Credential Redaction (`redact_sensitive_data`)
Every MCP tool return value, MCP resource response, client error message, and log record passes through [`redact_sensitive_data`](src/go2rtc_mcp/security.py):
- **Universal URI Credential Masking**: Masks credentials in any URI scheme (`rtsp://`, `rtsps://`, `http://`, `https://`, `rtmp://`, `onvif://`, `dvrip://`, including chained prefixes like `ffmpeg:rtsp://...`).
- **Query Parameter Token Masking**: Masks sensitive query parameters (`token`, `access_token`, `auth`, `password`, `pass`, `pwd`, `secret`, `api_key`, `jwt`).
- **Recursive Dict Key & Value Sanitization**: Sanitizes both dictionary keys and values (crucial because `go2rtc` creates dynamic stream keys named after raw RTSP URLs), lists, tuples, sets, Pydantic models, and multiline YAML text.
- **Log Stream Redaction**: Attaches `RedactingLoggingFilter` to `httpx`, `httpcore`, `mcp`, and `go2rtc_mcp` loggers so credentials never reach `stdout`/`stderr` or `journald`.

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
`go2rtc` allows stream sources starting with `exec:`, `echo:`, and `expr:` to execute host shell commands. By default (`GO2RTC_ALLOW_EXEC_STREAMS=false`), `go2rtc-mcp` rejects any `add_stream` or `update_stream` request containing `exec:`, `echo:`, or `expr:` (including chained forms like `ffmpeg:exec:...`) before any network request is issued.

---

## Linux Installation & Quick Start

### Prerequisites
- **Linux** (Debian, Ubuntu, Alpine, Arch, Fedora, Raspberry Pi OS, etc.)
- **Python** `>= 3.11`
- **[uv](https://docs.astral.sh/uv/)** package manager (recommended: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
### Instant Run with uvx (No Clone Required)
Run `go2rtc-mcp` directly using `uvx` from [PyPI](https://pypi.org/project/go2rtc-mcp/):
```bash
# Run over stdio
GO2RTC_URL=http://localhost:1984 uvx go2rtc-mcp
```

---

### Manual Installation from Source

#### 1. Clone the Repository
```bash
git clone https://github.com/gaxkalik/go2rtc-mcp.git
cd go2rtc-mcp
```

### 2. Install Dependencies with `uv`
```bash
uv sync
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` using your preferred editor (`nano .env` or `vim .env`):
```env
GO2RTC_URL=http://localhost:1984
GO2RTC_USERNAME=
GO2RTC_PASSWORD=
GO2RTC_TIMEOUT=15.0
GO2RTC_ALLOW_EXEC_STREAMS=false
```

### 4. Run and Test the MCP Server
Run over `stdio` transport (standard for MCP clients):
```bash
uv run go2rtc-mcp
```

Or test interactively in your browser with the official MCP Inspector:
```bash
npx @modelcontextprotocol/inspector uv run go2rtc-mcp
```

---

## Configuration

`go2rtc-mcp` loads settings from environment variables (and automatically reads a local `.env` file if present):

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `GO2RTC_URL` | `http://localhost:1984` | Base HTTP/HTTPS URL of your `go2rtc` server |
| `GO2RTC_USERNAME` | *(empty)* | Optional HTTP Basic Auth username |
| `GO2RTC_PASSWORD` | *(empty)* | Optional HTTP Basic Auth password |
| `GO2RTC_TIMEOUT` | `15.0` | Request timeout in seconds |
| `GO2RTC_ALLOW_EXEC_STREAMS` | `false` | Set to `true` only if you explicitly allow `exec:` / `echo:` / `expr:` sources |

---

## MCP Client Configuration (Linux, macOS, Windows)

### Linux (`~/.config/Claude/claude_desktop_config.json` or `~/.gemini/config/mcp_config.json`)
```json
{
  "mcpServers": {
    "go2rtc": {
      "command": "uv",
      "args": [
        "--directory",
        "/home/user/go2rtc-mcp",
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

> **Note**: Adjust `/home/user/go2rtc-mcp` (or `/config/go2rtc-mcp` on Home Assistant) to your actual installation path. Ensure `uv` is in your system `PATH` (e.g. `/home/user/.cargo/bin/uv` or `/usr/local/bin/uv`).

### macOS (`~/Library/Application Support/Claude/claude_desktop_config.json`)
Replace the directory path with `/Users/username/go2rtc-mcp`.

### Windows (`%APPDATA%\Claude\claude_desktop_config.json`)
Replace the directory path with `C:/Users/username/go2rtc-mcp`.

---

## Running as a Systemd Service (Linux)

If you wish to run `go2rtc-mcp` as a persistent background daemon or manage it through Linux `systemctl`:

Create `/etc/systemd/system/go2rtc-mcp.service`:
```ini
[Unit]
Description=go2rtc Model Context Protocol Server
After=network.target

[Service]
Type=simple
User=user
WorkingDirectory=/home/user/go2rtc-mcp
EnvironmentFile=/home/user/go2rtc-mcp/.env
ExecStart=/home/user/.cargo/bin/uv run go2rtc-mcp
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now go2rtc-mcp
sudo systemctl status go2rtc-mcp
```

---

## Usage Guide

### Example Natural-Language Prompts
Ask your AI assistant:
- *"List all cameras configured on my go2rtc server."*
- *"Take a snapshot of `door_camera` and describe the current scene."*
- *"Perform a security patrol across all active cameras."*
- *"Probe `garage_camera` codecs, resolution, and RTSP protocol."*
- *"Generate WebRTC viewer, HLS (.m3u8), and RTSP playback links for `outside_camera`."*
- *"Check recent go2rtc logs for connection errors or offline feeds."*

---

### MCP Tools Reference & Examples

#### 1. `get_server_info()`
Fetches `go2rtc` version, revision, host, and RTSP port (`GET /api`).
- **Sample Output:**
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
Lists all configured and active streams (`GET /api/streams`) with credentials automatically masked.
- **Sample Output:**
  ```json
  {
    "door_camera": {
      "producers": [
        {
          "url": "rtsp://***:***@192.0.2.10:554/Streaming/Channels/101"
        }
      ],
      "consumers": []
    },
    "garage_camera": {
      "producers": [
        {
          "url": "rtsp://***:***@192.0.2.11:554/Streaming/Channels/101"
        }
      ],
      "consumers": []
    }
  }
  ```

#### 3. `get_stream_info(stream_name: str, probe: bool = False)`
Fetches producer and consumer state for a specific camera (`GET /api/streams?src=<stream_name>`). Pass `probe=True` to query live codecs and SDP.

#### 4. `probe_stream(stream_name: str)`
Actively queries `GET /api/streams?src=<stream_name>&video=all&audio=all` to inspect active codecs (H.264, H.265, AAC, PCMA, Opus), SDP tracks, protocol (`rtsp+tcp`), and byte counters.

#### 5. `get_stream_snapshot(stream_name: str, width: int | None = None, height: int | None = None)`
Captures a live JPEG frame from `stream_name` (`GET /api/frame.jpeg?src=<stream_name>`) and returns it as a native MCP `Image` (`image/jpeg`) for multimodal vision models.

#### 6. `get_stream_urls(stream_name: str)`
Generates ready-to-use streaming URLs for web, mobile, and NVR playback:
- **Sample Output:**
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
Dynamically registers or updates a stream (`PUT /api/streams?name=<name>&src=<url>`), validating against `GO2RTC_ALLOW_EXEC_STREAMS`.

#### 8. `update_stream(stream_name: str, source_url: str)`
Dynamically updates an existing stream source (`PATCH /api/streams`).

#### 9. `delete_stream(stream_name: str)`
Removes a dynamically registered stream (`DELETE /api/streams?src=<name>`).

#### 10. `get_config()`
Retrieves sanitized `go2rtc.yaml` configuration (`GET /api/config`) with all secrets masked.

#### 11. `get_server_logs(limit: int = 50)`
Fetches recent `go2rtc` log entries (`GET /api/log`) with credentials redacted.

#### 12. `discover_sources(provider: str = "hass")`
Discovers stream sources from integrations (`hass`, `onvif`, `dvrip`, `homekit`, `roborock`, `webtorrent`).

---

### MCP Resources Reference

| Resource URI | MIME Type | Description |
| :--- | :--- | :--- |
| `go2rtc://server/info` | `application/json` | Server version, revision, host, and RTSP listener config |
| `go2rtc://streams` | `application/json` | Complete dictionary of streams with redacted producer URLs |
| `go2rtc://streams/{stream_name}` | `application/json` | Producer and consumer details for `{stream_name}` |
| `go2rtc://config` | `text/yaml` | Sanitized `go2rtc.yaml` configuration |

---

### MCP Prompts Reference

- **`snapshot_all`**: Captures live frames from all cameras and generates a multi-camera visual security summary.
- **`security_patrol`**: Full security assessment combining stream health, frame capture, and log error analysis.
- **`diagnose_stream(stream_name)`**: Guided step-by-step diagnostic workflow for troubleshooting a camera.
- **`camera_urls(stream_name)`**: Formats all direct streaming integration links.
- **`stream_health_check`**: System-wide health audit of all streams, codecs, and logs.

---

### Programmatic Python Usage

```python
import asyncio
from go2rtc_mcp import Go2RtcClient, Go2RtcSettings, redact_sensitive_data


async def main() -> None:
    settings = Go2RtcSettings.from_env()
    client = Go2RtcClient(settings=settings)

    # 1. Fetch server metadata
    info = await client.get_server_info()
    print("Server version:", info.get("version"))

    # 2. List streams (credentials automatically masked)
    streams = await client.list_streams()
    for name, data in streams.items():
        print(f"Stream: {name} -> {data}")

    # 3. Capture a live JPEG snapshot
    jpeg_bytes = await client.get_snapshot("door_camera", width=1280)
    with open("door_snapshot.jpg", "wb") as f:
        f.write(jpeg_bytes)
    print("Saved door_snapshot.jpg")


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
├── README.md                    # Project documentation and Linux usage guide
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

All unit tests use synthetic RFC 5737 (`192.0.2.0/24`) test fixtures and mock responses via `respx` so tests run offline and deterministically on Linux:

```bash
# Run unit tests
uv run python -m pytest -v

# Run ruff linter
uv run ruff check src/ tests/
```

---

## License

Released under the [MIT License](LICENSE).
