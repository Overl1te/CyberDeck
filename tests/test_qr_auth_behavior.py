import unittest
from unittest.mock import patch

from cyberdeck import config
from cyberdeck.qr_auth import QrTokenStore, _QrToken


class QrAuthBehaviorTests(unittest.TestCase):
    def test_issue_then_consume_is_single_use(self):
        """Validate scenario: test issue then consume is single use."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        store = QrTokenStore()
        token = store.issue()
        self.assertTrue(store.consume(token))
        self.assertFalse(store.consume(token))

    def test_consume_rejects_empty_token(self):
        """Validate scenario: test consume rejects empty token."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        store = QrTokenStore()
        self.assertFalse(store.consume(""))
        self.assertFalse(store.consume("   "))

    def test_cleanup_drops_expired_tokens_on_consume(self):
        """Validate scenario: test cleanup drops expired tokens on consume."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        store = QrTokenStore()
        store._tokens["expired"] = _QrToken(created_ts=1.0, expires_ts=2.0)
        with patch("cyberdeck.qr_auth.time.time", return_value=3.0):
            self.assertFalse(store.consume("expired"))
        self.assertNotIn("expired", store._tokens)

    def test_ttl_has_lower_bound(self):
        """Validate scenario: test ttl has lower bound."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        store = QrTokenStore()
        old_ttl = config.QR_TOKEN_TTL_S
        try:
            config.QR_TOKEN_TTL_S = 1
            self.assertEqual(store._ttl_s(), 10)
        finally:
            config.QR_TOKEN_TTL_S = old_ttl

    def test_cleanup_caps_token_count(self):
        """Validate scenario: test cleanup caps token count."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        store = QrTokenStore()
        for i in range(8205):
            key = f"t{i:04d}"
            store._tokens[key] = _QrToken(created_ts=float(i), expires_ts=999999.0)
        store._cleanup_locked(now=10.0)
        self.assertLessEqual(len(store._tokens), 8192)
        self.assertNotIn("t0000", store._tokens)


if __name__ == "__main__":
    unittest.main()
