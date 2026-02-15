import importlib
import os
import unittest
from unittest.mock import patch

import cyberdeck.config as config


class ConfigBehaviorTests(unittest.TestCase):
    def setUp(self):
        """Prepare test preconditions for each test case."""
        self._state = {
            "PORT": config.PORT,
            "PORT_AUTO": config.PORT_AUTO,
            "MDNS_ENABLED": config.MDNS_ENABLED,
            "DEBUG": config.DEBUG,
            "CONSOLE_LOG": config.CONSOLE_LOG,
            "LOG_ENABLED": config.LOG_ENABLED,
            "STREAM_MONITOR": config.STREAM_MONITOR,
            "PROTOCOL_VERSION": config.PROTOCOL_VERSION,
            "MIN_SUPPORTED_PROTOCOL_VERSION": config.MIN_SUPPORTED_PROTOCOL_VERSION,
            "WS_HEARTBEAT_INTERVAL_S": config.WS_HEARTBEAT_INTERVAL_S,
            "WS_HEARTBEAT_TIMEOUT_S": config.WS_HEARTBEAT_TIMEOUT_S,
            "VERBOSE_STREAM_LOG": config.VERBOSE_STREAM_LOG,
            "VERBOSE_WS_LOG": config.VERBOSE_WS_LOG,
            "VERBOSE_HTTP_LOG": config.VERBOSE_HTTP_LOG,
            "CORS_ORIGINS": list(config.CORS_ORIGINS),
            "CORS_ALLOW_CREDENTIALS": config.CORS_ALLOW_CREDENTIALS,
            "ALLOW_QUERY_TOKEN": config.ALLOW_QUERY_TOKEN,
            "TLS_CERT": config.TLS_CERT,
            "TLS_KEY": config.TLS_KEY,
            "TLS_ENABLED": config.TLS_ENABLED,
            "SCHEME": config.SCHEME,
            "PAIRING_TTL_S": config.PAIRING_TTL_S,
            "PAIRING_EXPIRES_AT": config.PAIRING_EXPIRES_AT,
            "QR_TOKEN_TTL_S": config.QR_TOKEN_TTL_S,
            "UPLOAD_MAX_BYTES": config.UPLOAD_MAX_BYTES,
            "UPLOAD_ALLOWED_EXT": list(config.UPLOAD_ALLOWED_EXT),
            "TRANSFER_SCHEME": config.TRANSFER_SCHEME,
            "PIN_STATE_STALE_S": config.PIN_STATE_STALE_S,
            "PIN_STATE_MAX_IPS": config.PIN_STATE_MAX_IPS,
            "PAIRING_CODE": config.PAIRING_CODE,
        }

    def tearDown(self):
        """Clean up resources created by each test case."""
        for key, value in self._state.items():
            setattr(config, key, value)

    def test_csv_list_trims_and_deduplicates(self):
        """Validate scenario: test csv list trims and deduplicates."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        out = config._csv_list("  a, b ,a,, c  ")
        self.assertEqual(out, ["a", "b", "c"])

    def test_reload_from_env_updates_runtime_flags(self):
        """Validate scenario: test reload from env updates runtime flags."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        env = {
            "CYBERDECK_PORT": "9090",
            "CYBERDECK_PORT_AUTO": "0",
            "CYBERDECK_MDNS": "0",
            "CYBERDECK_DEBUG": "1",
            "CYBERDECK_CONSOLE": "1",
            "CYBERDECK_LOG": "1",
            "CYBERDECK_STREAM_MONITOR": "2",
            "CYBERDECK_PROTOCOL_VERSION": "5",
            "CYBERDECK_MIN_PROTOCOL_VERSION": "3",
            "CYBERDECK_WS_HEARTBEAT_INTERVAL_S": "10",
            "CYBERDECK_WS_HEARTBEAT_TIMEOUT_S": "25",
            "CYBERDECK_VERBOSE_STREAM_LOG": "0",
            "CYBERDECK_VERBOSE_WS_LOG": "0",
            "CYBERDECK_VERBOSE_HTTP_LOG": "0",
            "CYBERDECK_CORS_ORIGINS": "http://a.test, http://b.test",
            "CYBERDECK_CORS_ALLOW_CREDENTIALS": "1",
            "CYBERDECK_ALLOW_QUERY_TOKEN": "1",
            "CYBERDECK_TLS": "1",
            "CYBERDECK_TLS_CERT": "/tmp/cert.pem",
            "CYBERDECK_TLS_KEY": "/tmp/key.pem",
            "CYBERDECK_PAIRING_TTL_S": "30",
            "CYBERDECK_QR_TOKEN_TTL_S": "90",
            "CYBERDECK_UPLOAD_MAX_BYTES": "1000",
            "CYBERDECK_UPLOAD_ALLOWED_EXT": ".txt,.zip",
            "CYBERDECK_TRANSFER_SCHEME": "https",
            "CYBERDECK_PIN_STATE_STALE_S": "111",
            "CYBERDECK_PIN_STATE_MAX_IPS": "222",
            "CYBERDECK_PAIRING_CODE": "987654",
        }
        with patch.dict(os.environ, env, clear=False), patch("cyberdeck.config.time.time", return_value=100.0):
            config.reload_from_env()

        self.assertEqual(config.PORT, 9090)
        self.assertFalse(config.PORT_AUTO)
        self.assertFalse(config.MDNS_ENABLED)
        self.assertTrue(config.DEBUG)
        self.assertTrue(config.CONSOLE_LOG)
        self.assertTrue(config.LOG_ENABLED)
        self.assertEqual(config.STREAM_MONITOR, 2)
        self.assertEqual(config.PROTOCOL_VERSION, 5)
        self.assertEqual(config.MIN_SUPPORTED_PROTOCOL_VERSION, 3)
        self.assertEqual(config.WS_HEARTBEAT_INTERVAL_S, 10)
        self.assertEqual(config.WS_HEARTBEAT_TIMEOUT_S, 25)
        self.assertFalse(config.VERBOSE_STREAM_LOG)
        self.assertFalse(config.VERBOSE_WS_LOG)
        self.assertFalse(config.VERBOSE_HTTP_LOG)
        self.assertEqual(config.CORS_ORIGINS, ["http://a.test", "http://b.test"])
        self.assertTrue(config.CORS_ALLOW_CREDENTIALS)
        self.assertTrue(config.ALLOW_QUERY_TOKEN)
        self.assertTrue(config.TLS_ENABLED)
        self.assertEqual(config.SCHEME, "https")
        self.assertEqual(config.PAIRING_EXPIRES_AT, 130.0)
        self.assertEqual(config.QR_TOKEN_TTL_S, 90)
        self.assertEqual(config.UPLOAD_MAX_BYTES, 1000)
        self.assertEqual(config.UPLOAD_ALLOWED_EXT, [".txt", ".zip"])
        self.assertEqual(config.TRANSFER_SCHEME, "https")
        self.assertEqual(config.PIN_STATE_STALE_S, 111)
        self.assertEqual(config.PIN_STATE_MAX_IPS, 222)
        self.assertEqual(config.PAIRING_CODE, "9876")

    def test_reload_from_env_disables_credentials_when_wildcard_origin(self):
        """Validate scenario: test reload from env disables credentials when wildcard origin."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch.dict(
            os.environ,
            {
                "CYBERDECK_CORS_ORIGINS": "*",
                "CYBERDECK_CORS_ALLOW_CREDENTIALS": "1",
                "CYBERDECK_TLS": "0",
            },
            clear=False,
        ):
            config.reload_from_env()
        self.assertEqual(config.CORS_ORIGINS, ["*"])
        self.assertFalse(config.CORS_ALLOW_CREDENTIALS)
        self.assertEqual(config.SCHEME, "http")

    def test_module_reload_uses_non_frozen_base_dir_branch(self):
        """Validate scenario: test module reload uses non frozen base dir branch."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        mod = importlib.reload(config)
        self.assertTrue(os.path.isabs(mod.BASE_DIR))
        self.assertTrue(mod.SESSION_FILE.endswith("cyberdeck_sessions.json"))
        # Restore globals from the reloaded module side-effects.
        importlib.reload(config)


if __name__ == "__main__":
    unittest.main()
