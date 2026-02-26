import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cyberdeck.video.ffmpeg as video_ffmpeg


class VideoAudioInputBehaviorTests(unittest.TestCase):
    def setUp(self):
        """Reset ffmpeg audio probe caches for deterministic assertions."""
        video_ffmpeg._FFMPEG_DEMUXER_CACHE.clear()
        video_ffmpeg._FFMPEG_DSHOW_AUDIO_CACHE = (0.0, [])
        video_ffmpeg._PULSE_MONITOR_CACHE = (0.0, [])
        video_ffmpeg._FFMPEG_LAST_GOOD_CMD.clear()

    def test_demuxer_probe_parses_three_flag_format_lines(self):
        """Validate scenario: ffmpeg -formats output with device flag should detect dshow."""
        sample = (
            "Formats:\n"
            " D.. = Demuxing supported\n"
            " .E. = Muxing supported\n"
            " ..d = Is a device\n"
            " D d dshow           DirectShow capture\n"
        )
        with patch.object(video_ffmpeg, "_ffmpeg_formats", return_value=sample):
            self.assertTrue(video_ffmpeg._ffmpeg_demuxer_available("dshow"))
            self.assertFalse(video_ffmpeg._ffmpeg_demuxer_available("wasapi"))

    def test_dshow_device_probe_parses_audio_lines_without_section_header(self):
        """Validate scenario: parse modern ffmpeg dshow output that marks lines as '(audio)'."""
        sample = (
            "[dshow] \"OBS Virtual Camera\" (none)\n"
            "[dshow] \"Microphone (USB)\" (audio)\n"
            "[dshow]   Alternative name \"@device_cm_x\"\n"
            "[dshow] \"Stereo Mix (Realtek)\" (audio)\n"
        )
        with patch.object(video_ffmpeg, "_ffmpeg_binary", return_value="ffmpeg"), patch.object(
            video_ffmpeg.subprocess,
            "run",
            return_value=SimpleNamespace(stdout=sample),
        ):
            out = video_ffmpeg._ffmpeg_dshow_audio_devices()
        self.assertEqual(out[0], "Stereo Mix (Realtek)")
        self.assertIn("Microphone (USB)", out)
        self.assertNotIn("OBS Virtual Camera", out)

    def test_dshow_device_probe_caches_empty_results(self):
        """Validate scenario: empty dshow probe must be cached to avoid repeated startup delay."""
        sample = "[dshow] \"OBS Virtual Camera\" (none)\n"
        with patch.object(video_ffmpeg, "_ffmpeg_binary", return_value="ffmpeg"), patch.object(
            video_ffmpeg.subprocess,
            "run",
            return_value=SimpleNamespace(stdout=sample),
        ) as mocked_run:
            first = video_ffmpeg._ffmpeg_dshow_audio_devices()
            second = video_ffmpeg._ffmpeg_dshow_audio_devices()
        self.assertEqual(first, [])
        self.assertEqual(second, [])
        self.assertEqual(mocked_run.call_count, 1)

    def test_windows_audio_input_sets_use_detected_dshow_devices(self):
        """Validate scenario: windows audio input should prefer loopback devices instead of microphones."""
        with patch.dict(video_ffmpeg.os.environ, {"CYBERDECK_AUDIO_WINDOWS_FORCE_SOUNDCARD": "0"}, clear=False), patch.object(
            video_ffmpeg.os,
            "name",
            "nt",
        ), patch.object(
            video_ffmpeg,
            "_ffmpeg_demuxer_available",
            side_effect=lambda name: str(name).lower() == "dshow",
        ), patch.object(
            video_ffmpeg,
            "_ffmpeg_dshow_audio_devices",
            return_value=["Stereo Mix (Realtek)", "Microphone (USB)", "What U Hear"],
        ):
            out = video_ffmpeg._ffmpeg_audio_input_arg_sets()

        self.assertEqual(out[0], ["-f", "dshow", "-i", "audio=Stereo Mix (Realtek)"])
        self.assertEqual(out[1], ["-f", "dshow", "-i", "audio=What U Hear"])
        self.assertEqual(len(out), 2)

    def test_windows_audio_input_sets_can_fallback_to_microphone(self):
        """Validate scenario: mic fallback should be opt-in via env for setups without loopback."""
        with patch.dict(
            video_ffmpeg.os.environ,
            {"CYBERDECK_AUDIO_ALLOW_MIC_FALLBACK": "1", "CYBERDECK_AUDIO_WINDOWS_FORCE_SOUNDCARD": "0"},
            clear=False,
        ), patch.object(
            video_ffmpeg.os,
            "name",
            "nt",
        ), patch.object(
            video_ffmpeg,
            "_ffmpeg_demuxer_available",
            side_effect=lambda name: str(name).lower() == "dshow",
        ), patch.object(
            video_ffmpeg,
            "_ffmpeg_dshow_audio_devices",
            return_value=["Microphone (USB)"],
        ):
            out = video_ffmpeg._ffmpeg_audio_input_arg_sets()
        self.assertEqual(out, [["-f", "dshow", "-i", "audio=Microphone (USB)"]])

    def test_env_audio_input_args_falls_back_to_auto_detection_when_demuxer_is_unavailable(self):
        """Validate scenario: invalid env override should not block auto detection."""
        with patch.dict(
            video_ffmpeg.os.environ,
            {"CYBERDECK_AUDIO_INPUT_ARGS": "-f wasapi -i default", "CYBERDECK_AUDIO_WINDOWS_FORCE_SOUNDCARD": "0"},
            clear=False,
        ), patch.object(
            video_ffmpeg.os,
            "name",
            "nt",
        ), patch.object(
            video_ffmpeg,
            "_ffmpeg_demuxer_available",
            side_effect=lambda name: str(name).lower() == "dshow",
        ), patch.object(
            video_ffmpeg,
            "_ffmpeg_dshow_audio_devices",
            return_value=["Stereo Mix (Realtek)"],
        ):
            out = video_ffmpeg._ffmpeg_audio_input_arg_sets()
        self.assertEqual(out, [["-f", "dshow", "-i", "audio=Stereo Mix (Realtek)"]])

    def test_windows_audio_input_prefers_dshow_loopback_before_wasapi(self):
        """Validate scenario: on Windows, loopback dshow source should be preferred before wasapi fallback."""
        with patch.dict(video_ffmpeg.os.environ, {"CYBERDECK_AUDIO_WINDOWS_FORCE_SOUNDCARD": "0"}, clear=False), patch.object(
            video_ffmpeg.os,
            "name",
            "nt",
        ), patch.object(
            video_ffmpeg,
            "_ffmpeg_demuxer_available",
            side_effect=lambda name: str(name).lower() in {"dshow", "wasapi"},
        ), patch.object(
            video_ffmpeg,
            "_ffmpeg_dshow_audio_devices",
            return_value=["Stereo Mix (Realtek)"],
        ):
            out = video_ffmpeg._ffmpeg_audio_input_arg_sets()
        self.assertEqual(out[0], ["-f", "dshow", "-i", "audio=Stereo Mix (Realtek)"])
        self.assertEqual(out[1], ["-f", "wasapi", "-i", "default"])

    def test_windows_audio_input_sets_can_be_forced_to_soundcard_path(self):
        """Validate scenario: forced soundcard mode should skip ffmpeg input candidate generation on Windows."""
        with patch.dict(video_ffmpeg.os.environ, {"CYBERDECK_AUDIO_WINDOWS_FORCE_SOUNDCARD": "1"}, clear=False), patch.object(
            video_ffmpeg.os,
            "name",
            "nt",
        ):
            out = video_ffmpeg._ffmpeg_audio_input_arg_sets()
        self.assertEqual(out, [])

    def test_build_ffmpeg_cmds_can_disable_silent_fallback_when_audio_requested(self):
        """Validate scenario: when silent fallback is disabled and no audio source exists, command list should be empty."""
        with patch.object(video_ffmpeg, "_available_codec_encoders", return_value=["libx264"]), patch.object(
            video_ffmpeg,
            "_build_ffmpeg_input_arg_sets",
            return_value=[["-f", "gdigrab", "-i", "desktop"]],
        ), patch.object(
            video_ffmpeg,
            "_ffmpeg_audio_input_arg_sets",
            return_value=[],
        ), patch.object(
            video_ffmpeg,
            "_ffmpeg_binary",
            return_value="ffmpeg",
        ), patch.object(
            video_ffmpeg,
            "_env_int",
            return_value=128,
        ), patch.object(
            video_ffmpeg,
            "_env_bool",
            side_effect=lambda name, default: False if str(name) == "CYBERDECK_AUDIO_FALLBACK_TO_SILENT" else bool(default),
        ):
            cmds = video_ffmpeg._build_ffmpeg_cmds(
                "h264",
                1,
                30,
                4000,
                60,
                "ultrafast",
                max_w=0,
                low_latency=False,
                audio=True,
            )
        self.assertEqual(cmds, [])

    def test_ffmpeg_stream_uses_fast_timeout_for_intermediate_attempts(self):
        """Validate scenario: failed intermediate command attempts should fail fast before final fallback."""
        with patch.object(video_ffmpeg, "_ffmpeg_available", return_value=True), patch.object(
            video_ffmpeg,
            "_build_ffmpeg_cmds",
            return_value=[["ffmpeg", "cmd1"], ["ffmpeg", "cmd2"], ["ffmpeg", "cmd3"]],
        ), patch.object(
            video_ffmpeg,
            "_spawn_stream_process",
            side_effect=[None, None, "ok_stream"],
        ) as mocked_spawn, patch.object(
            video_ffmpeg,
            "_STREAM_FIRST_CHUNK_TIMEOUT_S",
            4.0,
        ), patch.object(
            video_ffmpeg,
            "_env_float",
            side_effect=lambda name, default: (
                1.1 if str(name) == "CYBERDECK_STREAM_FIRST_CHUNK_TIMEOUT_FAST_S" else float(default)
            ),
        ):
            out = video_ffmpeg._ffmpeg_stream("h264", 1, 30, 4000, 60, "ultrafast", audio=True)

        self.assertEqual(out, "ok_stream")
        self.assertEqual(mocked_spawn.call_count, 3)
        first_kwargs = mocked_spawn.call_args_list[0].kwargs
        second_kwargs = mocked_spawn.call_args_list[1].kwargs
        third_kwargs = mocked_spawn.call_args_list[2].kwargs
        self.assertAlmostEqual(float(first_kwargs["first_chunk_timeout"]), 1.1, places=2)
        self.assertAlmostEqual(float(second_kwargs["first_chunk_timeout"]), 1.1, places=2)
        self.assertAlmostEqual(float(third_kwargs["first_chunk_timeout"]), 4.0, places=2)
        self.assertAlmostEqual(float(first_kwargs["settle_s"]), 0.08, places=2)
        self.assertAlmostEqual(float(third_kwargs["settle_s"]), 0.15, places=2)

    def test_build_ffmpeg_cmds_prioritizes_all_audio_candidates_before_silent(self):
        """Validate scenario: when audio requested, all audio commands should be tried before silent fallback."""
        with patch.object(video_ffmpeg, "_available_codec_encoders", return_value=["libx264"]), patch.object(
            video_ffmpeg,
            "_build_ffmpeg_input_arg_sets",
            return_value=[
                ["-f", "ddagrab", "-i", "desktop"],
                ["-f", "gdigrab", "-i", "desktop"],
            ],
        ), patch.object(
            video_ffmpeg,
            "_ffmpeg_audio_input_arg_sets",
            return_value=[["-f", "dshow", "-i", "audio=Stereo Mix"]],
        ), patch.object(
            video_ffmpeg,
            "_ffmpeg_binary",
            return_value="ffmpeg",
        ), patch.object(
            video_ffmpeg,
            "_env_int",
            return_value=128,
        ), patch.object(
            video_ffmpeg,
            "_env_bool",
            side_effect=lambda name, default: True,
        ):
            cmds = video_ffmpeg._build_ffmpeg_cmds(
                "h264",
                1,
                30,
                4000,
                60,
                "ultrafast",
                max_w=0,
                low_latency=False,
                audio=True,
            )

        self.assertGreaterEqual(len(cmds), 4)
        first_two = cmds[:2]
        later = cmds[2:]
        for cmd in first_two:
            joined = " ".join(cmd)
            self.assertIn("-map 1:a:0", joined)
            self.assertNotIn(" -an ", f" {joined} ")
        for cmd in later:
            joined = " ".join(cmd)
            self.assertIn(" -an ", f" {joined} ")

    def test_ffmpeg_stream_prefers_last_known_good_command_first(self):
        """Validate scenario: command order should be reordered to previously successful candidate."""
        cmd1 = ["ffmpeg", "cmd1"]
        cmd2 = ["ffmpeg", "cmd2"]
        sig2 = "\x1f".join(cmd2)
        with patch.object(video_ffmpeg, "_ffmpeg_available", return_value=True), patch.object(
            video_ffmpeg,
            "_build_ffmpeg_cmds",
            return_value=[cmd1, cmd2],
        ), patch.object(
            video_ffmpeg,
            "_spawn_stream_process",
            return_value="ok_stream",
        ) as mocked_spawn, patch.object(
            video_ffmpeg,
            "_STREAM_FIRST_CHUNK_TIMEOUT_S",
            4.0,
        ), patch.object(
            video_ffmpeg,
            "_env_float",
            return_value=1.1,
        ):
            key = "h264|m=1|fps=30|w=0|low=0|a=0"
            video_ffmpeg._FFMPEG_LAST_GOOD_CMD[key] = (video_ffmpeg.time.time(), sig2)
            out = video_ffmpeg._ffmpeg_stream("h264", 1, 30, 3000, 60, "ultrafast", audio=False)

        self.assertEqual(out, "ok_stream")
        self.assertEqual(mocked_spawn.call_count, 1)
        first_cmd = mocked_spawn.call_args_list[0].args[0]
        self.assertEqual(first_cmd, cmd2)

    def test_build_ffmpeg_audio_cmds_uses_aac_mpegts_output(self):
        """Validate scenario: audio-only relay command should encode AAC within MPEG-TS container."""
        with patch.object(video_ffmpeg, "_ffmpeg_audio_input_arg_sets", return_value=[["-f", "dshow", "-i", "audio=Stereo Mix"]]), patch.object(
            video_ffmpeg,
            "_ffmpeg_binary",
            return_value="ffmpeg",
        ), patch.object(
            video_ffmpeg,
            "_env_int",
            side_effect=lambda name, default: default,
        ), patch.object(
            video_ffmpeg,
            "_env_bool",
            side_effect=lambda name, default: True if str(name) == "CYBERDECK_AUDIO_PAD_WITH_SILENCE" else bool(default),
        ):
            cmds = video_ffmpeg._build_ffmpeg_audio_cmds()
        self.assertEqual(len(cmds), 1)
        joined = " ".join(cmds[0])
        self.assertIn(" -c:a aac ", f" {joined} ")
        self.assertIn(" anullsrc=", joined)
        self.assertIn("amix=inputs=2", joined)
        self.assertIn(" -f mpegts pipe:1", joined)

    def test_ffmpeg_audio_stream_returns_none_when_audio_input_unavailable(self):
        """Validate scenario: audio relay should fail fast when no input backend exists."""
        with patch.object(video_ffmpeg, "_ffmpeg_available", return_value=True), patch.object(
            video_ffmpeg,
            "_build_ffmpeg_audio_cmds",
            return_value=[],
        ), patch.object(
            video_ffmpeg,
            "_env_bool",
            return_value=False,
        ):
            out = video_ffmpeg._ffmpeg_audio_stream()
        self.assertIsNone(out)

    def test_ffmpeg_audio_stream_uses_soundcard_loopback_fallback_when_enabled(self):
        """Validate scenario: soundcard loopback fallback should be used when ffmpeg inputs are unavailable."""
        with patch.object(video_ffmpeg, "_ffmpeg_available", return_value=True), patch.object(
            video_ffmpeg,
            "_build_ffmpeg_audio_cmds",
            return_value=[],
        ), patch.object(
            video_ffmpeg,
            "_soundcard_loopback_stream",
            return_value="soundcard_stream",
        ), patch.object(
            video_ffmpeg,
            "_env_bool",
            return_value=True,
        ), patch.object(
            video_ffmpeg.os,
            "name",
            "nt",
        ):
            out = video_ffmpeg._ffmpeg_audio_stream()
        self.assertEqual(out, "soundcard_stream")

    def test_ffmpeg_audio_stream_can_force_soundcard_before_ffmpeg_inputs(self):
        """Validate scenario: forced Windows soundcard mode should bypass ffmpeg command probing."""
        with patch.object(video_ffmpeg, "_ffmpeg_available", return_value=True), patch.object(
            video_ffmpeg,
            "_build_ffmpeg_audio_cmds",
            return_value=[["ffmpeg", "-f", "dshow", "-i", "audio=Stereo Mix"]],
        ), patch.object(
            video_ffmpeg,
            "_soundcard_loopback_stream",
            return_value="soundcard_stream",
        ), patch.object(
            video_ffmpeg,
            "_spawn_stream_process",
            return_value=None,
        ) as mocked_spawn, patch.object(
            video_ffmpeg,
            "_env_bool",
            side_effect=lambda name, default: True
            if str(name)
            in {"CYBERDECK_AUDIO_WINDOWS_FORCE_SOUNDCARD", "CYBERDECK_AUDIO_ENABLE_SOUNDCARD_LOOPBACK"}
            else bool(default),
        ), patch.object(
            video_ffmpeg.os,
            "name",
            "nt",
        ):
            out = video_ffmpeg._ffmpeg_audio_stream()

        self.assertEqual(out, "soundcard_stream")
        self.assertEqual(mocked_spawn.call_count, 0)

    def test_ffmpeg_audio_stream_prefers_soundcard_before_silent_on_windows(self):
        """Validate scenario: Windows should try soundcard loopback before silent fallback after ffmpeg input failures."""
        with patch.object(video_ffmpeg, "_ffmpeg_available", return_value=True), patch.object(
            video_ffmpeg,
            "_build_ffmpeg_audio_cmds",
            return_value=[["ffmpeg", "-f", "wasapi", "-i", "default"]],
        ), patch.object(
            video_ffmpeg,
            "_spawn_stream_process",
            return_value=None,
        ), patch.object(
            video_ffmpeg,
            "_soundcard_loopback_stream",
            return_value="soundcard_stream",
        ), patch.object(
            video_ffmpeg,
            "_build_ffmpeg_audio_silent_cmd",
            return_value=["ffmpeg", "-f", "lavfi", "-i", "anullsrc"],
        ) as mocked_silent_cmd, patch.object(
            video_ffmpeg,
            "_env_bool",
            side_effect=lambda name, default: str(name)
            in {"CYBERDECK_AUDIO_ENABLE_SOUNDCARD_LOOPBACK", "CYBERDECK_AUDIO_FALLBACK_TO_SILENT"},
        ), patch.object(
            video_ffmpeg,
            "_env_float",
            return_value=4.0,
        ), patch.object(
            video_ffmpeg,
            "_env_int",
            side_effect=lambda _name, default: int(default),
        ), patch.object(
            video_ffmpeg.os,
            "name",
            "nt",
        ):
            out = video_ffmpeg._ffmpeg_audio_stream()

        self.assertEqual(out, "soundcard_stream")
        mocked_silent_cmd.assert_not_called()

    def test_linux_audio_input_sets_prefer_pulse_monitor_sources(self):
        """Validate scenario: Linux audio relay should prioritize pulse monitor sources before default input."""
        with patch.dict(video_ffmpeg.os.environ, {}, clear=False), patch.object(
            video_ffmpeg.os,
            "name",
            "posix",
        ), patch.object(
            video_ffmpeg.sys,
            "platform",
            "linux",
        ), patch.object(
            video_ffmpeg,
            "_ffmpeg_demuxer_available",
            side_effect=lambda name: str(name).lower() in {"pulse", "alsa"},
        ), patch.object(
            video_ffmpeg,
            "_pulse_monitor_sources",
            return_value=["alsa_output.pci.monitor", "default.monitor"],
        ), patch.object(
            video_ffmpeg,
            "_env_int",
            side_effect=lambda name, default: 4,
        ), patch.object(
            video_ffmpeg,
            "_env_bool",
            side_effect=lambda _name, default: bool(default),
        ):
            out = video_ffmpeg._ffmpeg_audio_input_arg_sets()

        self.assertEqual(out[0], ["-f", "pulse", "-i", "@DEFAULT_MONITOR@"])
        self.assertEqual(out[1], ["-f", "pulse", "-i", "alsa_output.pci.monitor"])
        self.assertEqual(out[2], ["-f", "pulse", "-i", "default.monitor"])
        self.assertIn(["-f", "pulse", "-i", "default"], out)
        self.assertIn(["-f", "alsa", "-i", "default"], out)

    def test_ffmpeg_audio_stream_uses_silent_fallback_when_enabled(self):
        """Validate scenario: silent fallback should keep audio relay endpoint alive when capture input is missing."""
        with patch.object(video_ffmpeg, "_ffmpeg_available", return_value=True), patch.object(
            video_ffmpeg,
            "_build_ffmpeg_audio_cmds",
            return_value=[],
        ), patch.object(
            video_ffmpeg,
            "_spawn_stream_process",
            return_value="silent_stream",
        ), patch.object(
            video_ffmpeg,
            "_env_bool",
            side_effect=lambda name, default: True if str(name) == "CYBERDECK_AUDIO_FALLBACK_TO_SILENT" else False,
        ), patch.object(
            video_ffmpeg,
            "_env_float",
            return_value=8.0,
        ), patch.object(
            video_ffmpeg.os,
            "name",
            "posix",
        ):
            out = video_ffmpeg._ffmpeg_audio_stream()

        self.assertEqual(out, "silent_stream")


if __name__ == "__main__":
    unittest.main()
