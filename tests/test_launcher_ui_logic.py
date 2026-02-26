import sys
import types
import unittest
import urllib.parse


if "pystray" not in sys.modules:
    pystray_stub = types.ModuleType("pystray")
    pystray_stub.Menu = lambda *args, **kwargs: None
    pystray_stub.MenuItem = lambda *args, **kwargs: None

    class _Icon:
        def __init__(self, *args, **kwargs):
            """Create a no-op tray icon stub for launcher tests."""
            pass

        def run(self):
            """Simulate starting the tray icon loop."""
            return None

        def stop(self):
            """Simulate stopping the tray icon loop."""
            return None

    pystray_stub.Icon = _Icon
    sys.modules["pystray"] = pystray_stub

import launcher


class _CfgWidget:
    def __init__(self):
        """Initialize _CfgWidget state and collaborator references."""
        self.last_config = {}

    def configure(self, **kwargs):
        """Configure the target operation."""
        self.last_config.update(kwargs)


class _FakeRow:
    def __init__(self):
        """Initialize _FakeRow state and collaborator references."""
        self.pack_calls = 0
        self.pack_forget_calls = 0
        self.destroy_calls = 0

    def pack(self, **_kwargs):
        """Record a simulated pack() call on the widget stub."""
        self.pack_calls += 1

    def pack_forget(self):
        """Pack forget."""
        self.pack_forget_calls += 1

    def destroy(self):
        """Record a simulated widget destroy() call."""
        self.destroy_calls += 1


class _GridWidget:
    def __init__(self):
        """Initialize _GridWidget state and collaborator references."""
        self.grid_calls = 0
        self.grid_remove_calls = 0
        self.last_config = {}

    def grid(self, **_kwargs):
        """Record a simulated grid() placement call on the widget stub."""
        self.grid_calls += 1

    def grid_remove(self):
        """Place remove using grid layout."""
        self.grid_remove_calls += 1

    def configure(self, **kwargs):
        """Configure the target operation."""
        self.last_config.update(kwargs)


class _SplitWidget:
    def __init__(self):
        """Initialize _SplitWidget state and collaborator references."""
        self.columns = {}

    def grid_columnconfigure(self, idx, **kwargs):
        """Place columnconfigure using grid layout."""
        self.columns[idx] = kwargs


class LauncherUiLogicTests(unittest.TestCase):
    def test_build_app_qr_deep_link_prefers_custom_scheme(self):
        """Validate scenario: app-mode QR payload should use cyberdeck:// deep link."""
        payload = {
            "type": "cyberdeck_qr_v1",
            "server_id": "srv-01",
            "hostname": "pc",
            "version": "1.0.0",
            "ip": "192.168.1.10",
            "port": 8080,
            "pairing_code": "1234",
            "scheme": "http",
            "ts": 123456,
            "nonce": "nonce-01",
            "qr_token": "qr-01",
            "pairing_expires_at": 987654.0,
        }

        out = launcher.App._build_app_qr_deep_link(payload)
        parsed = urllib.parse.urlsplit(out)
        query = urllib.parse.parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "cyberdeck")
        self.assertEqual(parsed.netloc, "pair")
        self.assertEqual(query.get("ip", [""])[0], "192.168.1.10")
        self.assertEqual(query.get("port", [""])[0], "8080")
        self.assertEqual(query.get("code", [""])[0], "1234")
        self.assertEqual(query.get("qr_token", [""])[0], "qr-01")
        self.assertEqual(query.get("exp", [""])[0], "987654")
        self.assertNotIn("open", query)

    def test_build_android_intent_qr_link_includes_browser_fallback(self):
        """Validate scenario: android intent QR should include fallback URL with open=app."""
        deep_link = "cyberdeck://pair?ip=10.0.0.2&port=8080&code=1122&qr_token=qr-1"
        fallback = "http://10.0.0.2:8080/?ip=10.0.0.2&port=8080&code=1122"

        out = launcher.App._build_android_intent_qr_link(deep_link, fallback_url=fallback)
        self.assertTrue(out.startswith("intent://pair?"))
        self.assertIn("#Intent;scheme=cyberdeck;action=android.intent.action.VIEW;", out)

        encoded_fallback = out.split("S.browser_fallback_url=", 1)[1].split(";end", 1)[0]
        decoded_fallback = urllib.parse.unquote(encoded_fallback)
        parsed = urllib.parse.urlsplit(decoded_fallback)
        query = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "http")
        self.assertEqual(parsed.netloc, "10.0.0.2:8080")
        self.assertEqual(query.get("open", [""])[0], "app")

    def test_build_app_fallback_url_is_compact_and_contains_required_fields(self):
        """Validate scenario: fallback URL should remain compact and preserve pairing essentials."""
        payload = {
            "type": "cyberdeck_qr_v1",
            "ip": "192.168.0.201",
            "port": 8080,
            "pairing_code": "1775",
            "scheme": "http",
            "qr_token": "fbca942d3cfc4f67b2127fc2ef8f138a",
            "pairing_expires_at": 1772135660.0,
        }
        out = launcher.App._build_app_fallback_url(payload, base_url="http://192.168.0.201:8080/")
        parsed = urllib.parse.urlsplit(out)
        query = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "http")
        self.assertEqual(parsed.netloc, "192.168.0.201:8080")
        self.assertEqual(query.get("ip", [""])[0], "192.168.0.201")
        self.assertEqual(query.get("port", [""])[0], "8080")
        self.assertEqual(query.get("code", [""])[0], "1775")
        self.assertEqual(query.get("scheme", [""])[0], "http")
        self.assertEqual(query.get("qr_token", [""])[0], "fbca942d3cfc4f67b2127fc2ef8f138a")
        self.assertEqual(query.get("open", [""])[0], "app")
        self.assertEqual(query.get("exp", [""])[0], "1772135660")

    def test_qr_render_size_scales_for_long_payloads(self):
        """Validate scenario: larger payloads should request larger QR bitmap size."""
        self.assertEqual(launcher.App._qr_render_size_for_payload("x" * 120), 240)
        self.assertEqual(launcher.App._qr_render_size_for_payload("x" * 200), 280)
        self.assertEqual(launcher.App._qr_render_size_for_payload("x" * 300), 320)
        self.assertEqual(launcher.App._qr_render_size_for_payload("x" * 420), 360)

    def test_set_device_settings_dirty_controls_buttons_and_status(self):
        """Validate scenario: test set device settings dirty controls buttons and status."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake = types.SimpleNamespace(
            selected_token="token-1",
            _device_settings_dirty=False,
            btn_save_device_settings=_CfgWidget(),
            btn_reset_device_settings=_CfgWidget(),
            lbl_device_dirty=_CfgWidget(),
            lbl_status=_CfgWidget(),
        )

        launcher.App._set_device_settings_dirty(
            fake,
            True,
            status_text="> Dirty",
            status_color="warn",
        )
        self.assertTrue(fake._device_settings_dirty)
        self.assertEqual(fake.btn_save_device_settings.last_config.get("state"), "normal")
        self.assertEqual(fake.btn_reset_device_settings.last_config.get("state"), "normal")
        self.assertEqual(fake.lbl_device_dirty.last_config.get("text"), "Есть несохраненные изменения")
        self.assertEqual(fake.lbl_status.last_config.get("text"), "> Dirty")

        fake.selected_token = None
        launcher.App._set_device_settings_dirty(fake, True)
        self.assertFalse(fake._device_settings_dirty)
        self.assertEqual(fake.btn_save_device_settings.last_config.get("state"), "disabled")
        self.assertEqual(fake.btn_reset_device_settings.last_config.get("state"), "disabled")

    def test_sync_device_list_updates_only_changed_rows(self):
        """Validate scenario: test sync device list updates only changed rows."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake = types.SimpleNamespace(
            selected_token="a",
            _device_rows={},
            _device_row_order=[],
            _device_empty_label=None,
            device_list=object(),
        )
        fake.visible = [
            ("a", {"name": "A", "ip": "1.1.1.1", "settings": {"transfer_preset": "balanced"}}, True),
            ("b", {"name": "B", "ip": "1.1.1.2", "settings": {"transfer_preset": "balanced"}}, True),
        ]
        fake.update_calls = []

        fake._iter_visible_devices = lambda: list(fake.visible)
        fake._device_row_key = lambda d, online, is_sel: (d.get("name"), bool(online), bool(is_sel), d.get("ip"))

        def _create_row(_token):
            """Create row."""
            return {"row": _FakeRow(), "render_key": None}

        def _update_row(entry, d, online, is_sel):
            """Update row."""
            fake.update_calls.append(d.get("name"))
            entry["render_key"] = fake._device_row_key(d, online, is_sel)

        fake._create_device_row = _create_row
        fake._update_device_row = _update_row

        launcher.App._sync_device_list(fake)
        self.assertEqual(set(fake._device_rows.keys()), {"a", "b"})
        self.assertEqual(fake.update_calls, ["A", "B"])

        rows = dict(fake._device_rows)
        pack_forget_counts = {k: v["row"].pack_forget_calls for k, v in rows.items()}
        pack_counts = {k: v["row"].pack_calls for k, v in rows.items()}

        fake.update_calls = []
        launcher.App._sync_device_list(fake)
        self.assertEqual(fake.update_calls, [])
        self.assertEqual(pack_forget_counts["a"], rows["a"]["row"].pack_forget_calls)
        self.assertEqual(pack_forget_counts["b"], rows["b"]["row"].pack_forget_calls)
        self.assertEqual(pack_counts["a"], rows["a"]["row"].pack_calls)
        self.assertEqual(pack_counts["b"], rows["b"]["row"].pack_calls)

        fake.visible = [
            ("a", {"name": "A", "ip": "1.1.1.1", "settings": {"transfer_preset": "balanced"}}, True),
            ("b", {"name": "B", "ip": "1.1.1.2", "settings": {"transfer_preset": "balanced"}}, False),
        ]
        fake.update_calls = []
        launcher.App._sync_device_list(fake)
        self.assertEqual(fake.update_calls, ["B"])

        fake.visible = [
            ("b", {"name": "B", "ip": "1.1.1.2", "settings": {"transfer_preset": "balanced"}}, False),
        ]
        launcher.App._sync_device_list(fake)
        self.assertEqual(rows["a"]["row"].destroy_calls, 1)
        self.assertEqual(fake._device_row_order, ["b"])

    def test_apply_devices_panel_layout_and_toggle(self):
        """Validate scenario: test apply devices panel layout and toggle."""
        # Test body is intentionally explicit so regressions are easy to diagnose.
        fake = types.SimpleNamespace(
            settings={"devices_panel_visible": True, "devices_panel_width": 120},
            devices_split=_SplitWidget(),
            devices_splitter=_GridWidget(),
            devices_panel=_GridWidget(),
            btn_toggle_devices_panel=_CfgWidget(),
            _save_layout_settings_calls=0,
        )
        fake._save_layout_settings = lambda: setattr(
            fake,
            "_save_layout_settings_calls",
            fake._save_layout_settings_calls + 1,
        )

        launcher.App._apply_devices_panel_layout(fake, persist=True)
        self.assertEqual(fake.settings["devices_panel_width"], 320)
        self.assertEqual(fake.devices_splitter.grid_calls, 1)
        self.assertEqual(fake.devices_panel.grid_calls, 1)
        self.assertEqual(fake.devices_split.columns[2].get("minsize"), 320)
        self.assertEqual(fake.btn_toggle_devices_panel.last_config.get("text"), "Скрыть панель")
        self.assertEqual(fake._save_layout_settings_calls, 1)

        fake.settings["devices_panel_visible"] = False
        launcher.App._apply_devices_panel_layout(fake, persist=False)
        self.assertEqual(fake.devices_splitter.grid_remove_calls, 1)
        self.assertEqual(fake.devices_panel.grid_remove_calls, 1)
        self.assertEqual(fake.devices_split.columns[2].get("minsize"), 0)
        self.assertEqual(fake.btn_toggle_devices_panel.last_config.get("text"), "Показать панель")

        toggle_fake = types.SimpleNamespace(settings={"devices_panel_visible": True}, calls=[])
        toggle_fake._apply_devices_panel_layout = lambda persist=False: toggle_fake.calls.append(persist)
        launcher.App.toggle_devices_panel(toggle_fake)
        self.assertFalse(toggle_fake.settings["devices_panel_visible"])
        self.assertEqual(toggle_fake.calls, [True])


if __name__ == "__main__":
    unittest.main()
