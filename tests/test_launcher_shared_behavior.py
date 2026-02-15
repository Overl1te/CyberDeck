import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

if "pystray" not in sys.modules:
    pystray_stub = types.ModuleType("pystray")
    pystray_stub.Menu = lambda *args, **kwargs: None
    pystray_stub.MenuItem = lambda *args, **kwargs: None
    pystray_stub.Icon = lambda *args, **kwargs: None
    sys.modules["pystray"] = pystray_stub

import cyberdeck.launcher_shared as ls


class _OwnerWithTr:
    def tr(self, key: str, **kwargs):
        """Return mock localized value."""
        return f"{key}:{kwargs.get('x', '')}"


class _OwnerBrokenTr:
    def tr(self, key: str, **kwargs):
        """Raise to exercise fallback translator path."""
        raise RuntimeError("boom")


class LauncherSharedBehaviorTests(unittest.TestCase):
    def test_tr_any_uses_owner_translator_and_fallback(self):
        """Validate scenario: test tr any uses owner translator and fallback."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        self.assertEqual(ls._tr_any(_OwnerWithTr(), "k", x="1"), "k:1")
        with patch("cyberdeck.launcher_shared.i18n_tr", return_value="fallback"):
            self.assertEqual(ls._tr_any(_OwnerBrokenTr(), "k2"), "fallback")

    def test_tray_unavailable_reason_linux_wayland(self):
        """Validate scenario: test tray unavailable reason linux wayland."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch.object(sys, "platform", "linux"), patch.dict(
            os.environ,
            {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ""},
            clear=False,
        ):
            reason = ls.tray_unavailable_reason()
        self.assertIn("Wayland", reason)

    def test_load_json_merge_and_fallback(self):
        """Validate scenario: test load json merge and fallback."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "settings.json")
            default = {"a": 1, "b": 2}
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"b": 3, "c": 4}, f)
            out = ls.load_json(path, default)
            self.assertEqual(out, {"a": 1, "b": 3, "c": 4})
            with open(path, "w", encoding="utf-8") as f:
                f.write("{bad json")
            out2 = ls.load_json(path, default)
            self.assertEqual(out2, default)

    def test_save_json_writes_file(self):
        """Validate scenario: test save json writes file."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "out.json")
            ls.save_json(path, {"x": 1})
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data, {"x": 1})

    def test_set_autostart_linux_creates_and_removes_desktop_file(self):
        """Validate scenario: test set autostart linux creates and removes desktop file."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with tempfile.TemporaryDirectory() as td, patch.object(sys, "platform", "linux"), patch(
            "cyberdeck.launcher_shared.is_windows", return_value=False
        ), patch.dict(os.environ, {"HOME": td}, clear=False), patch(
            "cyberdeck.launcher_shared.os.path.expanduser", return_value=td
        ):
            ls.set_autostart(True, ["python", "main.py"])
            desktop = os.path.join(td, ".config", "autostart", "CyberDeck.desktop")
            self.assertTrue(os.path.exists(desktop))
            with open(desktop, "r", encoding="utf-8") as f:
                txt = f.read()
            self.assertIn("Exec=sh -lc", txt)
            ls.set_autostart(False, ["python", "main.py"])
            self.assertFalse(os.path.exists(desktop))

    def test_set_autostart_windows_write_and_delete(self):
        """Validate scenario: test set autostart windows write and delete."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake_key = MagicMock()
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_key
        fake_cm.__exit__.return_value = False
        fake_winreg = types.SimpleNamespace(
            HKEY_CURRENT_USER=1,
            KEY_SET_VALUE=2,
            REG_SZ=3,
            OpenKey=MagicMock(return_value=fake_cm),
            SetValueEx=MagicMock(),
            DeleteValue=MagicMock(),
        )
        sys.modules["winreg"] = fake_winreg  # imported lazily inside function
        try:
            with patch("cyberdeck.launcher_shared.is_windows", return_value=True):
                ls.set_autostart(True, "cmd")
                ls.set_autostart(False, "cmd")
        finally:
            sys.modules.pop("winreg", None)
        self.assertTrue(fake_winreg.SetValueEx.called)
        self.assertTrue(fake_winreg.DeleteValue.called)

    def test_ensure_null_stdio(self):
        """Validate scenario: test ensure null stdio."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        old_out = sys.stdout
        old_err = sys.stderr
        new_out = None
        new_err = None
        try:
            sys.stdout = None
            sys.stderr = None
            ls.ensure_null_stdio()
            new_out = sys.stdout
            new_err = sys.stderr
            self.assertIsNotNone(sys.stdout)
            self.assertIsNotNone(sys.stderr)
        finally:
            for h in (new_out, new_err):
                try:
                    if h not in (None, old_out, old_err):
                        h.close()
                except Exception:
                    pass
            sys.stdout = old_out
            sys.stderr = old_err

    def test_cyberbtn_applies_default_theme_values(self):
        """Validate scenario: test cyberbtn applies default theme values."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch.object(ls.ctk.CTkButton, "__init__", return_value=None) as minit:
            ls.CyberBtn(object(), text="ok")
        kwargs = minit.call_args.kwargs
        self.assertEqual(kwargs["text"], "ok")
        self.assertEqual(kwargs["corner_radius"], 8)
        self.assertEqual(kwargs["border_color"], ls.COLOR_BORDER)


if __name__ == "__main__":
    unittest.main()
