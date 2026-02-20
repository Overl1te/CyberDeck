import importlib
import os
import unittest
from unittest.mock import patch

import cyberdeck.ws.mouse as ws_mouse


class WsEnvBehaviorTests(unittest.TestCase):
    def tearDown(self):
        """Restore ws_mouse module constants after each env-driven test."""
        importlib.reload(ws_mouse)

    def test_module_reload_tolerates_invalid_mouse_env_values(self):
        """Validate scenario: invalid numeric mouse env values should not break import-time setup."""
        env = {
            "CYBERDECK_MOUSE_GAIN": "broken",
            "CYBERDECK_MOUSE_MAX_DELTA": "broken",
            "CYBERDECK_MOUSE_DEADZONE": "broken",
            "CYBERDECK_MOUSE_LAG_DAMP_START_S": "broken",
            "CYBERDECK_MOUSE_LAG_DAMP_MIN": "broken",
        }
        with patch.dict(os.environ, env, clear=False):
            mod = importlib.reload(ws_mouse)

        self.assertTrue(0.1 <= mod._MOUSE_GAIN <= 8.0)
        self.assertGreaterEqual(mod._MOUSE_MAX_DELTA, 8)
        self.assertTrue(0.0 <= mod._MOUSE_DEADZONE <= 2.0)
        self.assertTrue(0.01 <= mod._MOUSE_LAG_DAMP_START_S <= 1.0)
        self.assertTrue(0.1 <= mod._MOUSE_LAG_DAMP_MIN <= 1.0)

    def test_safe_screen_size_falls_back_when_env_is_invalid(self):
        """Validate scenario: safe screen size should fall back to defaults for malformed env."""
        with patch.dict(
            os.environ,
            {"CYBERDECK_STREAM_W": "bad", "CYBERDECK_STREAM_H": "bad"},
            clear=False,
        ), patch.object(ws_mouse.INPUT_BACKEND, "screen_size", return_value=None):
            w, h = ws_mouse._safe_screen_size()
        self.assertEqual((w, h), (1920, 1080))

    def test_safe_screen_size_uses_valid_env_values_when_backend_size_missing(self):
        """Validate scenario: env stream dimensions should be respected when backend size is unavailable."""
        with patch.dict(
            os.environ,
            {"CYBERDECK_STREAM_W": "1366", "CYBERDECK_STREAM_H": "768"},
            clear=False,
        ), patch.object(ws_mouse.INPUT_BACKEND, "screen_size", return_value=None):
            w, h = ws_mouse._safe_screen_size()
        self.assertEqual((w, h), (1366, 768))

    def test_env_bool_supports_common_true_false_forms(self):
        """Validate scenario: bool helper should parse common textual values."""
        with patch.dict(os.environ, {"CYBERDECK_WS_PROTO_PUSH": "off"}, clear=False):
            self.assertFalse(ws_mouse._env_bool("CYBERDECK_WS_PROTO_PUSH", True))
        with patch.dict(os.environ, {"CYBERDECK_WS_PROTO_PUSH": "yes"}, clear=False):
            self.assertTrue(ws_mouse._env_bool("CYBERDECK_WS_PROTO_PUSH", False))


if __name__ == "__main__":
    unittest.main()

