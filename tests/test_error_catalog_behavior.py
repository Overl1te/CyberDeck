import unittest

from fastapi.testclient import TestClient

from cyberdeck.server import app


class ErrorCatalogBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_errors_catalog_returns_unique_codes(self):
        r = self.client.get("/api/errors/catalog")
        self.assertEqual(r.status_code, 200, r.text)
        payload = r.json()
        self.assertEqual(payload.get("status"), "ok")
        items = payload.get("items") or []
        self.assertTrue(items)
        codes = [str(item.get("code") or "") for item in items]
        self.assertEqual(len(codes), len(set(codes)))

    def test_errors_catalog_supports_query_filter(self):
        r = self.client.get("/api/errors/catalog", params={"q": "checksum"})
        self.assertEqual(r.status_code, 200, r.text)
        items = r.json().get("items") or []
        self.assertTrue(any("checksum" in str((x.get("slug") or "")).lower() for x in items))

    def test_unauthorized_error_has_normalized_error_block(self):
        r = self.client.get("/api/stats")
        self.assertEqual(r.status_code, 403, r.text)
        payload = r.json()
        self.assertEqual(payload.get("detail"), "Unauthorized")
        err = payload.get("error") or {}
        self.assertEqual(err.get("code"), "CD-1401")
        self.assertTrue(str(err.get("incident_id") or "").startswith("CDI-"))
        self.assertIn("/errors.html?code=CD-1401", str(err.get("docs_url") or ""))

    def test_validation_error_uses_catalog_code(self):
        r = self.client.post(
            "/api/handshake",
            json={"device_id": "dev-1", "device_name": "Phone"},
        )
        self.assertEqual(r.status_code, 422, r.text)
        payload = r.json()
        self.assertEqual(payload.get("detail"), "validation_error")
        self.assertTrue(isinstance(payload.get("validation_errors"), list))
        err = payload.get("error") or {}
        self.assertEqual(err.get("code"), "CD-1000")


if __name__ == "__main__":
    unittest.main()
