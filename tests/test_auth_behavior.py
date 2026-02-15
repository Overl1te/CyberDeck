import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

import cyberdeck.auth as auth


class AuthBehaviorTests(unittest.TestCase):
    def test_as_bool_handles_common_input_types(self):
        """Validate scenario: test as bool handles common input types."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        self.assertTrue(auth._as_bool(True))
        self.assertFalse(auth._as_bool(False))
        self.assertTrue(auth._as_bool(1))
        self.assertFalse(auth._as_bool(0))
        self.assertTrue(auth._as_bool(0.1))
        self.assertTrue(auth._as_bool("yes"))
        self.assertTrue(auth._as_bool("on"))
        self.assertFalse(auth._as_bool("off"))
        self.assertFalse(auth._as_bool("false"))
        self.assertFalse(auth._as_bool(""))
        self.assertTrue(auth._as_bool("random-text"))

    def test_get_perm_uses_session_and_default_values(self):
        """Validate scenario: test get perm uses session and default values."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        s = SimpleNamespace(settings={"perm_upload": "0", "perm_power": "1"})
        with patch.object(auth.device_manager, "get_session", return_value=s):
            self.assertFalse(auth.get_perm("tok", "perm_upload"))
            self.assertTrue(auth.get_perm("tok", "perm_power"))
            self.assertTrue(auth.get_perm("tok", "perm_stream"))
            self.assertFalse(auth.get_perm("tok", "perm_unknown"))

    def test_get_perm_handles_broken_settings_object(self):
        """Validate scenario: test get perm handles broken settings object."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        s = SimpleNamespace(settings=object())
        with patch.object(auth.device_manager, "get_session", return_value=s):
            self.assertFalse(auth.get_perm("tok", "perm_unknown"))

    def test_require_perm_raises_for_denied_permission(self):
        """Validate scenario: test require perm raises for denied permission."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch("cyberdeck.auth.get_perm", return_value=False):
            with self.assertRaises(HTTPException) as cm:
                auth.require_perm("tok", "perm_upload")
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("permission_denied:perm_upload", str(cm.exception.detail))

    def test_get_token_accepts_explicit_query_token_param(self):
        """Validate scenario: test get token accepts explicit query token param."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        req = SimpleNamespace(headers={}, query_params={})
        with patch.object(auth.config, "ALLOW_QUERY_TOKEN", True), patch.object(
            auth.device_manager,
            "get_session",
            side_effect=lambda t: t == "tok-query",
        ):
            out = asyncio.run(auth.get_token(req, token="tok-query"))
        self.assertEqual(out, "tok-query")

    def test_get_token_accepts_bearer_header(self):
        """Validate scenario: test get token accepts bearer header."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        req = SimpleNamespace(headers={"Authorization": "Bearer tok-header"}, query_params={})
        with patch.object(auth.config, "ALLOW_QUERY_TOKEN", False), patch.object(
            auth.device_manager,
            "get_session",
            side_effect=lambda t: t == "tok-header",
        ):
            out = asyncio.run(auth.get_token(req, token=None))
        self.assertEqual(out, "tok-header")

    def test_get_token_accepts_ws_query_when_enabled(self):
        """Validate scenario: test get token accepts ws query when enabled."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        req = SimpleNamespace(headers={}, query_params={"token": "tok-ws"})
        with patch.object(auth.config, "ALLOW_QUERY_TOKEN", True), patch.object(
            auth.device_manager,
            "get_session",
            side_effect=lambda t: t == "tok-ws",
        ):
            out = asyncio.run(auth.get_token(req, token=None))
        self.assertEqual(out, "tok-ws")

    def test_get_token_rejects_unauthorized_request(self):
        """Validate scenario: test get token rejects unauthorized request."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        req = SimpleNamespace(headers={"Authorization": "Bearer nope"}, query_params={"token": "nope"})
        with patch.object(auth.config, "ALLOW_QUERY_TOKEN", True), patch.object(
            auth.device_manager,
            "get_session",
            return_value=None,
        ):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(auth.get_token(req, token="bad"))
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn("Unauthorized", str(cm.exception.detail))


if __name__ == "__main__":
    unittest.main()
