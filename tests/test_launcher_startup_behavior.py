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

from cyberdeck.launcher.app_startup import AppStartupMixin


class LauncherStartupBehaviorTests(unittest.TestCase):
    def test_run_as_admin_uses_launcher_entry_script_for_non_frozen_mode(self):
        """Validate scenario: test run as admin uses launcher entry script for non frozen mode."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake_shell32 = types.SimpleNamespace(ShellExecuteW=lambda *args: 33)
        fake_windll = types.SimpleNamespace(shell32=fake_shell32)
        with patch("cyberdeck.launcher.app_startup.is_windows", return_value=True), patch.object(
            sys, "argv", ["C:\\Work\\CyberDeck\\launcher.py", "-c"]
        ), patch(
            "cyberdeck.launcher.app_startup.ctypes", types.SimpleNamespace(windll=fake_windll)
        ):
            ok = AppStartupMixin.run_as_admin(types.SimpleNamespace())
        self.assertTrue(ok)

    def test_run_as_admin_returns_false_when_shell_execute_fails(self):
        """Validate scenario: test run as admin returns false when shell execute fails."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake_shell32 = types.SimpleNamespace(ShellExecuteW=lambda *args: 31)
        fake_windll = types.SimpleNamespace(shell32=fake_shell32)
        with patch("cyberdeck.launcher.app_startup.is_windows", return_value=True), patch.object(
            sys, "argv", ["C:\\Work\\CyberDeck\\launcher.py"]
        ), patch(
            "cyberdeck.launcher.app_startup.ctypes", types.SimpleNamespace(windll=fake_windll)
        ):
            ok = AppStartupMixin.run_as_admin(types.SimpleNamespace())
        self.assertFalse(ok)

    def test_enforce_admin_rights_relaunches_and_exits_when_not_admin(self):
        """Validate scenario: startup should relaunch elevated and terminate current process."""
        fake = types.SimpleNamespace(
            console_mode=False,
            is_admin=lambda: False,
            run_as_admin=lambda: True,
        )
        with patch("cyberdeck.launcher.app_startup.is_windows", return_value=True), patch.dict(
            "os.environ", {}, clear=False
        ), patch.object(sys, "argv", ["C:\\Work\\CyberDeck\\launcher.py"]):
            with self.assertRaises(SystemExit) as ctx:
                AppStartupMixin._enforce_admin_rights(fake)
        self.assertEqual(ctx.exception.code, 0)

    def test_enforce_admin_rights_exits_with_error_when_relaunch_fails(self):
        """Validate scenario: startup should stop when elevation cannot be acquired."""
        fake = types.SimpleNamespace(
            console_mode=False,
            is_admin=lambda: False,
            run_as_admin=lambda: False,
        )
        with patch("cyberdeck.launcher.app_startup.is_windows", return_value=True), patch.dict(
            "os.environ", {}, clear=False
        ), patch.object(sys, "argv", ["C:\\Work\\CyberDeck\\launcher.py"]), patch(
            "cyberdeck.launcher.app_startup.messagebox.showerror", return_value=None
        ):
            with self.assertRaises(SystemExit) as ctx:
                AppStartupMixin._enforce_admin_rights(fake)
        self.assertEqual(ctx.exception.code, 1)

    def test_enforce_admin_rights_noop_when_already_admin(self):
        """Validate scenario: startup should continue normally when already elevated."""
        fake = types.SimpleNamespace(
            console_mode=False,
            is_admin=lambda: True,
            run_as_admin=lambda: False,
        )
        with patch("cyberdeck.launcher.app_startup.is_windows", return_value=True):
            AppStartupMixin._enforce_admin_rights(fake)


if __name__ == "__main__":
    unittest.main()

