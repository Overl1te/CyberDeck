import os
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import cyberdeck.video.ffmpeg as video_ffmpeg_module
import cyberdeck.video.core as video_core_module
import cyberdeck.video.streamer as video_streamer_module
import cyberdeck.video.wayland as video_wayland_module


class _NoopThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        """Initialize _NoopThread state and collaborator references."""
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        """Avoid starting background worker thread during constructor tests."""
        return None


class VideoStreamerRegressionBehaviorTests(unittest.TestCase):
    def test_codec_encoder_available_accepts_hardware_fallback_encoders(self):
        """Validate scenario: hardware encoder fallback should count as codec support."""
        with patch.object(video_core_module, "_ffmpeg_available", return_value=True), patch.object(
            video_core_module,
            "_ffmpeg_supports_encoder",
            side_effect=lambda name: str(name) in {"h264_nvenc", "hevc_nvenc"},
        ):
            self.assertTrue(video_core_module._codec_encoder_available("h264"))
            self.assertTrue(video_core_module._codec_encoder_available("h265"))
            self.assertEqual(video_core_module._preferred_codec_encoder("h264"), "h264_nvenc")
            self.assertEqual(video_core_module._preferred_codec_encoder("h265"), "hevc_nvenc")

    def test_codec_encoder_preference_keeps_libx_first_when_available(self):
        """Validate scenario: libx encoders should stay preferred when present."""
        with patch.object(video_core_module, "_ffmpeg_available", return_value=True), patch.object(
            video_core_module,
            "_ffmpeg_supports_encoder",
            side_effect=lambda name: str(name) in {"libx264", "h264_nvenc"},
        ):
            self.assertEqual(video_core_module._preferred_codec_encoder("h264"), "libx264")

    def test_build_ffmpeg_cmds_includes_fallback_encoder_variants(self):
        """Validate scenario: ffmpeg command builder should include multiple encoder fallbacks."""
        with patch.object(
            video_ffmpeg_module,
            "_available_codec_encoders",
            return_value=["libx264", "h264_nvenc"],
        ), patch.object(
            video_ffmpeg_module,
            "_build_ffmpeg_input_arg_sets",
            return_value=[["-f", "x11grab", "-i", ":0.0"]],
        ):
            cmds = video_ffmpeg_module._build_ffmpeg_cmds(
                codec="h264",
                monitor=1,
                fps=30,
                bitrate_k=2500,
                gop=60,
                preset="veryfast",
                max_w=1280,
                low_latency=False,
            )

        self.assertEqual(len(cmds), 2)
        first = cmds[0]
        second = cmds[1]
        self.assertIn("-c:v", first)
        self.assertIn("-c:v", second)
        self.assertEqual(first[first.index("-c:v") + 1], "libx264")
        self.assertEqual(second[second.index("-c:v") + 1], "h264_nvenc")
        self.assertEqual(first[first.index("-r") + 1], "30")
        self.assertEqual(first[first.index("-vsync") + 1], "cfr")

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

    def test_video_streamer_ctor_tolerates_invalid_env_values(self):
        """Validate scenario: constructor should not crash on invalid stream env values."""
        env = {
            "CYBERDECK_STREAM_W": "bad",
            "CYBERDECK_STREAM_Q": "bad",
            "CYBERDECK_STREAM_FPS": "bad",
            "CYBERDECK_STREAM_CURSOR": "bad",
            "CYBERDECK_STREAM_MONITOR": "bad",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(
            video_streamer_module.threading, "Thread", _NoopThread
        ):
            streamer = video_streamer_module._VideoStreamer()

        expected_monitor = max(1, int(getattr(video_streamer_module.config, "STREAM_MONITOR", 1)))
        self.assertEqual(streamer.base_w, 960)
        self.assertEqual(streamer.base_q, 25)
        self.assertEqual(streamer.base_fps, 60)
        self.assertFalse(streamer.base_cursor)
        self.assertEqual(streamer.base_monitor, expected_monitor)
        self.assertEqual(streamer._desired_key, (960, 25, False, expected_monitor))
        streamer.stop()

    def test_video_streamer_ctor_clamps_values_and_supports_bool_words(self):
        """Validate scenario: constructor should clamp ranges and parse bool-like cursor env."""
        env = {
            "CYBERDECK_STREAM_W": "200",
            "CYBERDECK_STREAM_Q": "200",
            "CYBERDECK_STREAM_FPS": "0",
            "CYBERDECK_STREAM_CURSOR": "yes",
            "CYBERDECK_STREAM_MONITOR": "0",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(
            video_streamer_module.threading, "Thread", _NoopThread
        ):
            streamer = video_streamer_module._VideoStreamer()

        self.assertEqual(streamer.base_w, 320)
        self.assertEqual(streamer.base_q, 95)
        self.assertEqual(streamer.base_fps, 5)
        self.assertTrue(streamer.base_cursor)
        self.assertEqual(streamer.base_monitor, 1)
        self.assertEqual(streamer._desired_key, (320, 95, True, 1))
        streamer.stop()

    def test_video_streamer_stats_include_jpeg_reuse_counters(self):
        """Validate scenario: stream stats should expose JPEG reuse diagnostics."""
        with patch.object(video_streamer_module.threading, "Thread", _NoopThread):
            streamer = video_streamer_module._VideoStreamer()

        streamer._encoded_jpeg_frames = 6
        streamer._reused_jpeg_frames = 4
        stats = streamer.get_stats()
        self.assertEqual(stats.get("encoded_jpeg_frames"), 6)
        self.assertEqual(stats.get("reused_jpeg_frames"), 4)
        self.assertAlmostEqual(float(stats.get("jpeg_reuse_ratio", 0.0)), 0.4, places=3)
        streamer.stop()

    def test_ffmpeg_available_detects_winget_install_without_path(self):
        """Validate scenario: ffmpeg resolver should find Winget install on Windows."""
        with tempfile.TemporaryDirectory() as td:
            ffmpeg_dir = os.path.join(
                td,
                "Microsoft",
                "WinGet",
                "Packages",
                "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe",
                "ffmpeg-8.0.1-full_build",
                "bin",
            )
            os.makedirs(ffmpeg_dir, exist_ok=True)
            ffmpeg_exe = os.path.join(ffmpeg_dir, "ffmpeg.exe")
            with open(ffmpeg_exe, "wb") as f:
                f.write(b"")

            with patch.object(video_core_module.shutil, "which", return_value=None), patch.object(
                video_core_module.os, "name", "nt"
            ), patch.dict(
                video_core_module.os.environ, {"LOCALAPPDATA": td}, clear=False
            ):
                video_core_module._ffmpeg_bin_cached = None
                video_core_module._ffmpeg_bin_probe_ts = 0.0
                self.assertTrue(video_core_module._ffmpeg_available())
                resolved = video_core_module._ffmpeg_binary()
                self.assertIsNotNone(resolved)
                self.assertTrue(str(resolved).lower().endswith("ffmpeg.exe"))

    def test_ffmpeg_mjpeg_stream_accepts_bool_words_for_lowlat_flag(self):
        """Validate scenario: ffmpeg MJPEG low-latency env should support bool-like words."""
        seen_cmds = []

        def _fake_spawn(cmd, *_args, **_kwargs):
            seen_cmds.append(list(cmd))
            return object()

        with patch.object(video_ffmpeg_module, "_ffmpeg_available", return_value=True), patch.object(
            video_ffmpeg_module, "_build_ffmpeg_input_arg_sets", return_value=[["-f", "x11grab", "-i", ":0.0"]]
        ), patch.object(
            video_ffmpeg_module, "_spawn_stream_process", side_effect=_fake_spawn
        ), patch.dict(
            os.environ, {"CYBERDECK_MJPEG_LOWLAT_DEFAULT": "off"}, clear=False
        ):
            out = video_ffmpeg_module._ffmpeg_mjpeg_stream(monitor=1, fps=20, quality=55, width=960)

        self.assertIsNotNone(out)
        self.assertEqual(len(seen_cmds), 1)
        cmd = seen_cmds[0]
        self.assertIn("lanczos", " ".join(cmd))
        self.assertIn("yuvj444p", cmd)

        seen_cmds.clear()
        with patch.object(video_ffmpeg_module, "_ffmpeg_available", return_value=True), patch.object(
            video_ffmpeg_module, "_build_ffmpeg_input_arg_sets", return_value=[["-f", "x11grab", "-i", ":0.0"]]
        ), patch.object(
            video_ffmpeg_module, "_spawn_stream_process", side_effect=_fake_spawn
        ), patch.dict(
            os.environ, {"CYBERDECK_MJPEG_LOWLAT_DEFAULT": "yes"}, clear=False
        ):
            out = video_ffmpeg_module._ffmpeg_mjpeg_stream(monitor=1, fps=20, quality=55, width=960)

        self.assertIsNotNone(out)
        self.assertEqual(len(seen_cmds), 1)
        cmd = seen_cmds[0]
        self.assertIn("fast_bilinear", " ".join(cmd))
        self.assertIn("yuvj420p", cmd)


if __name__ == "__main__":
    unittest.main()

