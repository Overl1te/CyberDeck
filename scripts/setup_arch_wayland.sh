#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
UINPUT_RULE_FILE="/etc/udev/rules.d/99-cyberdeck-uinput.rules"
UINPUT_MODULE_FILE="/etc/modules-load.d/uinput.conf"
TARGET_USER="${SUDO_USER:-${USER:-}}"
TARGET_HOME="${HOME}"
SUDO_KEEPALIVE_PID=""

cleanup() {
  if [[ -n "${SUDO_KEEPALIVE_PID}" ]]; then
    kill "${SUDO_KEEPALIVE_PID}" >/dev/null 2>&1 || true
  fi
}

on_err() {
  local code=$?
  echo "[ERR] setup_arch_wayland.sh failed at line ${BASH_LINENO[0]}: ${BASH_COMMAND}" >&2
  echo "[ERR] Exit code: ${code}" >&2
  exit "${code}"
}

trap cleanup EXIT
trap on_err ERR

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

if ! command -v pacman >/dev/null 2>&1; then
  echo "[ERR] This script is for Arch Linux (pacman is required)."
  exit 1
fi

require_sudo_session() {
  echo "[preflight] Checking sudo access..."
  if ! sudo -v; then
    echo "[ERR] sudo authentication failed."
    exit 1
  fi
  (
    while true; do
      sudo -n true >/dev/null 2>&1 || exit 0
      sleep 45
    done
  ) &
  SUDO_KEEPALIVE_PID="$!"
}

wait_for_pacman_lock() {
  local lock_file="/var/lib/pacman/db.lck"
  local max_wait_s=180
  local elapsed=0
  local step=3
  local auto_clear_stale="${CYBERDECK_AUTO_CLEAR_PACMAN_LOCK:-1}"

  lock_has_owner() {
    if command -v lsof >/dev/null 2>&1; then
      sudo lsof -t "${lock_file}" >/dev/null 2>&1
      return $?
    fi
    if command -v fuser >/dev/null 2>&1; then
      sudo fuser -s "${lock_file}" >/dev/null 2>&1
      return $?
    fi
    return 1
  }

  package_manager_running() {
    pgrep -x pacman >/dev/null 2>&1 || \
    pgrep -x pamac >/dev/null 2>&1 || \
    pgrep -x yay >/dev/null 2>&1 || \
    pgrep -x paru >/dev/null 2>&1
  }

  while sudo test -e "${lock_file}"; do
    if ! lock_has_owner && ! package_manager_running; then
      if [[ "${auto_clear_stale}" == "1" ]]; then
        echo "[warn] Detected stale pacman lock with no active package manager."
        echo "[fix ] Removing stale lock: ${lock_file}"
        sudo rm -f "${lock_file}"
        break
      fi
      echo "[ERR] Detected stale pacman lock (no active package manager)."
      echo "      Remove manually: sudo rm -f ${lock_file}"
      echo "      Or set CYBERDECK_AUTO_CLEAR_PACMAN_LOCK=1"
      exit 1
    fi

    echo "[wait] pacman lock exists (${lock_file}), waiting..."
    sleep "${step}"
    elapsed=$((elapsed + step))
    if (( elapsed >= max_wait_s )); then
      echo "[ERR] pacman lock still present after ${max_wait_s}s."
      echo "      Close other package managers (pamac/octopi) and retry."
      echo "      Check processes: ps -ef | grep -E 'pacman|pamac|yay|paru'"
      exit 1
    fi
  done
}

install_if_present() {
  local pkg="$1"
  if pacman -Si "${pkg}" >/dev/null 2>&1; then
    sudo pacman -S --needed --noconfirm "${pkg}"
    return 0
  fi
  return 1
}

require_sudo_session
wait_for_pacman_lock

echo "[1/10] Installing required system packages from official repos..."
echo "      Running full system upgrade + required packages install..."
if ! sudo pacman -Syu --needed --noconfirm \
  python \
  python-virtualenv \
  python-pip \
  python-evdev \
  tk \
  wtype \
  wl-clipboard \
  pipewire \
  wireplumber \
  xdg-desktop-portal \
  xdg-desktop-portal-gtk \
  ffmpeg \
  gstreamer \
  gst-plugin-pipewire \
  gst-plugins-base \
  gst-plugins-good
then
  echo "[ERR] pacman failed during full upgrade/install step."
  echo "      This usually means mirror desync, package holds, or repo mismatch."
  echo "      Try manually:"
  echo "        sudo pacman -Syyu"
  echo "      Then rerun this script."
  exit 1
fi

wait_for_pacman_lock

echo "[2/10] Installing optional Wayland helpers (if available)..."
install_if_present xdg-desktop-portal-gnome || true
install_if_present xdg-desktop-portal-kde || true
install_if_present xdg-desktop-portal-wlr || true
install_if_present gnome-screenshot || true
install_if_present grim || true
install_if_present spectacle || true

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

echo "[5/10] Verifying Wayland stream backend..."
FFMPEG_PIPEWIRE_OK=0
FFMPEG_X11_OK=0
GST_PIPEWIRE_OK=0
if ffmpeg -hide_banner -formats 2>/dev/null | grep -qi 'pipewire'; then
  FFMPEG_PIPEWIRE_OK=1
fi
if ffmpeg -hide_banner -formats 2>/dev/null | grep -qi 'x11grab'; then
  FFMPEG_X11_OK=1
fi
if gst-inspect-1.0 pipewiresrc >/dev/null 2>&1; then
  GST_PIPEWIRE_OK=1
fi
if [[ "${FFMPEG_PIPEWIRE_OK}" -eq 1 || "${GST_PIPEWIRE_OK}" -eq 1 || "${FFMPEG_X11_OK}" -eq 1 ]]; then
  echo "      OK: Wayland stream backend is available."
else
  echo "[ERR] No working Wayland stream backend found."
  echo "      Need one of:"
  echo "      - ffmpeg with pipewire input"
  echo "      - GStreamer with pipewiresrc plugin"
  echo "      - ffmpeg with x11grab (XWayland fallback)"
  exit 1
fi

echo "[6/10] Enabling uinput (for keyboard/mouse control on Wayland)..."
echo "uinput" | sudo tee "${UINPUT_MODULE_FILE}" >/dev/null
sudo modprobe -r uinput >/dev/null 2>&1 || true
sudo modprobe uinput || true
sudo groupadd -f input
sudo usermod -aG input "${TARGET_USER}"
cat <<'EOF' | sudo tee "${UINPUT_RULE_FILE}" >/dev/null
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=misc --action=add || true
if [[ -e /dev/uinput ]]; then
  sudo chgrp input /dev/uinput || true
  sudo chmod 0660 /dev/uinput || true
fi

echo "[7/10] Preparing Python virtual environment..."
cd "${REPO_ROOT}"
python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt

echo "[8/10] Runtime checks..."
if [[ -e /dev/uinput ]]; then
  ls -l /dev/uinput || true
else
  echo "      WARN: /dev/uinput does not exist right now."
fi
ffmpeg -hide_banner -formats 2>/dev/null | grep -i 'pipewire' || true
gst-inspect-1.0 pipewiresrc >/dev/null 2>&1 && echo "gstreamer: pipewiresrc OK" || true

echo "[9/10] Smoke tests (stream + screenshot fallback)..."
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
if [[ "${SHOT_OK}" -ne 1 ]] && command -v spectacle >/dev/null 2>&1; then
  if spectacle -b -n -o "${TMP_SHOT}" >/dev/null 2>&1 && [[ -s "${TMP_SHOT}" ]]; then
    SHOT_OK=1
    SHOT_TOOL="spectacle"
    echo "      OK: spectacle test passed."
  fi
fi
rm -f "${TMP_SHOT}" >/dev/null 2>&1 || true
if [[ "${SHOT_OK}" -ne 1 ]]; then
  echo "      WARN: screenshot fallback test failed."
fi

echo "[10/10] Writing automatic backend policy..."
ORDER="ffmpeg,gstreamer,screenshot,native"
if [[ "${FFMPEG_PIPEWIRE_OK}" -eq 1 ]]; then
  ORDER="ffmpeg,gstreamer,screenshot,native"
elif [[ "${FFMPEG_X11_OK}" -eq 1 && -n "${DISPLAY:-}" ]]; then
  if [[ "${SHOT_OK}" -eq 1 ]]; then
    ORDER="screenshot,ffmpeg,gstreamer,native"
  else
    ORDER="ffmpeg,gstreamer,screenshot,native"
  fi
elif [[ "${GST_CAPTURE_OK}" -eq 1 ]]; then
  ORDER="gstreamer,screenshot,ffmpeg,native"
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
CYBERDECK_MJPEG_DEFAULT_W=854
CYBERDECK_MJPEG_DEFAULT_Q=38
CYBERDECK_LOWLAT_MAX_W=854
CYBERDECK_LOWLAT_MAX_Q=38
CYBERDECK_LOWLAT_MAX_FPS=20
CYBERDECK_SCREENSHOT_MAX_W=854
CYBERDECK_SCREENSHOT_MAX_Q=36
CYBERDECK_SCREENSHOT_MAX_FPS=8
CYBERDECK_JPEG_SUBSAMPLING=2
CYBERDECK_FAST_RESIZE=1
CYBERDECK_MOUSE_GAIN=1.35
CYBERDECK_MOUSE_MAX_DELTA=160
CYBERDECK_MOUSE_DEADZONE=0.2
CYBERDECK_MOUSE_LAG_DAMP_START_S=0.085
CYBERDECK_MOUSE_LAG_DAMP_MIN=0.35
CYBERDECK_CURSOR_STREAM=0
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

echo "Done."
echo
echo "Next steps:"
echo "  1) Log out and log back in (or reboot) to apply group membership and environment.d."
echo "  2) Run CyberDeck as regular user (NOT sudo):"
echo "       cd ${REPO_ROOT}"
echo "       source .venv/bin/activate"
echo "       CYBERDECK_DEBUG=1 CYBERDECK_LOG=1 python launcher.py"
