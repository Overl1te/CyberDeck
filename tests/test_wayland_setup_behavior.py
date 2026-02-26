import sys
import unittest
from unittest.mock import patch

import cyberdeck.platform.wayland_setup as wayland_setup


class WaylandSetupBehaviorTests(unittest.TestCase):
    def test_wayland_setup_script_names_prioritize_fedora_for_dnf(self):
        """Validate scenario: dnf hosts should prioritize the Fedora setup script first."""
        with patch.object(wayland_setup, "_linux_pkg_manager", return_value="dnf"):
            names = wayland_setup._wayland_setup_script_names()

        self.assertTrue(names)
        self.assertEqual(names[0], "setup_fedora_wayland.sh")

    def test_check_wayland_requirements_accepts_x11grab_fallback(self):
        """Validate scenario: X11 fallback should satisfy stream backend requirement on Wayland."""
        with patch.object(wayland_setup, "is_linux_wayland_session", return_value=True), patch.object(
            wayland_setup, "_ffmpeg_supports_pipewire", return_value=False
        ), patch.object(
            wayland_setup, "_ffmpeg_supports_x11grab", return_value=True
        ), patch.object(
            wayland_setup, "_wayland_allow_x11_fallback", return_value=True
        ), patch.object(
            wayland_setup, "_gst_supports_pipewire", return_value=False
        ), patch.object(
            wayland_setup, "_wayland_screenshot_available", return_value=False
        ), patch.object(
            wayland_setup, "_wayland_text_tools_available", return_value=True
        ), patch.object(
            wayland_setup.shutil, "which", return_value="/usr/bin/ffmpeg"
        ), patch.object(
            wayland_setup.os.path, "exists", return_value=True
        ), patch.object(
            wayland_setup.os, "access", return_value=True
        ), patch.dict(
            sys.modules, {"evdev": object()}
        ):
            issues = wayland_setup.check_wayland_requirements()

        self.assertEqual(issues, [])

    def test_check_wayland_requirements_flags_missing_backends(self):
        """Validate scenario: no capture backend should report stream backend issue."""
        with patch.object(wayland_setup, "is_linux_wayland_session", return_value=True), patch.object(
            wayland_setup, "_ffmpeg_supports_pipewire", return_value=False
        ), patch.object(
            wayland_setup, "_ffmpeg_supports_x11grab", return_value=False
        ), patch.object(
            wayland_setup, "_wayland_allow_x11_fallback", return_value=False
        ), patch.object(
            wayland_setup, "_gst_supports_pipewire", return_value=False
        ), patch.object(
            wayland_setup, "_wayland_screenshot_available", return_value=False
        ), patch.object(
            wayland_setup, "_wayland_text_tools_available", return_value=True
        ), patch.object(
            wayland_setup.shutil, "which", return_value=None
        ), patch.object(
            wayland_setup.os.path, "exists", return_value=True
        ), patch.object(
            wayland_setup.os, "access", return_value=True
        ), patch.dict(
            sys.modules, {"evdev": object()}
        ):
            issues = wayland_setup.check_wayland_requirements()

        self.assertIn("stream_backend_missing_pipewire", issues)

    def test_format_wayland_issues_returns_readable_messages(self):
        """Validate scenario: issue formatter should return readable text, not mojibake."""
        message = wayland_setup.format_wayland_issues([
            "stream_backend_missing_pipewire",
            "uinput_no_access",
        ])
        self.assertIn("no working Wayland stream backend", message)
        self.assertIn("no access to /dev/uinput", message)

    def test_runtime_wayland_policy_sets_x11_fallback_order(self):
        """Validate scenario: runtime policy should prioritize ffmpeg x11 fallback when available."""
        with patch.object(wayland_setup, "is_linux_wayland_session", return_value=True), patch.object(
            wayland_setup, "_ffmpeg_supports_pipewire", return_value=False
        ), patch.object(
            wayland_setup, "_ffmpeg_supports_x11grab", return_value=True
        ), patch.object(
            wayland_setup, "_wayland_allow_x11_fallback", return_value=True
        ), patch.object(
            wayland_setup, "_gst_supports_pipewire", return_value=False
        ), patch.object(
            wayland_setup, "_wayland_screenshot_available", return_value=False
        ), patch.object(
            wayland_setup.shutil, "which", return_value="/usr/bin/ffmpeg"
        ), patch.dict(
            wayland_setup.os.environ, {"DISPLAY": ":0"}, clear=True
        ):
            applied = wayland_setup._apply_runtime_wayland_policy()
            order = wayland_setup.os.environ.get("CYBERDECK_MJPEG_BACKEND_ORDER")
            prefer = wayland_setup.os.environ.get("CYBERDECK_PREFER_MJPEG_OFFER")

        self.assertIn("CYBERDECK_MJPEG_BACKEND_ORDER=ffmpeg,screenshot,gstreamer,native", applied)
        self.assertEqual(order, "ffmpeg,screenshot,gstreamer,native")
        self.assertEqual(prefer, "1")

    def test_runtime_wayland_policy_prefers_realtime_backends_over_screenshot(self):
        """Validate scenario: when gstreamer+ffmpeg are usable, screenshot should stay as fallback."""
        with patch.object(wayland_setup, "is_linux_wayland_session", return_value=True), patch.object(
            wayland_setup, "_ffmpeg_supports_pipewire", return_value=False
        ), patch.object(
            wayland_setup, "_ffmpeg_supports_x11grab", return_value=True
        ), patch.object(
            wayland_setup, "_wayland_allow_x11_fallback", return_value=True
        ), patch.object(
            wayland_setup, "_gst_supports_pipewire", return_value=True
        ), patch.object(
            wayland_setup, "_wayland_screenshot_available", return_value=True
        ), patch.object(
            wayland_setup.shutil, "which", return_value="/usr/bin/ffmpeg"
        ), patch.dict(
            wayland_setup.os.environ, {"DISPLAY": ":0"}, clear=True
        ):
            _ = wayland_setup._apply_runtime_wayland_policy()
            order = wayland_setup.os.environ.get("CYBERDECK_MJPEG_BACKEND_ORDER")

        self.assertEqual(order, "gstreamer,ffmpeg,screenshot,native")

    def test_wayland_allow_x11_fallback_accepts_boolean_words(self):
        """Validate scenario: x11 fallback flag should support bool-like env forms."""
        with patch.object(wayland_setup, "is_linux_wayland_session", return_value=True), patch.dict(
            wayland_setup.os.environ,
            {"DISPLAY": ":0", "CYBERDECK_WAYLAND_ALLOW_X11_FALLBACK": "off"},
            clear=True,
        ):
            self.assertFalse(wayland_setup._wayland_allow_x11_fallback())

        with patch.object(wayland_setup, "is_linux_wayland_session", return_value=True), patch.dict(
            wayland_setup.os.environ,
            {"DISPLAY": ":0", "CYBERDECK_WAYLAND_ALLOW_X11_FALLBACK": "yes"},
            clear=True,
        ):
            self.assertTrue(wayland_setup._wayland_allow_x11_fallback())

    def test_ensure_wayland_ready_ok_with_noncritical_issues(self):
        """Validate scenario: non-critical issues should keep startup path healthy."""
        with patch.object(wayland_setup, "_apply_runtime_wayland_policy", return_value=[]), patch.object(
            wayland_setup, "check_wayland_requirements", return_value=["uinput_no_access"]
        ):
            ok, issues, attempted, reason = wayland_setup.ensure_wayland_ready("C:/repo", auto_install=True, log=None)

        self.assertTrue(ok)
        self.assertEqual(issues, ["uinput_no_access"])
        self.assertFalse(attempted)
        self.assertEqual(reason, "ready_with_warnings")


if __name__ == "__main__":
    unittest.main()

