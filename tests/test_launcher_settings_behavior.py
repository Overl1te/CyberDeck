import sys
import types
import unittest

if "pystray" not in sys.modules:
    pystray_stub = types.ModuleType("pystray")
    pystray_stub.Menu = lambda *args, **kwargs: None
    pystray_stub.MenuItem = lambda *args, **kwargs: None
    pystray_stub.Icon = lambda *args, **kwargs: None
    sys.modules["pystray"] = pystray_stub

from cyberdeck.launcher.app_startup import AppStartupMixin
from cyberdeck.launcher.settings import DEFAULT_SETTINGS


class LauncherSettingsBehaviorTests(unittest.TestCase):
    def test_default_tls_enabled_for_new_installs(self):
        """Validate scenario: launcher should default to TLS enabled."""
        self.assertTrue(bool(DEFAULT_SETTINGS.get("tls_enabled")))

    def test_normalize_app_config_removes_legacy_token_login_key(self):
        """Validate scenario: deprecated token URL login should be removed from launcher config."""
        fake = types.SimpleNamespace(
            app_config={
                "allow_query_token": True,
                "pairing_single_use": True,
                "ignore_vpn": True,
                "upload_max_bytes": "1024",
                "upload_allowed_ext": "txt, png",
                "verbose_http_log": False,
                "verbose_ws_log": True,
                "verbose_stream_log": False,
                "mdns_enabled": True,
                "device_approval_required": False,
            },
            _normalize_ext_csv=AppStartupMixin._normalize_ext_csv,
        )
        AppStartupMixin._normalize_app_config(fake)
        self.assertNotIn("allow_query_token", fake.app_config)
        self.assertEqual(fake.app_config.get("upload_allowed_ext"), ".txt,.png")


if __name__ == "__main__":
    unittest.main()
