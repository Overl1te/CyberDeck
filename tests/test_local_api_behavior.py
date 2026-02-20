import os
import tempfile
import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from cyberdeck import config
from cyberdeck import context
from cyberdeck.api.local import _require_localhost, router as local_router
from cyberdeck.qr_auth import qr_token_store


class _Client:
    def __init__(self, host: str):
        """Initialize _Client state and collaborator references."""
        self.host = host


class _Req:
    def __init__(self, host: str):
        """Initialize _Req state and collaborator references."""
        self.client = _Client(host)


class LocalApiBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepare shared fixtures for the test class."""
        cls._old_session_file = config.SESSION_FILE
        cls._old_sessions = dict(context.device_manager.sessions)
        cls._tmp = tempfile.TemporaryDirectory()
        config.SESSION_FILE = os.path.join(cls._tmp.name, "cyberdeck_sessions.json")
        context.device_manager.sessions = {}
        app = FastAPI()
        app.include_router(local_router)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        """Clean up shared fixtures for the test class."""
        context.device_manager.sessions = cls._old_sessions
        config.SESSION_FILE = cls._old_session_file
        cls._tmp.cleanup()

    def test_loopback_guard_accepts_ipv4_ipv6_and_localhost(self):
        """Validate scenario: test loopback guard accepts ipv4 ipv6 and localhost."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        _require_localhost(_Req("127.0.0.1"))
        _require_localhost(_Req("::1"))
        _require_localhost(_Req("::ffff:127.0.0.1"))
        _require_localhost(_Req("localhost"))
        with self.assertRaises(HTTPException):
            _require_localhost(_Req("192.168.1.10"))
        with self.assertRaises(HTTPException):
            _require_localhost(_Req("::ffff:192.168.1.10"))

    def test_qr_login_consumes_single_use_token(self):
        """Validate scenario: test qr login consumes single use token."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        old_ttl = config.QR_TOKEN_TTL_S
        try:
            config.QR_TOKEN_TTL_S = 120
            qr_token = qr_token_store.issue()
            ok = self.client.post(
                "/api/qr/login",
                json={"qr_token": qr_token, "device_id": "qr-test-device-1", "device_name": "QR Device"},
            )
            self.assertEqual(ok.status_code, 200, ok.text)
            body = ok.json()
            self.assertEqual(body.get("status"), "ok")
            self.assertIn("token", body)

            reused = self.client.post(
                "/api/qr/login",
                json={"qr_token": qr_token, "device_id": "qr-test-device-2", "device_name": "QR Device 2"},
            )
            self.assertEqual(reused.status_code, 403, reused.text)
            self.assertIn("invalid_or_expired_qr_token", reused.text)
        finally:
            config.QR_TOKEN_TTL_S = old_ttl


if __name__ == "__main__":
    unittest.main()

