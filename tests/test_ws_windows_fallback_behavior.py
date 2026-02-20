import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cyberdeck import config, context
from cyberdeck.sessions import DeviceSession
from cyberdeck.ws.mouse import router as ws_router
import cyberdeck.ws.mouse as ws_mouse


class _FailingPointerBackend:
    name = "failing_pointer"
    can_pointer = True
    can_keyboard = True
    can_position = False
    can_screen_size = False

    def position(self):
        return None

    def screen_size(self):
        return None

    def move_rel(self, dx: int, dy: int) -> bool:
        return False

    def click(self, button: str = "left", double: bool = False) -> bool:
        return False

    def scroll(self, dy: int) -> bool:
        return False

    def mouse_down(self, button: str = "left") -> bool:
        return False

    def mouse_up(self, button: str = "left") -> bool:
        return False

    def write_text(self, text: str) -> bool:
        return True

    def press(self, key: str) -> bool:
        return True

    def hotkey(self, *keys: str) -> bool:
        return True


class WsWindowsFallbackBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_input_backend = ws_mouse.INPUT_BACKEND
        cls._old_cursor_stream = config.CURSOR_STREAM
        cls._old_allow_query_token = config.ALLOW_QUERY_TOKEN
        cls._old_sessions = dict(context.device_manager.sessions)

        ws_mouse.INPUT_BACKEND = _FailingPointerBackend()
        config.CURSOR_STREAM = False
        config.ALLOW_QUERY_TOKEN = False

        app = FastAPI()
        app.include_router(ws_router)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        ws_mouse.INPUT_BACKEND = cls._old_input_backend
        config.CURSOR_STREAM = cls._old_cursor_stream
        config.ALLOW_QUERY_TOKEN = cls._old_allow_query_token
        context.device_manager.sessions = cls._old_sessions
        ws_mouse._ws_runtime.clear()
        ws_mouse._mouse_remainders.clear()
        ws_mouse._virtual_cursor.clear()
        ws_mouse._windows_warned_input_block.clear()

    def setUp(self):
        context.device_manager.sessions = {}
        ws_mouse._ws_runtime.clear()
        ws_mouse._mouse_remainders.clear()
        ws_mouse._virtual_cursor.clear()
        ws_mouse._windows_warned_input_block.clear()

    @staticmethod
    def _headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _add_session(token: str, settings=None) -> None:
        context.device_manager.sessions[token] = DeviceSession(
            device_id=f"dev-{token}",
            device_name=f"Device {token}",
            ip="127.0.0.1",
            token=token,
            settings=settings or {},
        )

    def test_move_uses_windows_fallback_when_backend_move_fails(self):
        token = "tok-win-move"
        self._add_session(token)
        with patch.object(ws_mouse, "_IS_WINDOWS", True), patch.object(
            ws_mouse, "_windows_force_move_rel", return_value=True
        ) as m_fallback:
            with self.client.websocket_connect("/ws/mouse", headers=self._headers(token)) as ws:
                ws.send_json({"type": "move", "dx": 3, "dy": -2})
                ws.send_json({"type": "ping", "id": "p1"})
                ws.receive_json()
        self.assertTrue(m_fallback.called)

    def test_click_uses_windows_fallback_when_backend_click_fails(self):
        token = "tok-win-click"
        self._add_session(token)
        with patch.object(ws_mouse, "_IS_WINDOWS", True), patch.object(
            ws_mouse, "_windows_force_click", return_value=True
        ) as c_fallback:
            with self.client.websocket_connect("/ws/mouse", headers=self._headers(token)) as ws:
                ws.send_json({"type": "click"})
                ws.send_json({"type": "ping", "id": "p1"})
                ws.receive_json()
        self.assertTrue(c_fallback.called)

    def test_scroll_uses_windows_fallback_when_backend_scroll_fails(self):
        token = "tok-win-scroll"
        self._add_session(token)
        with patch.object(ws_mouse, "_IS_WINDOWS", True), patch.object(
            ws_mouse, "_windows_force_scroll", return_value=True
        ) as s_fallback:
            with self.client.websocket_connect("/ws/mouse", headers=self._headers(token)) as ws:
                ws.send_json({"type": "scroll", "dy": 2})
                ws.send_json({"type": "ping", "id": "p1"})
                ws.receive_json()
        self.assertTrue(s_fallback.called)


if __name__ == "__main__":
    unittest.main()
