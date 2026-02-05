import os
import socket
import sys
import time
import uuid


VERSION = "v1.3.0"

HOST = "0.0.0.0"
PORT = int(os.environ.get("CYBERDECK_PORT", "8080"))
PORT_AUTO = os.environ.get("CYBERDECK_PORT_AUTO", "1") == "1"
UDP_PORT = int(os.environ.get("CYBERDECK_UDP_PORT", "5555"))
MDNS_ENABLED = os.environ.get("CYBERDECK_MDNS", "1") == "1"

CURSOR_STREAM = int(os.environ.get("CYBERDECK_CURSOR_STREAM", "1")) == 1
CURSOR_STREAM_FPS = int(os.environ.get("CYBERDECK_CURSOR_FPS", "30"))
STREAM_MONITOR = int(os.environ.get("CYBERDECK_STREAM_MONITOR", "1"))

DEBUG = os.environ.get("CYBERDECK_DEBUG", "0") == "1"
CONSOLE_LOG = os.environ.get("CYBERDECK_CONSOLE", "0") == "1"
LOG_ENABLED = os.environ.get("CYBERDECK_LOG", "0") == "1" or CONSOLE_LOG

TLS_CERT = os.environ.get("CYBERDECK_TLS_CERT", "")
TLS_KEY = os.environ.get("CYBERDECK_TLS_KEY", "")
TLS_ENABLED = os.environ.get("CYBERDECK_TLS", "0") == "1" and bool(TLS_CERT and TLS_KEY)
SCHEME = "https" if TLS_ENABLED else "http"

SESSION_TTL_S = int(os.environ.get("CYBERDECK_SESSION_TTL_S", "0"))
SESSION_IDLE_TTL_S = int(os.environ.get("CYBERDECK_SESSION_IDLE_TTL_S", "0"))
MAX_SESSIONS = int(os.environ.get("CYBERDECK_MAX_SESSIONS", "0"))

PIN_WINDOW_S = int(os.environ.get("CYBERDECK_PIN_WINDOW_S", "60"))
PIN_MAX_FAILS = int(os.environ.get("CYBERDECK_PIN_MAX_FAILS", "8"))
PIN_BLOCK_S = int(os.environ.get("CYBERDECK_PIN_BLOCK_S", "300"))

PAIRING_TTL_S = int(os.environ.get("CYBERDECK_PAIRING_TTL_S", "0"))

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # корень репозитория (родительская папка пакета)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILES_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
SESSION_FILE = os.path.join(BASE_DIR, "cyberdeck_sessions.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
LOG_FILE = os.path.join(BASE_DIR, "cyberdeck.log")

if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR, exist_ok=True)

PAIRING_CODE = str(uuid.uuid4().int)[:4]
PAIRING_EXPIRES_AT = (time.time() + PAIRING_TTL_S) if PAIRING_TTL_S > 0 else None
SERVER_ID = str(uuid.uuid4())[:8]
if os.name == "nt":
    HOSTNAME = os.environ.get("COMPUTERNAME") or "CyberDeck PC"
else:
    HOSTNAME = os.environ.get("HOSTNAME") or socket.gethostname() or "CyberDeck PC"


def reload_from_env() -> None:
    global PORT, PORT_AUTO, DEBUG, CONSOLE_LOG, LOG_ENABLED
    global SESSION_TTL_S, SESSION_IDLE_TTL_S, MAX_SESSIONS
    global PIN_WINDOW_S, PIN_MAX_FAILS, PIN_BLOCK_S
    global PAIRING_TTL_S, PAIRING_EXPIRES_AT
    global MDNS_ENABLED, STREAM_MONITOR
    global TLS_CERT, TLS_KEY, TLS_ENABLED, SCHEME

    PORT = int(os.environ.get("CYBERDECK_PORT", str(PORT)))
    PORT_AUTO = os.environ.get("CYBERDECK_PORT_AUTO", "1") == "1"
    MDNS_ENABLED = os.environ.get("CYBERDECK_MDNS", "1") == "1"

    DEBUG = os.environ.get("CYBERDECK_DEBUG", "0") == "1"
    CONSOLE_LOG = os.environ.get("CYBERDECK_CONSOLE", "0") == "1"
    LOG_ENABLED = os.environ.get("CYBERDECK_LOG", "0") == "1" or CONSOLE_LOG

    SESSION_TTL_S = int(os.environ.get("CYBERDECK_SESSION_TTL_S", str(SESSION_TTL_S)))
    SESSION_IDLE_TTL_S = int(os.environ.get("CYBERDECK_SESSION_IDLE_TTL_S", str(SESSION_IDLE_TTL_S)))
    MAX_SESSIONS = int(os.environ.get("CYBERDECK_MAX_SESSIONS", str(MAX_SESSIONS)))

    PIN_WINDOW_S = int(os.environ.get("CYBERDECK_PIN_WINDOW_S", str(PIN_WINDOW_S)))
    PIN_MAX_FAILS = int(os.environ.get("CYBERDECK_PIN_MAX_FAILS", str(PIN_MAX_FAILS)))
    PIN_BLOCK_S = int(os.environ.get("CYBERDECK_PIN_BLOCK_S", str(PIN_BLOCK_S)))

    STREAM_MONITOR = int(os.environ.get("CYBERDECK_STREAM_MONITOR", str(STREAM_MONITOR)))

    TLS_CERT = os.environ.get("CYBERDECK_TLS_CERT", TLS_CERT)
    TLS_KEY = os.environ.get("CYBERDECK_TLS_KEY", TLS_KEY)
    TLS_ENABLED = os.environ.get("CYBERDECK_TLS", "0") == "1" and bool(TLS_CERT and TLS_KEY)
    SCHEME = "https" if TLS_ENABLED else "http"

    PAIRING_TTL_S = int(os.environ.get("CYBERDECK_PAIRING_TTL_S", str(PAIRING_TTL_S)))
    PAIRING_EXPIRES_AT = (time.time() + PAIRING_TTL_S) if PAIRING_TTL_S > 0 else None
