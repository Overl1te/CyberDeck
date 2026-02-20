import json
import unittest
from unittest.mock import patch

import cyberdeck.update_checker as update_checker


class _FakeResponse:
    """Minimal context-manager HTTP response stub used in unit tests."""

    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._raw


class UpdateCheckerBehaviorTests(unittest.TestCase):
    def setUp(self):
        """Reset module cache before each test for deterministic behavior."""
        update_checker._CACHE.clear()

    def test_is_newer_version_compares_semver_tags(self):
        """Validate scenario: semantic version comparison should ignore leading `v`."""
        self.assertTrue(update_checker.is_newer_version("v1.3.1", "1.3.0"))
        self.assertTrue(update_checker.is_newer_version("1.4.0", "v1.3.9"))
        self.assertFalse(update_checker.is_newer_version("1.3.1", "1.3.1"))
        self.assertFalse(update_checker.is_newer_version("1.3.0", "1.3.1"))
        self.assertFalse(update_checker.is_newer_version("latest", "1.3.1"))

    def test_fetch_latest_release_tag_reads_github_payload(self):
        """Validate scenario: release fetch should parse tag and release URL from JSON payload."""
        payload = {
            "tag_name": "v1.3.7",
            "html_url": "https://github.com/Overl1te/CyberDeck/releases/tag/v1.3.7",
            "published_at": "2026-02-18T00:00:00Z",
        }
        with patch("cyberdeck.update_checker.request.urlopen", return_value=_FakeResponse(payload)):
            out = update_checker.fetch_latest_release_tag("Overl1te/CyberDeck", timeout_s=1.0, ttl_s=30)

        self.assertTrue(out["ok"])
        self.assertEqual(out["latest_tag"], "v1.3.7")
        self.assertIn("github.com/Overl1te/CyberDeck", out["release_url"])

    def test_fetch_latest_release_tag_uses_ttl_cache(self):
        """Validate scenario: repeated fetch within TTL should reuse cached payload."""
        payload = {"tag_name": "v1.3.7", "html_url": "https://example/release", "published_at": "2026-02-18T00:00:00Z"}
        with patch("cyberdeck.update_checker.request.urlopen", return_value=_FakeResponse(payload)) as mocked:
            first = update_checker.fetch_latest_release_tag("Overl1te/CyberDeck", ttl_s=300)
            second = update_checker.fetch_latest_release_tag("Overl1te/CyberDeck", ttl_s=300)

        self.assertEqual(first["latest_tag"], second["latest_tag"])
        self.assertEqual(mocked.call_count, 1)

    def test_build_update_status_marks_outdated_channels(self):
        """Validate scenario: combined status should flag server/launcher/mobile update availability."""

        def _fake_fetch(repo_slug: str, **_kwargs):
            if repo_slug == "Overl1te/CyberDeck":
                return {
                    "ok": True,
                    "api_url": "https://api.github.com/repos/Overl1te/CyberDeck/releases/latest",
                    "latest_tag": "v1.3.5",
                    "release_url": "https://github.com/Overl1te/CyberDeck/releases/tag/v1.3.5",
                    "published_at": "2026-02-18T00:00:00Z",
                    "checked_at": 1700000000,
                    "error": "",
                }
            return {
                "ok": True,
                "api_url": "https://api.github.com/repos/Overl1te/CyberDeck-Mobile/releases/latest",
                "latest_tag": "v1.1.2",
                "release_url": "https://github.com/Overl1te/CyberDeck-Mobile/releases/tag/v1.1.2",
                "published_at": "2026-02-18T00:00:00Z",
                "checked_at": 1700000001,
                "error": "",
            }

        with patch("cyberdeck.update_checker.fetch_latest_release_tag", side_effect=_fake_fetch):
            out = update_checker.build_update_status(
                current_server_version="v1.3.1",
                current_launcher_version="v1.3.1",
                current_mobile_version="1.1.1",
                server_repo="Overl1te/CyberDeck",
                mobile_repo="Overl1te/CyberDeck-Mobile",
                timeout_s=1.0,
                ttl_s=300,
                force_refresh=True,
            )

        self.assertTrue(out["server"]["has_update"])
        self.assertTrue(out["launcher"]["has_update"])
        self.assertTrue(out["mobile"]["has_update"])


if __name__ == "__main__":
    unittest.main()

