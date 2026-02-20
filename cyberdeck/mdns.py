import atexit
import socket
from typing import Optional, Tuple

from . import config
from .logging_config import log
from .net import get_local_ip


def start_mdns() -> Optional[Tuple[object, object]]:
    """Manage lifecycle transition to start mdns."""
    # Lifecycle transitions are centralized here to prevent partial-state bugs.
    try:
        from zeroconf import ServiceInfo, Zeroconf
    except Exception:
        log.info("mDNS disabled: zeroconf not installed")
        return None

    try:
        ip = get_local_ip()
        addr = socket.inet_aton(ip)
        service_type = "_cyberdeck._tcp.local."
        name = f"CyberDeck-{config.SERVER_ID}.{service_type}"

        props = {
            b"version": str(config.VERSION).encode("utf-8"),
            b"hostname": str(config.HOSTNAME).encode("utf-8"),
            b"id": str(config.SERVER_ID).encode("utf-8"),
            b"udp_port": str(config.UDP_PORT).encode("utf-8"),
            b"scheme": str(config.SCHEME).encode("utf-8"),
        }

        info = ServiceInfo(
            type_=service_type,
            name=name,
            addresses=[addr],
            port=int(config.PORT),
            properties=props,
            server=f"{config.HOSTNAME}.local.",
        )

        zc = Zeroconf()
        zc.register_service(info)
        log.info(f"mDNS broadcast started: {name} -> {ip}:{config.PORT}")

        def _cleanup():
            """Unregister mDNS service and close Zeroconf resources."""
            try:
                zc.unregister_service(info)
                zc.close()
            except Exception:
                pass

        atexit.register(_cleanup)
        return zc, info
    except Exception:
        log.exception("mDNS start failed")
        return None


