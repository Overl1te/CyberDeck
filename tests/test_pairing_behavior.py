import unittest
from unittest.mock import patch

from cyberdeck import config
from cyberdeck import pairing


class PairingBehaviorTests(unittest.TestCase):
    def setUp(self):
        """Prepare test preconditions for each test case."""
        self._old_code = config.PAIRING_CODE
        self._old_exp = config.PAIRING_EXPIRES_AT
        self._old_ttl = config.PAIRING_TTL_S
        self._old_single_use = config.PAIRING_SINGLE_USE

    def tearDown(self):
        """Restore config values touched by tests."""
        config.PAIRING_CODE = self._old_code
        config.PAIRING_EXPIRES_AT = self._old_exp
        config.PAIRING_TTL_S = self._old_ttl
        config.PAIRING_SINGLE_USE = self._old_single_use

    def test_pairing_meta_includes_remaining_ttl(self):
        """Validate scenario: pairing meta should report TTL countdown."""
        config.PAIRING_CODE = "4321"
        config.PAIRING_TTL_S = 120
        config.PAIRING_SINGLE_USE = True
        config.PAIRING_EXPIRES_AT = 100.0
        with patch("cyberdeck.pairing.time.time", return_value=40.0):
            out = pairing.pairing_meta()
        self.assertEqual(out["pairing_code"], "4321")
        self.assertEqual(out["pairing_ttl_s"], 120)
        self.assertEqual(out["pairing_expires_in_s"], 60)
        self.assertTrue(out["pairing_single_use"])

    def test_rotate_pairing_code_updates_expiry_using_ttl(self):
        """Validate scenario: rotate pairing code should refresh code and expiry."""
        config.PAIRING_TTL_S = 30
        with patch("cyberdeck.pairing.time.time", return_value=1000.0), patch(
            "cyberdeck.pairing.uuid.uuid4"
        ) as muid:
            muid.return_value.int = 98765432101234
            new_code = pairing.rotate_pairing_code()
        self.assertEqual(new_code, "9876")
        self.assertEqual(config.PAIRING_EXPIRES_AT, 1030.0)


if __name__ == "__main__":
    unittest.main()

