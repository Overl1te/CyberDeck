import unittest

from cyberdeck import config
from cyberdeck.protocol import protocol_payload


class ProtocolBehaviorTests(unittest.TestCase):
    def test_protocol_payload_reflects_runtime_config(self):
        """Validate scenario: test protocol payload reflects runtime config."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        old_ver = config.PROTOCOL_VERSION
        old_min = config.MIN_SUPPORTED_PROTOCOL_VERSION
        try:
            config.PROTOCOL_VERSION = 7
            config.MIN_SUPPORTED_PROTOCOL_VERSION = 3
            p = protocol_payload()
            self.assertEqual(p.get("protocol_version"), 7)
            self.assertEqual(p.get("min_supported_protocol_version"), 3)
            self.assertIsInstance(p.get("features"), dict)
            self.assertIn("ws_heartbeat", p.get("features", {}))
        finally:
            config.PROTOCOL_VERSION = old_ver
            config.MIN_SUPPORTED_PROTOCOL_VERSION = old_min


if __name__ == "__main__":
    unittest.main()
