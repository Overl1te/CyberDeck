# CyberDeck Control

<div style='text-align: center'>

  <img src='icon.png' style='border-radius: 50%' width='400px' height='400px' />

  # CyberDeck Control

  <p>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License"></a>
    <a href="https://github.com/Overl1te/CyberDeck-Mobile"><img src="https://img.shields.io/badge/Mobile-CyberDeck--Mobile-00A7E1" alt="Mobile"></a>
    <a href="README_EN.md"><img src="https://img.shields.io/badge/lang-Russian-1f6feb" alt="Russian"></a>
  </p>

  Control your PC from a phone over local network: QR/PIN pairing, input control, screen stream, file transfer, and per-device permissions.

  [Features](#features) | [Usage flow](#usage-flow) | [Gestures](#basic-gestures) | [FAQ](#faq)

</div>


---

## Features

- Pair a device using PIN or QR.
- Control mouse, keyboard, and media keys remotely.
- Stream screen video (MJPEG / H.264 / H.265 depending on environment).
- Transfer files in both directions (phone <-> PC).
- Use system actions (power/volume).
- Manage runtime from launcher with status, devices, and QR.
- Configure granular permissions per device.

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
- API and endpoints;
- testing;
- build and packaging.

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
