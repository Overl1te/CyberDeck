import os
import unittest
from unittest.mock import patch

import cyberdeck.video as video
import cyberdeck.video.mjpeg as video_mjpeg


class _InlineThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        """Initialize _InlineThread state and collaborator references."""
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        """Start the thread stub immediately for deterministic tests."""
        if self._target:
            self._target(*self._args, **self._kwargs)


class _EmptyStdout:
    def read(self, _size: int) -> bytes:
        """Read input data."""
        return b""


class _FakeProc:
    def __init__(self):
        """Initialize _FakeProc state and collaborator references."""
        self.stdout = _EmptyStdout()
        self.stderr = None
        self.returncode = None

    def poll(self):
        """Poll subprocess state."""
        return None

    def terminate(self):
        """Simulate process termination in the test process stub."""
        return None

    def kill(self):
        """Terminate the target operation."""
        return None


class VideoHelpersBehaviorTests(unittest.TestCase):
    def test_mjpeg_backend_order_respects_env_override(self):
        """Validate scenario: test mjpeg backend order respects env override."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        status = {
            "native": False,
            "ffmpeg": True,
            "gstreamer": True,
            "screenshot": True,
        }
        with patch.dict(os.environ, {"CYBERDECK_MJPEG_BACKEND_ORDER": "ffmpeg,native,screenshot"}):
            out = video._mjpeg_backend_order("auto", status)
        self.assertEqual(out, ["ffmpeg", "screenshot", "gstreamer"])

    def test_mjpeg_backend_order_keeps_preferred_first(self):
        """Validate scenario: test mjpeg backend order keeps preferred first."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        status = {
            "native": True,
            "ffmpeg": True,
            "gstreamer": True,
            "screenshot": False,
        }
        with patch.dict(os.environ, {}, clear=False), patch.object(video, "_is_wayland_session", return_value=False), patch.object(
            video, "_prefer_gst_over_ffmpeg_mjpeg", return_value=False
        ):
            out = video._mjpeg_backend_order("gstreamer", status)
        self.assertEqual(out, ["gstreamer", "native", "ffmpeg"])

    def test_spawn_stream_process_returns_none_on_spawn_error(self):
        """Validate scenario: test spawn stream process returns none on spawn error."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch("cyberdeck.video.subprocess.Popen", side_effect=OSError("boom")), patch(
            "cyberdeck.video._set_ffmpeg_diag"
        ) as mdiag:
            out = video._spawn_stream_process(
                ["ffmpeg", "-h"],
                "multipart/x-mixed-replace; boundary=frame",
                settle_s=0.05,
                stderr_lines=1,
                exit_tag="spawn_fail",
            )
        self.assertIsNone(out)
        self.assertIn("OSError", str(mdiag.call_args_list[-1].args[1]))

    def test_spawn_stream_process_handles_eof_before_first_chunk(self):
        """Validate scenario: test spawn stream process handles eof before first chunk."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        proc = _FakeProc()
        with patch("cyberdeck.video.subprocess.Popen", return_value=proc), patch(
            "cyberdeck.video.threading.Thread", _InlineThread
        ), patch(
            "cyberdeck.video.time.sleep", return_value=None
        ), patch(
            "cyberdeck.video._set_ffmpeg_diag"
        ) as mdiag:
            out = video._spawn_stream_process(
                ["ffmpeg", "-f", "x11grab"],
                "multipart/x-mixed-replace; boundary=frame",
                settle_s=0.05,
                stderr_lines=1,
                exit_tag="eof_path",
                first_chunk_timeout=0.4,
            )

        self.assertIsNone(out)
        diag_values = [str(c.args[1]) for c in mdiag.call_args_list if len(c.args) > 1]
        self.assertTrue(any("eof_before_output" in x for x in diag_values))

    def test_mjpeg_backend_status_skips_heavy_probe_by_default(self):
        """Validate scenario: request-time backend status should avoid heavy probe subprocesses."""
        with patch.object(video_mjpeg, "_ffmpeg_available", return_value=True), patch.object(
            video_mjpeg, "_build_ffmpeg_input_arg_sets", return_value=[["-f", "x11grab"]]
        ), patch.object(
            video_mjpeg, "_ffmpeg_mjpeg_capture_healthy", side_effect=AssertionError("heavy probe must not run")
        ), patch.object(
            video_mjpeg, "video_streamer"
        ) as mstream:
            mstream.disabled_reason.return_value = "wayland_session"
            mstream.is_native_healthy.return_value = False
            status = video_mjpeg._mjpeg_backend_status(1, 20)

        self.assertTrue(status["ffmpeg"])

    def test_wayland_x11grab_only_ffmpeg_is_deprioritized_when_alternatives_exist(self):
        """Validate scenario: on Wayland, x11grab-only ffmpeg should not win over screenshot/gstreamer."""
        with patch.object(video_mjpeg, "os") as mos, patch.object(
            video_mjpeg, "_is_wayland_session", return_value=True
        ), patch.object(
            video_mjpeg, "_ffmpeg_available", return_value=True
        ), patch.object(
            video_mjpeg, "_build_ffmpeg_input_arg_sets", return_value=[["-f", "x11grab"]]
        ), patch.object(
            video_mjpeg, "_ffmpeg_supports_pipewire", return_value=False
        ), patch.object(
            video_mjpeg, "_ffmpeg_supports_x11grab", return_value=True
        ), patch.object(
            video_mjpeg, "_gst_available", return_value=True
        ), patch.object(
            video_mjpeg, "_gst_supports_pipewire", return_value=True
        ), patch.object(
            video_mjpeg, "_grim_available", return_value=False
        ), patch.object(
            video_mjpeg, "_screenshot_tool_available", return_value=False
        ), patch.object(
            video_mjpeg, "video_streamer"
        ) as mstream:
            mos.name = "posix"
            mos.environ = {}
            mstream.disabled_reason.return_value = "wayland_session"
            mstream.is_native_healthy.return_value = False
            status = video_mjpeg._mjpeg_backend_status(1, 20)

        self.assertFalse(status["ffmpeg"])
        self.assertTrue(status["gstreamer"])

    def test_mjpeg_backend_status_can_disable_ffmpeg_via_env(self):
        """Validate scenario: env switch should disable ffmpeg MJPEG backend entirely."""
        with patch.object(video_mjpeg, "_ffmpeg_available", return_value=True), patch.object(
            video_mjpeg, "_build_ffmpeg_input_arg_sets", return_value=[["-f", "x11grab"]]
        ), patch.object(
            video_mjpeg, "video_streamer"
        ) as mstream, patch.dict(
            video_mjpeg.os.environ, {"CYBERDECK_DISABLE_FFMPEG_MJPEG": "1"}, clear=False
        ):
            mstream.disabled_reason.return_value = "wayland_session"
            mstream.is_native_healthy.return_value = False
            status = video_mjpeg._mjpeg_backend_status(1, 20)

        self.assertFalse(status["ffmpeg"])

    def test_mjpeg_backend_status_accepts_boolean_words_for_disable_flag(self):
        """Validate scenario: disable flag should support bool-like env values, not only 1/0."""
        with patch.object(video_mjpeg, "_ffmpeg_available", return_value=True), patch.object(
            video_mjpeg, "_build_ffmpeg_input_arg_sets", return_value=[["-f", "x11grab"]]
        ), patch.object(
            video_mjpeg, "video_streamer"
        ) as mstream, patch.dict(
            video_mjpeg.os.environ, {"CYBERDECK_DISABLE_FFMPEG_MJPEG": "yes"}, clear=False
        ):
            mstream.disabled_reason.return_value = "wayland_session"
            mstream.is_native_healthy.return_value = False
            status = video_mjpeg._mjpeg_backend_status(1, 20)

        self.assertFalse(status["ffmpeg"])

    def test_wayland_force_x11grab_accepts_boolean_words(self):
        """Validate scenario: force-x11grab env should accept bool-like values."""
        with patch.object(video_mjpeg.os, "name", "posix"), patch.dict(
            os.environ, {"CYBERDECK_FORCE_WAYLAND_X11GRAB": "yes"}, clear=False
        ), patch.object(
            video_mjpeg, "_is_wayland_session", return_value=True
        ), patch.object(
            video_mjpeg, "_ffmpeg_available", return_value=True
        ), patch.object(
            video_mjpeg, "_build_ffmpeg_input_arg_sets", return_value=[["-f", "x11grab"]]
        ), patch.object(
            video_mjpeg, "_ffmpeg_supports_pipewire", return_value=False
        ), patch.object(
            video_mjpeg, "_ffmpeg_supports_x11grab", return_value=True
        ), patch.object(
            video_mjpeg, "_gst_available", return_value=True
        ), patch.object(
            video_mjpeg, "_gst_supports_pipewire", return_value=True
        ), patch.object(
            video_mjpeg, "_grim_available", return_value=False
        ), patch.object(
            video_mjpeg, "_screenshot_tool_available", return_value=False
        ), patch.object(
            video_mjpeg, "video_streamer"
        ) as mstream:
            mstream.disabled_reason.return_value = "wayland_session"
            mstream.is_native_healthy.return_value = False
            status = video_mjpeg._mjpeg_backend_status(1, 20)

        self.assertTrue(status["ffmpeg"])


if __name__ == "__main__":
    unittest.main()

