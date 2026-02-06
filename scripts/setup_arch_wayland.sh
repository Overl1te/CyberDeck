#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
UINPUT_RULE_FILE="/etc/udev/rules.d/99-cyberdeck-uinput.rules"
UINPUT_MODULE_FILE="/etc/modules-load.d/uinput.conf"
TARGET_USER="${SUDO_USER:-${USER:-}}"

if [[ -z "${TARGET_USER}" ]]; then
  echo "[ERR] Could not detect target user."
  exit 1
fi

if [[ "${EUID}" -eq 0 ]]; then
  echo "[ERR] Run this script as your regular user, not root."
  echo "      It will use sudo only where needed."
  exit 1
fi

if ! command -v pacman >/dev/null 2>&1; then
  echo "[ERR] This script is for Arch Linux (pacman is required)."
  exit 1
fi

echo "[1/7] Installing required system packages from official repos..."
sudo pacman -Sy --needed --noconfirm \
  python \
  python-pip \
  tk \
  pipewire \
  wireplumber \
  xdg-desktop-portal \
  xdg-desktop-portal-gtk \
  ffmpeg \
  gstreamer \
  gst-plugin-pipewire \
  gst-plugins-base \
  gst-plugins-good

echo "[2/7] Checking stream backends for Wayland..."
FFMPEG_PIPEWIRE_OK=0
GST_PIPEWIRE_OK=0
if ffmpeg -hide_banner -formats 2>/dev/null | grep -qi 'pipewire'; then
  FFMPEG_PIPEWIRE_OK=1
  echo "      OK: ffmpeg supports pipewire."
else
  echo "      WARN: ffmpeg has no pipewire input."
fi
if gst-inspect-1.0 pipewiresrc >/dev/null 2>&1; then
  GST_PIPEWIRE_OK=1
  echo "      OK: GStreamer pipewiresrc is available."
else
  echo "      WARN: GStreamer pipewiresrc is unavailable."
fi

if [[ "${FFMPEG_PIPEWIRE_OK}" -ne 1 && "${GST_PIPEWIRE_OK}" -ne 1 ]]; then
  if [[ "${CYBERDECK_INSTALL_FFMPEG_FULL:-0}" == "1" ]]; then
    echo "      Trying optional AUR install: ffmpeg-full (can take a long time)..."
    if command -v yay >/dev/null 2>&1; then
      yay -S --needed --noconfirm ffmpeg-full
    elif command -v paru >/dev/null 2>&1; then
      paru -S --needed --noconfirm ffmpeg-full
    else
      echo "      No AUR helper found (yay/paru)."
    fi
  fi
fi

echo "[3/7] Verifying Wayland stream backend..."
FFMPEG_PIPEWIRE_OK=0
GST_PIPEWIRE_OK=0
if ffmpeg -hide_banner -formats 2>/dev/null | grep -qi 'pipewire'; then
  FFMPEG_PIPEWIRE_OK=1
fi
if gst-inspect-1.0 pipewiresrc >/dev/null 2>&1; then
  GST_PIPEWIRE_OK=1
fi
if [[ "${FFMPEG_PIPEWIRE_OK}" -eq 1 || "${GST_PIPEWIRE_OK}" -eq 1 ]]; then
  echo "      OK: Wayland stream backend is available."
else
  echo "[ERR] No working Wayland stream backend found."
  echo "      Need one of:"
  echo "      - ffmpeg with pipewire input"
  echo "      - GStreamer with pipewiresrc plugin"
  exit 1
fi

echo "[4/7] Enabling uinput (for keyboard/mouse control on Wayland)..."
echo "uinput" | sudo tee "${UINPUT_MODULE_FILE}" >/dev/null
sudo modprobe uinput || true
sudo groupadd -f input
sudo usermod -aG input "${TARGET_USER}"
cat <<'EOF' | sudo tee "${UINPUT_RULE_FILE}" >/dev/null
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "[5/7] Preparing Python virtual environment..."
cd "${REPO_ROOT}"
python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt

echo "[6/7] Runtime checks..."
if [[ -e /dev/uinput ]]; then
  ls -l /dev/uinput || true
else
  echo "      WARN: /dev/uinput does not exist right now."
fi
ffmpeg -hide_banner -formats 2>/dev/null | grep -i 'pipewire' || true
gst-inspect-1.0 pipewiresrc >/dev/null 2>&1 && echo "gstreamer: pipewiresrc OK" || true

echo "[7/7] Done."
echo
echo "Next steps:"
echo "  1) Log out and log back in (or reboot) to apply new group membership (input)."
echo "  2) Run server as regular user (NOT sudo):"
echo "       cd ${REPO_ROOT}"
echo "       source .venv/bin/activate"
echo "       CYBERDECK_DEBUG=1 CYBERDECK_LOG=1 python launcher.py"
echo
echo "Quick video test:"
echo "       ffmpeg -f pipewire -i default -frames:v 1 /tmp/pw-test.jpg"
