import os
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cyberdeck import config
from cyberdeck import context
from cyberdeck.api_core import router as core_router


class UploadConstraintsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepare shared fixtures for the test class."""
        cls._old_code = config.PAIRING_CODE
        cls._old_files_dir = config.FILES_DIR
        cls._old_session_file = config.SESSION_FILE
        cls._old_sessions = dict(context.device_manager.sessions)
        cls._old_upload_max = config.UPLOAD_MAX_BYTES
        cls._old_upload_allowed_ext = list(config.UPLOAD_ALLOWED_EXT)
        cls._old_allow_query_token = config.ALLOW_QUERY_TOKEN
        cls._tmp = tempfile.TemporaryDirectory()
        cls._tmp_sessions = tempfile.TemporaryDirectory()
        config.PAIRING_CODE = "1234"
        config.FILES_DIR = cls._tmp.name
        config.SESSION_FILE = os.path.join(cls._tmp_sessions.name, "cyberdeck_sessions.json")
        context.device_manager.sessions = {}
        config.UPLOAD_MAX_BYTES = 0
        config.ALLOW_QUERY_TOKEN = False
        app = FastAPI()
        app.include_router(core_router)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        """Clean up shared fixtures for the test class."""
        config.PAIRING_CODE = cls._old_code
        config.FILES_DIR = cls._old_files_dir
        context.device_manager.sessions = cls._old_sessions
        config.SESSION_FILE = cls._old_session_file
        config.UPLOAD_MAX_BYTES = cls._old_upload_max
        config.UPLOAD_ALLOWED_EXT = cls._old_upload_allowed_ext
        config.ALLOW_QUERY_TOKEN = cls._old_allow_query_token
        cls._tmp.cleanup()
        cls._tmp_sessions.cleanup()

    def _token(self) -> str:
        """Return active session token used by test requests."""
        r = self.client.post(
            "/api/handshake",
            json={"code": "1234", "device_id": "upload-tests", "device_name": "Upload Tests"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        return str(r.json()["token"])

    @staticmethod
    def _auth_headers(token: str, **extra: str) -> dict:
        """Return authorization headers for test API requests."""
        out = {"Authorization": f"Bearer {token}"}
        out.update(extra)
        return out

    def test_upload_renames_on_collision(self):
        """Validate scenario: test upload renames on collision."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = self._token()
        data = b"same-content"

        r1 = self.client.post(
            "/api/file/upload",
            files={"file": ("dup.txt", data, "text/plain")},
            headers=self._auth_headers(token),
        )
        self.assertEqual(r1.status_code, 200, r1.text)
        name1 = str(r1.json().get("filename"))
        self.assertEqual(name1, "dup.txt")
        self.assertTrue(os.path.exists(os.path.join(config.FILES_DIR, name1)))

        r2 = self.client.post(
            "/api/file/upload",
            files={"file": ("dup.txt", data, "text/plain")},
            headers=self._auth_headers(token),
        )
        self.assertEqual(r2.status_code, 200, r2.text)
        name2 = str(r2.json().get("filename"))
        self.assertNotEqual(name1, name2)
        self.assertTrue(os.path.exists(os.path.join(config.FILES_DIR, name2)))

    def test_upload_respects_size_limit(self):
        """Validate scenario: test upload respects size limit."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = self._token()
        old = config.UPLOAD_MAX_BYTES
        try:
            config.UPLOAD_MAX_BYTES = 8
            r = self.client.post(
                "/api/file/upload",
                files={"file": ("big.bin", b"123456789", "application/octet-stream")},
                headers=self._auth_headers(token),
            )
            self.assertEqual(r.status_code, 413, r.text)
            self.assertIn("upload_too_large", r.text)
        finally:
            config.UPLOAD_MAX_BYTES = old

    def test_upload_rejects_disallowed_extension(self):
        """Validate scenario: test upload rejects disallowed extension."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = self._token()
        old_ext = list(config.UPLOAD_ALLOWED_EXT)
        try:
            config.UPLOAD_ALLOWED_EXT = [".txt"]
            bad = self.client.post(
                "/api/file/upload",
                files={"file": ("payload.bin", b"x", "application/octet-stream")},
                headers=self._auth_headers(token),
            )
            self.assertEqual(bad.status_code, 415, bad.text)
            self.assertIn("upload_extension_not_allowed", bad.text)

            ok = self.client.post(
                "/api/file/upload",
                files={"file": ("payload.TXT", b"x", "text/plain")},
                headers=self._auth_headers(token),
            )
            self.assertEqual(ok.status_code, 200, ok.text)
        finally:
            config.UPLOAD_ALLOWED_EXT = old_ext

    def test_upload_normalizes_filename(self):
        """Validate scenario: test upload normalizes filename."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = self._token()
        r = self.client.post(
            "/api/file/upload",
            files={"file": ("../evil.txt", b"abc", "text/plain")},
            headers=self._auth_headers(token),
        )
        self.assertEqual(r.status_code, 200, r.text)
        name = str(r.json().get("filename"))
        self.assertEqual(name, "evil.txt")
        self.assertTrue(os.path.exists(os.path.join(config.FILES_DIR, name)))

    def test_upload_truncates_very_long_filename(self):
        """Validate scenario: test upload truncates very long filename."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = self._token()
        long_name = ("a" * 320) + ".txt"
        r = self.client.post(
            "/api/file/upload",
            files={"file": (long_name, b"abc", "text/plain")},
            headers=self._auth_headers(token),
        )
        self.assertEqual(r.status_code, 200, r.text)
        name = str(r.json().get("filename"))
        self.assertLessEqual(len(name), 240)
        self.assertTrue(os.path.exists(os.path.join(config.FILES_DIR, name)))

    def test_upload_checksum_mismatch_removes_temp_part_file(self):
        """Validate scenario: test upload checksum mismatch removes temp part file."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = self._token()
        before = {x for x in os.listdir(config.FILES_DIR) if ".part-" in x}
        bad = self.client.post(
            "/api/file/upload",
            files={"file": ("bad.txt", b"content", "text/plain")},
            headers=self._auth_headers(token, **{"X-File-Sha256": "deadbeef"}),
        )
        self.assertEqual(bad.status_code, 400, bad.text)
        self.assertIn("upload_checksum_mismatch", bad.text)
        after = {x for x in os.listdir(config.FILES_DIR) if ".part-" in x}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
