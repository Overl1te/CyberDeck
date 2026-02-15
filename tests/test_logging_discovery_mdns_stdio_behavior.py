import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

import cyberdeck.discovery as discovery
import cyberdeck.logging_config as logging_config
import cyberdeck.mdns as mdns
import cyberdeck.stdio as stdio


class LoggingDiscoveryMdnsStdioBehaviorTests(unittest.TestCase):
    def test_ensure_null_stdio_restores_missing_streams(self):
        """Validate scenario: test ensure null stdio restores missing streams."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        old_out = sys.stdout
        old_err = sys.stderr
        new_out = None
        new_err = None
        try:
            sys.stdout = None
            sys.stderr = None
            stdio.ensure_null_stdio()
            new_out = sys.stdout
            new_err = sys.stderr
            self.assertIsNotNone(sys.stdout)
            self.assertIsNotNone(sys.stderr)
        finally:
            for h in (new_out, new_err):
                try:
                    if h not in (None, old_out, old_err):
                        h.close()
                except Exception:
                    pass
            sys.stdout = old_out
            sys.stderr = old_err

    def test_setup_logging_when_disabled_uses_null_handler(self):
        """Validate scenario: test setup logging when disabled uses null handler."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch.object(logging_config.config, "LOG_ENABLED", False), patch.object(
            logging_config.config, "BASE_DIR", tempfile.gettempdir()
        ):
            logger = logging_config.setup_logging()
        self.assertTrue(any(h.__class__.__name__ == "NullHandler" for h in logger.handlers))

    def test_reload_logging_rebuilds_handlers(self):
        """Validate scenario: test reload logging rebuilds handlers."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with tempfile.TemporaryDirectory() as td, patch.object(logging_config.config, "BASE_DIR", td), patch.object(
            logging_config.config, "LOG_FILE", os.path.join(td, "cyberdeck.log")
        ), patch.object(
            logging_config.config, "LOG_ENABLED", True
        ), patch.object(
            logging_config.config, "CONSOLE_LOG", False
        ), patch.object(
            logging_config.config, "DEBUG", False
        ):
            logger = logging_config.reload_logging()
            self.assertGreaterEqual(len(logger.handlers), 1)
            for h in list(logger.handlers):
                try:
                    h.close()
                except Exception:
                    pass
            logger.handlers.clear()

    def test_udp_discovery_service_replies_with_nonce(self):
        """Validate scenario: test udp discovery service replies with nonce."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        class _StopLoop(BaseException):
            """Stop infinite discovery loop in test after first response."""

        fake_sock = MagicMock()
        fake_sock.recvfrom.side_effect = [
            (b"CYBERDECK_DISCOVER:abc123", ("1.2.3.4", 9999)),
            _StopLoop(),
        ]

        with patch("cyberdeck.discovery.socket.socket", return_value=fake_sock), patch.object(
            discovery.config, "UDP_PORT", 5555
        ), patch.object(
            discovery.config, "PROTOCOL_VERSION", 2
        ), patch.object(
            discovery.config, "SERVER_ID", "srv-id"
        ), patch.object(
            discovery.config, "HOSTNAME", "host"
        ), patch.object(
            discovery.config, "PORT", 8080
        ), patch.object(
            discovery.config, "VERSION", "v"
        ), patch.object(
            discovery.config, "SCHEME", "http"
        ):
            with self.assertRaises(_StopLoop):
                discovery.udp_discovery_service()

        self.assertTrue(fake_sock.sendto.called)
        payload = fake_sock.sendto.call_args[0][0].decode("utf-8")
        self.assertIn('"nonce": "abc123"', payload)

    def test_start_udp_discovery_starts_background_thread(self):
        """Validate scenario: test start udp discovery starts background thread."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake_thread = MagicMock()
        with patch("cyberdeck.discovery.threading.Thread", return_value=fake_thread) as mthread:
            discovery.start_udp_discovery()
        mthread.assert_called_once()
        fake_thread.start.assert_called_once()

    def test_start_mdns_returns_none_when_zeroconf_missing(self):
        """Validate scenario: test start mdns returns none when zeroconf missing."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        real_import = __import__

        def _imp(name, *args, **kwargs):
            """Raise import error for zeroconf only."""
            if name == "zeroconf":
                raise ImportError("no zeroconf")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_imp):
            out = mdns.start_mdns()
        self.assertIsNone(out)

    def test_start_mdns_success_registers_cleanup(self):
        """Validate scenario: test start mdns success registers cleanup."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake_zc = MagicMock()
        fake_info = object()
        fake_service_info = MagicMock(return_value=fake_info)
        fake_module = types.SimpleNamespace(ServiceInfo=fake_service_info, Zeroconf=MagicMock(return_value=fake_zc))

        real_import = __import__

        def _imp(name, *args, **kwargs):
            """Return fake zeroconf module for deterministic mdns tests."""
            if name == "zeroconf":
                return fake_module
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_imp), patch(
            "cyberdeck.mdns.get_local_ip", return_value="127.0.0.1"
        ), patch.object(
            mdns.config, "SERVER_ID", "srv"
        ), patch.object(
            mdns.config, "VERSION", "v1"
        ), patch.object(
            mdns.config, "HOSTNAME", "host"
        ), patch.object(
            mdns.config, "UDP_PORT", 5555
        ), patch.object(
            mdns.config, "SCHEME", "http"
        ), patch.object(
            mdns.config, "PORT", 8080
        ), patch(
            "cyberdeck.mdns.atexit.register"
        ) as mareg:
            out = mdns.start_mdns()

        self.assertIsNotNone(out)
        fake_zc.register_service.assert_called_once_with(fake_info)
        mareg.assert_called_once()


if __name__ == "__main__":
    unittest.main()
