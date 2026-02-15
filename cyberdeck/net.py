"""Networking helpers for local bind and host discovery."""

import socket


def get_local_ip() -> str:
    """Return best-effort LAN IPv4 address of the current host.
    # Read-path helpers should avoid mutating shared state where possible.

    Falls back to loopback if outbound probing is unavailable.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def find_free_port() -> int:
    """Return an ephemeral TCP port that is currently free."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]
