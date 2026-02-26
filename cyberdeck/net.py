"""Networking helpers for local bind and host discovery."""

import ipaddress
import os
import socket
from typing import Iterator

import psutil


_VPN_IFACE_HINTS = (
    "vpn",
    "tun",
    "tap",
    "wireguard",
    "wg",
    "tailscale",
    "zerotier",
    "hamachi",
    "nordlynx",
    "proton",
    "wintun",
    "utun",
    "ipsec",
    "ppp",
    "warp",
)

_NET_IFACE_HINTS = ("ethernet", "wifi", "wi-fi", "wlan", "eth", "en")


def _env_bool(name: str, default: bool) -> bool:
    """Read bool env var supporting common truthy/falsy forms."""
    raw = os.environ.get(name, None)
    if raw is None:
        return bool(default)
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on", "y", "t"}:
        return True
    if value in {"0", "false", "no", "off", "n", "f"}:
        return False
    return bool(default)


def _probe_route_ip() -> str:
    """Return best-effort IPv4 from default route probing."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return str(s.getsockname()[0] or "127.0.0.1")
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _iface_has_hint(name: str, hints: tuple[str, ...]) -> bool:
    """Return True if an interface name contains any hint token."""
    val = str(name or "").strip().lower()
    if not val:
        return False
    return any(h in val for h in hints)


def _score_ipv4_candidate(ip: str, iface_name: str) -> int:
    """Return quality score for IPv4 candidate; negative means unusable."""
    try:
        addr = ipaddress.ip_address(str(ip or "").strip())
    except Exception:
        return -1
    if not isinstance(addr, ipaddress.IPv4Address):
        return -1
    if addr.is_loopback or addr.is_link_local:
        return -1
    if _iface_has_hint(iface_name, _VPN_IFACE_HINTS):
        return -1

    score = 50
    if addr.is_private:
        score += 60
    if _iface_has_hint(iface_name, _NET_IFACE_HINTS):
        score += 12
    return score


def _iter_non_vpn_ipv4() -> Iterator[str]:
    """Yield IPv4 addresses from active non-VPN interfaces ordered by score."""
    try:
        by_iface = psutil.net_if_addrs() or {}
    except Exception:
        by_iface = {}
    try:
        stats = psutil.net_if_stats() or {}
    except Exception:
        stats = {}

    ranked: list[tuple[int, str]] = []
    for iface_name, entries in by_iface.items():
        st = stats.get(iface_name)
        if st is not None and (not bool(getattr(st, "isup", False))):
            continue
        for entry in entries or []:
            if getattr(entry, "family", None) != socket.AF_INET:
                continue
            ip = str(getattr(entry, "address", "") or "").strip()
            if not ip:
                continue
            score = _score_ipv4_candidate(ip, str(iface_name or ""))
            if score >= 0:
                ranked.append((score, ip))

    ranked.sort(key=lambda item: item[0], reverse=True)
    seen = set()
    for _score, ip in ranked:
        if ip in seen:
            continue
        seen.add(ip)
        yield ip


def get_local_ip() -> str:
    """Return best-effort LAN IPv4 address of the current host."""
    route_ip = _probe_route_ip()
    if not _env_bool("CYBERDECK_IGNORE_VPN", False):
        return route_ip

    for ip in _iter_non_vpn_ipv4():
        return ip
    return route_ip


def find_free_port() -> int:
    """Return an ephemeral TCP port that is currently free."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]
