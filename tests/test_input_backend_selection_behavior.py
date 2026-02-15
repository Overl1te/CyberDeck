import unittest
from unittest.mock import patch

import cyberdeck.input_backend as input_backend


class InputBackendSelectionBehaviorTests(unittest.TestCase):
    def test_windows_session_uses_windows_backend(self):
        """Validate scenario: test windows session uses windows backend."""

        class FakeWindowsBackend:
            name = "fake_windows"

            def __init__(self) -> None:
                self.configured = False

            def _ensure(self) -> bool:
                return True

            def configure(self) -> None:
                self.configured = True

        with (
            patch.object(input_backend, "_session_kind", return_value="windows"),
            patch.object(input_backend, "_PyAutoGuiBackend", FakeWindowsBackend),
            patch.object(input_backend, "_is_linux_platform", return_value=False),
        ):
            backend = input_backend._build_backend()

        self.assertIsInstance(backend, FakeWindowsBackend)
        self.assertTrue(backend.configured)

    def test_linux_wayland_fallbacks_to_pyautogui_when_specialized_backend_fails(self):
        """Validate scenario: test linux wayland fallbacks to pyautogui when specialized backend fails."""

        class FakeWaylandBackend:
            name = "fake_wayland"

            def _ensure(self) -> bool:
                return False

            def configure(self) -> None:
                return None

        class FakeWindowsBackend:
            name = "fake_pyautogui"

            def __init__(self) -> None:
                self.configured = False

            def _ensure(self) -> bool:
                return True

            def configure(self) -> None:
                self.configured = True

        with (
            patch.object(input_backend, "_session_kind", return_value="wayland"),
            patch.object(input_backend, "_WaylandBackend", FakeWaylandBackend),
            patch.object(input_backend, "_PyAutoGuiBackend", FakeWindowsBackend),
            patch.object(input_backend, "_is_linux_platform", return_value=True),
        ):
            backend = input_backend._build_backend()

        self.assertIsInstance(backend, FakeWindowsBackend)
        self.assertTrue(backend.configured)

    def test_pyautogui_failure_falls_back_to_null_backend(self):
        """Validate scenario: test pyautogui failure falls back to null backend."""

        class FakeWindowsBackend:
            name = "fake_pyautogui"

            def _ensure(self) -> bool:
                return False

            def configure(self) -> None:
                return None

        class FakeNullBackend:
            name = "fake_null"

            def __init__(self) -> None:
                self.configured = False

            def configure(self) -> None:
                self.configured = True

        with (
            patch.object(input_backend, "_session_kind", return_value="windows"),
            patch.object(input_backend, "_PyAutoGuiBackend", FakeWindowsBackend),
            patch.object(input_backend, "_NullBackend", FakeNullBackend),
            patch.object(input_backend, "_is_linux_platform", return_value=False),
        ):
            backend = input_backend._build_backend()

        self.assertIsInstance(backend, FakeNullBackend)
        self.assertTrue(backend.configured)

    def test_linux_x11_keeps_x11_backend_when_ready(self):
        """Validate scenario: test linux x11 keeps x11 backend when ready."""

        class FakeX11Backend:
            name = "fake_x11"

            def __init__(self) -> None:
                self.configured = False

            def _ensure(self) -> bool:
                return True

            def configure(self) -> None:
                self.configured = True

        with (
            patch.object(input_backend, "_session_kind", return_value="x11"),
            patch.object(input_backend, "_X11Backend", FakeX11Backend),
            patch.object(input_backend, "_is_linux_platform", return_value=True),
        ):
            backend = input_backend._build_backend()

        self.assertIsInstance(backend, FakeX11Backend)
        self.assertTrue(backend.configured)


if __name__ == "__main__":
    unittest.main()

