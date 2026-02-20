import unittest

import cyberdeck.video.ffmpeg as video_ffmpeg_module
import cyberdeck.video.wayland as video_wayland_module


class VideoStreamHeadersRegressionBehaviorTests(unittest.TestCase):
    def test_video_ffmpeg_module_has_shared_stream_headers(self):
        """Validate scenario: ffmpeg module should expose shared stream headers helper."""
        headers_fn = getattr(video_ffmpeg_module, "_stream_headers", None)
        self.assertTrue(callable(headers_fn))
        headers = headers_fn()
        self.assertIsInstance(headers, dict)
        self.assertIn("Cache-Control", headers)

    def test_video_wayland_module_has_shared_stream_headers(self):
        """Validate scenario: wayland module should expose shared stream headers helper."""
        headers_fn = getattr(video_wayland_module, "_stream_headers", None)
        self.assertTrue(callable(headers_fn))
        headers = headers_fn()
        self.assertIsInstance(headers, dict)
        self.assertIn("Cache-Control", headers)


if __name__ == "__main__":
    unittest.main()

