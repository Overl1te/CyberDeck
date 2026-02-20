import importlib
import os
import unittest
from unittest.mock import patch

import cyberdeck.video.core as video_core


class VideoCoreEnvBehaviorTests(unittest.TestCase):
    def tearDown(self):
        """Restore module constants from ambient environment after each test."""
        importlib.reload(video_core)

    def test_module_reload_tolerates_invalid_numeric_env_values(self):
        """Validate scenario: invalid numeric env values should not crash video core import."""
        env = {
            "CYBERDECK_MJPEG_DEFAULT_W": "oops",
            "CYBERDECK_MJPEG_DEFAULT_Q": "bad",
            "CYBERDECK_STREAM_OFFER_MAX_W": "NaN",
            "CYBERDECK_STREAM_OFFER_Q": "NaN",
            "CYBERDECK_H264_BITRATE_K": "bad",
            "CYBERDECK_H265_BITRATE_K": "bad",
            "CYBERDECK_LOWLAT_MAX_W": "broken",
            "CYBERDECK_LOWLAT_MAX_Q": "broken",
            "CYBERDECK_LOWLAT_MAX_FPS": "broken",
            "CYBERDECK_MJPEG_MIN_Q": "broken",
            "CYBERDECK_MJPEG_MIN_Q_LOWLAT": "broken",
            "CYBERDECK_SCREENSHOT_MAX_W": "broken",
            "CYBERDECK_SCREENSHOT_MAX_Q": "broken",
            "CYBERDECK_SCREENSHOT_MAX_FPS": "broken",
            "CYBERDECK_JPEG_SUBSAMPLING": "broken",
            "CYBERDECK_STREAM_FIRST_CHUNK_TIMEOUT_S": "slow",
            "CYBERDECK_STREAM_STALE_KEEPALIVE_S": "slow",
            "CYBERDECK_STREAM_STDOUT_QUEUE_SIZE": "queue",
            "CYBERDECK_STREAM_STDOUT_READ_CHUNK": "chunk",
            "CYBERDECK_STREAM_RECONNECT_HINT_MS": "hint",
            "CYBERDECK_ADAPT_MIN_SWITCH_S": "switch",
            "CYBERDECK_ADAPT_HYST_RATIO": "ratio",
            "CYBERDECK_STREAM_MIN_W_FLOOR": "floor",
            "CYBERDECK_ADAPT_RTT_HIGH_MS": "high",
            "CYBERDECK_ADAPT_RTT_CRIT_MS": "crit",
            "CYBERDECK_ADAPT_FPS_DROP_THRESHOLD": "drop",
            "CYBERDECK_ADAPT_DEC_FPS_STEP": "dec",
            "CYBERDECK_ADAPT_DEC_W_STEP": "dec",
            "CYBERDECK_ADAPT_DEC_Q_STEP": "dec",
            "CYBERDECK_ADAPT_INC_FPS_STEP": "inc",
            "CYBERDECK_ADAPT_INC_W_STEP": "inc",
            "CYBERDECK_ADAPT_INC_Q_STEP": "inc",
        }
        with patch.dict(os.environ, env, clear=False):
            mod = importlib.reload(video_core)

        self.assertGreaterEqual(mod._DEFAULT_MJPEG_W, 640)
        self.assertTrue(20 <= mod._DEFAULT_MJPEG_Q <= 95)
        self.assertGreaterEqual(mod._DEFAULT_H264_BITRATE_K, 500)
        self.assertGreaterEqual(mod._DEFAULT_H265_BITRATE_K, 500)
        self.assertGreaterEqual(mod._STREAM_FIRST_CHUNK_TIMEOUT_S, 2.5)
        self.assertGreaterEqual(mod._STREAM_STALE_FRAME_KEEPALIVE_S, 0.2)
        self.assertGreaterEqual(mod._STREAM_STDOUT_QUEUE_SIZE, 1)
        self.assertGreaterEqual(mod._STREAM_STDOUT_READ_CHUNK, 4096)
        self.assertGreaterEqual(mod._STREAM_RECONNECT_HINT_MS, 250)
        self.assertGreaterEqual(mod._ADAPTIVE_RTT_CRIT_MS, mod._ADAPTIVE_RTT_HIGH_MS + 40)
        self.assertIn(mod._JPEG_SUBSAMPLING, (0, 1, 2))

    def test_module_reload_supports_common_boolean_env_forms(self):
        """Validate scenario: bool-like env values should be parsed consistently."""
        env = {
            "CYBERDECK_ALLOW_GNOME_SCREENSHOT": "yes",
            "CYBERDECK_MJPEG_LOWLAT_DEFAULT": "on",
            "CYBERDECK_FAST_RESIZE": "true",
            "CYBERDECK_OFFER_CURSOR_DEFAULT": "y",
            "CYBERDECK_OFFER_LOW_LATENCY_DEFAULT": "t",
            "CYBERDECK_DISABLE_WIDTH_STABILIZER": "no",
        }
        with patch.dict(os.environ, env, clear=False):
            mod = importlib.reload(video_core)

        self.assertTrue(mod._ALLOW_GNOME_SCREENSHOT)
        self.assertEqual(mod._DEFAULT_MJPEG_LOW_LATENCY, 1)
        self.assertTrue(mod._FAST_RESIZE)
        self.assertEqual(mod._DEFAULT_OFFER_CURSOR, 1)
        self.assertEqual(mod._DEFAULT_OFFER_LOW_LATENCY, 1)
        self.assertTrue(mod._WIDTH_STABILIZER.enabled)


if __name__ == "__main__":
    unittest.main()

