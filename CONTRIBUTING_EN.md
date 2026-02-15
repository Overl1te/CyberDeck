# Contributing to CyberDeck

<p align="left">
  <a href="CONTRIBUTING.md">Russian version</a> •
  <a href="README_EN.md">README</a> •
  <a href="CODE_OF_CONDUCT_EN.md">Code of Conduct</a> •
  <a href="SECURITY_EN.md">Security</a>
</p>

This document explains project architecture and contribution workflow to keep changes predictable, testable, and secure.

## Principles

- Changes must be reproducible and covered by tests.
- Security beats convenience hacks.
- Prefer modular changes over monolithic edits.
- Documentation and code should evolve together.

## Tech stack

- Python 3.11+
- FastAPI + Uvicorn
- CustomTkinter (launcher UI)
- WebSocket for live input
- Pillow / qrcode / mss for graphics and streaming
- unittest + pytest (selected scenarios)

## Project map

| Path | Purpose |
|---|---|
| `launcher.py` | Launcher orchestration: UI, server lifecycle, tray, QR, settings |
| `cyberdeck/launcher_ui_home.py` | Home view |
| `cyberdeck/launcher_ui_devices.py` | Devices view, permissions, transfer presets |
| `cyberdeck/launcher_ui_settings.py` | Settings view, app config, TLS, runtime params |
| `main.py` | Server entry point |
| `cyberdeck/server.py` | FastAPI app composition and router wiring |
| `cyberdeck/api_core.py` | Public API (handshake/upload/protocol/stats) |
| `cyberdeck/api_local.py` | Local launcher API (`/api/local/*`) |
| `cyberdeck/api_system.py` | System actions and volume control |
| `cyberdeck/ws_mouse.py` | Input WebSocket channel |
| `cyberdeck/video.py` | Streaming endpoints and backend adaptation |
| `cyberdeck/transfer.py` | Host-to-device file transfer |
| `cyberdeck/sessions.py` | Session persistence, TTL, cleanup |
| `tests/` | Unit/behavioral test suite |

## Workflow

1. Branch from `main`.
2. Implement a minimal coherent change set.
3. Add or update tests.
4. Update docs when behavior changes.
5. Open PR with clear rationale and validation.

Suggested branch naming:

- `feat/<short-name>`
- `fix/<short-name>`
- `refactor/<short-name>`
- `docs/<short-name>`

## Local development

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements-dev.txt
```

## Setup and run from source

Base setup:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Run application (launcher):

```bash
python launcher.py
```

Run server only:

```bash
python main.py
```

## API (technical)

Public endpoints:

- `POST /api/handshake` - PIN handshake.
- `GET /api/stats` - server stats.
- `POST /api/file/upload` - upload file to host.
- `WS /ws/mouse` - remote input channel.
- `GET /video_feed` - MJPEG stream.
- `GET /video_h264` - H.264 stream.
- `GET /video_h265` - H.265 stream.
- `GET /api/stream_offer` - transport/codec fallback hints.
- `POST /system/*` and `POST /volume/{up|down|mute}` - system actions.

Local endpoints (`127.0.0.1` only):

- `GET /api/local/info`
- `GET /api/local/stats`
- `GET|POST /api/local/device_settings`
- `POST /api/local/device_disconnect`
- `POST /api/local/device_delete`
- `POST /api/local/regenerate_code`
- `POST /api/local/trigger_file`

## Testing

Full run:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Focused run:

```bash
pytest -q tests/test_launcher_ui_logic.py
```

Docker run:

```bash
docker compose -f docker-compose.tests.yml build
docker compose -f docker-compose.tests.yml run --rm tests
```

## Build

Windows (Nuitka):

```powershell
pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_nuitka.ps1
```

Linux (Arch helper script):

```bash
bash ./scripts/build_arch_linux.sh
```

## Code standards

- Use explicit naming and short cohesive functions.
- Avoid hidden global state.
- Add concise comments only where intent is non-obvious.
- Permission checks must stay centralized and testable.
- Prefer dependency injection over hardcoded dependencies in refactors.

## Device permissions

Per-device permissions supported by the server:

- `perm_mouse`
- `perm_keyboard`
- `perm_upload`
- `perm_file_send`
- `perm_stream`
- `perm_power`

Any permission-related change must include:

1. API/WS enforcement check.
2. Negative test (denied path).
3. Positive test (allowed path).

## Configuration

- `launcher_settings.json` - launcher settings and part of server runtime.
- `cyberdeck_app_config.json` - dedicated app config (not `.env`).
- `cyberdeck_sessions.json` - persisted device sessions.

When config format changes:

- preserve backward compatibility;
- provide sane defaults;
- document new fields.

## PR checklist

- [ ] Change solves a concrete problem and does not regress existing behavior.
- [ ] Tests were added/updated.
- [ ] `README*`/`CONTRIBUTING*` updated when UX/API changed.
- [ ] Edge cases were validated (offline, invalid input, permission denied).
- [ ] No temporary debug code/log spam left.

## Reporting

For bugs/features, use Issues:

- <https://github.com/Overl1te/CyberDeck/issues>

For security topics:

- `SECURITY_EN.md`

For support topics:

- `SUPPORT_EN.md`
