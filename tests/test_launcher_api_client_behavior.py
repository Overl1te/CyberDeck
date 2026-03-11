import unittest
from unittest.mock import patch

import requests

from cyberdeck.launcher.api_client import LauncherApiClient


class LauncherApiClientBehaviorTests(unittest.TestCase):
    def test_configure_normalizes_url(self):
        """Validate scenario: test configure normalizes url."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        c = LauncherApiClient("http://127.0.0.1:8080/api/local/")
        self.assertEqual(c.base_url, "http://127.0.0.1:8080/api/local")
        c.configure("https://localhost:9999/x///", verify=False)
        self.assertEqual(c.base_url, "https://localhost:9999/x")
        self.assertFalse(c.verify)

    def test_get_info_calls_requests_get_with_expected_args(self):
        """Validate scenario: test get info calls requests get with expected args."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        c = LauncherApiClient("http://127.0.0.1:8080/api/local", verify=False)
        with patch("cyberdeck.launcher.api_client.requests.get") as mget:
            c.get_info(timeout=1.25)
        mget.assert_called_once_with(
            "http://127.0.0.1:8080/api/local/info",
            timeout=1.25,
            verify=False,
        )

    def test_device_settings_posts_payload(self):
        """Validate scenario: test device settings posts payload."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        c = LauncherApiClient("http://127.0.0.1:8080/api/local", verify=True)
        payload = {"token": "abc", "settings": {"perm_stream": True}}
        with patch("cyberdeck.launcher.api_client.requests.post") as mpost:
            c.device_settings(payload, timeout=2.5)
        mpost.assert_called_once_with(
            "http://127.0.0.1:8080/api/local/device_settings",
            json=payload,
            timeout=2.5,
            verify=True,
        )

    def test_regenerate_code_posts_without_payload(self):
        """Validate scenario: test regenerate code posts without payload."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        c = LauncherApiClient("http://127.0.0.1:8080/api/local")
        with patch("cyberdeck.launcher.api_client.requests.post") as mpost:
            c.regenerate_code(timeout=3.0)
        mpost.assert_called_once_with(
            "http://127.0.0.1:8080/api/local/regenerate_code",
            json=None,
            timeout=3.0,
            verify=True,
        )

    def test_set_input_lock_posts_payload(self):
        """Validate scenario: input lock client call should post lock payload."""
        c = LauncherApiClient("http://127.0.0.1:8080/api/local")
        with patch("cyberdeck.launcher.api_client.requests.post") as mpost:
            c.set_input_lock(True, reason="test", actor="launcher", timeout=2.0)
        mpost.assert_called_once_with(
            "http://127.0.0.1:8080/api/local/input_lock",
            json={"locked": True, "reason": "test", "actor": "launcher"},
            timeout=2.0,
            verify=True,
        )

    def test_panic_mode_posts_payload(self):
        """Validate scenario: panic mode client call should post revoke/lock payload."""
        c = LauncherApiClient("http://127.0.0.1:8080/api/local")
        with patch("cyberdeck.launcher.api_client.requests.post") as mpost:
            c.panic_mode(keep_token="tok", lock_input=True, reason="panic", timeout=4.0)
        mpost.assert_called_once_with(
            "http://127.0.0.1:8080/api/local/panic_mode",
            json={"keep_token": "tok", "lock_input": True, "reason": "panic"},
            timeout=4.0,
            verify=True,
        )

    def test_json_dict_returns_fallback_for_invalid_payload(self):
        """Validate scenario: json dict helper should return fallback on invalid payload."""
        c = LauncherApiClient("http://127.0.0.1:8080/api/local")
        resp = type("R", (), {"json": lambda self: ["not", "a", "dict"]})()
        self.assertEqual(c.json_dict(resp, default={"x": 1}), {"x": 1})

    def test_describe_api_error_prefers_structured_error_fields(self):
        """Validate scenario: structured API payload should produce readable error string."""
        c = LauncherApiClient("http://127.0.0.1:8080/api/local")
        payload = {
            "detail": "ignored detail",
            "error": {
                "code": "CD-3001",
                "title": "Bad extension",
                "hint": "Upload allowed extension",
            },
        }
        resp = type("R", (), {"status_code": 415, "json": lambda self: payload})()
        msg = c.describe_api_error(resp)
        self.assertIn("CD-3001", msg)
        self.assertIn("Bad extension", msg)
        self.assertIn("Upload allowed extension", msg)

    def test_describe_exception_handles_common_requests_errors(self):
        """Validate scenario: transport exceptions should be normalized for UI."""
        c = LauncherApiClient("http://127.0.0.1:8080/api/local")
        self.assertEqual(c.describe_exception(requests.Timeout()), "request timeout")
        self.assertEqual(c.describe_exception(requests.ConnectionError()), "connection failed")
        self.assertEqual(c.describe_exception(requests.exceptions.SSLError()), "TLS verification failed")


if __name__ == "__main__":
    unittest.main()
