import os
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cyberdeck import config
from cyberdeck import context
from cyberdeck.api.core import router as core_router
from cyberdeck.video import router as video_router


class ContractSmokeTests(unittest.TestCase):
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

    def _handshake(self) -> str:
        """Return the public handshake payload for new clients."""
        r = self.client.post(
            "/api/handshake",
            json={"code": "1234", "device_id": "test-device-1", "device_name": "CI Device"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body.get("status"), "ok")
        self.assertIn("token", body)
        self.assertIn("protocol_version", body)
        return str(body["token"])

    @staticmethod
    def _auth_headers(token: str) -> dict:
        """Return authorization headers for test API requests."""
        return {"Authorization": f"Bearer {token}"}

    def test_protocol_endpoint(self):
        """Validate scenario: test protocol endpoint."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        r = self.client.get("/api/protocol")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("protocol_version", body)
        self.assertIn("min_supported_protocol_version", body)
        self.assertIn("features", body)
        self.assertIsInstance(body.get("features"), dict)

    def test_stream_offer_and_diag_contract(self):
        """Validate scenario: test stream offer and diag contract."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = self._handshake()

        offer = self.client.get("/api/stream_offer", headers=self._auth_headers(token))
        self.assertEqual(offer.status_code, 200, offer.text)
        offer_body = offer.json()
        self.assertIn("candidates", offer_body)
        self.assertIn("protocol_version", offer_body)
        self.assertIn("fallback_policy", offer_body)
        self.assertIsInstance(offer_body.get("candidates"), list)

        diag = self.client.get("/api/diag", headers=self._auth_headers(token))
        self.assertEqual(diag.status_code, 200, diag.text)
        diag_body = diag.json()
        self.assertIn("stream", diag_body)
        self.assertIn("ws", diag_body)
        self.assertIn("protocol_version", diag_body)


if __name__ == "__main__":
    unittest.main()

