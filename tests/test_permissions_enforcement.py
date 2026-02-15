import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

import cyberdeck.api_system as api_system
from cyberdeck import context
from cyberdeck.api_core import router as core_router
from cyberdeck.sessions import DeviceSession
from cyberdeck.video import router as video_router


class PermissionsEnforcementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepare shared fixtures for the test class."""
        app = FastAPI()
        app.include_router(core_router)
        app.include_router(video_router)
        app.include_router(api_system.router)
        cls.client = TestClient(app)

    def setUp(self):
        """Prepare test preconditions for each test case."""
        self._old_sessions = dict(context.device_manager.sessions)
        context.device_manager.sessions = {}

    def tearDown(self):
        """Clean up resources created by each test case."""
        context.device_manager.sessions = self._old_sessions

    @staticmethod
    def _headers(token: str) -> dict:
        """Return authorization headers for the active test session."""
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _add_session(token: str, settings: dict):
        """Register a synthetic session used by the test case."""
        context.device_manager.sessions[token] = DeviceSession(
            device_id=f"perm-{token}",
            device_name=f"Perm {token}",
            ip="127.0.0.1",
            token=token,
            settings=settings,
        )

    def test_upload_denied_without_perm_upload(self):
        """Validate scenario: test upload denied without perm upload."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-upload-deny"
        self._add_session(token, {"perm_upload": False})
        r = self.client.post(
            "/api/file/upload",
            files={"file": ("a.txt", b"x", "text/plain")},
            headers=self._headers(token),
        )
        self.assertEqual(r.status_code, 403, r.text)
        self.assertIn("permission_denied:perm_upload", r.text)

    def test_stream_offer_denied_without_perm_stream(self):
        """Validate scenario: test stream offer denied without perm stream."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-stream-deny"
        self._add_session(token, {"perm_stream": False})
        r = self.client.get("/api/stream_offer", headers=self._headers(token))
        self.assertEqual(r.status_code, 403, r.text)
        self.assertIn("permission_denied:perm_stream", r.text)

    def test_system_shutdown_denied_without_perm_power(self):
        """Validate scenario: test system shutdown denied without perm power."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-power-deny"
        self._add_session(token, {"perm_power": False})
        r = self.client.post("/system/shutdown", headers=self._headers(token))
        self.assertEqual(r.status_code, 403, r.text)
        self.assertIn("permission_denied:perm_power", r.text)

    def test_string_false_in_settings_is_treated_as_false(self):
        """Validate scenario: test string false in settings is treated as false."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-upload-str-false"
        self._add_session(token, {"perm_upload": "false"})
        r = self.client.post(
            "/api/file/upload",
            files={"file": ("b.txt", b"x", "text/plain")},
            headers=self._headers(token),
        )
        self.assertEqual(r.status_code, 403, r.text)
        self.assertIn("permission_denied:perm_upload", r.text)


if __name__ == "__main__":
    unittest.main()
