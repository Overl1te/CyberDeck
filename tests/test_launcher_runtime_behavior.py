import os
import sys
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


if __name__ == "__main__":
    unittest.main()

