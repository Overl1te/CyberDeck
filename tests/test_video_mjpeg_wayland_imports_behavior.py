import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cyberdeck.video.mjpeg as video_mjpeg


class VideoMjpegWaylandImportsBehaviorTests(unittest.TestCase):
    def test_screenshot_capture_health_uses_wayland_helpers_without_name_error(self):
        """Validate scenario: test screenshot capture health uses wayland helpers without name error."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch.object(video_mjpeg, "os", SimpleNamespace(name="posix")), patch.object(
            video_mjpeg, "_is_wayland_session", return_value=True
        ), patch.object(
            video_mjpeg, "_wayland_grim_frame", return_value=b"\xff\xd8\xff\xd9"
        ), patch.object(
            video_mjpeg, "_jpeg_has_visible_content", return_value=True
        ), patch.object(
            video_mjpeg, "_shot_probe_ok", None
        ), patch.object(
            video_mjpeg, "_shot_probe_ts", 0.0
        ):
            out = video_mjpeg._screenshot_capture_healthy()

        self.assertTrue(out)


if __name__ == "__main__":
    unittest.main()


