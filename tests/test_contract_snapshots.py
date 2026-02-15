import json
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cyberdeck import config, context
from cyberdeck.api_core import router as core_router
from cyberdeck.sessions import DeviceSession
from cyberdeck.video import router as video_router
import cyberdeck.video as video


class ContractSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepare shared fixtures for the test class."""
        cls._old_sessions = dict(context.device_manager.sessions)
        cls._old_allow_query_token = config.ALLOW_QUERY_TOKEN
        cls._old_protocol_version = config.PROTOCOL_VERSION
        cls._old_min_protocol_version = config.MIN_SUPPORTED_PROTOCOL_VERSION

        config.ALLOW_QUERY_TOKEN = False
        config.PROTOCOL_VERSION = 2
        config.MIN_SUPPORTED_PROTOCOL_VERSION = 1

        app = FastAPI()
        app.include_router(core_router)
        app.include_router(video_router)
        cls.client = TestClient(app)
        cls.snapshots_dir = Path(__file__).parent / "snapshots"

    @classmethod
    def tearDownClass(cls):
        """Clean up shared fixtures for the test class."""
        context.device_manager.sessions = cls._old_sessions
        config.ALLOW_QUERY_TOKEN = cls._old_allow_query_token
        config.PROTOCOL_VERSION = cls._old_protocol_version
        config.MIN_SUPPORTED_PROTOCOL_VERSION = cls._old_min_protocol_version

    def setUp(self):
        """Prepare test preconditions for each test case."""
        context.device_manager.sessions = {}
        context.device_manager.sessions["snap-token"] = DeviceSession(
            device_id="snapshot-device",
            device_name="Snapshot Device",
            ip="127.0.0.1",
            token="snap-token",
        )

    @staticmethod
    def _auth_headers(token: str) -> dict:
        """Return authorization headers for test API requests."""
        return {"Authorization": f"Bearer {token}"}

    def _load_snapshot(self, name: str) -> dict:
        """Load snapshot."""
        path = self.snapshots_dir / name
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _canonical_url(url: str) -> str:
        """Normalize URL to canonical form for snapshot comparisons."""
        parsed = urlparse(str(url or ""))
        query = sorted(parse_qsl(parsed.query, keep_blank_values=True))
        qs = urlencode(query, doseq=True)
        return f"{parsed.path}?{qs}" if qs else parsed.path

    def test_protocol_snapshot(self):
        """Validate scenario: test protocol snapshot."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        r = self.client.get("/api/protocol")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        canonical = {
            "protocol_version": body.get("protocol_version"),
            "min_supported_protocol_version": body.get("min_supported_protocol_version"),
            "server_version": body.get("server_version"),
            "features": body.get("features"),
        }
        self.assertEqual(canonical, self._load_snapshot("protocol_snapshot.json"))

    def test_stream_offer_snapshot(self):
        """Validate scenario: test stream offer snapshot."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with patch.object(video, "_capture_input_available", return_value=True), patch.object(
            video, "_ffmpeg_wayland_capture_reliable", return_value=True
        ), patch.object(
            video,
            "_codec_encoder_available",
            side_effect=lambda codec: str(codec).lower() in ("h264", "h265"),
        ), patch.object(
            video, "_mjpeg_backend_status", return_value={"native": True, "ffmpeg": True, "gstreamer": False, "screenshot": False}
        ), patch.object(
            video, "_mjpeg_backend_order", return_value=["native", "ffmpeg"]
        ), patch.object(
            video, "_get_ffmpeg_diag", return_value={"ffmpeg_available": True}
        ), patch.object(
            video._WIDTH_STABILIZER, "decide", return_value=1280
        ), patch.multiple(
            video,
            _ADAPTIVE_RTT_HIGH_MS=220,
            _ADAPTIVE_RTT_CRIT_MS=340,
            _ADAPTIVE_FPS_DROP_THRESHOLD=0.62,
            _ADAPTIVE_DEC_FPS_STEP=2,
            _ADAPTIVE_DEC_W_STEP=64,
            _ADAPTIVE_DEC_Q_STEP=5,
            _ADAPTIVE_INC_FPS_STEP=1,
            _ADAPTIVE_INC_W_STEP=64,
            _ADAPTIVE_INC_Q_STEP=2,
            _ADAPTIVE_WIDTH_LADDER=[1920, 1280, 960],
            _ADAPTIVE_MIN_SWITCH_S=8.0,
            _ADAPTIVE_HYST_RATIO=0.18,
            _STREAM_MIN_W_FLOOR=1024,
            _DEFAULT_OFFER_LOW_LATENCY=1,
            _DEFAULT_OFFER_CURSOR=0,
            _STREAM_RECONNECT_HINT_MS=700,
        ):
            r = self.client.get(
                "/api/stream_offer",
                params={
                    "monitor": 1,
                    "fps": 30,
                    "max_w": 1600,
                    "quality": 55,
                    "bitrate_k": 3200,
                    "gop": 60,
                    "preset": "veryfast",
                    "low_latency": 0,
                    "cursor": 0,
                },
                headers=self._auth_headers("snap-token"),
            )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()

        canonical_candidates = []
        for c in (body.get("candidates") or []):
            item = {
                "id": c.get("id"),
                "codec": c.get("codec"),
                "container": c.get("container"),
                "mime": c.get("mime"),
                "url": self._canonical_url(str(c.get("url") or "")),
            }
            if "backend" in c:
                item["backend"] = c.get("backend")
            canonical_candidates.append(item)

        canonical = {
            "recommended": body.get("recommended"),
            "candidates": canonical_candidates,
            "fallback_policy": body.get("fallback_policy"),
            "reconnect_hint_ms": body.get("reconnect_hint_ms"),
            "adaptive_hint": body.get("adaptive_hint"),
            "support": body.get("support"),
            "diag": body.get("diag"),
            "protocol_version": body.get("protocol_version"),
            "min_supported_protocol_version": body.get("min_supported_protocol_version"),
            "server_version": body.get("server_version"),
            "features": body.get("features"),
        }
        self.assertEqual(canonical, self._load_snapshot("stream_offer_snapshot.json"))


if __name__ == "__main__":
    unittest.main()
