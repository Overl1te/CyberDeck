import unittest

from cyberdeck.video.stream_adaptation import (
    StreamFeedbackStore,
    WidthStabilizer,
    parse_width_ladder,
)


class StreamAdaptationTests(unittest.TestCase):
    def test_parse_width_ladder(self):
        """Validate scenario: test parse width ladder."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        vals = parse_width_ladder("1920, 1600, abc, 960, 960, 640", [1280, 960])
        self.assertEqual(vals, [1920, 1600, 960, 640])

    def test_stabilizer_hysteresis_and_cooldown(self):
        """Validate scenario: test stabilizer hysteresis and cooldown."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        st = WidthStabilizer(
            ladder=[1920, 1600, 1280, 1024, 960, 768, 640],
            min_switch_s=8.0,
            hysteresis_ratio=0.15,
            min_floor=640,
            enabled=True,
        )
        t0 = 100.0
        # Initial pick snaps to ladder.
        self.assertEqual(st.decide("t1", 1280, now=t0), 1280)
        # Small jitter to 1200 should stay at previous width (hysteresis).
        self.assertEqual(st.decide("t1", 1200, now=t0 + 1.0), 1280)
        # Cooldown: minor downgrade to 1024 should still stay 1280.
        self.assertEqual(st.decide("t1", 1024, now=t0 + 2.0), 1280)
        # Major downgrade during cooldown is allowed.
        self.assertEqual(st.decide("t1", 700, now=t0 + 3.0), 640)
        # Floor is enforced: request below floor remains floor.
        self.assertEqual(st.decide("t1", 320, now=t0 + 20.0), 640)

    def test_feedback_store_recommendations_for_critical_profile(self):
        """Validate scenario: high RTT/jitter/drop should produce critical profile and low-latency hint."""
        store = StreamFeedbackStore(stale_after_s=30.0)
        out = store.update(
            "tok-critical",
            rtt_ms=420,
            jitter_ms=130,
            drop_ratio=0.12,
            decode_fps=10,
        )
        self.assertTrue(bool(out.get("ok")))
        self.assertEqual(out.get("network_profile"), "critical")
        suggested = out.get("suggested") or {}
        self.assertLess(int(suggested.get("fps_delta", 0)), 0)
        self.assertLess(int(suggested.get("max_w_delta", 0)), 0)
        self.assertLess(int(suggested.get("quality_delta", 0)), 0)
        self.assertTrue(bool(suggested.get("prefer_low_latency")))

    def test_feedback_store_ema_avoids_zero_fps_spike(self):
        """Validate scenario: zero decode fps sample should be smoothed by previous telemetry."""
        store = StreamFeedbackStore(stale_after_s=30.0, ema_alpha=0.4)
        first = store.update(
            "tok-smooth",
            rtt_ms=80,
            jitter_ms=8,
            drop_ratio=0.0,
            decode_fps=55,
        )
        self.assertTrue(bool(first.get("ok")))
        second = store.update(
            "tok-smooth",
            rtt_ms=85,
            jitter_ms=10,
            drop_ratio=0.0,
            decode_fps=0,
        )
        self.assertTrue(bool(second.get("ok")))
        self.assertGreater(float(second.get("decode_fps") or 0.0), 10.0)


if __name__ == "__main__":
    unittest.main()
