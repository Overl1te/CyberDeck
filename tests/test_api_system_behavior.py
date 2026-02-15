import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import cyberdeck.api_system as api_system
from cyberdeck import context
from cyberdeck.sessions import DeviceSession


class ApiSystemBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepare shared fixtures for the test class."""
        app = FastAPI()
        app.include_router(api_system.router)
        cls.client = TestClient(app)

    def setUp(self):
        """Prepare test preconditions for each test case."""
        self._old_sessions = dict(context.device_manager.sessions)
        context.device_manager.sessions = {}

    def tearDown(self):
        """Clean up resources created by each test case."""
        context.device_manager.sessions = self._old_sessions

    @staticmethod
    def _headers(token: str) -> dict:
        """Return authorization headers for the active test session."""
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _add_session(token: str, settings: dict | None = None):
        """Register a synthetic session used by the test case."""
        context.device_manager.sessions[token] = DeviceSession(
            device_id=f"dev-{token}",
            device_name=f"Device {token}",
            ip="127.0.0.1",
            token=token,
            settings=settings or {},
        )

    def test_run_first_ok_returns_true_when_any_command_succeeds(self):
        """Validate scenario: test run first ok returns true when any command succeeds."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        p_fail = MagicMock(returncode=1)
        p_ok = MagicMock(returncode=0)
        with patch("cyberdeck.api_system.subprocess.run", side_effect=[p_fail, p_ok]) as mrun:
            ok = api_system._run_first_ok([["cmd1"], ["cmd2"]])
        self.assertTrue(ok)
        self.assertEqual(mrun.call_count, 2)

    def test_run_first_ok_returns_false_when_all_fail(self):
        """Validate scenario: test run first ok returns false when all fail."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        p_fail = MagicMock(returncode=5)
        with patch("cyberdeck.api_system.subprocess.run", return_value=p_fail):
            ok = api_system._run_first_ok([["a"], ["b"]])
        self.assertFalse(ok)

    def test_shutdown_linux_success(self):
        """Validate scenario: test shutdown linux success."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-power-ok"
        self._add_session(token, settings={"perm_power": True})
        with patch.object(api_system, "_IS_WINDOWS", False), patch.object(
            api_system, "_run_first_ok", return_value=True
        ) as mrun:
            r = self.client.post("/system/shutdown", headers=self._headers(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("status"), "shutdown")
        self.assertTrue(mrun.called)

    def test_shutdown_linux_failure(self):
        """Validate scenario: test shutdown linux failure."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-power-fail"
        self._add_session(token, settings={"perm_power": True})
        with patch.object(api_system, "_IS_WINDOWS", False), patch.object(
            api_system, "_run_first_ok", return_value=False
        ):
            r = self.client.post("/system/shutdown", headers=self._headers(token))
        self.assertEqual(r.status_code, 500, r.text)
        self.assertIn("shutdown_failed", r.text)

    def test_restart_windows_uses_shutdown_command(self):
        """Validate scenario: test restart windows uses shutdown command."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-restart"
        self._add_session(token, settings={"perm_power": True})
        with patch.object(api_system, "_IS_WINDOWS", True), patch.object(
            api_system, "_run_first_ok", return_value=True
        ) as mrun:
            r = self.client.post("/system/restart", headers=self._headers(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("status"), "restart")
        self.assertEqual(mrun.call_args[0][0], [["shutdown", "/r", "/t", "1"]])

    def test_logoff_windows_failure_propagates_http_error(self):
        """Validate scenario: test logoff windows failure propagates http error."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-logoff-fail"
        self._add_session(token, settings={"perm_power": True})
        with patch.object(api_system, "_IS_WINDOWS", True), patch.object(
            api_system, "_run_first_ok", return_value=False
        ):
            r = self.client.post("/system/logoff", headers=self._headers(token))
        self.assertEqual(r.status_code, 500, r.text)
        self.assertIn("logoff_failed", r.text)

    def test_volume_unknown_action(self):
        """Validate scenario: test volume unknown action."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-vol-unknown"
        self._add_session(token, settings={"perm_keyboard": True})
        r = self.client.post("/volume/not-real", headers=self._headers(token))
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("unknown_action", r.text)

    def test_volume_denied_without_keyboard_permission(self):
        """Validate scenario: test volume denied without keyboard permission."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-vol-denied"
        self._add_session(token, settings={"perm_keyboard": False})
        r = self.client.post("/volume/up", headers=self._headers(token))
        self.assertEqual(r.status_code, 403, r.text)

    def test_volume_returns_501_when_backend_cannot_press(self):
        """Validate scenario: test volume returns 501 when backend cannot press."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-vol-501"
        self._add_session(token, settings={"perm_keyboard": True})
        with patch.object(api_system.INPUT_BACKEND, "press", return_value=False):
            r = self.client.post("/volume/up", headers=self._headers(token))
        self.assertEqual(r.status_code, 501, r.text)
        self.assertIn("keyboard_input_unavailable", r.text)

    def test_volume_success(self):
        """Validate scenario: test volume success."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-vol-ok"
        self._add_session(token, settings={"perm_keyboard": True})
        with patch.object(api_system.INPUT_BACKEND, "press", return_value=True) as mpress:
            r = self.client.post("/volume/mute", headers=self._headers(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("status"), "ok")
        mpress.assert_called_once_with("volumemute")

    def test_run_background_ok_handles_spawn_errors(self):
        """Validate scenario: test run background ok handles spawn errors."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch("cyberdeck.api_system.subprocess.Popen", side_effect=OSError("boom")):
            self.assertFalse(api_system._run_background_ok(["noop"]))

    def test_linux_logoff_cmds_includes_session_terminate_when_session_id_present(self):
        """Validate scenario: test linux logoff cmds includes session terminate when session id present."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch.dict("os.environ", {"XDG_SESSION_ID": "s123"}, clear=False):
            cmds = api_system._linux_logoff_cmds()
        self.assertIn(["loginctl", "terminate-session", "s123"], cmds)

    def test_logoff_linux_not_supported_when_all_commands_fail(self):
        """Validate scenario: test logoff linux not supported when all commands fail."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-logoff-linux-fail"
        self._add_session(token, settings={"perm_power": True})
        with patch.object(api_system, "_IS_WINDOWS", False), patch.object(
            api_system, "_run_first_ok", return_value=False
        ):
            r = self.client.post("/system/logoff", headers=self._headers(token))
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("logoff_not_supported_on_this_system", r.text)

    def test_lock_linux_not_supported_when_commands_fail(self):
        """Validate scenario: test lock linux not supported when commands fail."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-lock-linux-fail"
        self._add_session(token, settings={"perm_power": True})
        with patch.object(api_system, "_IS_WINDOWS", False), patch.object(
            api_system, "_run_first_ok", return_value=False
        ):
            r = self.client.post("/system/lock", headers=self._headers(token))
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("lock_not_supported_on_this_system", r.text)

    def test_lock_windows_failure_propagates_error(self):
        """Validate scenario: test lock windows failure propagates error."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-lock-win-fail"
        self._add_session(token, settings={"perm_power": True})
        fake_windll = SimpleNamespace(user32=SimpleNamespace(LockWorkStation=MagicMock(side_effect=RuntimeError("deny"))))
        with patch.object(api_system, "_IS_WINDOWS", True), patch.object(api_system, "ctypes", SimpleNamespace(windll=fake_windll)):
            r = self.client.post("/system/lock", headers=self._headers(token))
        self.assertEqual(r.status_code, 500, r.text)
        self.assertIn("lock_failed", r.text)

    def test_sleep_linux_failure(self):
        """Validate scenario: test sleep linux failure."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-sleep-linux-fail"
        self._add_session(token, settings={"perm_power": True})
        with patch.object(api_system, "_IS_WINDOWS", False), patch.object(
            api_system, "_run_first_ok", return_value=False
        ):
            r = self.client.post("/system/sleep", headers=self._headers(token))
        self.assertEqual(r.status_code, 500, r.text)
        self.assertIn("sleep_failed", r.text)

    def test_hibernate_linux_success(self):
        """Validate scenario: test hibernate linux success."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-hibernate-linux-ok"
        self._add_session(token, settings={"perm_power": True})
        with patch.object(api_system, "_IS_WINDOWS", False), patch.object(
            api_system, "_run_first_ok", return_value=True
        ):
            r = self.client.post("/system/hibernate", headers=self._headers(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("status"), "hibernate")

    def test_sleep_windows_uses_rundll32_fallback(self):
        """Validate scenario: test sleep windows uses rundll32 fallback."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-sleep-win-fallback"
        self._add_session(token, settings={"perm_power": True})
        fake_windll = SimpleNamespace(powrprof=SimpleNamespace(SetSuspendState=MagicMock(side_effect=RuntimeError("fail"))))
        with patch.object(api_system, "_IS_WINDOWS", True), patch.object(api_system, "ctypes", SimpleNamespace(windll=fake_windll)), patch.object(
            api_system, "_run_background_ok", return_value=True
        ) as mbg:
            r = self.client.post("/system/sleep", headers=self._headers(token))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("status"), "sleep")
        self.assertTrue(mbg.called)

    def test_hibernate_windows_fails_when_fallback_cannot_start(self):
        """Validate scenario: test hibernate windows fails when fallback cannot start."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-hibernate-win-fail"
        self._add_session(token, settings={"perm_power": True})
        fake_windll = SimpleNamespace(powrprof=SimpleNamespace(SetSuspendState=MagicMock(side_effect=RuntimeError("fail"))))
        with patch.object(api_system, "_IS_WINDOWS", True), patch.object(api_system, "ctypes", SimpleNamespace(windll=fake_windll)), patch.object(
            api_system, "_run_background_ok", return_value=False
        ):
            r = self.client.post("/system/hibernate", headers=self._headers(token))
        self.assertEqual(r.status_code, 500, r.text)
        self.assertIn("hibernate_failed", r.text)


if __name__ == "__main__":
    unittest.main()
