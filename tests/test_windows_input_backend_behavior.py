import types
import unittest
from unittest.mock import MagicMock

from cyberdeck.input.backends.windows import _PyAutoGuiBackend


class _FailingPyAutoGui:
    FAILSAFE = True
    PAUSE = 0.1

    def moveRel(self, *args, **kwargs):
        raise RuntimeError("move_failed")

    def click(self, *args, **kwargs):
        raise RuntimeError("click_failed")

    def mouseDown(self, *args, **kwargs):
        raise RuntimeError("down_failed")

    def mouseUp(self, *args, **kwargs):
        raise RuntimeError("up_failed")

    def scroll(self, *args, **kwargs):
        raise RuntimeError("scroll_failed")


class WindowsInputBackendBehaviorTests(unittest.TestCase):
    def _backend_with_winapi_fallback(self) -> _PyAutoGuiBackend:
        backend = _PyAutoGuiBackend()
        backend._loaded = True
        backend._pg = _FailingPyAutoGui()
        backend._win_loaded = True
        backend._user32 = types.SimpleNamespace(
            SetCursorPos=MagicMock(return_value=1),
            mouse_event=MagicMock(),
        )
        return backend

    def test_move_rel_falls_back_to_set_cursor_pos_when_pyautogui_fails(self):
        """Validate scenario: move_rel should use WinAPI fallback when pyautogui move fails."""
        backend = self._backend_with_winapi_fallback()
        backend.position = lambda: (100, 200)

        ok = backend.move_rel(5, -3)

        self.assertTrue(ok)
        backend._user32.SetCursorPos.assert_called_once_with(105, 197)

    def test_click_falls_back_to_mouse_event_for_double_click(self):
        """Validate scenario: double click should emit down/up pairs through WinAPI fallback."""
        backend = self._backend_with_winapi_fallback()

        ok = backend.click("right", double=True)

        self.assertTrue(ok)
        # right-down + right-up repeated twice
        self.assertEqual(backend._user32.mouse_event.call_count, 4)

    def test_scroll_falls_back_to_mouse_event_wheel(self):
        """Validate scenario: wheel scroll should map to WinAPI wheel delta fallback."""
        backend = self._backend_with_winapi_fallback()

        ok = backend.scroll(2)

        self.assertTrue(ok)
        backend._user32.mouse_event.assert_called_once()
        args = backend._user32.mouse_event.call_args.args
        self.assertEqual(args[3], 240)


if __name__ == "__main__":
    unittest.main()
