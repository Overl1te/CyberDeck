import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

import cyberdeck.api.local as api_local


class _Client:
    def __init__(self, host: str):
        """Initialize _Client state and collaborator references."""
        self.host = host


class _Req:
    def __init__(self, host: str):
        """Initialize _Req state and collaborator references."""
        self.client = _Client(host)


class LocalApiExtendedBehaviorTests(unittest.TestCase):
    def setUp(self):
        """Prepare test preconditions for each test case."""
        self._old_pairing_code = api_local.config.PAIRING_CODE
        self._old_pairing_expires_at = getattr(api_local.config, "PAIRING_EXPIRES_AT", None)

    def tearDown(self):
        """Clean up resources created by each test case."""
        api_local.config.PAIRING_CODE = self._old_pairing_code
        api_local.config.PAIRING_EXPIRES_AT = self._old_pairing_expires_at

    def test_local_trigger_file_calls_transfer_logic(self):
        """Validate scenario: test local trigger file calls transfer logic."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        req = api_local.LocalFileRequest(token="tok", file_path="c:/tmp/file.txt")
        with patch("cyberdeck.api.local.trigger_file_send_logic", return_value=(True, "ok")) as m:
            out = api_local.local_trigger_file(req, _Req("127.0.0.1"))
        self.assertEqual(out, {"ok": True, "msg": "ok"})
        m.assert_called_once_with("tok", "c:/tmp/file.txt")

    def test_local_qr_payload_contains_single_use_token_and_url(self):
        """Validate scenario: test local qr payload contains single use token and url."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch("cyberdeck.api.local.get_local_ip", return_value="10.1.1.50"), patch.object(
            api_local.qr_token_store, "issue", return_value="qr-abc"
        ), patch.object(
            api_local.config, "SCHEME", "https"
        ), patch.object(
            api_local.config, "SERVER_ID", "srv-id"
        ), patch.object(
            api_local.config, "HOSTNAME", "deck-host"
        ), patch.object(
            api_local.config, "VERSION", "1.2.3"
        ), patch.object(
            api_local.config, "PORT", 8443
        ), patch.object(
            api_local.config, "PAIRING_CODE", "1234"
        ), patch(
            "cyberdeck.api.local.time.time", return_value=1700000000
        ):
            out = api_local.local_qr_payload(_Req("localhost"))

        payload = out["payload"]
        self.assertEqual(payload["nonce"], "qr-abc")
        self.assertEqual(payload["qr_token"], "qr-abc")
        self.assertEqual(payload["ip"], "10.1.1.50")
        self.assertIn("https://10.1.1.50:8443/?", out["url"])
        self.assertIn("qr_token=qr-abc", out["url"])

    def test_local_info_uses_safe_port_defaults_for_invalid_port(self):
        """Validate scenario: test local info uses safe port defaults for invalid port."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch("cyberdeck.api.local.get_local_ip", return_value="10.1.1.70"), patch.object(
            api_local.config,
            "SCHEME",
            "https",
        ), patch.object(
            api_local.config,
            "PORT",
            "bad-port",
        ), patch.object(
            api_local.device_manager,
            "get_all_devices",
            return_value=[],
        ), patch(
            "cyberdeck.api.local.protocol_payload",
            return_value={"protocol": "v1"},
        ):
            out = api_local.local_info(_Req("127.0.0.1"))

        self.assertEqual(out["ip"], "10.1.1.70")
        self.assertEqual(out["scheme"], "https")
        self.assertEqual(out["port"], 443)
        self.assertEqual(out["protocol"], "v1")

    def test_local_stats_reads_psutil_snapshot(self):
        """Validate scenario: test local stats reads psutil snapshot."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake_vm = SimpleNamespace(percent=44.5)
        fake_proc = MagicMock()
        fake_proc.memory_info.return_value = SimpleNamespace(rss=123456)

        with patch("cyberdeck.api.local.psutil.cpu_percent", return_value=12.5), patch(
            "cyberdeck.api.local.psutil.virtual_memory", return_value=fake_vm
        ), patch(
            "cyberdeck.api.local.psutil.boot_time", return_value=100.0
        ), patch(
            "cyberdeck.api.local.psutil.Process", return_value=fake_proc
        ), patch(
            "cyberdeck.api.local.time.time", return_value=130.0
        ):
            out = api_local.local_stats(_Req("::1"))

        self.assertEqual(out["cpu"], 12.5)
        self.assertEqual(out["ram"], 44.5)
        self.assertEqual(out["uptime_s"], 30)
        self.assertEqual(out["process_ram"], 123456)

    def test_local_set_device_settings_returns_404_for_unknown_token(self):
        """Validate scenario: test local set device settings returns 404 for unknown token."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        req = api_local.LocalSettingsRequest(token="tok-missing", settings={"perm_mouse": True})
        with patch.object(api_local.device_manager, "update_settings", return_value=False):
            with self.assertRaises(HTTPException) as cm:
                api_local.local_set_device_settings(req, _Req("127.0.0.1"))
        self.assertEqual(cm.exception.status_code, 404)

    def test_local_device_delete_by_id_success(self):
        """Validate scenario: test local device delete by id success."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        session = SimpleNamespace(device_id="dev-1", websocket=None)
        fake_manager = SimpleNamespace(
            sessions={"tok-1": session},
            get_session=MagicMock(return_value=session),
            unregister_socket=MagicMock(),
            delete_session=MagicMock(return_value=True),
        )
        req = api_local.LocalDeviceIdRequest(device_id="dev-1")
        with patch.object(api_local, "device_manager", fake_manager), patch("cyberdeck.context.running_loop", None):
            out = api_local.local_device_delete_by_id(req, _Req("127.0.0.1"))

        self.assertEqual(out["ok"], True)
        self.assertEqual(out["token"], "tok-1")
        self.assertEqual(out["device_id"], "dev-1")
        fake_manager.unregister_socket.assert_called_once_with("tok-1")
        fake_manager.delete_session.assert_called_once_with("tok-1")

    def test_local_device_delete_by_id_not_found(self):
        """Validate scenario: test local device delete by id not found."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake_manager = SimpleNamespace(
            sessions={},
            get_session=MagicMock(return_value=None),
            unregister_socket=MagicMock(),
            delete_session=MagicMock(return_value=False),
        )
        req = api_local.LocalDeviceIdRequest(device_id="missing")
        with patch.object(api_local, "device_manager", fake_manager):
            with self.assertRaises(HTTPException) as cm:
                api_local.local_device_delete_by_id(req, _Req("127.0.0.1"))
        self.assertEqual(cm.exception.status_code, 404)
        self.assertEqual(cm.exception.detail, "device_not_found")

    def test_local_revoke_all_keeps_requested_token(self):
        """Validate scenario: test local revoke all keeps requested token."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        s_keep = SimpleNamespace(websocket=None)
        s_drop = SimpleNamespace(websocket=None)
        sessions = {"keep-tok": s_keep, "drop-tok": s_drop}
        fake_manager = SimpleNamespace(
            sessions=sessions,
            get_session=MagicMock(side_effect=lambda t: sessions.get(t)),
            unregister_socket=MagicMock(),
            delete_session=MagicMock(side_effect=lambda t: t == "drop-tok"),
        )
        req = api_local.LocalRevokeAllRequest(keep_token="keep-tok")
        with patch.object(api_local, "device_manager", fake_manager), patch("cyberdeck.context.running_loop", None):
            out = api_local.local_revoke_all(req, _Req("127.0.0.1"))

        self.assertEqual(out["ok"], True)
        self.assertEqual(out["revoked"], 1)
        self.assertEqual(out["kept"], "keep-tok")
        fake_manager.unregister_socket.assert_called_once_with("drop-tok")

    def test_regenerate_code_resets_pin_limiter_and_expiry(self):
        """Validate scenario: test regenerate code resets pin limiter and expiry."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake_uuid = SimpleNamespace(int=98765432109876)
        with patch("cyberdeck.api.local.uuid.uuid4", return_value=fake_uuid), patch.object(
            api_local.config, "PAIRING_TTL_S", 60
        ), patch(
            "cyberdeck.api.local.time.time", return_value=1000.0
        ), patch.object(
            api_local.pin_limiter, "reset"
        ) as mreset:
            out = api_local.regenerate_code(_Req("127.0.0.1"))

        self.assertEqual(out["new_code"], "9876")
        self.assertEqual(api_local.config.PAIRING_EXPIRES_AT, 1060.0)
        mreset.assert_called_once()

    def test_require_localhost_rejects_missing_or_invalid_host(self):
        """Validate scenario: test require localhost rejects missing or invalid host."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with self.assertRaises(HTTPException) as cm_missing:
            api_local._require_localhost(SimpleNamespace(client=None))
        self.assertEqual(cm_missing.exception.status_code, 403)

        with self.assertRaises(HTTPException) as cm_invalid:
            api_local._require_localhost(_Req("definitely-not-ip-address"))
        self.assertEqual(cm_invalid.exception.status_code, 403)

    def test_local_qr_payload_falls_back_to_base_url_when_encoding_fails(self):
        """Validate scenario: test local qr payload falls back to base url when encoding fails."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch("cyberdeck.api.local.get_local_ip", return_value="10.1.1.60"), patch.object(
            api_local.qr_token_store,
            "issue",
            return_value="qr-fallback",
        ), patch.object(
            api_local.config,
            "SCHEME",
            "http",
        ), patch.object(
            api_local.config,
            "PORT",
            8080,
        ), patch(
            "cyberdeck.api.local.urllib.parse.urlencode",
            side_effect=ValueError("boom"),
        ):
            out = api_local.local_qr_payload(_Req("127.0.0.1"))
        self.assertEqual(out["url"], "http://10.1.1.60:8080/")

    def test_local_qr_payload_uses_default_port_when_config_port_is_invalid(self):
        """Validate scenario: test local qr payload uses default port when config port is invalid."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch("cyberdeck.api.local.get_local_ip", return_value="10.1.1.61"), patch.object(
            api_local.qr_token_store,
            "issue",
            return_value="qr-invalid-port",
        ), patch.object(
            api_local.config,
            "SCHEME",
            "http",
        ), patch.object(
            api_local.config,
            "PORT",
            "not-a-port",
        ):
            out = api_local.local_qr_payload(_Req("127.0.0.1"))
        self.assertEqual(out["payload"]["port"], 80)
        self.assertIn("http://10.1.1.61:80/?", out["url"])

    def test_qr_login_requires_qr_token(self):
        """Validate scenario: test qr login requires qr token."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with self.assertRaises(HTTPException) as cm:
            api_local.qr_login(api_local.QrLoginRequest(), _Req("127.0.0.1"))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertEqual(cm.exception.detail, "qr_token_required")

    def test_qr_login_tolerates_bad_pairing_expiry_value(self):
        """Validate scenario: test qr login tolerates bad pairing expiry value."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        old_exp = getattr(api_local.config, "PAIRING_EXPIRES_AT", None)
        try:
            api_local.config.PAIRING_EXPIRES_AT = "not-a-float"
            with patch.object(api_local.qr_token_store, "consume", return_value=True), patch.object(
                api_local.device_manager,
                "authorize",
                return_value="tok-qr-1",
            ) as mauth:
                out = api_local.qr_login(
                    api_local.QrLoginRequest(qr_token="qr-ok", device_id="dev-q1", device_name="Phone"),
                    _Req("127.0.0.1"),
                )
        finally:
            api_local.config.PAIRING_EXPIRES_AT = old_exp
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["token"], "tok-qr-1")
        mauth.assert_called_once()

    def test_local_get_device_settings_returns_404_for_unknown_token(self):
        """Validate scenario: test local get device settings returns 404 for unknown token."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch.object(api_local.device_manager, "get_session", return_value=None):
            with self.assertRaises(HTTPException) as cm:
                api_local.local_get_device_settings("missing", _Req("localhost"))
        self.assertEqual(cm.exception.status_code, 404)

    def test_local_set_device_settings_success(self):
        """Validate scenario: test local set device settings success."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        req = api_local.LocalSettingsRequest(token="tok-ok", settings={"perm_mouse": True})
        with patch.object(api_local.device_manager, "update_settings", return_value=True):
            out = api_local.local_set_device_settings(req, _Req("::1"))
        self.assertEqual(out, {"ok": True})

    def test_local_updates_returns_release_status_payload(self):
        """Validate scenario: local updates endpoint should proxy normalized release status payload."""
        fake_payload = {
            "checked_at": 1700000002,
            "server": {"current_version": "v1.3.1", "latest_tag": "v1.3.1", "has_update": False},
            "launcher": {"current_version": "v1.3.1", "latest_tag": "v1.3.1", "has_update": False},
            "mobile": {"current_version": "1.1.1", "latest_tag": "v1.1.1", "has_update": False},
            "sources": {},
        }
        with patch("cyberdeck.api.local.build_update_status", return_value=fake_payload) as mocked:
            out = api_local.local_updates(_Req("127.0.0.1"), force_refresh=1)
        self.assertEqual(out, fake_payload)
        self.assertTrue(mocked.called)

    def test_local_stats_tolerates_psutil_errors(self):
        """Validate scenario: test local stats tolerates psutil errors."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch(
            "cyberdeck.api.local.psutil.cpu_percent",
            side_effect=RuntimeError("cpu-error"),
        ), patch(
            "cyberdeck.api.local.psutil.virtual_memory",
            side_effect=RuntimeError("ram-error"),
        ), patch(
            "cyberdeck.api.local.psutil.boot_time",
            side_effect=RuntimeError("boot-error"),
        ), patch(
            "cyberdeck.api.local.psutil.Process",
            side_effect=RuntimeError("rss-error"),
        ), patch(
            "cyberdeck.api.local.time.time",
            return_value=123.0,
        ):
            out = api_local.local_stats(_Req("localhost"))

        self.assertEqual(out["cpu"], 0.0)
        self.assertEqual(out["ram"], 0.0)
        self.assertEqual(out["uptime_s"], 0)
        self.assertEqual(out["process_ram"], 0)

    def test_local_device_disconnect_returns_404_for_unknown_token(self):
        """Validate scenario: test local device disconnect returns 404 for unknown token."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        req = api_local.LocalTokenRequest(token="tok-missing")
        with patch.object(api_local.device_manager, "get_session", return_value=None):
            with self.assertRaises(HTTPException) as cm:
                api_local.local_device_disconnect(req, _Req("127.0.0.1"))
        self.assertEqual(cm.exception.status_code, 404)

    def test_local_device_disconnect_closes_online_socket(self):
        """Validate scenario: test local device disconnect closes online socket."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        websocket = SimpleNamespace(close=lambda **_kw: "close-coro")
        session = SimpleNamespace(websocket=websocket)
        req = api_local.LocalTokenRequest(token="tok-online")
        with patch.object(api_local.device_manager, "get_session", return_value=session), patch.object(
            api_local.device_manager,
            "unregister_socket",
        ) as munreg, patch(
            "cyberdeck.context.running_loop",
            object(),
        ), patch(
            "cyberdeck.api.local.asyncio.run_coroutine_threadsafe",
            return_value=None,
        ) as mrun:
            out = api_local.local_device_disconnect(req, _Req("127.0.0.1"))
        self.assertEqual(out, {"ok": True})
        munreg.assert_called_once_with("tok-online")
        mrun.assert_called_once()

    def test_local_device_delete_returns_500_when_delete_fails(self):
        """Validate scenario: test local device delete returns 500 when delete fails."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        session = SimpleNamespace(websocket=None)
        req = api_local.LocalTokenRequest(token="tok-del-fail")
        with patch.object(api_local.device_manager, "get_session", return_value=session), patch.object(
            api_local.device_manager,
            "unregister_socket",
            return_value=None,
        ), patch.object(
            api_local.device_manager,
            "delete_session",
            return_value=False,
        ):
            with self.assertRaises(HTTPException) as cm:
                api_local.local_device_delete(req, _Req("127.0.0.1"))
        self.assertEqual(cm.exception.status_code, 500)

    def test_local_device_delete_by_id_requires_device_id(self):
        """Validate scenario: test local device delete by id requires device id."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        req = api_local.LocalDeviceIdRequest(device_id="")
        with self.assertRaises(HTTPException) as cm:
            api_local.local_device_delete_by_id(req, _Req("127.0.0.1"))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertEqual(cm.exception.detail, "device_id_required")

    def test_local_device_delete_by_id_returns_500_when_delete_fails(self):
        """Validate scenario: test local device delete by id returns 500 when delete fails."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        session = SimpleNamespace(device_id="dev-fail", websocket=None)
        fake_manager = SimpleNamespace(
            sessions={"tok-fail": session},
            get_session=MagicMock(return_value=session),
            unregister_socket=MagicMock(),
            delete_session=MagicMock(return_value=False),
        )
        req = api_local.LocalDeviceIdRequest(device_id="dev-fail")
        with patch.object(api_local, "device_manager", fake_manager), patch("cyberdeck.context.running_loop", None):
            with self.assertRaises(HTTPException) as cm:
                api_local.local_device_delete_by_id(req, _Req("127.0.0.1"))
        self.assertEqual(cm.exception.status_code, 500)
        self.assertEqual(cm.exception.detail, "delete_failed")

    def test_local_revoke_all_ignores_socket_close_errors(self):
        """Validate scenario: test local revoke all ignores socket close errors."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        ws = SimpleNamespace(close=lambda **_kw: "close-coro")
        s_drop = SimpleNamespace(websocket=ws)
        fake_manager = SimpleNamespace(
            sessions={"drop": s_drop},
            get_session=MagicMock(return_value=s_drop),
            unregister_socket=MagicMock(),
            delete_session=MagicMock(return_value=True),
        )
        req = api_local.LocalRevokeAllRequest(keep_token=None)
        with patch.object(api_local, "device_manager", fake_manager), patch(
            "cyberdeck.context.running_loop",
            object(),
        ), patch(
            "cyberdeck.api.local.asyncio.run_coroutine_threadsafe",
            side_effect=RuntimeError("close-error"),
        ):
            out = api_local.local_revoke_all(req, _Req("127.0.0.1"))
        self.assertEqual(out["ok"], True)
        self.assertEqual(out["revoked"], 1)
        fake_manager.unregister_socket.assert_called_once_with("drop")

    def test_regenerate_code_handles_bad_ttl_and_reset_error(self):
        """Validate scenario: test regenerate code handles bad ttl and reset error."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake_uuid = SimpleNamespace(int=1111222233334444)
        with patch("cyberdeck.api.local.uuid.uuid4", return_value=fake_uuid), patch.object(
            api_local.config,
            "PAIRING_TTL_S",
            "bad",
        ), patch.object(
            api_local.pin_limiter,
            "reset",
            side_effect=RuntimeError("reset-error"),
        ):
            out = api_local.regenerate_code(_Req("127.0.0.1"))

        self.assertEqual(out["new_code"], "1111")
        self.assertIsNone(api_local.config.PAIRING_EXPIRES_AT)


if __name__ == "__main__":
    unittest.main()

