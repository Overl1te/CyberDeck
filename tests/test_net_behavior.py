import unittest
import os
import socket
from unittest.mock import patch

from cyberdeck import net


class _FakeSocket:
    def __init__(self, *, ip: str = "192.168.10.55", raise_connect: bool = False):
        """Initialize _FakeSocket state and collaborator references."""
        self._ip = ip
        self._raise_connect = raise_connect
        self.closed = False
        self.connected_to = None
        self.bound_to = None

    def connect(self, addr):
        """Connect the target operation."""
        self.connected_to = addr
        if self._raise_connect:
            raise OSError("connect failed")

    def getsockname(self):
        """Return mocked socket address tuple for test networking paths."""
        return (self._ip, 8080)

    def close(self):
        """Close test double resources and mark object as closed."""
        self.closed = True

    def bind(self, addr):
        """Bind the target operation."""
        self.bound_to = addr

    def __enter__(self):
        """Enter the managed runtime context."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the managed runtime context and release resources."""
        self.close()
        return False


class _FakeAddr:
    def __init__(self, family, address: str):
        """Initialize fake psutil address entry used by net helper tests."""
        self.family = family
        self.address = address


class _FakeStat:
    def __init__(self, isup: bool = True):
        """Initialize fake psutil interface stat entry."""
        self.isup = bool(isup)


class NetBehaviorTests(unittest.TestCase):
    def test_get_local_ip_returns_socket_address_on_success(self):
        """Validate scenario: test get local ip returns socket address on success."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake = _FakeSocket(ip="10.0.0.42", raise_connect=False)
        with patch.dict(os.environ, {"CYBERDECK_IGNORE_VPN": "0"}, clear=False), patch(
            "cyberdeck.net.socket.socket", return_value=fake
        ):
            ip = net.get_local_ip()
        self.assertEqual(ip, "10.0.0.42")
        self.assertEqual(fake.connected_to, ("10.255.255.255", 1))
        self.assertTrue(fake.closed)

    def test_get_local_ip_falls_back_to_loopback_on_error(self):
        """Validate scenario: test get local ip falls back to loopback on error."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake = _FakeSocket(raise_connect=True)
        with patch.dict(os.environ, {"CYBERDECK_IGNORE_VPN": "0"}, clear=False), patch(
            "cyberdeck.net.socket.socket", return_value=fake
        ):
            ip = net.get_local_ip()
        self.assertEqual(ip, "127.0.0.1")
        self.assertTrue(fake.closed)

    def test_get_local_ip_prefers_non_vpn_iface_when_ignore_vpn_enabled(self):
        """Validate scenario: ignore-vpn mode should prefer non-tunnel interface addresses."""
        fake = _FakeSocket(ip="100.64.2.10", raise_connect=False)
        addrs = {
            "NordLynx": [_FakeAddr(socket.AF_INET, "100.64.2.10")],
            "Ethernet": [_FakeAddr(socket.AF_INET, "192.168.1.77")],
        }
        stats = {"NordLynx": _FakeStat(True), "Ethernet": _FakeStat(True)}
        with patch.dict(os.environ, {"CYBERDECK_IGNORE_VPN": "1"}, clear=False), patch(
            "cyberdeck.net.socket.socket", return_value=fake
        ), patch("cyberdeck.net.psutil.net_if_addrs", return_value=addrs), patch(
            "cyberdeck.net.psutil.net_if_stats", return_value=stats
        ):
            ip = net.get_local_ip()
        self.assertEqual(ip, "192.168.1.77")

    def test_get_local_ip_keeps_route_ip_when_only_vpn_candidates_exist(self):
        """Validate scenario: ignore-vpn mode falls back to route IP when no LAN candidate exists."""
        fake = _FakeSocket(ip="100.64.10.9", raise_connect=False)
        addrs = {
            "tailscale0": [_FakeAddr(socket.AF_INET, "100.64.10.9")],
        }
        stats = {"tailscale0": _FakeStat(True)}
        with patch.dict(os.environ, {"CYBERDECK_IGNORE_VPN": "1"}, clear=False), patch(
            "cyberdeck.net.socket.socket", return_value=fake
        ), patch("cyberdeck.net.psutil.net_if_addrs", return_value=addrs), patch(
            "cyberdeck.net.psutil.net_if_stats", return_value=stats
        ):
            ip = net.get_local_ip()
        self.assertEqual(ip, "100.64.10.9")

    def test_find_free_port_binds_ephemeral_port(self):
        """Validate scenario: test find free port binds ephemeral port."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake = _FakeSocket(ip="127.0.0.1")
        with patch("cyberdeck.net.socket.socket", return_value=fake):
            port = net.find_free_port()
        self.assertEqual(port, 8080)
        self.assertEqual(fake.bound_to, ("", 0))
        self.assertTrue(fake.closed)


if __name__ == "__main__":
    unittest.main()
