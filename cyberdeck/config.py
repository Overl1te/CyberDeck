import os
import socket
import sys
import time
import uuid
from typing import List


VERSION = "v1.3.2"


def _is_packaged_runtime() -> bool:
    """Return True when running from a packaged executable (Nuitka/PyInstaller)."""
    if bool(getattr(sys, "frozen", False)):
        return True
    if "__compiled__" in globals():
        return True
    try:
        main_mod = sys.modules.get("__main__")
        if main_mod is not None and hasattr(main_mod, "__compiled__"):
            return True
    except Exception:
        pass
    try:
        exe_path = str(getattr(sys, "executable", "") or "")
        exe_name = os.path.basename(exe_path).strip().lower()
        python_like = {"python", "python3", "python.exe", "pythonw.exe", "py.exe", "pypy", "pypy3"}
        if exe_name and (exe_name not in python_like) and ("python" not in exe_name) and ("pypy" not in exe_name):
            return True
    except Exception:
        pass
    return False


def _csv_list(raw: str) -> List[str]:
    """Parse a comma-separated string into normalized non-empty values."""
    out: List[str] = []
    for x in str(raw or "").split(","):
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable with a safe fallback."""
    raw = os.environ.get(name, None)
    if raw is None:
        return int(default)
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return int(default)


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable with a safe fallback."""
    raw = os.environ.get(name, None)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return float(default)


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable using common truthy/falsy forms."""
    raw = os.environ.get(name, None)
    if raw is None:
        return bool(default)
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on", "y", "t"}:
        return True
    if value in {"0", "false", "no", "off", "n", "f"}:
        return False
    return bool(default)

HOST = "0.0.0.0"
PROTOCOL_VERSION = _env_int("CYBERDECK_PROTOCOL_VERSION", 2)
MIN_SUPPORTED_PROTOCOL_VERSION = _env_int("CYBERDECK_MIN_PROTOCOL_VERSION", 1)
PORT = _env_int("CYBERDECK_PORT", 8080)
PORT_AUTO = _env_bool("CYBERDECK_PORT_AUTO", True)
UDP_PORT = _env_int("CYBERDECK_UDP_PORT", 5555)
MDNS_ENABLED = _env_bool("CYBERDECK_MDNS", True)

_IS_LINUX_WAYLAND = (
    os.name != "nt"
    and (
        (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower() == "wayland"
        or bool(os.environ.get("WAYLAND_DISPLAY"))
    )
)
_CURSOR_STREAM_DEFAULT = "0" if _IS_LINUX_WAYLAND else "1"
CURSOR_STREAM = _env_bool("CYBERDECK_CURSOR_STREAM", _CURSOR_STREAM_DEFAULT == "1")
CURSOR_STREAM_FPS = _env_int("CYBERDECK_CURSOR_FPS", 30)
STREAM_MONITOR = _env_int("CYBERDECK_STREAM_MONITOR", 1)
WS_HEARTBEAT_INTERVAL_S = _env_int("CYBERDECK_WS_HEARTBEAT_INTERVAL_S", 15)
WS_HEARTBEAT_TIMEOUT_S = _env_int("CYBERDECK_WS_HEARTBEAT_TIMEOUT_S", 45)
VERBOSE_STREAM_LOG = _env_bool("CYBERDECK_VERBOSE_STREAM_LOG", True)
VERBOSE_WS_LOG = _env_bool("CYBERDECK_VERBOSE_WS_LOG", True)
VERBOSE_HTTP_LOG = _env_bool("CYBERDECK_VERBOSE_HTTP_LOG", True)
CORS_ORIGINS = _csv_list(os.environ.get("CYBERDECK_CORS_ORIGINS", "*")) or ["*"]
CORS_ALLOW_CREDENTIALS = _env_bool("CYBERDECK_CORS_ALLOW_CREDENTIALS", False)
if "*" in CORS_ORIGINS:
    CORS_ALLOW_CREDENTIALS = False
ALLOW_QUERY_TOKEN = _env_bool("CYBERDECK_ALLOW_QUERY_TOKEN", False)
DEVICE_APPROVAL_REQUIRED = _env_bool("CYBERDECK_DEVICE_APPROVAL_REQUIRED", False)
CYBERDECK_GITHUB_REPO = str(os.environ.get("CYBERDECK_GITHUB_REPO", "Overl1te/CyberDeck") or "Overl1te/CyberDeck").strip()
CYBERDECK_MOBILE_GITHUB_REPO = str(
    os.environ.get("CYBERDECK_MOBILE_GITHUB_REPO", "Overl1te/CyberDeck-Mobile") or "Overl1te/CyberDeck-Mobile"
).strip()
MOBILE_VERSION = str(os.environ.get("CYBERDECK_MOBILE_VERSION", "1.1.2") or "1.1.2").strip()
MOBILE_ANDROID_PACKAGE = str(
    os.environ.get("CYBERDECK_MOBILE_ANDROID_PACKAGE", "com.example.cyberdeck_mobile.cyberdeck_mobile")
    or "com.example.cyberdeck_mobile.cyberdeck_mobile"
).strip()
UPDATE_CHECK_TIMEOUT_S = _env_float("CYBERDECK_UPDATE_CHECK_TIMEOUT_S", 2.5)
UPDATE_CHECK_TIMEOUT_S = max(0.5, min(15.0, UPDATE_CHECK_TIMEOUT_S))
UPDATE_CHECK_TTL_S = _env_int("CYBERDECK_UPDATE_CHECK_TTL_S", 300)
UPDATE_CHECK_TTL_S = max(15, min(3600, UPDATE_CHECK_TTL_S))

DEBUG = _env_bool("CYBERDECK_DEBUG", False)
CONSOLE_LOG = _env_bool("CYBERDECK_CONSOLE", False)
LOG_ENABLED = _env_bool("CYBERDECK_LOG", False) or CONSOLE_LOG

TLS_CERT = os.environ.get("CYBERDECK_TLS_CERT", "")
TLS_KEY = os.environ.get("CYBERDECK_TLS_KEY", "")
TLS_ENABLED = _env_bool("CYBERDECK_TLS", False) and bool(TLS_CERT and TLS_KEY)
SCHEME = "https" if TLS_ENABLED else "http"

SESSION_TTL_S = _env_int("CYBERDECK_SESSION_TTL_S", 0)
SESSION_IDLE_TTL_S = _env_int("CYBERDECK_SESSION_IDLE_TTL_S", 0)
MAX_SESSIONS = _env_int("CYBERDECK_MAX_SESSIONS", 0)
DEVICE_ONLINE_GRACE_S = _env_float("CYBERDECK_DEVICE_ONLINE_GRACE_S", 2.5)

PIN_WINDOW_S = _env_int("CYBERDECK_PIN_WINDOW_S", 60)
PIN_MAX_FAILS = _env_int("CYBERDECK_PIN_MAX_FAILS", 8)
PIN_BLOCK_S = _env_int("CYBERDECK_PIN_BLOCK_S", 300)
PIN_STATE_STALE_S = _env_int("CYBERDECK_PIN_STATE_STALE_S", 7200)
PIN_STATE_MAX_IPS = _env_int("CYBERDECK_PIN_STATE_MAX_IPS", 4096)

PAIRING_TTL_S = _env_int("CYBERDECK_PAIRING_TTL_S", 0)
PAIRING_SINGLE_USE = _env_bool("CYBERDECK_PAIRING_SINGLE_USE", False)
QR_TOKEN_TTL_S = _env_int("CYBERDECK_QR_TOKEN_TTL_S", 120)
UPLOAD_MAX_BYTES = _env_int("CYBERDECK_UPLOAD_MAX_BYTES", 0)
UPLOAD_ALLOWED_EXT = [x.lower() for x in _csv_list(os.environ.get("CYBERDECK_UPLOAD_ALLOWED_EXT", ""))]
TRANSFER_SCHEME = str(os.environ.get("CYBERDECK_TRANSFER_SCHEME", "auto") or "auto").strip().lower()

RUNTIME_PACKAGED = _is_packaged_runtime()

if RUNTIME_PACKAGED:
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Repository root (parent directory of the package folder).
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_data_dir() -> str:
    """Return default writable data/log directory for current OS."""
    if os.name == "nt":
        local_appdata = str(os.environ.get("LOCALAPPDATA", "") or "").strip()
        if local_appdata:
            appdata_root = os.path.dirname(local_appdata)
            if appdata_root:
                return os.path.join(appdata_root, "LocalLow", "CyberDeck")

        appdata_roaming = str(os.environ.get("APPDATA", "") or "").strip()
        if appdata_roaming:
            appdata_root = os.path.dirname(appdata_roaming)
            if appdata_root:
                return os.path.join(appdata_root, "LocalLow", "CyberDeck")

        return os.path.join(os.path.expanduser("~"), "AppData", "LocalLow", "CyberDeck")

    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "CyberDeck")

    xdg_state_home = str(os.environ.get("XDG_STATE_HOME", "") or "").strip()
    if xdg_state_home:
        return os.path.join(os.path.expanduser(xdg_state_home), "CyberDeck")
    return os.path.join(os.path.expanduser("~"), ".local", "state", "CyberDeck")


def _default_files_dir() -> str:
    """Return default upload/download directory for current user."""
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.isdir(downloads):
        return downloads
    return os.path.expanduser("~")


def _resolve_path(raw: str, fallback: str) -> str:
    """Resolve a user/environment path to absolute form with fallback."""
    value = str(raw or "").strip() or str(fallback or "").strip()
    return os.path.abspath(os.path.expanduser(value))


def _default_log_file(data_dir: str) -> str:
    """Return default log file path for current OS."""
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Logs", "CyberDeck", "cyberdeck.log")
    return os.path.join(str(data_dir or "").strip(), "cyberdeck.log")

_MODULE_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RESOURCE_DIR_ENV = str(os.environ.get("CYBERDECK_RESOURCE_DIR", "") or "").strip()
RESOURCE_DIR = _RESOURCE_DIR_ENV or _MODULE_BASE_DIR
if not os.path.exists(os.path.join(RESOURCE_DIR, "static")):
    RESOURCE_DIR = BASE_DIR

_DEFAULT_DATA_DIR = _default_data_dir()
_DEFAULT_FILES_DIR = _default_files_dir()
DATA_DIR = _resolve_path(os.environ.get("CYBERDECK_DATA_DIR", ""), _DEFAULT_DATA_DIR)
_FILES_DIR_ENV = str(os.environ.get("CYBERDECK_FILES_DIR", "") or "").strip()
FILES_DIR = _resolve_path(_FILES_DIR_ENV, _DEFAULT_FILES_DIR)
_LOG_FILE_ENV = str(os.environ.get("CYBERDECK_LOG_FILE", "") or "").strip()
LOG_FILE = _resolve_path(_LOG_FILE_ENV, _default_log_file(DATA_DIR))
SESSION_FILE = os.path.join(DATA_DIR, "cyberdeck_sessions.json")
STATIC_DIR = os.path.join(RESOURCE_DIR, "static")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)
if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR, exist_ok=True)
_LOG_DIR = os.path.dirname(os.path.abspath(LOG_FILE))
if _LOG_DIR and (not os.path.exists(_LOG_DIR)):
    os.makedirs(_LOG_DIR, exist_ok=True)

_PAIRING_CODE_ENV = str(os.environ.get("CYBERDECK_PAIRING_CODE", "") or "").strip()
PAIRING_CODE = (_PAIRING_CODE_ENV[:4] if _PAIRING_CODE_ENV else str(uuid.uuid4().int)[:4])
PAIRING_EXPIRES_AT = (time.time() + PAIRING_TTL_S) if PAIRING_TTL_S > 0 else None
SERVER_ID = str(uuid.uuid4())[:8]
if os.name == "nt":
    HOSTNAME = os.environ.get("COMPUTERNAME") or "CyberDeck PC"
else:
    HOSTNAME = os.environ.get("HOSTNAME") or socket.gethostname() or "CyberDeck PC"


def reload_from_env() -> None:
    """Reload runtime configuration from environment variables."""
    global PORT, PORT_AUTO, UDP_PORT, DEBUG, CONSOLE_LOG, LOG_ENABLED
    global SESSION_TTL_S, SESSION_IDLE_TTL_S, MAX_SESSIONS, DEVICE_ONLINE_GRACE_S
    global PIN_WINDOW_S, PIN_MAX_FAILS, PIN_BLOCK_S
    global PAIRING_TTL_S, PAIRING_EXPIRES_AT, PAIRING_CODE, PAIRING_SINGLE_USE
    global MDNS_ENABLED, CURSOR_STREAM, CURSOR_STREAM_FPS, STREAM_MONITOR
    global PROTOCOL_VERSION, MIN_SUPPORTED_PROTOCOL_VERSION
    global WS_HEARTBEAT_INTERVAL_S, WS_HEARTBEAT_TIMEOUT_S
    global VERBOSE_STREAM_LOG, VERBOSE_WS_LOG, VERBOSE_HTTP_LOG
    global CORS_ORIGINS, CORS_ALLOW_CREDENTIALS
    global ALLOW_QUERY_TOKEN, DEVICE_APPROVAL_REQUIRED
    global CYBERDECK_GITHUB_REPO, CYBERDECK_MOBILE_GITHUB_REPO, MOBILE_VERSION, MOBILE_ANDROID_PACKAGE
    global UPDATE_CHECK_TIMEOUT_S, UPDATE_CHECK_TTL_S
    global TLS_CERT, TLS_KEY, TLS_ENABLED, SCHEME
    global PIN_STATE_STALE_S, PIN_STATE_MAX_IPS
    global QR_TOKEN_TTL_S, UPLOAD_MAX_BYTES, UPLOAD_ALLOWED_EXT, TRANSFER_SCHEME
    global DATA_DIR, FILES_DIR, SESSION_FILE, LOG_FILE

    PORT = _env_int("CYBERDECK_PORT", PORT)
    PORT_AUTO = _env_bool("CYBERDECK_PORT_AUTO", PORT_AUTO)
    UDP_PORT = _env_int("CYBERDECK_UDP_PORT", UDP_PORT)
    MDNS_ENABLED = _env_bool("CYBERDECK_MDNS", MDNS_ENABLED)
    CURSOR_STREAM = _env_bool("CYBERDECK_CURSOR_STREAM", CURSOR_STREAM)
    CURSOR_STREAM_FPS = _env_int("CYBERDECK_CURSOR_FPS", CURSOR_STREAM_FPS)

    DEBUG = _env_bool("CYBERDECK_DEBUG", DEBUG)
    CONSOLE_LOG = _env_bool("CYBERDECK_CONSOLE", CONSOLE_LOG)
    LOG_ENABLED = _env_bool("CYBERDECK_LOG", LOG_ENABLED) or CONSOLE_LOG

    SESSION_TTL_S = _env_int("CYBERDECK_SESSION_TTL_S", SESSION_TTL_S)
    SESSION_IDLE_TTL_S = _env_int("CYBERDECK_SESSION_IDLE_TTL_S", SESSION_IDLE_TTL_S)
    MAX_SESSIONS = _env_int("CYBERDECK_MAX_SESSIONS", MAX_SESSIONS)
    DEVICE_ONLINE_GRACE_S = _env_float("CYBERDECK_DEVICE_ONLINE_GRACE_S", DEVICE_ONLINE_GRACE_S)

    PIN_WINDOW_S = _env_int("CYBERDECK_PIN_WINDOW_S", PIN_WINDOW_S)
    PIN_MAX_FAILS = _env_int("CYBERDECK_PIN_MAX_FAILS", PIN_MAX_FAILS)
    PIN_BLOCK_S = _env_int("CYBERDECK_PIN_BLOCK_S", PIN_BLOCK_S)

    STREAM_MONITOR = _env_int("CYBERDECK_STREAM_MONITOR", STREAM_MONITOR)
    PROTOCOL_VERSION = _env_int("CYBERDECK_PROTOCOL_VERSION", PROTOCOL_VERSION)
    MIN_SUPPORTED_PROTOCOL_VERSION = _env_int("CYBERDECK_MIN_PROTOCOL_VERSION", MIN_SUPPORTED_PROTOCOL_VERSION)
    WS_HEARTBEAT_INTERVAL_S = _env_int("CYBERDECK_WS_HEARTBEAT_INTERVAL_S", WS_HEARTBEAT_INTERVAL_S)
    WS_HEARTBEAT_TIMEOUT_S = _env_int("CYBERDECK_WS_HEARTBEAT_TIMEOUT_S", WS_HEARTBEAT_TIMEOUT_S)
    VERBOSE_STREAM_LOG = _env_bool("CYBERDECK_VERBOSE_STREAM_LOG", VERBOSE_STREAM_LOG)
    VERBOSE_WS_LOG = _env_bool("CYBERDECK_VERBOSE_WS_LOG", VERBOSE_WS_LOG)
    VERBOSE_HTTP_LOG = _env_bool("CYBERDECK_VERBOSE_HTTP_LOG", VERBOSE_HTTP_LOG)
    CORS_ORIGINS = _csv_list(os.environ.get("CYBERDECK_CORS_ORIGINS", ",".join(CORS_ORIGINS))) or ["*"]
    CORS_ALLOW_CREDENTIALS = _env_bool("CYBERDECK_CORS_ALLOW_CREDENTIALS", CORS_ALLOW_CREDENTIALS)
    if "*" in CORS_ORIGINS:
        CORS_ALLOW_CREDENTIALS = False
    ALLOW_QUERY_TOKEN = _env_bool("CYBERDECK_ALLOW_QUERY_TOKEN", ALLOW_QUERY_TOKEN)
    DEVICE_APPROVAL_REQUIRED = _env_bool("CYBERDECK_DEVICE_APPROVAL_REQUIRED", DEVICE_APPROVAL_REQUIRED)
    CYBERDECK_GITHUB_REPO = str(
        os.environ.get("CYBERDECK_GITHUB_REPO", CYBERDECK_GITHUB_REPO or "Overl1te/CyberDeck") or "Overl1te/CyberDeck"
    ).strip()
    CYBERDECK_MOBILE_GITHUB_REPO = str(
        os.environ.get(
            "CYBERDECK_MOBILE_GITHUB_REPO",
            CYBERDECK_MOBILE_GITHUB_REPO or "Overl1te/CyberDeck-Mobile",
        )
        or "Overl1te/CyberDeck-Mobile"
    ).strip()
    MOBILE_VERSION = str(os.environ.get("CYBERDECK_MOBILE_VERSION", MOBILE_VERSION or "1.1.2") or "1.1.2").strip()
    MOBILE_ANDROID_PACKAGE = str(
        os.environ.get(
            "CYBERDECK_MOBILE_ANDROID_PACKAGE",
            MOBILE_ANDROID_PACKAGE or "com.example.cyberdeck_mobile.cyberdeck_mobile",
        )
        or "com.example.cyberdeck_mobile.cyberdeck_mobile"
    ).strip()
    UPDATE_CHECK_TIMEOUT_S = _env_float("CYBERDECK_UPDATE_CHECK_TIMEOUT_S", UPDATE_CHECK_TIMEOUT_S)
    UPDATE_CHECK_TIMEOUT_S = max(0.5, min(15.0, UPDATE_CHECK_TIMEOUT_S))
    UPDATE_CHECK_TTL_S = _env_int("CYBERDECK_UPDATE_CHECK_TTL_S", UPDATE_CHECK_TTL_S)
    UPDATE_CHECK_TTL_S = max(15, min(3600, UPDATE_CHECK_TTL_S))

    TLS_CERT = os.environ.get("CYBERDECK_TLS_CERT", TLS_CERT)
    TLS_KEY = os.environ.get("CYBERDECK_TLS_KEY", TLS_KEY)
    TLS_ENABLED = _env_bool("CYBERDECK_TLS", TLS_ENABLED) and bool(TLS_CERT and TLS_KEY)
    SCHEME = "https" if TLS_ENABLED else "http"

    PAIRING_TTL_S = _env_int("CYBERDECK_PAIRING_TTL_S", PAIRING_TTL_S)
    PAIRING_SINGLE_USE = _env_bool("CYBERDECK_PAIRING_SINGLE_USE", PAIRING_SINGLE_USE)
    PAIRING_EXPIRES_AT = (time.time() + PAIRING_TTL_S) if PAIRING_TTL_S > 0 else None
    QR_TOKEN_TTL_S = _env_int("CYBERDECK_QR_TOKEN_TTL_S", QR_TOKEN_TTL_S)
    UPLOAD_MAX_BYTES = _env_int("CYBERDECK_UPLOAD_MAX_BYTES", UPLOAD_MAX_BYTES)
    UPLOAD_ALLOWED_EXT = [
        x.lower() for x in _csv_list(os.environ.get("CYBERDECK_UPLOAD_ALLOWED_EXT", ",".join(UPLOAD_ALLOWED_EXT)))
    ]
    TRANSFER_SCHEME = str(
        os.environ.get("CYBERDECK_TRANSFER_SCHEME", TRANSFER_SCHEME or "auto") or "auto"
    ).strip().lower()
    PIN_STATE_STALE_S = _env_int("CYBERDECK_PIN_STATE_STALE_S", PIN_STATE_STALE_S)
    PIN_STATE_MAX_IPS = _env_int("CYBERDECK_PIN_STATE_MAX_IPS", PIN_STATE_MAX_IPS)

    DATA_DIR = _resolve_path(os.environ.get("CYBERDECK_DATA_DIR", DATA_DIR), DATA_DIR)
    FILES_DIR = _resolve_path(os.environ.get("CYBERDECK_FILES_DIR", FILES_DIR), FILES_DIR)
    LOG_FILE = _resolve_path(os.environ.get("CYBERDECK_LOG_FILE", ""), _default_log_file(DATA_DIR))
    SESSION_FILE = os.path.join(DATA_DIR, "cyberdeck_sessions.json")
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(FILES_DIR):
        os.makedirs(FILES_DIR, exist_ok=True)
    log_dir = os.path.dirname(os.path.abspath(LOG_FILE))
    if log_dir and (not os.path.exists(log_dir)):
        os.makedirs(log_dir, exist_ok=True)

    p = str(os.environ.get("CYBERDECK_PAIRING_CODE", "") or "").strip()
    if p:
        PAIRING_CODE = p[:4]
