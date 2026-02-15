import json
import socket
import threading

from . import config
from .logging_config import log


def udp_discovery_service() -> None:
    """Run UDP discovery service and answer clients with server endpoint data."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", config.UDP_PORT))
        log.info(f"UDP discovery listening on {config.UDP_PORT}")
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                if b"CYBERDECK_DISCOVER" in data:
                    nonce = None
                    try:
                        if data.startswith(b"CYBERDECK_DISCOVER:"):
                            nonce = data.split(b":", 1)[1].decode("utf-8", "ignore")[:32]
                    except Exception:
                        nonce = None
                    resp_dict = {
                        "cyberdeck": True,
                        "proto": int(getattr(config, "PROTOCOL_VERSION", 2)),
                        "id": config.SERVER_ID,
                        "name": config.HOSTNAME,
                        "port": config.PORT,
                        "version": config.VERSION,
                        "scheme": getattr(config, "SCHEME", "http"),
                    }
                    if nonce:
                        resp_dict["nonce"] = nonce
                    resp = json.dumps(resp_dict)
                    sock.sendto(resp.encode("utf-8"), addr)
            except Exception:
                pass
    except Exception:
        log.exception("UDP discovery died")


def start_udp_discovery() -> None:
    """Manage lifecycle transition to start udp discovery."""
    # Lifecycle transitions are centralized here to prevent partial-state bugs.
    threading.Thread(target=udp_discovery_service, daemon=True).start()
