#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
UINPUT_RULE_FILE="/etc/udev/rules.d/99-cyberdeck-uinput.rules"
UINPUT_MODULE_FILE="/etc/modules-load.d/uinput.conf"
TARGET_USER="${SUDO_USER:-${USER:-}}"
TARGET_HOME="${HOME}"

if [[ -n "${TARGET_USER}" ]]; then
  TARGET_HOME="$(getent passwd "${TARGET_USER}" | cut -d: -f6 || true)"
  TARGET_HOME="${TARGET_HOME:-$HOME}"
fi

if [[ -z "${TARGET_USER}" ]]; then
  echo "[ERR] Could not detect target user."
  exit 1
fi

if [[ "${EUID}" -eq 0 ]]; then
  echo "[ERR] Run this script as your regular user, not root."
  echo "      It will use sudo only where needed."
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "[ERR] This script is for Debian/Ubuntu (apt-get is required)."
  exit 1
fi

install_if_present() {
  local pkg="$1"
  if apt-cache show "${pkg}" >/dev/null 2>&1; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${pkg}"
    return 0
  fi
  return 1
}

echo "[1/10] Installing required system packages..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  python3-tk \
  wtype \
  wl-clipboard \
  pipewire \
  wireplumber \
  xdg-desktop-portal \
  xdg-desktop-portal-gtk \
  ffmpeg \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  libglib2.0-bin

echo "[2/10] Installing optional Wayland capture helpers (if available)..."
install_if_present gstreamer1.0-pipewire || true
install_if_present xdg-desktop-portal-gnome || true
install_if_present xdg-desktop-portal-kde || true
install_if_present xdg-desktop-portal-wlr || true
install_if_present gnome-screenshot || true
install_if_present grim || true

echo "[3/10] Ensuring user-level media/portal services are running..."
if command -v systemctl >/dev/null 2>&1; then
  USER_UID="$(id -u "${TARGET_USER}")"
  USER_ENV=(env "XDG_RUNTIME_DIR=/run/user/${USER_UID}")
  for svc in \
    pipewire \
    wireplumber \
    xdg-desktop-portal \
    xdg-desktop-portal-gnome \
    xdg-desktop-portal-gtk \
    xdg-desktop-portal-kde \
    xdg-desktop-portal-wlr
  do
    sudo -u "${TARGET_USER}" "${USER_ENV[@]}" systemctl --user enable --now "${svc}" >/dev/null 2>&1 || true
  done
fi

echo "[4/10] Checking stream backends for Wayland..."
FFMPEG_PIPEWIRE_OK=0
FFMPEG_X11_OK=0
GST_PIPEWIRE_OK=0
if ffmpeg -hide_banner -formats 2>/dev/null | grep -qi 'pipewire'; then
  FFMPEG_PIPEWIRE_OK=1
  echo "      OK: ffmpeg supports pipewire."
else
  echo "      WARN: ffmpeg has no pipewire input."
fi
if ffmpeg -hide_banner -formats 2>/dev/null | grep -qi 'x11grab'; then
  FFMPEG_X11_OK=1
  echo "      OK: ffmpeg supports x11grab fallback."
else
  echo "      WARN: ffmpeg has no x11grab input."
fi
if gst-inspect-1.0 pipewiresrc >/dev/null 2>&1; then
  GST_PIPEWIRE_OK=1
  echo "      OK: GStreamer pipewiresrc is available."
else
  echo "      WARN: GStreamer pipewiresrc is unavailable."
fi

echo "[5/10] Enabling uinput (for keyboard/mouse control on Wayland)..."
sudo groupadd -f input
sudo usermod -aG input "${TARGET_USER}"
cat <<'EOF' | sudo tee "${UINPUT_RULE_FILE}" >/dev/null
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
EOF
echo "uinput" | sudo tee "${UINPUT_MODULE_FILE}" >/dev/null
sudo udevadm control --reload-rules
sudo modprobe -r uinput >/dev/null 2>&1 || true
sudo modprobe uinput || true
sudo udevadm trigger --subsystem-match=misc --action=add || true
if [[ -e /dev/uinput ]]; then
  sudo chgrp input /dev/uinput || true
  sudo chmod 0660 /dev/uinput || true
fi

echo "[6/10] Preparing Python virtual environment..."
cd "${REPO_ROOT}"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt

echo "[7/10] Runtime checks..."
if [[ -e /dev/uinput ]]; then
  ls -l /dev/uinput || true
else
  echo "      WARN: /dev/uinput does not exist right now."
fi
ffmpeg -hide_banner -formats 2>/dev/null | grep -i 'pipewire' || true
gst-inspect-1.0 pipewiresrc >/dev/null 2>&1 && echo "gstreamer: pipewiresrc OK" || true

echo "[8/10] Smoke tests (stream + screenshot fallback)..."
GST_CAPTURE_OK=0
SHOT_OK=0
SHOT_TOOL=""
if command -v timeout >/dev/null 2>&1 && command -v gst-launch-1.0 >/dev/null 2>&1; then
  if timeout 8s gst-launch-1.0 -q pipewiresrc num-buffers=1 do-timestamp=true ! videoconvert ! jpegenc quality=50 ! fakesink sync=false >/dev/null 2>&1; then
    GST_CAPTURE_OK=1
    echo "      OK: gstreamer capture test passed."
  else
    echo "      WARN: gstreamer capture smoke test failed."
  fi
fi
TMP_SHOT="$(mktemp /tmp/cyberdeck-shot-XXXXXX.png)"
if command -v gdbus >/dev/null 2>&1; then
  DBUS_OUT="$(gdbus call --session \
    --dest org.gnome.Shell.Screenshot \
    --object-path /org/gnome/Shell/Screenshot \
    --method org.gnome.Shell.Screenshot.Screenshot \
    false false "" 2>/dev/null || true)"
  DBUS_PATH="$(printf '%s' "${DBUS_OUT}" | sed -n "s/.*'\(\/[^']*\.\(png\|jpg\|jpeg\)\)'.*/\1/p" | head -n1)"
  if [[ -n "${DBUS_PATH}" && -s "${DBUS_PATH}" ]]; then
    SHOT_OK=1
    SHOT_TOOL="gdbus_gnome_shell"
    echo "      OK: gdbus gnome-shell screenshot test passed."
  fi
fi
if [[ "${SHOT_OK}" -ne 1 ]] && command -v grim >/dev/null 2>&1; then
  if grim "${TMP_SHOT}" >/dev/null 2>&1 && [[ -s "${TMP_SHOT}" ]]; then
    SHOT_OK=1
    SHOT_TOOL="grim"
    echo "      OK: grim test passed."
  fi
fi
if [[ "${SHOT_OK}" -ne 1 ]] && command -v gnome-screenshot >/dev/null 2>&1; then
  if gnome-screenshot -f "${TMP_SHOT}" >/dev/null 2>&1 && [[ -s "${TMP_SHOT}" ]]; then
    SHOT_OK=1
    SHOT_TOOL="gnome-screenshot"
    echo "      OK: gnome-screenshot test passed."
  fi
fi
rm -f "${TMP_SHOT}" >/dev/null 2>&1 || true
if [[ "${SHOT_OK}" -ne 1 ]]; then
  echo "      WARN: screenshot fallback test failed."
fi

echo "[9/10] Writing automatic backend policy..."
ORDER="ffmpeg,gstreamer,screenshot,native"
if [[ "${FFMPEG_PIPEWIRE_OK}" -eq 1 ]]; then
  ORDER="ffmpeg,gstreamer,screenshot,native"
elif [[ "${FFMPEG_X11_OK}" -eq 1 && -n "${DISPLAY:-}" ]]; then
  if [[ "${GST_CAPTURE_OK}" -eq 1 ]]; then
    ORDER="gstreamer,ffmpeg,screenshot,native"
  elif [[ "${SHOT_OK}" -eq 1 ]]; then
    ORDER="ffmpeg,screenshot,gstreamer,native"
  else
    ORDER="ffmpeg,gstreamer,screenshot,native"
  fi
elif [[ "${GST_CAPTURE_OK}" -eq 1 ]]; then
  ORDER="gstreamer,ffmpeg,screenshot,native"
elif [[ "${SHOT_OK}" -eq 1 ]]; then
  ORDER="screenshot,ffmpeg,gstreamer,native"
elif [[ -n "${DISPLAY:-}" ]]; then
  ORDER="ffmpeg,screenshot,gstreamer,native"
fi
ENV_DIR="${TARGET_HOME}/.config/environment.d"
ENV_FILE="${ENV_DIR}/60-cyberdeck-wayland.conf"
mkdir -p "${ENV_DIR}"
cat > "${ENV_FILE}" <<EOF
CYBERDECK_MJPEG_BACKEND_ORDER=${ORDER}
CYBERDECK_WAYLAND_ALLOW_X11_FALLBACK=1
CYBERDECK_MJPEG_LOWLAT_DEFAULT=1
CYBERDECK_MJPEG_DEFAULT_W=1280
CYBERDECK_MJPEG_DEFAULT_Q=55
CYBERDECK_LOWLAT_MAX_W=1280
CYBERDECK_LOWLAT_MAX_Q=50
CYBERDECK_LOWLAT_MAX_FPS=20
CYBERDECK_SCREENSHOT_MAX_W=1280
CYBERDECK_SCREENSHOT_MAX_Q=50
CYBERDECK_SCREENSHOT_MAX_FPS=8
CYBERDECK_JPEG_SUBSAMPLING=1
CYBERDECK_FAST_RESIZE=1
CYBERDECK_MOUSE_GAIN=1.35
CYBERDECK_MOUSE_MAX_DELTA=160
CYBERDECK_MOUSE_DEADZONE=0.2
CYBERDECK_MOUSE_LAG_DAMP_START_S=0.085
CYBERDECK_MOUSE_LAG_DAMP_MIN=0.35
CYBERDECK_CURSOR_STREAM=0
CYBERDECK_AUDIO_ENABLE_PIPEWIRE=1
CYBERDECK_AUDIO_PULSE_MAX_CANDIDATES=2
CYBERDECK_AUDIO_PULSE_PROBE_TIMEOUT_S=0.45
CYBERDECK_AUDIO_MAX_CMD_CANDIDATES=4
CYBERDECK_AUDIO_STARTUP_BUDGET_S=5.5
CYBERDECK_AUDIO_FIRST_CHUNK_TIMEOUT_S=4.0
CYBERDECK_AUDIO_FIRST_CHUNK_TIMEOUT_FAST_S=1.6
CYBERDECK_PIPEWIRE_MAX_SOURCES=2
CYBERDECK_PIPEWIRE_DISCOVER_TIMEOUT_S=0.45
CYBERDECK_STREAM_MAX_CMD_CANDIDATES=6
CYBERDECK_STREAM_STARTUP_BUDGET_S=6.5
CYBERDECK_VERBOSE_HTTP_LOG=0
CYBERDECK_VERBOSE_WS_LOG=0
CYBERDECK_VERBOSE_STREAM_LOG=0
EOF
if [[ -n "${SHOT_TOOL}" ]]; then
  echo "CYBERDECK_SCREENSHOT_TOOL=${SHOT_TOOL}" >> "${ENV_FILE}"
fi
if [[ "${SHOT_TOOL}" == "gnome-screenshot" ]]; then
  echo "CYBERDECK_ALLOW_GNOME_SCREENSHOT=1" >> "${ENV_FILE}"
else
  echo "CYBERDECK_ALLOW_GNOME_SCREENSHOT=0" >> "${ENV_FILE}"
fi
echo "      Wrote ${ENV_FILE}: CYBERDECK_MJPEG_BACKEND_ORDER=${ORDER}"

echo "[10/10] Done."
echo
echo "Next steps:"
echo "  1) Log out and log back in (or reboot) to apply group membership and environment.d."
echo "  2) Run CyberDeck as regular user (NOT sudo):"
echo "       cd ${REPO_ROOT}"
echo "       source .venv/bin/activate"
echo "       CYBERDECK_DEBUG=1 CYBERDECK_LOG=1 python launcher.py"
