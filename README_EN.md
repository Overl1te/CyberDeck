<p align="center">
  <img src="icon-qr-code.png" width="400" height="400" />
</p>

<h1 align="center">CyberDeck Control вЂ” Remote PC Management</h1>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License"></a>
  <a href="https://github.com/Overl1te/CyberDeck-Mobile"><img src="https://img.shields.io/badge/Mobile-CyberDeck--Mobile-00A7E1" alt="Mobile"></a>
  <a href="README.md"><img src="https://img.shields.io/badge/lang-Russian-1f6feb" alt="Russian"></a>
</p>

<p align="center">
  Control your PC from a phone over local network: QR/PIN pairing, input control, screen stream, file transfer, and per-device permissions.
</p>

<p align="center">
  <a href="#features">Features</a> вЂў
  <a href="#usage-flow">Usage flow</a> вЂў
  <a href="#basic-gestures">Gestures</a> вЂў
  <a href="#faq">FAQ</a>
</p>


<p align="center">
  <img src="https://repo-inspector.vercel.app/api?owner=Overl1te&repo=CyberDeck&kind=quality&format=svg&theme=midnight&locale=en&card_width=760&animate=true&animation=all&duration=1400" alt="CyberDeck quality card" />
</p>
<p align="center">
  <img src="https://repo-inspector.vercel.app/api?owner=Overl1te&repo=CyberDeck&kind=repo&format=svg&theme=midnight&locale=en&card_width=760&animate=true&animation=all&duration=1400&langs_count=4" alt="CyberDeck repository stats card" />
</p>

---

## Features

- Current release line:
  - `CyberDeck Server` / `Launcher`: `v1.3.2`
  - `CyberDeck-Mobile`: `1.1.2`
- Pair a device using PIN or QR.
- Control mouse, keyboard, and media keys remotely.
- Stream screen video (MJPEG / H.264 / H.265 depending on environment).
- Transfer files in both directions (phone <-> PC).
- Use system actions (power/volume).
- Manage runtime from launcher with status, devices, and QR.
- Configure granular permissions per device.

### Release update check

CyberDeck now provides a local release-status endpoint that queries latest GitHub tags:

- Source API (server/launcher): `https://api.github.com/repos/Overl1te/CyberDeck/releases/latest`
- Source API (mobile): `https://api.github.com/repos/Overl1te/CyberDeck-Mobile/releases/latest`
- Local endpoint: `GET /api/local/updates` (localhost-only)

The launcher polls this endpoint and shows update status in Home screen.

### Device permissions

- `perm_mouse` - mouse input.
- `perm_keyboard` - keyboard/text input.
- `perm_stream` - video stream access.
- `perm_upload` - upload files to PC.
- `perm_file_send` - send files from PC to device.
- `perm_power` - system actions (power/volume).

---

## Usage flow

1. Start CyberDeck on your PC.
2. Open mobile client: <https://github.com/Overl1te/CyberDeck-Mobile>.
3. Pair using QR or enter IP/port/PIN manually.
4. Select the device and start controlling the PC.

---

## Basic gestures

| Gesture | Action |
|---|---|
| 1 finger move | Cursor move |
| 1 finger tap | Left click |
| 2 fingers move | Scroll |
| 2 fingers tap | Right click |
| Hold + move | Drag and drop |

---

## Platforms

- Windows / Linux / macOS.
- Available codecs and video backends depend on OS/runtime capabilities.

---

## Technical documentation

`README_EN.md` contains product features and user usage only.

All technical details are in `CONTRIBUTING_EN.md`:

- setup from source;
- run modes;
- current package layout (`cyberdeck/api`, `cyberdeck/video`, `cyberdeck/ws`, `cyberdeck/launcher`, `cyberdeck/input`, `cyberdeck/platform`);
- dependency split (`requirements-core.txt`, `requirements-desktop-input.txt`);
- API and endpoints;
- testing;
- build and packaging.

Additional practical guides:

- Docker runtime: `docs/DOCKER.md`
- Stream/audio/pairing troubleshooting: `docs/STREAMING_TROUBLESHOOTING.md`

---

## FAQ

**Q: Device cannot connect.**  
A: Verify PC and phone are on the same network, and check IP/port/PIN values.

**Q: Can I limit what a specific device can do?**  
A: Yes, each device has independent `perm_*` permissions.

**Q: Why does stream quality/type differ across OSes?**  
A: Streaming path depends on system backends and codec availability.

---

**License:** GNU GPLv3 (`LICENSE`)  
**Author:** Overl1te - <https://github.com/Overl1te>


