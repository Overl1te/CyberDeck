import unittest

from PIL import Image

import cyberdeck.video_streamer as video_streamer_module
import cyberdeck.video_wayland as video_wayland_module


class VideoStreamerRegressionBehaviorTests(unittest.TestCase):
    def test_video_streamer_module_has_shared_jpeg_encoder(self):
        """Validate scenario: test video streamer module has shared jpeg encoder."""
        encoder = getattr(video_streamer_module, "_save_jpeg", None)
        self.assertTrue(callable(encoder))
        out = encoder(Image.new("RGB", (2, 2), (255, 0, 0)), 60)
        self.assertIsInstance(out, (bytes, bytearray))
        self.assertTrue(bytes(out).startswith(b"\xff\xd8"))

    def test_video_wayland_module_has_shared_jpeg_encoder(self):
        """Validate scenario: test video wayland module has shared jpeg encoder."""
        encoder = getattr(video_wayland_module, "_save_jpeg", None)
        self.assertTrue(callable(encoder))
        out = encoder(Image.new("RGB", (2, 2), (0, 255, 0)), 60)
        self.assertIsInstance(out, (bytes, bytearray))
        self.assertTrue(bytes(out).startswith(b"\xff\xd8"))


if __name__ == "__main__":
    unittest.main()

