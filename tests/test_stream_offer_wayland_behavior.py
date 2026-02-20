import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cyberdeck.video.api as video_api


class StreamOfferWaylandBehaviorTests(unittest.TestCase):
    def test_stream_offer_prefers_mjpeg_first_on_wayland_by_default(self):
        """Validate scenario: Wayland offer should recommend MJPEG first for client compatibility."""
        req = SimpleNamespace(base_url="http://127.0.0.1:8080/")
        with patch.object(video_api, "require_perm", return_value=None), patch.object(
            video_api, "_facade_attr", side_effect=lambda _name, default: default
        ), patch.object(
            video_api, "_capture_input_available", return_value=True
        ), patch.object(
            video_api, "_ffmpeg_wayland_capture_reliable", return_value=True
        ), patch.object(
            video_api, "_codec_encoder_available", return_value=True
        ), patch.object(
            video_api, "_mjpeg_backend_status", return_value={"native": False, "ffmpeg": True, "gstreamer": False, "screenshot": False}
        ), patch.object(
            video_api, "_mjpeg_backend_order", return_value=["ffmpeg"]
        ), patch.object(
            video_api, "_get_ffmpeg_diag", return_value={"ffmpeg_available": True}
        ), patch.object(
            video_api, "protocol_payload", return_value={}
        ), patch.object(
            video_api, "_is_wayland_session", return_value=True
        ), patch.object(
            video_api.os, "name", "posix"
        ), patch.dict(
            os.environ, {}, clear=True
        ):
            out = video_api.stream_offer(request=req, token="t", monitor=1, fps=30, max_w=1280, quality=50)

        self.assertEqual(out.get("recommended"), "mjpeg")
        candidates = out.get("candidates") or []
        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual((candidates[0] or {}).get("codec"), "mjpeg")

    def test_stream_offer_can_keep_h264_first_when_mjpeg_preference_disabled(self):
        """Validate scenario: explicit env override should allow H.264-first offer ordering."""
        req = SimpleNamespace(base_url="http://127.0.0.1:8080/")
        with patch.object(video_api, "require_perm", return_value=None), patch.object(
            video_api, "_facade_attr", side_effect=lambda _name, default: default
        ), patch.object(
            video_api, "_capture_input_available", return_value=True
        ), patch.object(
            video_api, "_ffmpeg_wayland_capture_reliable", return_value=True
        ), patch.object(
            video_api, "_codec_encoder_available", return_value=True
        ), patch.object(
            video_api, "_mjpeg_backend_status", return_value={"native": False, "ffmpeg": True, "gstreamer": False, "screenshot": False}
        ), patch.object(
            video_api, "_mjpeg_backend_order", return_value=["ffmpeg"]
        ), patch.object(
            video_api, "_get_ffmpeg_diag", return_value={"ffmpeg_available": True}
        ), patch.object(
            video_api, "protocol_payload", return_value={}
        ), patch.object(
            video_api, "_is_wayland_session", return_value=True
        ), patch.object(
            video_api.os, "name", "posix"
        ), patch.dict(
            os.environ, {"CYBERDECK_PREFER_MJPEG_OFFER": "0"}, clear=True
        ):
            out = video_api.stream_offer(request=req, token="t", monitor=1, fps=30, max_w=1280, quality=50)

        self.assertEqual(out.get("recommended"), "h264_ts")
        candidates = out.get("candidates") or []
        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual((candidates[0] or {}).get("codec"), "h264")

    def test_stream_offer_accepts_boolean_words_for_mjpeg_preference_override(self):
        """Validate scenario: env override should accept bool-like words for MJPEG preference toggle."""
        req = SimpleNamespace(base_url="http://127.0.0.1:8080/")
        with patch.object(video_api, "require_perm", return_value=None), patch.object(
            video_api, "_facade_attr", side_effect=lambda _name, default: default
        ), patch.object(
            video_api, "_capture_input_available", return_value=True
        ), patch.object(
            video_api, "_ffmpeg_wayland_capture_reliable", return_value=True
        ), patch.object(
            video_api, "_codec_encoder_available", return_value=True
        ), patch.object(
            video_api, "_mjpeg_backend_status", return_value={"native": False, "ffmpeg": True, "gstreamer": False, "screenshot": False}
        ), patch.object(
            video_api, "_mjpeg_backend_order", return_value=["ffmpeg"]
        ), patch.object(
            video_api, "_get_ffmpeg_diag", return_value={"ffmpeg_available": True}
        ), patch.object(
            video_api, "protocol_payload", return_value={}
        ), patch.object(
            video_api, "_is_wayland_session", return_value=True
        ), patch.object(
            video_api.os, "name", "posix"
        ), patch.dict(
            os.environ, {"CYBERDECK_PREFER_MJPEG_OFFER": "off"}, clear=True
        ):
            out = video_api.stream_offer(request=req, token="t", monitor=1, fps=30, max_w=1280, quality=50)

        self.assertEqual(out.get("recommended"), "h264_ts")
        candidates = out.get("candidates") or []
        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual((candidates[0] or {}).get("codec"), "h264")


if __name__ == "__main__":
    unittest.main()

