import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from cyberdeck import config, context
from cyberdeck.sessions import DeviceSession
from cyberdeck.ws.mouse import router as ws_router
import cyberdeck.ws.mouse as ws_mouse


class _FakeInputBackend:
    name = "fake"
    can_pointer = True
    can_keyboard = True
    can_position = False
    can_screen_size = False

    def __init__(self):
        """Initialize _FakeInputBackend state and collaborator references."""
        self.text_payloads = []
        self.moves = []

    def position(self):
        """Return the current pointer position."""
        return None

    def screen_size(self):
        """Return the active screen size in pixels."""
        return None

    def move_rel(self, dx: int, dy: int) -> bool:
        """Move the pointer by relative delta."""
        self.moves.append((int(dx), int(dy)))
        return True

    def click(self, button: str = "left", double: bool = False) -> bool:
        """Dispatch a mouse click through the active backend."""
        return True

    def scroll(self, dy: int) -> bool:
        """Dispatch a mouse scroll event through the active backend."""
        return True

    def mouse_down(self, button: str = "left") -> bool:
        """Press and hold the requested mouse button."""
        return True

    def mouse_up(self, button: str = "left") -> bool:
        """Release the requested mouse button."""
        return True

    def write_text(self, text: str) -> bool:
        """Type text using the active input backend."""
        # Write-path helpers should keep side effects minimal and well-scoped.
        self.text_payloads.append(str(text))
        return True

    def press(self, key: str) -> bool:
        """Send a single key press through the active backend."""
        return True

    def hotkey(self, *keys: str) -> bool:
        """Send a key combination through the active backend."""
        return True


class WsBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Prepare shared fixtures for the test class."""
        cls._old_input_backend = ws_mouse.INPUT_BACKEND
        cls._old_cursor_stream = config.CURSOR_STREAM
        cls._old_allow_query_token = config.ALLOW_QUERY_TOKEN
        cls._old_sessions = dict(context.device_manager.sessions)

        cls.fake_backend = _FakeInputBackend()
        ws_mouse.INPUT_BACKEND = cls.fake_backend
        config.CURSOR_STREAM = False
        config.ALLOW_QUERY_TOKEN = False

        app = FastAPI()
        app.include_router(ws_router)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        """Clean up shared fixtures for the test class."""
        ws_mouse.INPUT_BACKEND = cls._old_input_backend
        config.CURSOR_STREAM = cls._old_cursor_stream
        config.ALLOW_QUERY_TOKEN = cls._old_allow_query_token
        context.device_manager.sessions = cls._old_sessions
        ws_mouse._ws_runtime.clear()
        ws_mouse._mouse_remainders.clear()
        ws_mouse._virtual_cursor.clear()

    def setUp(self):
        """Prepare test preconditions for each test case."""
        context.device_manager.sessions = {}
        ws_mouse._ws_runtime.clear()
        ws_mouse._mouse_remainders.clear()
        ws_mouse._virtual_cursor.clear()
        self.fake_backend.text_payloads.clear()
        self.fake_backend.moves.clear()

    @staticmethod
    def _headers(token: str) -> dict:
        """Return authorization headers for the active test session."""
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _add_session(token: str, settings=None) -> None:
        """Register a synthetic session used by the test case."""
        context.device_manager.sessions[token] = DeviceSession(
            device_id=f"dev-{token}",
            device_name=f"Device {token}",
            ip="127.0.0.1",
            token=token,
            settings=settings or {},
        )

    def test_ws_rejects_unknown_token(self):
        """Validate scenario: test ws rejects unknown token."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws/mouse", headers=self._headers("missing")):
                pass
        self.assertEqual(ctx.exception.code, 4003)

    def test_ws_hello_ping_pong_and_text(self):
        """Validate scenario: test ws hello ping pong and text."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-hello"
        self._add_session(token)

        with patch.object(ws_mouse, "_IS_WINDOWS", False):
            with self.client.websocket_connect("/ws/mouse", headers=self._headers(token)) as ws:
                ws.send_json(
                    {
                        "type": "hello",
                        "protocol_version": 2,
                        "capabilities": {"heartbeat_ack": True},
                    }
                )
                hello_ack = ws.receive_json()
                server_hello = ws.receive_json()
                self.assertEqual(hello_ack.get("type"), "hello_ack")
                self.assertEqual(server_hello.get("type"), "hello")
                self.assertIn("protocol_version", hello_ack)
                self.assertIn("heartbeat_interval_ms", hello_ack)

                ws.send_json({"type": "ping", "id": "p1"})
                pong = ws.receive_json()
                self.assertEqual(pong.get("type"), "pong")
                self.assertEqual(pong.get("id"), "p1")

                ws.send_json({"type": "text", "text": "hello"})

        self.assertIn("hello", self.fake_backend.text_payloads)

    def test_ws_blocks_text_when_keyboard_permission_denied(self):
        """Validate scenario: test ws blocks text when keyboard permission denied."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-no-kbd"
        self._add_session(
            token,
            settings={"perm_mouse": True, "perm_keyboard": False},
        )

        with self.client.websocket_connect("/ws/mouse", headers=self._headers(token)) as ws:
            ws.send_json({"type": "text", "text": "blocked"})
            ws.send_json({"type": "ping", "id": "probe"})
            pong = ws.receive_json()
            self.assertEqual(pong.get("type"), "pong")

        self.assertEqual(self.fake_backend.text_payloads, [])

    def test_ws_rejects_when_all_input_permissions_denied(self):
        """Validate scenario: test ws rejects when all input permissions denied."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-no-input"
        self._add_session(
            token,
            settings={"perm_mouse": False, "perm_keyboard": False},
        )
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws/mouse", headers=self._headers(token)):
                pass
        self.assertEqual(ctx.exception.code, 4003)

    def test_ws_move_abs_accepts_normalized_coordinates(self):
        """Validate scenario: absolute move should map normalized coordinates onto the virtual screen."""
        token = "tok-move-abs-norm"
        self._add_session(token)

        with self.client.websocket_connect("/ws/mouse", headers=self._headers(token)) as ws:
            ws.send_json({"type": "move_abs", "x": 1.0, "y": 0.0})
            ws.send_json({"type": "ping", "id": "p1"})
            ws.receive_json()
            self.assertEqual(ws_mouse._get_virtual_cursor(token), (1919, 0, 1920, 1080))

        self.assertEqual(self.fake_backend.moves[-1], (959, -540))

    def test_ws_move_abs_accepts_pixel_coordinates(self):
        """Validate scenario: absolute move should also accept pixel coordinates for compatibility."""
        token = "tok-move-abs-px"
        self._add_session(token)

        with self.client.websocket_connect("/ws/mouse", headers=self._headers(token)) as ws:
            ws.send_json({"type": "move_abs", "x": 100, "y": 50})
            ws.send_json({"type": "ping", "id": "p1"})
            ws.receive_json()
            self.assertEqual(ws_mouse._get_virtual_cursor(token), (100, 50, 1920, 1080))

        self.assertEqual(self.fake_backend.moves[-1], (-860, -490))

    def test_ws_reconnect_keeps_newer_socket(self):
        """Validate scenario: test ws reconnect keeps newer socket."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        token = "tok-reconnect"
        self._add_session(token)

        ws1_cm = self.client.websocket_connect("/ws/mouse", headers=self._headers(token))
        ws2_cm = self.client.websocket_connect("/ws/mouse", headers=self._headers(token))
        ws1 = ws2 = None
        try:
            ws1 = ws1_cm.__enter__()
            s1 = context.device_manager.get_session(token)
            self.assertIsNotNone(s1)
            first_socket = s1.websocket
            self.assertIsNotNone(first_socket)

            ws2 = ws2_cm.__enter__()
            s2 = context.device_manager.get_session(token)
            self.assertIsNotNone(s2)
            second_socket = s2.websocket
            self.assertIsNotNone(second_socket)
            self.assertIsNot(first_socket, second_socket)

            ws1_cm.__exit__(None, None, None)
            ws1 = None
            s3 = context.device_manager.get_session(token)
            self.assertIsNotNone(s3)
            self.assertIs(s3.websocket, second_socket)
        finally:
            if ws1 is not None:
                ws1_cm.__exit__(None, None, None)
            if ws2 is not None:
                ws2_cm.__exit__(None, None, None)

        s4 = context.device_manager.get_session(token)
        self.assertIsNotNone(s4)
        self.assertIsNone(s4.websocket)


if __name__ == "__main__":
    unittest.main()
