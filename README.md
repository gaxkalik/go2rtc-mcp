# go2rtc-mcp

A production-grade **Model Context Protocol (MCP)** server for [go2rtc](https://github.com/AlexxIT/go2rtc), enabling AI assistants and agents to safely inspect camera streams, probe video/audio codecs, capture live JPEG snapshots, retrieve playback URLs (WebRTC, MSE, HLS, MP4, MJPEG, RTSP), and manage streams.

## Security & Credential Redaction

`go2rtc` `/api/streams` and `/api/config` responses often contain plaintext or URL-encoded camera credentials (e.g., `rtsp://admin:mockpass%2A@192.0.2.10:554/stream1`) or authentication query tokens.

`go2rtc-mcp` enforces defense-in-depth security guardrails:
1. **Centralized Recursive Credential Sanitizer (`redact_sensitive_data`)**: Every tool, resource, log record, and client error automatically masks credentials across all URI schemes (`rtsp://`, `rtsps://`, `http://`, `https://`, `rtmp://`, `onvif://`, `dvrip://`, etc.) into `scheme://***:***@host...` and masks query tokens (`?token=***`) and YAML secret fields before returning data to the LLM or logging.
2. **Command Execution Guardrail (`GO2RTC_ALLOW_EXEC_STREAMS`)**: Blocks dynamic creation or modification of `exec:`, `echo:`, and `expr:` stream sources by default (`GO2RTC_ALLOW_EXEC_STREAMS=false`) to prevent arbitrary command execution.

## Features

### MCP Tools
| Tool | Description |
| --- | --- |
| `get_server_info` | Fetch `go2rtc` version, revision, host, RTSP listener port, and config path (`GET /api`). |
| `list_streams` | List all configured and active streams with producer credentials redacted (`GET /api/streams`). |
| `get_stream_info` | Get producer/consumer details for a single stream, with optional codec probing (`GET /api/streams?src=...`). |
| `probe_stream` | Actively probe a stream's video/audio codecs, SDP, and media track counters. |
| `get_stream_snapshot` | Capture a live JPEG frame from a camera stream (`GET /api/frame.jpeg`) as an MCP `Image`. |
| `get_stream_urls` | Generate WebRTC, MSE, WebSocket, HLS (`.m3u8`), MP4, MJPEG, JPEG snapshot, and RTSP URLs. |
| `add_stream` | Dynamically add a stream (`PUT /api/streams`) with `exec:` policy validation and credential redaction. |
| `update_stream` | Dynamically update an existing stream (`PATCH /api/streams`). |
| `delete_stream` | Remove a stream (`DELETE /api/streams?src=...`). |
| `get_config` | Retrieve sanitized `go2rtc.yaml` configuration (`GET /api/config`). |
| `get_server_logs` | Retrieve recent `go2rtc` server log entries (`GET /api/log`) with credentials redacted. |
| `discover_sources` | Discover sources from integrations (`hass`, `onvif`, `dvrip`, `homekit`, `roborock`, `webtorrent`). |

### MCP Resources
- `go2rtc://server/info` — Redacted server metadata (`application/json`)
- `go2rtc://streams` — All configured streams with redacted URLs (`application/json`)
- `go2rtc://streams/{stream_name}` — Single stream detail (`application/json`)
- `go2rtc://config` — Sanitized `go2rtc.yaml` (`text/yaml`)

### MCP Prompts
- `diagnose_stream(stream_name)` — Guided workflow to probe codecs, capture a test snapshot, and inspect server logs for a stream.

## Installation & Configuration

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

### Setup
```powershell
git clone <repository-url>
cd go2rtc-mcp
uv sync
Copy-Item .env.example .env
```

### Environment Variables
| Variable | Default | Description |
| --- | --- | --- |
| `GO2RTC_URL` | `http://localhost:1984` | Base URL of your `go2rtc` instance |
| `GO2RTC_USERNAME` | *(empty)* | Optional HTTP Basic Auth username |
| `GO2RTC_PASSWORD` | *(empty)* | Optional HTTP Basic Auth password |
| `GO2RTC_TIMEOUT` | `15.0` | HTTP request timeout in seconds |
| `GO2RTC_ALLOW_EXEC_STREAMS` | `false` | Allow `exec:` / `echo:` / `expr:` stream sources |

### Running the Server
```powershell
uv run go2rtc-mcp
```

### Claude Desktop / MCP Client Configuration
```json
{
  "mcpServers": {
    "go2rtc": {
      "command": "uv",
      "args": ["--directory", "C:/path/to/go2rtc-mcp", "run", "go2rtc-mcp"],
      "env": {
        "GO2RTC_URL": "http://localhost:1984",
        "GO2RTC_ALLOW_EXEC_STREAMS": "false"
      }
    }
  }
}
```

## Development & Testing

```powershell
# Run unit tests
uv run pytest -v

# Run linter
uv run ruff check src/ tests/
```

## License

MIT
