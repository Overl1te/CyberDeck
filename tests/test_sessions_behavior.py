import unittest
import tempfile
import os
from unittest.mock import patch

from cyberdeck import config
from cyberdeck.sessions import DeviceManager, DeviceSession


class SessionsBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepare shared fixtures for the test class."""
        cls._old_session_file = config.SESSION_FILE
        cls._tmp = tempfile.TemporaryDirectory()
        config.SESSION_FILE = os.path.join(cls._tmp.name, "cyberdeck_sessions.json")

    @classmethod
    def tearDownClass(cls):
        """Clean up shared fixtures for the test class."""
        config.SESSION_FILE = cls._old_session_file
        cls._tmp.cleanup()

    def test_unregister_socket_does_not_drop_newer_ws(self):
        """Validate scenario: test unregister socket does not drop newer ws."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        dm = DeviceManager()
        token = "tok-1"
        dm.sessions[token] = DeviceSession(device_id="d1", device_name="n1", ip="127.0.0.1", token=token)

        ws_old = object()
        ws_new = object()

        dm.register_socket(token, ws_old)  # type: ignore[arg-type]
        dm.register_socket(token, ws_new)  # type: ignore[arg-type]
        self.assertIs(dm.sessions[token].websocket, ws_new)

        # Old socket disconnect arrives late, must not clear new active socket.
        dm.unregister_socket(token, ws_old)  # type: ignore[arg-type]
        self.assertIs(dm.sessions[token].websocket, ws_new)

        dm.unregister_socket(token, ws_new)  # type: ignore[arg-type]
        self.assertIsNone(dm.sessions[token].websocket)

    def test_authorize_updates_existing_session_for_same_device_id(self):
        """Validate scenario: test authorize updates existing session for same device id."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        dm = DeviceManager()
        token = dm.authorize("dev-1", "Device A", "10.0.0.1")
        token2 = dm.authorize("dev-1", "Device A2", "10.0.0.2")
        self.assertEqual(token, token2)
        self.assertEqual(dm.sessions[token].device_name, "Device A2")
        self.assertEqual(dm.sessions[token].ip, "10.0.0.2")

    def test_get_session_drops_expired_and_returns_none(self):
        """Validate scenario: test get session drops expired and returns none."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        dm = DeviceManager()
        token = "tok-expired"
        dm.sessions[token] = DeviceSession(device_id="d", device_name="n", ip="127.0.0.1", token=token)
        dm.sessions[token].created_ts = 0.0
        dm.sessions[token].last_seen_ts = 0.0
        old_ttl = config.SESSION_TTL_S
        try:
            config.SESSION_TTL_S = 1
            with patch("cyberdeck.sessions.time.time", return_value=10.0):
                out = dm.get_session(token)
        finally:
            config.SESSION_TTL_S = old_ttl
        self.assertIsNone(out)
        self.assertNotIn(token, dm.sessions)

    def test_update_settings_handles_none_and_non_dict_patch(self):
        """Validate scenario: test update settings handles none and non dict patch."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        dm = DeviceManager()
        token = dm.authorize("dev-2", "Device B", "10.0.0.3")
        dm.sessions[token].settings = {"a": 1, "b": 2}
        self.assertFalse(dm.update_settings(token, None))  # type: ignore[arg-type]
        self.assertTrue(dm.update_settings(token, {"a": None, "c": 3}))
        self.assertNotIn("a", dm.sessions[token].settings)
        self.assertEqual(dm.sessions[token].settings["c"], 3)

    def test_delete_session_returns_false_when_missing(self):
        """Validate scenario: test delete session returns false when missing."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        dm = DeviceManager()
        self.assertFalse(dm.delete_session("nope"))

    def test_get_all_devices_reports_online_flag(self):
        """Validate scenario: test get all devices reports online flag."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        dm = DeviceManager()
        token = dm.authorize("dev-3", "Device C", "10.0.0.4")
        ws = object()
        dm.register_socket(token, ws)  # type: ignore[arg-type]
        devices = dm.get_all_devices()
        self.assertEqual(len(devices), 1)
        self.assertTrue(devices[0]["online"])

    def test_get_all_devices_uses_online_grace_after_socket_drop(self):
        """Validate scenario: online state should not flap immediately after websocket reconnect gap."""
        dm = DeviceManager()
        token = dm.authorize("dev-4", "Device D", "10.0.0.5")
        ws = object()
        old_grace = config.DEVICE_ONLINE_GRACE_S
        try:
            config.DEVICE_ONLINE_GRACE_S = 2.5
            with patch("cyberdeck.sessions.time.time", return_value=100.0):
                dm.register_socket(token, ws)  # type: ignore[arg-type]
            with patch("cyberdeck.sessions.time.time", return_value=101.0):
                dm.unregister_socket(token, ws)  # type: ignore[arg-type]
                devices = dm.get_all_devices()
            self.assertTrue(devices[0]["online"])
            with patch("cyberdeck.sessions.time.time", return_value=104.0):
                devices2 = dm.get_all_devices()
            self.assertFalse(devices2[0]["online"])
        finally:
            config.DEVICE_ONLINE_GRACE_S = old_grace

    def test_load_sessions_prunes_test_records_and_expired_records(self):
        """Validate scenario: test load sessions prunes test records and expired records."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        dm = DeviceManager()
        old_file = config.SESSION_FILE
        old_ttl = config.SESSION_TTL_S
        try:
            with tempfile.TemporaryDirectory() as td:
                config.SESSION_FILE = os.path.join(td, "sessions.json")
                config.SESSION_TTL_S = 1
                data = {
                    "tok-test": {
                        "device_id": "test-1",
                        "device_name": "CI Device",
                        "ip": "testclient",
                        "settings": {},
                        "created_ts": 10.0,
                        "last_seen_ts": 10.0,
                    },
                    "tok-exp": {
                        "device_id": "prod-1",
                        "device_name": "Prod",
                        "ip": "127.0.0.1",
                        "settings": {},
                        "created_ts": 1.0,
                        "last_seen_ts": 1.0,
                    },
                    "tok-ok": {
                        "device_id": "prod-2",
                        "device_name": "Prod2",
                        "ip": "127.0.0.1",
                        "settings": {"k": 1},
                        "created_ts": 50.0,
                        "last_seen_ts": 50.0,
                    },
                }
                import json

                with open(config.SESSION_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                with patch("cyberdeck.sessions.time.time", return_value=50.0):
                    dm.load_sessions()
                self.assertNotIn("tok-test", dm.sessions)
                self.assertNotIn("tok-exp", dm.sessions)
                self.assertIn("tok-ok", dm.sessions)
        finally:
            config.SESSION_FILE = old_file
            config.SESSION_TTL_S = old_ttl

    def test_load_sessions_handles_corrupted_json(self):
        """Validate scenario: test load sessions handles corrupted json."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        dm = DeviceManager()
        old_file = config.SESSION_FILE
        try:
            with tempfile.TemporaryDirectory() as td:
                config.SESSION_FILE = os.path.join(td, "sessions.json")
                with open(config.SESSION_FILE, "w", encoding="utf-8") as f:
                    f.write("{bad json")
                dm.load_sessions()
                self.assertEqual(dm.sessions, {})
        finally:
            config.SESSION_FILE = old_file


if __name__ == "__main__":
    unittest.main()
