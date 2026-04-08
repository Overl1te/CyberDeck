import os
import sys
import tempfile
import types
import unittest
from unittest import mock

if "pystray" not in sys.modules:
    pystray_stub = types.ModuleType("pystray")
    pystray_stub.Menu = lambda *args, **kwargs: None
    pystray_stub.MenuItem = lambda *args, **kwargs: None
    pystray_stub.Icon = lambda *args, **kwargs: None
    sys.modules["pystray"] = pystray_stub

from cyberdeck.launcher.app_navigation import AppNavigationMixin
from cyberdeck.launcher.app_runtime import AppRuntimeMixin
from cyberdeck.launcher.app_startup import AppStartupMixin
from cyberdeck.launcher.app_devices import AppDevicesMixin
from cyberdeck.launcher.settings import DEFAULT_SETTINGS


class LauncherSettingsBehaviorTests(unittest.TestCase):
    def test_default_tls_enabled_for_new_installs(self):
        """Validate scenario: launcher should default to TLS enabled."""
        self.assertTrue(bool(DEFAULT_SETTINGS.get("tls_enabled")))
        self.assertTrue(bool(DEFAULT_SETTINGS.get("cloudflare_enabled")))
        self.assertTrue(bool(DEFAULT_SETTINGS.get("cloudflare_auto_install")))
        self.assertTrue(bool(DEFAULT_SETTINGS.get("auto_update_check")))
        self.assertTrue(bool(DEFAULT_SETTINGS.get("auto_update_install")))

    def test_qr_payload_can_be_rewritten_for_public_cloudflare_origin(self):
        """Validate scenario: launcher should publish public Cloudflare origin in QR payload for remote pairing."""
        payload = {
            "type": "cyberdeck_qr_v1",
            "ip": "192.168.0.10",
            "port": 8080,
            "scheme": "https",
            "pairing_code": "1234",
            "qr_token": "qr-1",
        }
        url = (
            "https://192.168.0.10:8080/?type=cyberdeck_qr_v1"
            "&ip=192.168.0.10&port=8080&code=1234&qr_token=qr-1"
        )
        rewritten, rewritten_url = AppDevicesMixin._rewrite_qr_for_public_origin(
            payload,
            url=url,
            public_origin="https://demo.trycloudflare.com",
        )
        self.assertEqual(rewritten.get("ip"), "demo.trycloudflare.com")
        self.assertEqual(int(rewritten.get("port")), 443)
        self.assertEqual(rewritten.get("scheme"), "https")
        self.assertEqual(rewritten.get("lan_ip"), "192.168.0.10")
        self.assertIn("demo.trycloudflare.com", rewritten_url)
        self.assertIn("ip=demo.trycloudflare.com", rewritten_url)
        self.assertIn("port=443", rewritten_url)

    def test_normalize_app_config_removes_legacy_token_login_key(self):
        """Validate scenario: deprecated token URL login should be removed from launcher config."""
        fake = types.SimpleNamespace(
            app_config={
                "allow_query_token": True,
                "pairing_single_use": True,
                "ignore_vpn": True,
                "upload_max_bytes": "1024",
                "upload_allowed_ext": "txt, png",
                "verbose_http_log": False,
                "verbose_ws_log": True,
                "verbose_stream_log": False,
                "mdns_enabled": True,
                "device_approval_required": False,
            },
            _normalize_ext_csv=AppStartupMixin._normalize_ext_csv,
        )
        AppStartupMixin._normalize_app_config(fake)
        self.assertNotIn("allow_query_token", fake.app_config)
        self.assertEqual(fake.app_config.get("upload_allowed_ext"), ".txt,.png")

    def test_normalize_app_config_clamps_stream_and_audio_tuning(self):
        """Validate scenario: launcher should clamp stream/audio tuning values into safe ranges."""
        fake = types.SimpleNamespace(
            app_config={
                "stream_profile": "turbo",
                "stream_offer_fps": 999,
                "stream_offer_max_w": 320,
                "stream_offer_q": -1,
                "stream_offer_gop": 1,
                "stream_offer_preset": "",
                "h264_bitrate_k": 10,
                "h265_bitrate_k": 999999,
                "offer_audio_default": "yes",
                "audio_bitrate_k": 2,
                "audio_sample_rate": 192000,
                "audio_channels": 8,
                "audio_fallback_silent": 1,
                "stream_fast_resample_threshold": 5,
                "stream_subsampling_threshold": 1000,
            },
            _normalize_ext_csv=AppStartupMixin._normalize_ext_csv,
        )
        AppStartupMixin._normalize_app_config(fake)
        self.assertEqual(fake.app_config.get("stream_profile"), "balanced")
        self.assertEqual(int(fake.app_config.get("stream_offer_fps")), 120)
        self.assertEqual(int(fake.app_config.get("stream_offer_max_w")), 640)
        self.assertEqual(int(fake.app_config.get("stream_offer_q")), 20)
        self.assertEqual(int(fake.app_config.get("stream_offer_gop")), 10)
        self.assertEqual(str(fake.app_config.get("stream_offer_preset")), "veryfast")
        self.assertEqual(int(fake.app_config.get("h264_bitrate_k")), 500)
        self.assertEqual(int(fake.app_config.get("h265_bitrate_k")), 30000)
        self.assertTrue(bool(fake.app_config.get("offer_audio_default")))
        self.assertEqual(int(fake.app_config.get("audio_bitrate_k")), 48)
        self.assertEqual(int(fake.app_config.get("audio_sample_rate")), 96000)
        self.assertEqual(int(fake.app_config.get("audio_channels")), 2)
        self.assertTrue(bool(fake.app_config.get("audio_fallback_silent")))
        self.assertEqual(int(fake.app_config.get("stream_fast_resample_threshold")), 30)
        self.assertEqual(int(fake.app_config.get("stream_subsampling_threshold")), 120)

    def test_apply_cloudflare_runtime_uses_auto_install_and_download_override(self):
        """Validate scenario: launcher should pass auto-install options into Cloudflare runtime configuration."""

        class _Manager:
            def __init__(self) -> None:
                self.calls = []

            def configure(self, **kwargs):
                self.calls.append(kwargs)

            def snapshot(self):
                return types.SimpleNamespace(
                    enabled=True,
                    running=False,
                    status="starting",
                    public_url="",
                    last_error="",
                    binary_path="",
                    target_url="https://127.0.0.1:9443",
                    configured_url="",
                    pid=0,
                )

        manager = _Manager()
        applied = []
        fake = types.SimpleNamespace(
            settings={
                "cloudflare_enabled": True,
                "cloudflare_auto_install": True,
                "cloudflare_binary_path": "",
                "cloudflare_tunnel_token": "",
                "cloudflare_hostname": "",
            },
            cloudflare_manager=manager,
            _cloudflare_target_origin=lambda: "https://127.0.0.1:9443",
            _apply_cloudflare_snapshot=lambda snap: applied.append(snap),
        )

        with mock.patch.dict(
            os.environ,
            {"CYBERDECK_CLOUDFLARE_DOWNLOAD_URL": "https://example.com/cloudflared.exe"},
            clear=False,
        ):
            AppRuntimeMixin._apply_cloudflare_runtime(fake)

        self.assertEqual(len(manager.calls), 1)
        self.assertTrue(bool(manager.calls[0].get("auto_install")))
        self.assertEqual(manager.calls[0].get("download_url"), "https://example.com/cloudflared.exe")
        self.assertEqual(manager.calls[0].get("target_url"), "https://127.0.0.1:9443")
        self.assertEqual(len(applied), 1)
        self.assertEqual(str(applied[0].status), "starting")

    def test_toggle_remote_access_action_persists_setting_and_requests_refresh(self):
        """Validate scenario: Home button should toggle remote access without a server restart."""

        class _Switch:
            def __init__(self) -> None:
                self.state = False

            def select(self) -> None:
                self.state = True

            def deselect(self) -> None:
                self.state = False

        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = os.path.join(tmpdir, "launcher_settings.json")
            sw = _Switch()
            applied = []
            qr_calls = []
            sync_calls = []
            status_lines = []
            fake = types.SimpleNamespace(
                settings={"cloudflare_enabled": False},
                settings_path=settings_path,
                sw_cloudflare_enabled=sw,
                _apply_cloudflare_runtime=lambda: applied.append("ok"),
                refresh_qr_code=lambda force=False: qr_calls.append(force),
                request_sync=lambda delay=0: sync_calls.append(delay),
                _set_settings_status=lambda text, color=None: status_lines.append((text, color)),
                _inline_text=lambda ru_text, en_text: ru_text,
                show_toast=lambda *args, **kwargs: None,
                append_log=lambda *args, **kwargs: None,
                tr=lambda key, **kwargs: key,
            )

            AppNavigationMixin.toggle_remote_access_action(fake)

            self.assertTrue(bool(fake.settings.get("cloudflare_enabled")))
            self.assertTrue(bool(sw.state))
            self.assertEqual(applied, ["ok"])
            self.assertEqual(qr_calls, [True])
            self.assertEqual(sync_calls, [0])
            self.assertTrue(status_lines)

    def test_copy_local_access_copies_full_origin(self):
        """Validate scenario: Home copy action should place the full local URL into clipboard."""
        clipboard = []
        toasts = []
        fake = types.SimpleNamespace(
            _local_access_origin=lambda: "https://192.168.0.201:8080",
            clipboard_clear=lambda: clipboard.clear(),
            clipboard_append=lambda value: clipboard.append(str(value)),
            show_toast=lambda text, level="info": toasts.append((text, level)),
            tr=lambda key, **_kwargs: {
                "toast_local_access_copied": "Локальный адрес скопирован",
            }.get(key, key),
        )
        fake._copy_text_to_clipboard = lambda value, **kwargs: AppDevicesMixin._copy_text_to_clipboard(fake, value, **kwargs)

        AppDevicesMixin.copy_local_access(fake)

        self.assertEqual(clipboard, ["https://192.168.0.201:8080"])
        self.assertEqual(toasts, [("Локальный адрес скопирован", "success")])

    def test_copy_public_access_copies_full_origin(self):
        """Validate scenario: Home copy action should place the full public URL into clipboard."""
        clipboard = []
        toasts = []
        fake = types.SimpleNamespace(
            _public_access_origin=lambda: "https://demo.trycloudflare.com",
            clipboard_clear=lambda: clipboard.clear(),
            clipboard_append=lambda value: clipboard.append(str(value)),
            show_toast=lambda text, level="info": toasts.append((text, level)),
            tr=lambda key, **_kwargs: {
                "toast_public_access_copied": "Публичный адрес скопирован",
            }.get(key, key),
        )
        fake._copy_text_to_clipboard = lambda value, **kwargs: AppDevicesMixin._copy_text_to_clipboard(fake, value, **kwargs)

        AppDevicesMixin.copy_public_access(fake)

        self.assertEqual(clipboard, ["https://demo.trycloudflare.com"])
        self.assertEqual(toasts, [("Публичный адрес скопирован", "success")])


    def test_help_runtime_summary_includes_access_points_and_diag(self):
        """Validate scenario: help window should show a concise runtime snapshot with addresses and diagnostics."""
        fake = types.SimpleNamespace(
            _local_access_origin=lambda: "https://192.168.0.201:8080",
            _public_access_origin=lambda: "https://demo.trycloudflare.com",
            _format_uptime_short=lambda _seconds: "12m",
            _inline_text=lambda ru_text, en_text: ru_text,
            tr=lambda key, **kwargs: {
                "server_online_state": "Сервер: онлайн",
                "server_offline_state": "Сервер: нет связи",
                "server_version_line": f"Сервер: {kwargs.get('server')} | Лаунчер: {kwargs.get('launcher')}",
            }.get(key, key),
            server_online=True,
            cloudflare_status="online",
            cloudflare_last_error="",
            server_diag={"uptime_s": 720, "cpu": 18.0, "ram": 41.0},
            server_version="v1.3.2",
            log_file="C:/tmp/cyberdeck.log",
        )

        summary = AppNavigationMixin._help_runtime_summary(fake)

        self.assertIn("Локальный доступ: https://192.168.0.201:8080", summary)
        self.assertIn("Публичный доступ: https://demo.trycloudflare.com", summary)
        self.assertIn("Диагностика: uptime 12m | CPU 18% | RAM 41%", summary)
        self.assertIn("Сервер: v1.3.2 | Лаунчер:", summary)

    def test_help_diag_payload_redacts_sensitive_tokens(self):
        """Validate scenario: exported diagnostics should redact device and QR tokens."""
        fake = types.SimpleNamespace(
            settings={
                "language": "ru",
                "tls_enabled": True,
                "preferred_port": 8080,
                "cloudflare_enabled": True,
                "cloudflare_auto_install": True,
                "cloudflare_hostname": "https://demo.trycloudflare.com",
                "qr_mode": "app",
                "devices_panel_visible": True,
            },
            server_online=True,
            server_ip="192.168.0.201",
            server_port=8080,
            port=8080,
            api_scheme="https",
            server_version="v1.3.2",
            status_text="online",
            log_file="C:/tmp/cyberdeck.log",
            cloudflare_status="online",
            cloudflare_public_url="https://demo.trycloudflare.com",
            cloudflare_last_error="",
            cloudflare_target_url="https://127.0.0.1:8080",
            cloudflare_binary_resolved="C:/tools/cloudflared.exe",
            server_diag={
                "pairing": {"qr_token": "secret-qr"},
                "devices": [{"token": "device-secret", "name": "Phone"}],
            },
            _server_log_ring=["line 1\n", "line 2\n"],
            _local_access_origin=lambda: "https://192.168.0.201:8080",
            _public_access_origin=lambda: "https://demo.trycloudflare.com",
        )
        fake._scrub_sensitive_payload = lambda value: AppNavigationMixin._scrub_sensitive_payload(fake, value)

        payload = AppNavigationMixin._build_help_diag_payload(fake)

        self.assertEqual(payload["launcher"]["local_access"], "https://192.168.0.201:8080")
        self.assertEqual(payload["launcher"]["public_access"], "https://demo.trycloudflare.com")
        self.assertEqual(payload["server_diag"]["pairing"]["qr_token"], "<redacted>")
        self.assertEqual(payload["server_diag"]["devices"][0]["token"], "<redacted>")
        self.assertIn("line 1", payload["recent_logs_tail"])


if __name__ == "__main__":
    unittest.main()
