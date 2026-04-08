import os
import tempfile
import unittest
from unittest.mock import patch

import cyberdeck.self_update as self_update


class SelfUpdateBehaviorTests(unittest.TestCase):
    def test_prepare_launcher_update_install_rejects_unsupported_runtime(self):
        """Validate scenario: unattended install should be disabled outside supported packaged Windows installs."""
        with patch("cyberdeck.self_update.self_update_supported", return_value=False):
            out = self_update.prepare_launcher_update_install(
                current_version="v1.3.2",
                repo_slug="Overl1te/CyberDeck",
            )
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "unsupported")

    def test_prepare_launcher_update_install_downloads_installer_and_writes_script(self):
        """Validate scenario: latest setup exe should be downloaded and scheduled through detached helper script."""
        release = {
            "ok": True,
            "latest_tag": "v1.3.3",
            "preferred_asset": {
                "name": "CyberDeck_Setup_v1.3.3.exe",
                "download_url": "https://github.com/Overl1te/CyberDeck/releases/download/v1.3.3/CyberDeck_Setup_v1.3.3.exe",
                "size": 11,
                "kind": "windows_installer",
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "cyberdeck.self_update.self_update_supported",
            return_value=True,
        ), patch(
            "cyberdeck.self_update.fetch_latest_release_tag",
            return_value=release,
        ), patch(
            "cyberdeck.self_update._launcher_pid",
            return_value=4321,
        ), patch.object(
            self_update.config,
            "DATA_DIR",
            tmpdir,
        ), patch(
            "cyberdeck.self_update._download_file",
            side_effect=lambda _url, dest, **_kwargs: open(dest, "wb").write(b"hello world"),
        ) as mocked_download, patch(
            "cyberdeck.self_update._spawn_detached_script",
            return_value=None,
        ) as mocked_spawn:
            out = self_update.prepare_launcher_update_install(
                current_version="v1.3.2",
                repo_slug="Overl1te/CyberDeck",
            )
            self.assertTrue(out["ok"])
            self.assertEqual(out["status"], "scheduled")
            self.assertTrue(os.path.exists(out["installer_path"]))
            self.assertTrue(os.path.exists(out["script_path"]))
            self.assertTrue(str(out["script_path"]).endswith(".cmd"))
            mocked_download.assert_called_once()
            mocked_spawn.assert_called_once_with(out["script_path"])

    def test_prepare_launcher_update_install_skips_when_version_is_current(self):
        """Validate scenario: updater should not stage installer when current version already matches latest tag."""
        release = {
            "ok": True,
            "latest_tag": "v1.3.2",
            "preferred_asset": {
                "name": "CyberDeck_Setup_v1.3.2.exe",
                "download_url": "https://github.com/example/CyberDeck_Setup_v1.3.2.exe",
                "kind": "windows_installer",
            },
        }
        with patch("cyberdeck.self_update.self_update_supported", return_value=True), patch(
            "cyberdeck.self_update.fetch_latest_release_tag",
            return_value=release,
        ):
            out = self_update.prepare_launcher_update_install(
                current_version="v1.3.2",
                repo_slug="Overl1te/CyberDeck",
            )
        self.assertFalse(out["ok"])
        self.assertEqual(out["status"], "no_update")
