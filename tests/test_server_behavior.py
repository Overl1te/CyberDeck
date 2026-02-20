import importlib
import os
import sys
import unittest
from unittest.mock import patch


class _FakeSocket:
    def __init__(self, should_fail: bool = False):
        """Initialize _FakeSocket state and collaborator references."""
        self.should_fail = should_fail
        self.bound_to = None

    def bind(self, addr):
        """Bind the target operation."""
        self.bound_to = addr
        if self.should_fail:
            raise OSError("bind failed")

    def __enter__(self):
        """Enter the managed runtime context."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the managed runtime context and release resources."""
        return False


class ServerBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepare shared fixtures for the test class."""
        if "cyberdeck.server" in sys.modules:
            del sys.modules["cyberdeck.server"]
        with patch("cyberdeck.discovery.start_udp_discovery", lambda: None):
            cls.server = importlib.import_module("cyberdeck.server")

    def test_sanitize_url_masks_sensitive_tokens(self):
        """Validate scenario: test sanitize url masks sensitive tokens."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        out = self.server._sanitize_url_for_log(
            "http://x.local/path?token=abc&t=xyz&auth=qwe&safe=ok"
        )
        self.assertIn("/path?", out)
        self.assertIn("token=%2A%2A%2A", out)
        self.assertIn("t=%2A%2A%2A", out)
        self.assertIn("auth=%2A%2A%2A", out)
        self.assertIn("safe=ok", out)

    def test_sanitize_url_trims_very_long_values(self):
        """Validate scenario: test sanitize url trims very long values."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        long_val = "x" * 120
        out = self.server._sanitize_url_for_log(f"https://host/a?name={long_val}")
        self.assertIn("/a?", out)
        self.assertIn("...", out)

    def test_sanitize_url_fallback_for_invalid_input(self):
        """Validate scenario: test sanitize url fallback for invalid input."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        out = self.server._sanitize_url_for_log(None)
        self.assertEqual(out, "")

    def test_port_available_true_when_bind_succeeds(self):
        """Validate scenario: test port available true when bind succeeds."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake = _FakeSocket(should_fail=False)
        with patch("cyberdeck.server.socket.socket", return_value=fake):
            ok = self.server._port_available(8080)
        self.assertTrue(ok)
        self.assertIsNotNone(fake.bound_to)

    def test_port_available_false_when_bind_fails(self):
        """Validate scenario: test port available false when bind fails."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake = _FakeSocket(should_fail=True)
        with patch("cyberdeck.server.socket.socket", return_value=fake):
            ok = self.server._port_available(8080)
        self.assertFalse(ok)

    def test_run_parses_wayland_auto_setup_boolean_words(self):
        """Validate scenario: run should parse CYBERDECK_WAYLAND_AUTO_SETUP using bool-like words."""
        with patch.dict(os.environ, {"CYBERDECK_WAYLAND_AUTO_SETUP": "off"}, clear=False), patch.object(
            self.server, "is_linux_wayland_session", return_value=True
        ), patch.object(
            self.server, "ensure_wayland_ready", return_value=(True, [], False, "already_ready")
        ) as mready, patch.object(
            self.server, "start_mdns", return_value=None
        ), patch.object(
            self.server, "_port_available", return_value=True
        ), patch.object(
            self.server.config, "PORT_AUTO", False
        ), patch.object(
            self.server.config, "MDNS_ENABLED", False
        ), patch.object(
            self.server.uvicorn, "run", return_value=None
        ):
            self.server.run()

        self.assertTrue(mready.called)
        kwargs = mready.call_args.kwargs
        self.assertIn("auto_install", kwargs)
        self.assertFalse(kwargs["auto_install"])

    def test_run_treats_yes_as_enabled_wayland_auto_setup(self):
        """Validate scenario: run should treat 'yes' as enabled auto setup."""
        with patch.dict(os.environ, {"CYBERDECK_WAYLAND_AUTO_SETUP": "yes"}, clear=False), patch.object(
            self.server, "is_linux_wayland_session", return_value=True
        ), patch.object(
            self.server, "ensure_wayland_ready", return_value=(True, [], False, "already_ready")
        ) as mready, patch.object(
            self.server, "start_mdns", return_value=None
        ), patch.object(
            self.server, "_port_available", return_value=True
        ), patch.object(
            self.server.config, "PORT_AUTO", False
        ), patch.object(
            self.server.config, "MDNS_ENABLED", False
        ), patch.object(
            self.server.uvicorn, "run", return_value=None
        ):
            self.server.run()

        self.assertTrue(mready.called)
        kwargs = mready.call_args.kwargs
        self.assertIn("auto_install", kwargs)
        self.assertTrue(kwargs["auto_install"])


if __name__ == "__main__":
    unittest.main()
