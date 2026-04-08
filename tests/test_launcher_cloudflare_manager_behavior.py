import json
import os
import threading
import tempfile
import time
import unittest
from unittest.mock import patch

import requests

from cyberdeck.launcher.cloudflare_manager import CloudflareManager


class _AliveThread:
    def is_alive(self) -> bool:
        return True


class CloudflareManagerBehaviorTests(unittest.TestCase):
    def test_resolve_binary_prefers_bundled_vendor_binary(self):
        """Validate scenario: bundled cloudflared from release assets should be preferred over runtime download."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bundled_dir = os.path.join(tmpdir, "vendor", "cloudflared", "windows-amd64")
            os.makedirs(bundled_dir, exist_ok=True)
            bundled_path = os.path.join(bundled_dir, "cloudflared.exe")
            with open(bundled_path, "wb") as fh:
                fh.write(b"stub")
            manager = CloudflareManager(search_roots=[tmpdir])
            self.assertEqual(os.path.abspath(manager._resolve_binary("")), os.path.abspath(bundled_path))

    def test_ensure_running_preserves_installing_status_during_background_install(self):
        """Validate scenario: manager should not downgrade active background install into missing-binary state."""
        manager = CloudflareManager()
        manager.configure(
            enabled=True,
            binary_path="",
            tunnel_token="",
            configured_hostname="",
            target_url="http://127.0.0.1:8080",
        )
        manager._install_thread = _AliveThread()
        manager._set_snapshot(status="installing", enabled=True, running=False, last_error="")
        with patch.object(manager, "_resolve_binary", return_value=""), patch.object(
            manager,
            "_ensure_managed_binary",
            return_value="",
        ):
            snap = manager.ensure_running()
        self.assertEqual(snap.status, "installing")
        self.assertEqual(snap.last_error, "")

    def test_ensure_managed_binary_starts_async_install_worker(self):
        """Validate scenario: auto-install should return immediately and continue in a background thread."""
        manager = CloudflareManager()
        manager.configure(
            enabled=True,
            binary_path="",
            tunnel_token="",
            configured_hostname="",
            target_url="http://127.0.0.1:8080",
        )
        started = threading.Event()
        release = threading.Event()

        def _fake_download() -> str:
            started.set()
            release.wait(1.0)
            return "C:\\temp\\cloudflared.exe"

        with patch.object(manager, "_download_binary", side_effect=_fake_download):
            out = manager._ensure_managed_binary()
            self.assertEqual(out, "")
            self.assertTrue(started.wait(0.2))
            self.assertEqual(manager.snapshot().status, "installing")
            release.set()
            worker = manager._install_thread
            self.assertIsNotNone(worker)
            worker.join(timeout=1.0)
        self.assertEqual(manager.snapshot().status, "starting")

    def test_format_install_error_simplifies_requests_timeout(self):
        """Validate scenario: UI should receive a short timeout message instead of raw requests internals."""
        manager = CloudflareManager()
        self.assertEqual(manager._format_install_error(requests.Timeout()), "cloudflared download timed out")

    def test_format_install_error_simplifies_requests_connection_error(self):
        """Validate scenario: connection failures should be reported concisely."""
        manager = CloudflareManager()
        self.assertEqual(
            manager._format_install_error(requests.ConnectionError()),
            "cloudflared download failed: connection error",
        )

    def test_validate_download_url_requires_https(self):
        """Validate scenario: managed download must not accept insecure URLs."""
        with self.assertRaisesRegex(RuntimeError, "https"):
            CloudflareManager._validate_download_url("http://example.com/cloudflared.exe")

    def test_verify_windows_signature_accepts_valid_cloudflare_signer(self):
        """Validate scenario: downloaded Windows binary should be accepted only with a valid Cloudflare signature."""
        payload = {"Status": "Valid", "Subject": "CN=Cloudflare, Inc.", "Issuer": "CN=DigiCert"}
        with patch("cyberdeck.launcher.cloudflare_manager.subprocess.run") as mocked_run:
            mocked_run.return_value.returncode = 0
            mocked_run.return_value.stdout = json.dumps(payload)
            mocked_run.return_value.stderr = ""
            CloudflareManager._verify_windows_signature("C:\\tools\\cloudflared.exe")

    def test_verify_windows_signature_rejects_invalid_status(self):
        """Validate scenario: invalid Authenticode status should block execution."""
        payload = {"Status": "UnknownError", "Subject": "CN=Cloudflare, Inc.", "Issuer": "CN=DigiCert"}
        with patch("cyberdeck.launcher.cloudflare_manager.subprocess.run") as mocked_run:
            mocked_run.return_value.returncode = 0
            mocked_run.return_value.stdout = json.dumps(payload)
            mocked_run.return_value.stderr = ""
            with self.assertRaisesRegex(RuntimeError, "not valid"):
                CloudflareManager._verify_windows_signature("C:\\tools\\cloudflared.exe")

    def test_verify_windows_signature_rejects_unexpected_signer(self):
        """Validate scenario: valid-looking signatures from the wrong signer must be rejected."""
        payload = {"Status": "Valid", "Subject": "CN=Example Corp", "Issuer": "CN=DigiCert"}
        with patch("cyberdeck.launcher.cloudflare_manager.subprocess.run") as mocked_run:
            mocked_run.return_value.returncode = 0
            mocked_run.return_value.stdout = json.dumps(payload)
            mocked_run.return_value.stderr = ""
            with self.assertRaisesRegex(RuntimeError, "signer mismatch"):
                CloudflareManager._verify_windows_signature("C:\\tools\\cloudflared.exe")

    def test_ensure_running_builds_quick_tunnel_without_token(self):
        """Validate scenario: manager should start a Quick Tunnel when no Named Tunnel token is configured."""
        manager = CloudflareManager()
        manager.configure(
            enabled=True,
            binary_path="",
            tunnel_token="",
            configured_hostname="",
            target_url="https://127.0.0.1:9443",
        )

        class _Proc:
            pid = 1234

            def poll(self):
                return None

        with patch.object(manager, "_resolve_binary", return_value="C:\\tools\\cloudflared.exe"), patch(
            "cyberdeck.launcher.cloudflare_manager.subprocess.Popen",
            return_value=_Proc(),
        ) as popen, patch.object(manager, "_start_stdout_reader", return_value=None):
            snap = manager.ensure_running()
        cmd = popen.call_args.args[0]
        self.assertIn("--url", cmd)
        self.assertIn("https://127.0.0.1:9443", cmd)
        self.assertIn("--no-tls-verify", cmd)
        self.assertEqual(snap.status, "starting")

    def test_http_loopback_origin_does_not_enable_tls_skip_verify(self):
        """Validate scenario: plain HTTP local origin should not add a pointless TLS bypass flag."""
        manager = CloudflareManager()
        manager.configure(
            enabled=True,
            binary_path="",
            tunnel_token="",
            configured_hostname="",
            target_url="http://127.0.0.1:8080",
        )

        class _Proc:
            pid = 1234

            def poll(self):
                return None

        with patch.object(manager, "_resolve_binary", return_value="C:\\tools\\cloudflared.exe"), patch(
            "cyberdeck.launcher.cloudflare_manager.subprocess.Popen",
            return_value=_Proc(),
        ) as popen, patch.object(manager, "_start_stdout_reader", return_value=None):
            manager.ensure_running()
        cmd = popen.call_args.args[0]
        self.assertNotIn("--no-tls-verify", cmd)

    def test_ensure_running_builds_named_tunnel_with_token(self):
        """Validate scenario: manager should start a Named Tunnel when a tunnel token is configured."""
        manager = CloudflareManager()
        manager.configure(
            enabled=True,
            binary_path="",
            tunnel_token="token-123",
            configured_hostname="https://remote.example.com",
            target_url="https://127.0.0.1:9443",
        )

        class _Proc:
            pid = 1234

            def poll(self):
                return None

        with patch.object(manager, "_resolve_binary", return_value="C:\\tools\\cloudflared.exe"), patch(
            "cyberdeck.launcher.cloudflare_manager.subprocess.Popen",
            return_value=_Proc(),
        ) as popen, patch.object(manager, "_start_stdout_reader", return_value=None):
            snap = manager.ensure_running()
        cmd = popen.call_args.args[0]
        self.assertIn("run", cmd)
        self.assertIn("--token", cmd)
        self.assertIn("token-123", cmd)
        self.assertEqual(snap.status, "starting")

    def test_ensure_running_respects_restart_backoff_after_error(self):
        """Validate scenario: manager should not respawn cloudflared every sync tick after a crash."""
        manager = CloudflareManager()
        manager.configure(
            enabled=True,
            binary_path="",
            tunnel_token="",
            configured_hostname="",
            target_url="http://127.0.0.1:8080",
        )
        manager._set_snapshot(status="error", enabled=True, running=False, last_error="boom")
        manager._next_restart_ts = time.time() + 30.0
        with patch.object(manager, "_resolve_binary", return_value="C:\\tools\\cloudflared.exe"), patch(
            "cyberdeck.launcher.cloudflare_manager.subprocess.Popen"
        ) as popen:
            snap = manager.ensure_running()
        popen.assert_not_called()
        self.assertEqual(snap.status, "error")
        self.assertEqual(snap.last_error, "boom")

    def test_build_process_env_uses_isolated_home_directory(self):
        """Validate scenario: launcher should isolate cloudflared from any user-global config files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = CloudflareManager(install_dir=tmpdir)
            env = manager._build_process_env()
        self.assertTrue(str(env.get("HOME") or "").endswith("runtime-home"))
        if os.name == "nt":
            self.assertEqual(env.get("USERPROFILE"), env.get("HOME"))

    def test_discover_public_url_prefers_named_hostname(self):
        """Validate scenario: Named Tunnel should expose configured hostname as public URL."""
        manager = CloudflareManager()
        manager.configure(
            enabled=True,
            binary_path="",
            tunnel_token="token-123",
            configured_hostname="https://remote.example.com",
            target_url="http://127.0.0.1:8080",
        )
        self.assertEqual(manager._discover_public_url(), "https://remote.example.com")

    def test_extract_process_exit_detail_prefers_human_error(self):
        """Validate scenario: cloudflared exit reason should keep the actual failure instead of a noisy line."""
        lines = [
            "INF Quick Tunnel will not be available on your free plan",
            "ERR failed to serve tunnel connection",
            "ERR lookup region1.v2.argotunnel.com: no such host",
        ]
        self.assertEqual(
            CloudflareManager._extract_process_exit_detail(lines, 1),
            "lookup region1.v2.argotunnel.com: no such host",
        )


if __name__ == "__main__":
    unittest.main()
