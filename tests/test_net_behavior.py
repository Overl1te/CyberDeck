import unittest
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


class NetBehaviorTests(unittest.TestCase):
    def test_get_local_ip_returns_socket_address_on_success(self):
        """Validate scenario: test get local ip returns socket address on success."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake = _FakeSocket(ip="10.0.0.42", raise_connect=False)
        with patch("cyberdeck.net.socket.socket", return_value=fake):
            ip = net.get_local_ip()
        self.assertEqual(ip, "10.0.0.42")
        self.assertEqual(fake.connected_to, ("10.255.255.255", 1))
        self.assertTrue(fake.closed)

    def test_get_local_ip_falls_back_to_loopback_on_error(self):
        """Validate scenario: test get local ip falls back to loopback on error."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake = _FakeSocket(raise_connect=True)
        with patch("cyberdeck.net.socket.socket", return_value=fake):
            ip = net.get_local_ip()
        self.assertEqual(ip, "127.0.0.1")
        self.assertTrue(fake.closed)

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
