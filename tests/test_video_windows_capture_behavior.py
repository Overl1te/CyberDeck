import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cyberdeck.video.core as video_core


class VideoWindowsCaptureBehaviorTests(unittest.TestCase):
    def test_windows_input_args_include_ddagrab_then_gdigrab_when_available(self):
        """Validate scenario: Windows ffmpeg input args should try ddagrab before gdigrab when supported."""
        fake_os = SimpleNamespace(name="nt", environ={})
        with patch.object(video_core, "os", fake_os), patch.object(
            video_core, "_ffmpeg_supports_ddagrab", return_value=True
        ), patch.object(video_core, "_get_monitor_rect", return_value=(10, 20, 1280, 720)):
            sets = video_core._build_ffmpeg_input_arg_sets(2, 30)

        self.assertGreaterEqual(len(sets), 2)
        self.assertEqual(sets[0][0:3], ["-f", "lavfi", "-i"])
        self.assertIn("ddagrab=framerate=30:draw_mouse=1:output_idx=1", sets[0][3])
        self.assertEqual(sets[1][0:2], ["-f", "gdigrab"])

    def test_windows_input_args_keep_gdigrab_when_ddagrab_unavailable(self):
        """Validate scenario: Windows ffmpeg input args should keep gdigrab path when ddagrab is unavailable."""
        fake_os = SimpleNamespace(name="nt", environ={})
        with patch.object(video_core, "os", fake_os), patch.object(
            video_core, "_ffmpeg_supports_ddagrab", return_value=False
        ), patch.object(video_core, "_get_monitor_rect", return_value=(0, 0, 1920, 1080)):
            sets = video_core._build_ffmpeg_input_arg_sets(1, 24)

        self.assertEqual(len(sets), 1)
        self.assertEqual(sets[0][0:2], ["-f", "gdigrab"])


if __name__ == "__main__":
    unittest.main()
