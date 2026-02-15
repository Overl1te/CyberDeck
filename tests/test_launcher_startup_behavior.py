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

from cyberdeck.launcher_app_startup import AppStartupMixin


class LauncherStartupBehaviorTests(unittest.TestCase):
    def test_run_as_admin_uses_launcher_entry_script_for_non_frozen_mode(self):
        """Validate scenario: test run as admin uses launcher entry script for non frozen mode."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake_shell32 = types.SimpleNamespace(ShellExecuteW=lambda *args: 33)
        fake_windll = types.SimpleNamespace(shell32=fake_shell32)
        with patch("cyberdeck.launcher_app_startup.is_windows", return_value=True), patch.object(
            sys, "argv", ["C:\\Work\\CyberDeck\\launcher.py", "-c"]
        ), patch(
            "cyberdeck.launcher_app_startup.ctypes", types.SimpleNamespace(windll=fake_windll)
        ):
            ok = AppStartupMixin.run_as_admin(types.SimpleNamespace())
        self.assertTrue(ok)

    def test_run_as_admin_returns_false_when_shell_execute_fails(self):
        """Validate scenario: test run as admin returns false when shell execute fails."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake_shell32 = types.SimpleNamespace(ShellExecuteW=lambda *args: 31)
        fake_windll = types.SimpleNamespace(shell32=fake_shell32)
        with patch("cyberdeck.launcher_app_startup.is_windows", return_value=True), patch.object(
            sys, "argv", ["C:\\Work\\CyberDeck\\launcher.py"]
        ), patch(
            "cyberdeck.launcher_app_startup.ctypes", types.SimpleNamespace(windll=fake_windll)
        ):
            ok = AppStartupMixin.run_as_admin(types.SimpleNamespace())
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
