DEFAULT_PORT = 8080
SETTINGS_FILE_NAME = "launcher_settings.json"
APP_CONFIG_FILE_NAME = "cyberdeck_app_config.json"

DEFAULT_SETTINGS = {
    "close_to_tray": True,
    "always_on_top": False,
    "autostart": False,
    "hotkey_enabled": False,
    "start_in_tray": True,
    "show_on_start": True,
    "debug": False,
    "preferred_port": DEFAULT_PORT,
    "pairing_ttl_min": 0,
    "session_ttl_days": 0,
    "session_idle_ttl_min": 0,
    "max_sessions": 0,
    "pin_window_s": 60,
    "pin_max_fails": 8,
    "pin_block_s": 300,
    "tls_enabled": False,
    "tls_cert_path": "",
    "tls_key_path": "",
    "tls_ca_path": "",
    "qr_mode": "app",  # site|app
    "language": "ru",
    "devices_panel_visible": True,
    "devices_panel_width": 430,
    "system_notifications": True,
}

DEFAULT_APP_CONFIG = {
    "allow_query_token": False,
    "pairing_single_use": False,
    "ignore_vpn": False,
    "upload_max_bytes": 0,
    "upload_allowed_ext": "",
    "verbose_http_log": True,
    "verbose_ws_log": True,
    "verbose_stream_log": True,
    "mdns_enabled": True,
    "device_approval_required": True,
}
