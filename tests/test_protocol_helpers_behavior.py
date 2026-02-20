import time
import unittest

from cyberdeck import config
from cyberdeck.protocol import protocol_features, protocol_payload
from cyberdeck.ws.protocol import extract_text_payload, is_text_event_type


class ProtocolHelpersBehaviorTests(unittest.TestCase):
    def test_protocol_features_contains_expected_flags(self):
        """Validate scenario: test protocol features contains expected flags."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        f = protocol_features()
        self.assertIn("stream_offer_v2", f)
        self.assertIn("ws_heartbeat", f)
        self.assertIn("file_transfer_checksum", f)
        self.assertTrue(all(isinstance(v, bool) for v in f.values()))

    def test_protocol_payload_server_time_is_near_now(self):
        """Validate scenario: test protocol payload server time is near now."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        now_ms = int(time.time() * 1000)
        p = protocol_payload()
        self.assertGreaterEqual(int(p["server_time_ms"]), now_ms - 5000)
        self.assertLessEqual(int(p["server_time_ms"]), now_ms + 5000)

    def test_protocol_payload_reflects_version_config(self):
        """Validate scenario: test protocol payload reflects version config."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        old_ver = config.PROTOCOL_VERSION
        old_min = config.MIN_SUPPORTED_PROTOCOL_VERSION
        try:
            config.PROTOCOL_VERSION = 11
            config.MIN_SUPPORTED_PROTOCOL_VERSION = 7
            p = protocol_payload()
            self.assertEqual(p["protocol_version"], 11)
            self.assertEqual(p["min_supported_protocol_version"], 7)
        finally:
            config.PROTOCOL_VERSION = old_ver
            config.MIN_SUPPORTED_PROTOCOL_VERSION = old_min

    def test_extract_text_payload_ignores_nested_values_and_keeps_order(self):
        """Validate scenario: test extract text payload ignores nested values and keeps order."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        data = {"value": "first", "text": "second"}
        self.assertEqual(extract_text_payload(data), "second")
        self.assertEqual(extract_text_payload({"text": {"nested": "x"}, "value": "ok"}), "ok")

    def test_extract_text_payload_accepts_non_string_scalars(self):
        """Validate scenario: test extract text payload accepts non string scalars."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        self.assertEqual(extract_text_payload({"text": 123}), "123")
        self.assertEqual(extract_text_payload({"value": True}), "True")

    def test_is_text_event_type_is_case_and_space_insensitive(self):
        """Validate scenario: test is text event type is case and space insensitive."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        self.assertTrue(is_text_event_type(" TEXT "))
        self.assertTrue(is_text_event_type("Input_Text"))
        self.assertFalse(is_text_event_type("move"))


if __name__ == "__main__":
    unittest.main()

