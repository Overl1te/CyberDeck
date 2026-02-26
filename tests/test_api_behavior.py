import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cyberdeck import config
from cyberdeck import context
from cyberdeck.api.core import router as core_router
from cyberdeck.video import router as video_router


class ApiBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepare shared fixtures for the test class."""
        cls._old_allow_query_token = config.ALLOW_QUERY_TOKEN
        cls._old_pairing_single_use = config.PAIRING_SINGLE_USE
        cls._old_session_file = config.SESSION_FILE
        cls._old_sessions = dict(context.device_manager.sessions)
        cls._tmp = tempfile.TemporaryDirectory()
        config.SESSION_FILE = os.path.join(cls._tmp.name, "cyberdeck_sessions.json")
        context.device_manager.sessions = {}
        config.PAIRING_CODE = "1234"
        config.ALLOW_QUERY_TOKEN = False
        config.PAIRING_SINGLE_USE = False
        app = FastAPI()
        app.include_router(core_router)
        app.include_router(video_router)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        """Clean up shared fixtures for the test class."""
        config.ALLOW_QUERY_TOKEN = cls._old_allow_query_token
        config.PAIRING_SINGLE_USE = cls._old_pairing_single_use
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

    def setUp(self):
        """Prepare test preconditions for each test case."""
        context.input_guard.set_locked(False, reason="test_reset", actor="tests")

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
        self.assertIn("min_quality", hint)
        self.assertIn("max_quality", hint)

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
            with patch("cyberdeck.api.core.time.time", return_value=2.0):
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
        with patch("cyberdeck.api.core.pin_limiter.check", return_value=(False, 4.2)):
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
        with patch("cyberdeck.api.core.pin_limiter.check", return_value=(True, 0)), patch(
            "cyberdeck.api.core.pin_limiter.record_failure"
        ) as mfail:
            r = self.client.post(
                "/api/handshake",
                json={"code": "0000", "device_id": "bad-code-1", "device_name": "Bad Code"},
            )
        self.assertEqual(r.status_code, 403, r.text)
        self.assertIn("Invalid Code", r.text)
        mfail.assert_called_once()

    def test_handshake_rotates_pairing_code_when_single_use_is_enabled(self):
        """Validate scenario: single-use pairing mode rotates code after successful handshake."""
        old_single_use = config.PAIRING_SINGLE_USE
        old_code = config.PAIRING_CODE
        try:
            config.PAIRING_SINGLE_USE = True
            config.PAIRING_CODE = "1234"
            with patch("cyberdeck.api.core.rotate_pairing_code", return_value="9999") as mrotate, patch(
                "cyberdeck.api.core.pin_limiter.reset"
            ) as mreset:
                r = self.client.post(
                    "/api/handshake",
                    json={"code": "1234", "device_id": "single-use-1", "device_name": "Single Use"},
                )
        finally:
            config.PAIRING_SINGLE_USE = old_single_use
            config.PAIRING_CODE = old_code
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body.get("pairing_rotated"))
        mrotate.assert_called_once()
        mreset.assert_called_once()

    def test_pairing_status_reports_pending_then_approved(self):
        """Validate scenario: pairing status endpoint should reflect approval transitions for the same token."""
        old_required = config.DEVICE_APPROVAL_REQUIRED
        try:
            config.DEVICE_APPROVAL_REQUIRED = True
            r = self.client.post(
                "/api/handshake",
                json={"code": "1234", "device_id": "pending-status-1", "device_name": "Pending Status"},
            )
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            token = str(body.get("token") or "")
            self.assertTrue(token)
            self.assertFalse(bool(body.get("approved", True)))

            p1 = self.client.get("/api/pairing_status", params={"token": token})
            self.assertEqual(p1.status_code, 200, p1.text)
            self.assertFalse(bool(p1.json().get("approved", True)))
            self.assertTrue(bool(p1.json().get("approval_pending", False)))

            self.assertTrue(context.device_manager.set_approved(token, True))
            p2 = self.client.get("/api/pairing_status", params={"token": token})
            self.assertEqual(p2.status_code, 200, p2.text)
            self.assertTrue(bool(p2.json().get("approved", False)))
            self.assertFalse(bool(p2.json().get("approval_pending", True)))
        finally:
            config.DEVICE_APPROVAL_REQUIRED = old_required

    def test_pairing_status_rejects_missing_or_unknown_token(self):
        """Validate scenario: pairing status endpoint should validate token presence and existence."""
        missing = self.client.get("/api/pairing_status")
        self.assertEqual(missing.status_code, 400, missing.text)
        self.assertIn("token_required", missing.text)

        unknown = self.client.get("/api/pairing_status", params={"token": "missing-token"})
        self.assertEqual(unknown.status_code, 404, unknown.text)
        self.assertIn("session_not_found", unknown.text)

    def test_stats_tolerates_psutil_errors(self):
        """Validate scenario: test stats tolerates psutil errors."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = self._token()
        with patch("cyberdeck.api.core.psutil.cpu_percent", side_effect=RuntimeError("cpu-error")), patch(
            "cyberdeck.api.core.psutil.virtual_memory",
            side_effect=RuntimeError("ram-error"),
        ):
            r = self.client.get("/api/stats", headers=self._auth_headers(token))
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body.get("cpu"), 0.0)
        self.assertEqual(body.get("ram"), 0.0)

    def test_diag_tolerates_psutil_errors(self):
        """Validate scenario: test diag tolerates psutil errors."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = self._token()
        with patch("cyberdeck.api.core.psutil.cpu_percent", side_effect=RuntimeError("cpu-error")), patch(
            "cyberdeck.api.core.psutil.virtual_memory",
            side_effect=RuntimeError("ram-error"),
        ):
            r = self.client.get("/api/diag", headers=self._auth_headers(token))
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body.get("cpu"), 0.0)
        self.assertEqual(body.get("ram"), 0.0)

    def test_audio_stream_returns_503_when_backend_is_unavailable(self):
        """Validate scenario: audio relay endpoint should surface backend failure as 503."""
        token = self._token()
        with patch("cyberdeck.video.api._ffmpeg_audio_stream", return_value=None), patch(
            "cyberdeck.video.api._get_ffmpeg_diag",
            return_value={"ffmpeg_last_error": "audio_probe_failed"},
        ):
            r = self.client.get("/audio_stream", headers=self._auth_headers(token))
        self.assertEqual(r.status_code, 503, r.text)
        self.assertIn("audio_probe_failed", r.text)

    def test_audio_stream_returns_backend_response_when_available(self):
        """Validate scenario: audio relay endpoint should forward backend stream response."""
        token = self._token()
        with patch("cyberdeck.video.api._ffmpeg_audio_stream", return_value={"status": "ok"}):
            r = self.client.get("/audio_stream", headers=self._auth_headers(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("status"), "ok")


if __name__ == "__main__":
    unittest.main()

