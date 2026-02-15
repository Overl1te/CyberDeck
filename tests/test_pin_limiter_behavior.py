import unittest

from cyberdeck import config
from cyberdeck.pin_limiter import PinLimiter


class PinLimiterBehaviorTests(unittest.TestCase):
    def test_cleanup_caps_ip_map_size(self):
        """Validate scenario: test cleanup caps ip map size."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        limiter = PinLimiter()
        old_max = config.PIN_STATE_MAX_IPS
        old_stale = config.PIN_STATE_STALE_S
        try:
            config.PIN_STATE_MAX_IPS = 3
            config.PIN_STATE_STALE_S = 3600
            now = 1000.0
            for i in range(8):
                limiter.record_failure(f"10.0.0.{i}", now=now + i)
            self.assertLessEqual(len(limiter._by_ip), 3)
        finally:
            config.PIN_STATE_MAX_IPS = old_max
            config.PIN_STATE_STALE_S = old_stale

    def test_cleanup_removes_stale_entries(self):
        """Validate scenario: test cleanup removes stale entries."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        limiter = PinLimiter()
        old_max = config.PIN_STATE_MAX_IPS
        old_stale = config.PIN_STATE_STALE_S
        try:
            config.PIN_STATE_MAX_IPS = 1024
            config.PIN_STATE_STALE_S = 10
            limiter.record_failure("10.0.0.10", now=100.0)
            limiter.record_failure("10.0.0.11", now=100.0)
            # Trigger maintenance after stale timeout elapsed.
            limiter.check("10.0.0.12", now=200.0)
            self.assertNotIn("10.0.0.10", limiter._by_ip)
            self.assertNotIn("10.0.0.11", limiter._by_ip)
        finally:
            config.PIN_STATE_MAX_IPS = old_max
            config.PIN_STATE_STALE_S = old_stale

    def test_check_returns_retry_after_when_ip_is_blocked(self):
        """Validate scenario: test check returns retry after when ip is blocked."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        limiter = PinLimiter()
        old_window = config.PIN_WINDOW_S
        old_max_fails = config.PIN_MAX_FAILS
        old_block = config.PIN_BLOCK_S
        try:
            config.PIN_WINDOW_S = 60
            config.PIN_MAX_FAILS = 2
            config.PIN_BLOCK_S = 30
            limiter.record_failure("10.10.0.1", now=100.0)
            limiter.record_failure("10.10.0.1", now=101.0)
            allowed, retry_after = limiter.check("10.10.0.1", now=102.0)
            self.assertFalse(allowed)
            self.assertGreaterEqual(retry_after, 1)
        finally:
            config.PIN_WINDOW_S = old_window
            config.PIN_MAX_FAILS = old_max_fails
            config.PIN_BLOCK_S = old_block

    def test_check_resets_fail_counter_after_window_elapsed(self):
        """Validate scenario: test check resets fail counter after window elapsed."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        limiter = PinLimiter()
        old_window = config.PIN_WINDOW_S
        old_max_fails = config.PIN_MAX_FAILS
        old_block = config.PIN_BLOCK_S
        try:
            config.PIN_WINDOW_S = 5
            config.PIN_MAX_FAILS = 3
            config.PIN_BLOCK_S = 30
            limiter.record_failure("10.10.0.2", now=200.0)
            allowed, retry_after = limiter.check("10.10.0.2", now=210.0)
            self.assertTrue(allowed)
            self.assertEqual(retry_after, 0)
            self.assertEqual(limiter._by_ip["10.10.0.2"].fails, 0)
        finally:
            config.PIN_WINDOW_S = old_window
            config.PIN_MAX_FAILS = old_max_fails
            config.PIN_BLOCK_S = old_block

    def test_record_success_and_reset_clear_state(self):
        """Validate scenario: test record success and reset clear state."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        limiter = PinLimiter()
        limiter.record_failure("10.10.0.3", now=300.0)
        limiter.record_failure("10.10.0.4", now=301.0)
        self.assertIn("10.10.0.3", limiter._by_ip)
        self.assertIn("10.10.0.4", limiter._by_ip)

        limiter.record_success("10.10.0.3")
        self.assertNotIn("10.10.0.3", limiter._by_ip)

        limiter.reset()
        self.assertEqual(limiter._by_ip, {})


if __name__ == "__main__":
    unittest.main()
