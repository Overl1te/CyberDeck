import unittest

from cyberdeck.video.stream_adaptation import WidthStabilizer, parse_width_ladder


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


if __name__ == "__main__":
    unittest.main()
