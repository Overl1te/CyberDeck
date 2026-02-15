import unittest

from cyberdeck.ws_protocol import (
    build_server_hello,
    extract_text_payload,
    is_text_event_type,
)


class WsTextBehaviorTests(unittest.TestCase):
    def test_text_event_aliases_supported(self):
        """Validate scenario: test text event aliases supported."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        self.assertTrue(is_text_event_type("text"))
        self.assertTrue(is_text_event_type("input_text"))
        self.assertTrue(is_text_event_type("insert_text"))
        self.assertTrue(is_text_event_type("keyboard_text"))
        self.assertFalse(is_text_event_type("move"))

    def test_extract_text_payload_uses_supported_fields(self):
        """Validate scenario: test extract text payload uses supported fields."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        self.assertEqual(extract_text_payload({"text": "hello"}), "hello")
        self.assertEqual(extract_text_payload({"value": "world"}), "world")
        self.assertEqual(extract_text_payload({"message": "ok"}), "ok")
        self.assertEqual(extract_text_payload({"payload": "v"}), "v")
        self.assertEqual(extract_text_payload({"data": "x"}), "x")
        self.assertEqual(extract_text_payload({"text": ""}), "")
        self.assertEqual(extract_text_payload({"text": None}), "")
        self.assertEqual(extract_text_payload({"text": {"nested": "bad"}}), "")

    def test_server_hello_payload_contains_heartbeat_fields(self):
        """Validate scenario: test server hello payload contains heartbeat fields."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        out = build_server_hello("hello", hb_interval_s=6, hb_timeout_s=24)
        self.assertEqual(out.get("type"), "hello")
        self.assertEqual(out.get("heartbeat_interval_ms"), 6000)
        self.assertEqual(out.get("heartbeat_timeout_ms"), 24000)
        self.assertIn("protocol_version", out)
        self.assertIn("features", out)


if __name__ == "__main__":
    unittest.main()
