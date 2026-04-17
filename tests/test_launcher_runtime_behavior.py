import os
import sys
import time
import types
import unittest
from unittest.mock import patch

if "pystray" not in sys.modules:
    pystray_stub = types.ModuleType("pystray")
    pystray_stub.Menu = lambda *args, **kwargs: None
    pystray_stub.MenuItem = lambda *args, **kwargs: None
    pystray_stub.Icon = lambda *args, **kwargs: None
    sys.modules["pystray"] = pystray_stub

from cyberdeck.launcher.app_runtime import AppRuntimeMixin


class _DummyRuntime(AppRuntimeMixin):
    def __init__(self):
        self.server_thread = None
        self._uvicorn_server = None
        self.port = 8080
        self.logs = []
        self.errors = []

    def append_log(self, text: str):
        self.logs.append(str(text))

    def _show_server_start_error(self, text: str):
        self.errors.append(str(text))


class _NoopThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}
        self.daemon = daemon

    def start(self):
        return None

    def is_alive(self):
        return False


class LauncherRuntimeBehaviorTests(unittest.TestCase):
    def test_start_server_inprocess_accepts_bool_words_for_debug_log_tls(self):
        """Validate scenario: runtime launch should parse bool-like words for debug/log/tls env flags."""
        dummy = _DummyRuntime()
        fake_main = types.ModuleType("main")
        fake_main.app = object()
        captured = {}

        class _Cfg:
            def __init__(self, *args, **kwargs):
                captured["cfg_args"] = args
                captured["cfg_kwargs"] = dict(kwargs)

        class _Srv:
            def __init__(self, cfg):
                captured["server_cfg"] = cfg

            def run(self):
                return None

        env = {
            "CYBERDECK_DEBUG": "yes",
            "CYBERDECK_LOG": "on",
            "CYBERDECK_TLS": "true",
            "CYBERDECK_TLS_CERT": "/tmp/cert.pem",
            "CYBERDECK_TLS_KEY": "/tmp/key.pem",
        }
        with patch.dict(sys.modules, {"main": fake_main}, clear=False), patch.dict(os.environ, env, clear=False), patch(
            "cyberdeck.config.reload_from_env", return_value=None
        ), patch(
            "cyberdeck.logging_config.reload_logging", return_value=None
        ), patch(
            "cyberdeck.launcher.app_runtime.uvicorn.Config", _Cfg
        ), patch(
            "cyberdeck.launcher.app_runtime.uvicorn.Server", _Srv
        ), patch(
            "cyberdeck.launcher.app_runtime.threading.Thread", _NoopThread
        ):
            dummy.start_server_inprocess()

        kwargs = captured["cfg_kwargs"]
        self.assertEqual(kwargs["log_level"], "debug")
        self.assertTrue(kwargs["access_log"])
        self.assertEqual(kwargs["ssl_certfile"], "/tmp/cert.pem")
        self.assertEqual(kwargs["ssl_keyfile"], "/tmp/key.pem")

    def test_start_server_inprocess_disables_logs_when_log_flag_is_off(self):
        """Validate scenario: log flag should disable uvicorn logs even when debug is enabled."""
        dummy = _DummyRuntime()
        fake_main = types.ModuleType("main")
        fake_main.app = object()
        captured = {}

        class _Cfg:
            def __init__(self, *args, **kwargs):
                captured["cfg_kwargs"] = dict(kwargs)

        class _Srv:
            def __init__(self, _cfg):
                return None

            def run(self):
                return None

        env = {
            "CYBERDECK_DEBUG": "yes",
            "CYBERDECK_LOG": "off",
            "CYBERDECK_TLS": "0",
        }
        with patch.dict(sys.modules, {"main": fake_main}, clear=False), patch.dict(os.environ, env, clear=False), patch(
            "cyberdeck.config.reload_from_env", return_value=None
        ), patch(
            "cyberdeck.logging_config.reload_logging", return_value=None
        ), patch(
            "cyberdeck.launcher.app_runtime.uvicorn.Config", _Cfg
        ), patch(
            "cyberdeck.launcher.app_runtime.uvicorn.Server", _Srv
        ), patch(
            "cyberdeck.launcher.app_runtime.threading.Thread", _NoopThread
        ):
            dummy.start_server_inprocess()

        kwargs = captured["cfg_kwargs"]
        self.assertEqual(kwargs["log_level"], "critical")
        self.assertFalse(kwargs["access_log"])

    def test_start_server_inprocess_disables_tls_for_off_value(self):
        """Validate scenario: tls flag should treat 'off' as disabled even when cert/key are set."""
        dummy = _DummyRuntime()
        fake_main = types.ModuleType("main")
        fake_main.app = object()
        captured = {}

        class _Cfg:
            def __init__(self, *args, **kwargs):
                captured["cfg_kwargs"] = dict(kwargs)

        class _Srv:
            def __init__(self, _cfg):
                return None

            def run(self):
                return None

        env = {
            "CYBERDECK_DEBUG": "0",
            "CYBERDECK_LOG": "1",
            "CYBERDECK_TLS": "off",
            "CYBERDECK_TLS_CERT": "/tmp/cert.pem",
            "CYBERDECK_TLS_KEY": "/tmp/key.pem",
        }
        with patch.dict(sys.modules, {"main": fake_main}, clear=False), patch.dict(os.environ, env, clear=False), patch(
            "cyberdeck.config.reload_from_env", return_value=None
        ), patch(
            "cyberdeck.logging_config.reload_logging", return_value=None
        ), patch(
            "cyberdeck.launcher.app_runtime.uvicorn.Config", _Cfg
        ), patch(
            "cyberdeck.launcher.app_runtime.uvicorn.Server", _Srv
        ), patch(
            "cyberdeck.launcher.app_runtime.threading.Thread", _NoopThread
        ):
            dummy.start_server_inprocess()

        kwargs = captured["cfg_kwargs"]
        self.assertIsNone(kwargs["ssl_certfile"])
        self.assertIsNone(kwargs["ssl_keyfile"])

    def test_sync_info_timeout_is_relaxed_during_startup_grace(self):
        """Validate scenario: first launcher sync should use a larger timeout while server is booting."""
        fake = types.SimpleNamespace(
            _boot_server_ready_announced=False,
            server_online=False,
            _boot_started_ts=time.time(),
            _startup_sync_grace_s=lambda: 8.0,
        )
        self.assertEqual(AppRuntimeMixin._sync_info_timeout(fake), 2.5)

    def test_sync_info_timeout_returns_default_after_boot_ready(self):
        """Validate scenario: normal sync timeout should be restored after boot is ready."""
        fake = types.SimpleNamespace(
            _boot_server_ready_announced=True,
            server_online=True,
            _boot_started_ts=time.time(),
            _startup_sync_grace_s=lambda: 8.0,
        )
        self.assertEqual(AppRuntimeMixin._sync_info_timeout(fake), 1.0)

    def test_startup_sync_timeout_is_suppressed_while_booting(self):
        """Validate scenario: early transport noise should stay out of launcher logs during boot."""
        fake = types.SimpleNamespace(
            _boot_server_ready_announced=False,
            server_online=False,
            _boot_started_ts=time.time(),
            _startup_sync_grace_s=lambda: 8.0,
        )
        self.assertTrue(AppRuntimeMixin._should_suppress_startup_sync_error(fake, "request timeout"))
        self.assertTrue(AppRuntimeMixin._should_suppress_startup_sync_error(fake, "connection failed"))
        self.assertFalse(AppRuntimeMixin._should_suppress_startup_sync_error(fake, "TLS verification failed"))

    def test_startup_sync_timeout_is_not_suppressed_after_grace(self):
        """Validate scenario: late startup failures should still be surfaced to the user."""
        fake = types.SimpleNamespace(
            _boot_server_ready_announced=False,
            server_online=False,
            _boot_started_ts=(time.time() - 20.0),
            _startup_sync_grace_s=lambda: 8.0,
        )
        self.assertFalse(AppRuntimeMixin._should_suppress_startup_sync_error(fake, "request timeout"))

    def test_rearm_server_startup_grace_resets_boot_state_for_restart(self):
        """Validate scenario: restart should regain startup grace instead of logging a false timeout."""
        fake = types.SimpleNamespace(
            _boot_server_ready_announced=True,
            server_online=True,
            _boot_started_ts=0.0,
        )
        with patch("cyberdeck.launcher.app_runtime.time.time", return_value=1234.5):
            AppRuntimeMixin._rearm_server_startup_grace(fake)
        self.assertFalse(fake._boot_server_ready_announced)
        self.assertFalse(fake.server_online)
        self.assertEqual(fake._boot_started_ts, 1234.5)

    def test_format_console_line_normalizes_launcher_prefix(self):
        """Validate scenario: console mode should render launcher logs in a concise structured format."""
        fake = types.SimpleNamespace(_console_timestamp=lambda: "11:35:07")
        out = AppRuntimeMixin._format_console_line(fake, "[launcher] server process started\n")
        self.assertEqual(out, "11:35:07 | launcher | server process started\n")

    def test_format_console_line_preserves_server_structured_logs(self):
        """Validate scenario: already-structured server logs should pass through unchanged."""
        fake = types.SimpleNamespace(_console_timestamp=lambda: "11:35:07")
        line = "2026-03-22 11:35:08,161 | INFO | cyberdeck | UDP discovery listening on 5555\n"
        self.assertEqual(AppRuntimeMixin._format_console_line(fake, line), line)

    def test_local_access_origin_uses_full_scheme_host_and_port(self):
        """Validate scenario: Home screen should expose a complete local origin that can be copied directly."""
        fake = types.SimpleNamespace(
            server_ip="192.168.0.201",
            server_port=8080,
            api_scheme="https",
            tls_enabled=True,
            port=8080,
        )
        self.assertEqual(
            AppRuntimeMixin._local_access_origin(fake),
            "https://192.168.0.201:8080",
        )

    def test_log_console_state_changes_reports_local_and_public_ready(self):
        """Validate scenario: console mode should emit readable runtime state transitions once."""
        fake = types.SimpleNamespace(
            logs_enabled=True,
            server_online=True,
            server_ip="192.168.0.201",
            server_port=8080,
            api_scheme="https",
            cloudflare_status="online",
            cloudflare_public_url="https://demo.trycloudflare.com",
            cloudflare_last_error="",
            _console_last_server_online=None,
            _console_last_server_endpoint="",
            _console_last_cloudflare_sig=None,
            append_log=lambda text: fake.logs.append(str(text)),
            logs=[],
        )
        AppRuntimeMixin._log_console_state_changes(fake)
        self.assertEqual(
            fake.logs,
            [
                "[launcher] local api ready: 192.168.0.201:8080 (HTTPS)\n",
                "[cloudflare] public access ready: https://demo.trycloudflare.com\n",
            ],
        )

    def test_friendly_remote_access_detail_maps_missing_cloudflare_token(self):
        """Validate scenario: launcher should show short translated Cloudflare token guidance in Home card."""
        fake = types.SimpleNamespace(
            tr=lambda key, **_kwargs: {
                "remote_access_cloudflare_token_needed": "Нужен токен Named Tunnel Cloudflare",
            }.get(key, key)
        )
        self.assertEqual(
            AppRuntimeMixin._friendly_remote_access_detail(
                fake,
                "cloudflared tunnel run --token requires a token value",
            ),
            "Нужен токен Named Tunnel Cloudflare",
        )

    def test_friendly_remote_access_detail_maps_quick_tunnel_dns_failure(self):
        """Validate scenario: DNS resolution failures should show short Quick Tunnel guidance instead of raw traceback text."""
        fake = types.SimpleNamespace(
            tr=lambda key, **_kwargs: {
                "remote_access_cloudflare_dns": "Адрес trycloudflare не резолвится через текущий DNS/IPv6",
            }.get(key, key)
        )
        self.assertEqual(
            AppRuntimeMixin._friendly_remote_access_detail(
                fake,
                "NameResolutionError: getaddrinfo failed for reported-opposed-periodic-holly.trycloudflare.com",
            ),
            "Адрес trycloudflare не резолвится через текущий DNS/IPv6",
        )

    def test_apply_cloudflare_snapshot_keeps_last_error_visible_until_online(self):
        """Validate scenario: Home card should preserve the last tunnel failure across automatic restarts until relay is healthy."""
        fake = types.SimpleNamespace(cloudflare_last_error_sticky="")
        AppRuntimeMixin._apply_cloudflare_snapshot(
            fake,
            types.SimpleNamespace(
                status="error",
                public_url="",
                last_error="quick tunnel public URL did not become reachable; retrying",
                binary_path="C:\\tools\\cloudflared.exe",
                target_url="http://127.0.0.1:8080",
            ),
        )
        self.assertEqual(
            fake.cloudflare_last_error_sticky,
            "quick tunnel public URL did not become reachable; retrying",
        )

        AppRuntimeMixin._apply_cloudflare_snapshot(
            fake,
            types.SimpleNamespace(
                status="starting",
                public_url="",
                last_error="",
                binary_path="C:\\tools\\cloudflared.exe",
                target_url="http://127.0.0.1:8080",
            ),
        )
        self.assertEqual(
            fake.cloudflare_last_error_sticky,
            "quick tunnel public URL did not become reachable; retrying",
        )

        AppRuntimeMixin._apply_cloudflare_snapshot(
            fake,
            types.SimpleNamespace(
                status="online",
                public_url="https://demo.trycloudflare.com",
                last_error="",
                binary_path="C:\\tools\\cloudflared.exe",
                target_url="http://127.0.0.1:8080",
            ),
        )
        self.assertEqual(fake.cloudflare_last_error_sticky, "")

    def test_should_attempt_auto_update_requires_windows_packaged_launcher_update(self):
        """Validate scenario: unattended install should start only for packaged Windows launcher updates with setup asset."""
        fake = types.SimpleNamespace(
            settings={"auto_update_check": True, "auto_update_install": True},
            server_online=True,
            _auto_update_request_inflight=False,
            _auto_update_shutdown_scheduled=False,
            _auto_update_last_attempt_tag="",
            _auto_update_last_attempt_ts=0.0,
            update_state={
                "launcher": {
                    "has_update": True,
                    "latest_tag": "v1.3.3",
                    "preferred_asset": {"kind": "windows_installer"},
                }
            },
            _launcher_update_channel=lambda: {"has_update": True, "latest_tag": "v1.3.3", "preferred_asset": {"kind": "windows_installer"}},
            _channel_has_update=AppRuntimeMixin._channel_has_update,
            _channel_preferred_asset=AppRuntimeMixin._channel_preferred_asset,
            _channel_latest_tag=AppRuntimeMixin._channel_latest_tag,
            _auto_update_retry_cooldown_s=lambda: 21600.0,
        )
        with patch("cyberdeck.launcher.app_runtime.is_windows", return_value=True), patch(
            "cyberdeck.launcher.app_runtime.is_packaged_runtime",
            return_value=True,
        ):
            should_run, latest_tag = AppRuntimeMixin._should_attempt_auto_update(fake)
        self.assertTrue(should_run)
        self.assertEqual(latest_tag, "v1.3.3")

    def test_should_attempt_auto_update_respects_retry_cooldown(self):
        """Validate scenario: same release should not be retried immediately after a failed automatic install attempt."""
        now_ts = time.time()
        fake = types.SimpleNamespace(
            settings={"auto_update_check": True, "auto_update_install": True},
            server_online=True,
            _auto_update_request_inflight=False,
            _auto_update_shutdown_scheduled=False,
            _auto_update_last_attempt_tag="v1.3.3",
            _auto_update_last_attempt_ts=now_ts,
            update_state={
                "launcher": {
                    "has_update": True,
                    "latest_tag": "v1.3.3",
                    "preferred_asset": {"kind": "windows_installer"},
                }
            },
            _launcher_update_channel=lambda: {"has_update": True, "latest_tag": "v1.3.3", "preferred_asset": {"kind": "windows_installer"}},
            _channel_has_update=AppRuntimeMixin._channel_has_update,
            _channel_preferred_asset=AppRuntimeMixin._channel_preferred_asset,
            _channel_latest_tag=AppRuntimeMixin._channel_latest_tag,
            _auto_update_retry_cooldown_s=lambda: 21600.0,
        )
        with patch("cyberdeck.launcher.app_runtime.is_windows", return_value=True), patch(
            "cyberdeck.launcher.app_runtime.is_packaged_runtime",
            return_value=True,
        ), patch("cyberdeck.launcher.app_runtime.time.time", return_value=now_ts + 120.0):
            should_run, latest_tag = AppRuntimeMixin._should_attempt_auto_update(fake)
        self.assertFalse(should_run)
        self.assertEqual(latest_tag, "")


if __name__ == "__main__":
    unittest.main()

