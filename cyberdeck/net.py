"""Networking helpers for local bind and host discovery."""

import ipaddress
import os
import socket
import subprocess
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

_VIRTUAL_IFACE_HINTS = (
    "docker",
    "veth",
    "virbr",
    "vmnet",
    "virtual",
    "hyper-v",
    "host-only",
    "default switch",
    "loopback",
    "wsl",
    "bridge",
    "br-",
)

_LAN_IFACE_HINTS = ("ethernet", "wifi", "wi-fi", "wlan", "lan")
_LAN_PREFIX_HINTS = ("eth", "en", "wl", "wlan")


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


def _iface_is_virtual(name: str) -> bool:
    """Return True when interface looks virtual/host-only/container-related."""
    return _iface_has_hint(name, _VIRTUAL_IFACE_HINTS)


def _iface_is_lan_like(name: str) -> bool:
    """Return True when interface name looks like physical LAN/Wi-Fi."""
    val = str(name or "").strip().lower()
    if not val:
        return False
    if _iface_has_hint(val, _LAN_IFACE_HINTS):
        return True
    for prefix in _LAN_PREFIX_HINTS:
        if val.startswith(prefix):
            return True
    return False


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
    if _iface_is_virtual(iface_name):
        return -1

    score = 40
    if addr.is_private:
        score += 60
    if _iface_is_lan_like(iface_name):
        score += 24
    # 100.64.0.0/10 is frequently used by VPN overlays; de-prioritize.
    try:
        if ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10"):
            score -= 20
    except Exception:
        pass
    return score


def _iter_non_vpn_ipv4(*, preferred_ip: str = "") -> Iterator[str]:
    """Yield IPv4 addresses from active non-VPN interfaces ordered by score."""
    try:
        by_iface = psutil.net_if_addrs() or {}
    except Exception:
        by_iface = {}
    try:
        stats = psutil.net_if_stats() or {}
    except Exception:
        stats = {}
    gateway_route_ips = _default_gateway_route_ips()

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
                try:
                    speed = int(getattr(st, "speed", 0) or 0)
                    if speed > 0:
                        score += 6
                except Exception:
                    pass
                if preferred_ip and ip == preferred_ip:
                    score += 18
                if ip in gateway_route_ips:
                    score += 40
                ranked.append((score, ip))

    ranked.sort(key=lambda item: item[0], reverse=True)
    seen = set()
    for _score, ip in ranked:
        if ip in seen:
            continue
        seen.add(ip)
        yield ip


def _iface_name_for_ipv4(ip: str) -> str:
    """Return interface name owning the given IPv4 address, if known."""
    target = str(ip or "").strip()
    if not target:
        return ""
    try:
        by_iface = psutil.net_if_addrs() or {}
    except Exception:
        by_iface = {}
    for iface_name, entries in by_iface.items():
        for entry in entries or []:
            if getattr(entry, "family", None) != socket.AF_INET:
                continue
            if str(getattr(entry, "address", "") or "").strip() == target:
                return str(iface_name or "")
    return ""


def _default_gateway_route_ips() -> set[str]:
    """Return interface IPv4 addresses used by default routes with a real gateway."""
    if os.name != "nt":
        return set()
    try:
        output = subprocess.check_output(
            ["route", "print", "0.0.0.0"],
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        return set()

    out: set[str] = set()
    for raw in str(output or "").splitlines():
        stripped = str(raw or "").strip()
        if not stripped.startswith("0.0.0.0"):
            continue
        parts = stripped.split()
        if len(parts) < 5:
            continue
        gateway = str(parts[2] or "").strip()
        iface_ip = str(parts[3] or "").strip()
        try:
            gw_addr = ipaddress.ip_address(gateway)
            iface_addr = ipaddress.ip_address(iface_ip)
        except Exception:
            continue
        if not isinstance(gw_addr, ipaddress.IPv4Address):
            continue
        if not isinstance(iface_addr, ipaddress.IPv4Address):
            continue
        if gateway == "0.0.0.0":
            continue
        out.add(iface_ip)
    return out


def _iface_names_with_default_gateway() -> set[str]:
    """Return interface names that own default-route IPv4 addresses with a real gateway."""
    out: set[str] = set()
    for ip in _default_gateway_route_ips():
        iface_name = _iface_name_for_ipv4(ip)
        if iface_name:
            out.add(iface_name)
    return out


def _route_ip_requires_lan_fallback(route_ip: str) -> bool:
    """Return True when route-probed IP points at VPN/virtual/non-usable adapter."""
    text = str(route_ip or "").strip()
    if not text:
        return False
    try:
        addr = ipaddress.ip_address(text)
    except Exception:
        return False
    if not isinstance(addr, ipaddress.IPv4Address):
        return True
    if addr.is_loopback or addr.is_link_local:
        return True

    iface_name = _iface_name_for_ipv4(text)
    if not iface_name:
        return False
    gateway_ifaces = _iface_names_with_default_gateway()
    if gateway_ifaces and iface_name not in gateway_ifaces:
        return True
    if _iface_has_hint(iface_name, _VPN_IFACE_HINTS):
        return True
    if _iface_is_virtual(iface_name):
        return True
    return False


def get_local_ip() -> str:
    """Return best-effort LAN IPv4 address of the current host."""
    route_ip = _probe_route_ip()
    prefer_lan = _env_bool("CYBERDECK_IGNORE_VPN", False) or _route_ip_requires_lan_fallback(route_ip)
    if prefer_lan:
        for ip in _iter_non_vpn_ipv4(preferred_ip=route_ip):
            return ip
    return route_ip


def find_free_port() -> int:
    """Return an ephemeral TCP port that is currently free."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]
