import hashlib
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cyberdeck.transfer as transfer


class TransferBehaviorTests(unittest.TestCase):
    def test_pick_transfer_params_clamps_values(self):
        """Validate scenario: test pick transfer params clamps values."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        out = transfer.pick_transfer_params(
            {
                "transfer_preset": "safe",
                "transfer_chunk": "512",
                "transfer_sleep": "-1",
            }
        )
        self.assertEqual(out["chunk"], 1024)
        self.assertEqual(out["sleep"], 0.0)

    def test_resolve_transfer_scheme_prefers_explicit_mode(self):
        """Validate scenario: test resolve transfer scheme prefers explicit mode."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch.object(transfer.config, "TRANSFER_SCHEME", "https"), patch.object(
            transfer.config, "SCHEME", "http"
        ):
            self.assertEqual(transfer._resolve_transfer_scheme(), "https")

    def test_resolve_transfer_scheme_uses_server_scheme_for_auto(self):
        """Validate scenario: test resolve transfer scheme uses server scheme for auto."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch.object(transfer.config, "TRANSFER_SCHEME", "auto"), patch.object(
            transfer.config, "SCHEME", "https"
        ):
            self.assertEqual(transfer._resolve_transfer_scheme(), "https")

    def test_trigger_file_send_denies_without_permission(self):
        """Validate scenario: test trigger file send denies without permission."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch("cyberdeck.transfer.get_perm", return_value=False):
            ok, msg = transfer.trigger_file_send_logic("tok", "x.txt")
        self.assertFalse(ok)
        self.assertEqual(msg, "permission_denied:perm_file_send")

    def test_trigger_file_send_returns_offline_without_websocket(self):
        """Validate scenario: test trigger file send returns offline without websocket."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        session = SimpleNamespace(websocket=None)
        with patch("cyberdeck.transfer.get_perm", return_value=True), patch.object(
            transfer.device_manager, "get_session", return_value=session
        ):
            ok, msg = transfer.trigger_file_send_logic("tok", "x.txt")
        self.assertFalse(ok)
        self.assertEqual(msg, "Offline")

    def test_trigger_file_send_returns_file_missing(self):
        """Validate scenario: test trigger file send returns file missing."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        session = SimpleNamespace(websocket=object())
        with patch("cyberdeck.transfer.get_perm", return_value=True), patch.object(
            transfer.device_manager, "get_session", return_value=session
        ), patch("cyberdeck.transfer.os.path.exists", return_value=False):
            ok, msg = transfer.trigger_file_send_logic("tok", "x.txt")
        self.assertFalse(ok)
        self.assertEqual(msg, "File missing")

    def test_trigger_file_send_returns_server_not_ready(self):
        """Validate scenario: test trigger file send returns server not ready."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        session = SimpleNamespace(websocket=object())
        with patch("cyberdeck.transfer.get_perm", return_value=True), patch.object(
            transfer.device_manager, "get_session", return_value=session
        ), patch("cyberdeck.transfer.os.path.exists", return_value=True), patch(
            "cyberdeck.context.running_loop", None
        ):
            ok, msg = transfer.trigger_file_send_logic("tok", "x.txt")
        self.assertFalse(ok)
        self.assertEqual(msg, "Server not ready")

    def test_trigger_file_send_returns_error_when_transporter_missing(self):
        """Validate scenario: test trigger file send returns error when transporter missing."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with tempfile.TemporaryDirectory() as td:
            file_path = os.path.join(td, "payload.bin")
            with open(file_path, "wb") as f:
                f.write(b"abc123")

            session = SimpleNamespace(
                websocket=object(),
                settings={},
            )
            loop_obj = object()
            with patch("cyberdeck.transfer.get_perm", return_value=True), patch.object(
                transfer.device_manager, "get_session", return_value=session
            ), patch.object(transfer.config, "BASE_DIR", td), patch(
                "cyberdeck.context.running_loop", loop_obj
            ):
                ok, msg = transfer.trigger_file_send_logic("tok", file_path)

        self.assertFalse(ok)
        self.assertEqual(msg, "transporter.py missing")

    def test_trigger_file_send_success_non_frozen_builds_payload(self):
        """Validate scenario: test trigger file send success non frozen builds payload."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with tempfile.TemporaryDirectory() as td:
            file_path = os.path.join(td, "payload.bin")
            with open(file_path, "wb") as f:
                f.write(b"hello-transfer")

            transporter_path = os.path.join(td, "transporter.py")
            with open(transporter_path, "w", encoding="utf-8") as f:
                f.write("print('stub transporter')\n")

            fake_ws = MagicMock()
            fake_ws.send_json = MagicMock(return_value="coro-token")
            session = SimpleNamespace(
                websocket=fake_ws,
                settings={"transfer_preset": "balanced"},
                device_name="Phone",
                ip="10.0.0.8",
            )
            loop_obj = object()

            uuid_values = [
                SimpleNamespace(hex="dl-token"),
                SimpleNamespace(hex="transfer-id"),
            ]

            with patch("cyberdeck.transfer.get_perm", return_value=True), patch.object(
                transfer.device_manager, "get_session", return_value=session
            ), patch("cyberdeck.context.running_loop", loop_obj), patch.object(
                transfer.config, "BASE_DIR", td
            ), patch.object(
                transfer.config, "CONSOLE_LOG", False
            ), patch.object(
                transfer.config, "TRANSFER_SCHEME", "https"
            ), patch.object(
                transfer.config, "TLS_CERT", ""
            ), patch.object(
                transfer.config, "TLS_KEY", ""
            ), patch(
                "cyberdeck.transfer.find_free_port", return_value=45678
            ), patch(
                "cyberdeck.transfer.get_local_ip", return_value="192.168.0.10"
            ), patch(
                "cyberdeck.transfer.uuid.uuid4", side_effect=uuid_values
            ), patch(
                "cyberdeck.transfer.subprocess.Popen"
            ) as mpopen, patch(
                "cyberdeck.transfer.asyncio.run_coroutine_threadsafe"
            ) as mrun:
                ok, msg = transfer.trigger_file_send_logic("tok", file_path)

            self.assertTrue(ok)
            self.assertEqual(msg, "Transporter started")
            self.assertTrue(mpopen.called)

            cmd = mpopen.call_args[0][0]
            self.assertEqual(cmd[0], transfer.sys.executable)
            self.assertEqual(cmd[1], transporter_path)
            self.assertIn("--token", cmd)
            self.assertIn("dl-token", cmd)

            fake_ws.send_json.assert_called_once()
            payload = fake_ws.send_json.call_args[0][0]
            self.assertEqual(payload["filename"], "payload.bin")
            self.assertEqual(payload["scheme"], "http")
            self.assertFalse(payload["tls"])
            self.assertIn("http://192.168.0.10:45678/payload.bin?t=dl-token", payload["url"])

            expected_sha = hashlib.sha256(b"hello-transfer").hexdigest()
            self.assertEqual(payload["sha256"], expected_sha)
            mrun.assert_called_once_with("coro-token", loop_obj)


if __name__ == "__main__":
    unittest.main()
