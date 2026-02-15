import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cyberdeck import config
from cyberdeck import context
from cyberdeck.api_core import router as core_router
from cyberdeck.video import router as video_router


class ApiBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepare shared fixtures for the test class."""
        cls._old_allow_query_token = config.ALLOW_QUERY_TOKEN
        cls._old_session_file = config.SESSION_FILE
        cls._old_sessions = dict(context.device_manager.sessions)
        cls._tmp = tempfile.TemporaryDirectory()
        config.SESSION_FILE = os.path.join(cls._tmp.name, "cyberdeck_sessions.json")
        context.device_manager.sessions = {}
        config.PAIRING_CODE = "1234"
        config.ALLOW_QUERY_TOKEN = False
        app = FastAPI()
        app.include_router(core_router)
        app.include_router(video_router)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        """Clean up shared fixtures for the test class."""
        config.ALLOW_QUERY_TOKEN = cls._old_allow_query_token
        context.device_manager.sessions = cls._old_sessions
        config.SESSION_FILE = cls._old_session_file
        cls._tmp.cleanup()

    def _token(self) -> str:
        """Return active session token used by test requests."""
        r = self.client.post(
            "/api/handshake",
            json={"code": "1234", "device_id": "api-behavior-1", "device_name": "API Behavior"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return str(r.json()["token"])

    @staticmethod
    def _auth_headers(token: str, **extra: str) -> dict:
        """Return authorization headers for test API requests."""
        out = {"Authorization": f"Bearer {token}"}
        out.update(extra)
        return out

    def test_upload_checksum_validation(self):
        """Validate scenario: test upload checksum validation."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = self._token()
        data = b"hello cyberdeck"
        good = hashlib.sha256(data).hexdigest()

        ok = self.client.post(
            "/api/file/upload",
            files={"file": ("sample.txt", data, "text/plain")},
            headers=self._auth_headers(token, **{"X-File-Sha256": good}),
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        body = ok.json()
        self.assertEqual(body.get("status"), "ok")
        self.assertEqual(body.get("sha256"), good)

        bad = self.client.post(
            "/api/file/upload",
            files={"file": ("sample-bad.txt", data, "text/plain")},
            headers=self._auth_headers(token, **{"X-File-Sha256": "deadbeef"}),
        )
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertIn("upload_checksum_mismatch", bad.text)

    def test_stream_offer_has_adaptive_hints(self):
        """Validate scenario: test stream offer has adaptive hints."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = self._token()
        r = self.client.get("/api/stream_offer", headers=self._auth_headers(token))
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("adaptive_hint", body)
        self.assertIn("reconnect_hint_ms", body)
        hint = body.get("adaptive_hint") or {}
        self.assertIsInstance(hint, dict)
        self.assertIn("decrease_step", hint)
        self.assertIn("increase_step", hint)

    def test_query_token_is_rejected_by_default(self):
        """Validate scenario: test query token is rejected by default."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = self._token()
        r = self.client.get(f"/api/stream_offer?token={token}")
        self.assertEqual(r.status_code, 403, r.text)
        self.assertIn("Unauthorized", r.text)

    def test_handshake_rejects_expired_pairing_window(self):
        """Validate scenario: test handshake rejects expired pairing window."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        old_exp = getattr(config, "PAIRING_EXPIRES_AT", None)
        try:
            config.PAIRING_EXPIRES_AT = 1.0
            with patch("cyberdeck.api_core.time.time", return_value=2.0):
                r = self.client.post(
                    "/api/handshake",
                    json={"code": "1234", "device_id": "expired-1", "device_name": "Expired"},
                )
        finally:
            config.PAIRING_EXPIRES_AT = old_exp
        self.assertEqual(r.status_code, 403, r.text)
        self.assertIn("pairing_expired", r.text)

    def test_handshake_rejects_rate_limited_client(self):
        """Validate scenario: test handshake rejects rate limited client."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch("cyberdeck.api_core.pin_limiter.check", return_value=(False, 4.2)):
            r = self.client.post(
                "/api/handshake",
                json={"code": "1234", "device_id": "rate-limit-1", "device_name": "Rate Limited"},
            )
        self.assertEqual(r.status_code, 429, r.text)
        self.assertEqual(r.headers.get("retry-after"), "4")
        self.assertIn("pin_rate_limited", r.text)

    def test_handshake_rejects_invalid_pairing_code(self):
        """Validate scenario: test handshake rejects invalid pairing code."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch("cyberdeck.api_core.pin_limiter.check", return_value=(True, 0)), patch(
            "cyberdeck.api_core.pin_limiter.record_failure"
        ) as mfail:
            r = self.client.post(
                "/api/handshake",
                json={"code": "0000", "device_id": "bad-code-1", "device_name": "Bad Code"},
            )
        self.assertEqual(r.status_code, 403, r.text)
        self.assertIn("Invalid Code", r.text)
        mfail.assert_called_once()


if __name__ == "__main__":
    unittest.main()
