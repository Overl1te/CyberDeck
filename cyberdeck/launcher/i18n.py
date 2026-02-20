from typing import Dict


LANG_CHOICES = (
    ("ru", "Русский"),
    ("en", "English"),
)


def normalize_language(value: str) -> str:
    """Normalize and transform values used to normalize language."""
    # Normalize inputs early so downstream logic receives stable values.
    v = str(value or "").strip().lower()
    return v if v in ("ru", "en") else "ru"


def language_options() -> list[str]:
    """Return available language labels for the UI."""
    return [label for _code, label in LANG_CHOICES]


def language_label(code: str) -> str:
    """Resolve a human-readable language label from a code."""
    c = normalize_language(code)
    for k, label in LANG_CHOICES:
        if k == c:
            return label
    return "Русский"


def language_code(label: str) -> str:
    """Resolve a language code from a localized label."""
    raw = str(label or "").strip().lower()
    for code, name in LANG_CHOICES:
        if raw == name.lower() or raw == code:
            return code
    return "ru"


_T: Dict[str, Dict[str, str]] = {
    "ru": {
        "app_subtitle": "Панель управления",
        "nav_home": "Сводка",
        "nav_devices": "Устройства",
        "nav_settings": "Настройки",
        "nav_support": "Поддержка",
        "nav_help": "Справка",
        "launcher_version": "Версия лаунчера: {version}",
        "home_title": "Состояние системы",
        "server_placeholder": "Сервер: ...",
        "access_code": "Код доступа",
        "copy": "Копировать",
        "refresh": "Обновить",
        "login_qr": "Вход по QR",
        "qr_unavailable": "QR недоступен",
        "refresh_qr": "Обновить QR",
        "server_label": "Сервер",
        "version_placeholder": "Версия: ...",
        "restart_server": "Перезапустить сервер",
        "summary": "Сводка",
        "devices_ratio": "Устройства: {online}/{total}",
        "logs_off": "Логи: выключены",
        "logs_console": "Логи: консоль",
        "tray_mode_main": "Трей: основной режим",
        "tray_mode_window": "Трей: окно",
        "logs_hint": "Подсказка: запустите с -c для вывода логов",
        "devices_title": "Устройства",
        "hide_panel": "Скрыть панель",
        "show_panel": "Показать панель",
        "updated_at": "Обновление: {time}",
        "updated_offline": "Обновление: нет связи",
        "show_offline": "Показывать офлайн",
        "target": "Цель",
        "none": "Нет",
        "target_not_selected": "Цель не выбрана",
        "disconnect": "Отключить",
        "delete": "Удалить",
        "delete_confirm": "Удалить устройство \"{name}\"?\n\nОно исчезнет из списка.",
        "alias": "Псевдоним",
        "transfer": "Передача",
        "transfer_profile": "Профиль передачи",
        "chunk_kb": "Размер блока (КБ)",
        "sleep_ms": "Пауза (мс)",
        "note": "Примечание",
        "permissions": "Права",
        "perm_mouse": "Управление курсором",
        "perm_keyboard": "Клавиатура и медиа",
        "perm_stream": "Видеопоток (экран)",
        "perm_upload": "Файлы на ПК (загрузка)",
        "perm_file_send": "Файлы на устройство (отправка)",
        "perm_power": "Питание и блокировка",
        "save": "Сохранить",
        "reset": "Сбросить",
        "send_file": "Отправить файл",
        "choose_device": "> Выберите устройство",
        "no_connections": "Подключений нет",
        "status_online": "Онлайн",
        "status_offline": "Офлайн",
        "profile": "профиль",
        "settings_title": "Настройки",
        "start_in_tray": "Запускать в трее",
        "show_on_start": "Открывать окно при запуске",
        "close_to_tray": "Закрывать в трей",
        "always_on_top": "Поверх окон",
        "autostart": "Автозапуск с системой",
        "hotkey": "Горячая клавиша Ctrl+Alt+D",
        "debug_logs": "Режим отладки логов сервера",
        "server_params_auto_restart": "Параметры сервера (перезапускаются автоматически после применения)",
        "preferred_port": "Порт (предпочтительный)",
        "pairing_ttl_min": "PIN действует, мин (0 = бесконечно)",
        "session_ttl_days": "TTL сессии, дней (0 = бесконечно)",
        "session_idle_ttl_min": "Idle TTL сессии, мин (0 = бесконечно)",
        "max_sessions": "Макс устройств (0 = без лимита)",
        "pin_window_s": "PIN окно, сек",
        "pin_max_fails": "PIN ошибок за окно",
        "pin_block_s": "PIN блокировка, сек",
        "tls_https": "TLS (HTTPS)",
        "enable_tls": "Включить TLS",
        "cert_file": "Сертификат (.crt/.pem)",
        "key_file": "Ключ (.key/.pem)",
        "ca_file": "CA (опционально)",
        "qr_mode": "Режим QR",
        "open_site": "Открывать сайт",
        "open_app": "Открывать приложение",
        "language": "Язык интерфейса",
        "app_config_title": "Конфиг приложения ({name})",
        "allow_query_token": "Разрешить вход по token в URL (устаревший режим)",
        "mdns_enable": "Включить mDNS-обнаружение",
        "upload_max_bytes": "Макс размер загрузки (байты, 0 = без лимита)",
        "upload_allowed_ext": "Разрешенные расширения (.txt,.zip), пусто = любые",
        "verbose_http": "Подробные HTTP-логи",
        "verbose_ws": "Подробные WS-логи",
        "verbose_stream": "Подробные логи стрима",
        "open_app_config": "Открыть конфиг приложения",
        "apply": "Применить",
        "about": "О приложении",
        "settings_applied": "Настройки применены",
        "settings_restart_launcher": "Настройки применены. Для полного применения перезапустите лаунчер.",
        "tls_invalid": "TLS включён, но не задан путь к сертификату или ключу.",
        "server_online_state": "Сервер: онлайн",
        "server_offline_state": "Сервер: нет связи",
        "server_version_line": "Сервер: {server} | Лаунчер: {launcher}",
        "device_not_selected": "> Устройство не выбрано",
        "choose_file": "Выберите файл",
        "transfer_request": "> Запрос передачи...",
        "transfer_started": "> Передача началась",
        "api_error": "> Ошибка API",
        "error_prefix": "> Ошибка: {msg}",
        "toast_transfer_started": "Передача файла запущена",
        "toast_transfer_error": "Ошибка передачи: {msg}",
        "toast_api_error_transfer": "Ошибка API при передаче файла",
        "toast_saving_error": "Ошибка сохранения: {msg}",
        "toast_save_failed": "Не удалось сохранить настройки",
        "device_settings_saved": "> Настройки сохранены",
        "toast_device_settings_saved": "Настройки сохранены",
        "device_settings_dirty": "> Есть несохраненные настройки (нажмите «Сохранить»)",
        "device_settings_no_changes": "> Изменений нет",
        "unsaved_changes": "Есть несохраненные изменения",
        "save_error": "> Ошибка сохранения",
        "code_copied": "> Код скопирован",
        "toast_code_copied": "Код доступа скопирован",
        "toast_code_refreshing": "Код доступа обновляется",
        "toast_code_refresh_failed": "Не удалось обновить код доступа",
        "transfer_msg_offline": "Устройство не в сети",
        "transfer_msg_file_missing": "Файл не найден",
        "transfer_msg_server_not_ready": "Сервер еще не готов",
        "transfer_msg_transporter_missing": "Не найден transporter.py",
        "transfer_msg_started": "Передача запущена",
        "open_file_failed": "Не удалось открыть {path}",
        "support_open_failed": "Не удалось открыть страницу поддержки",
        "help_title": "",
        "help_text": (),
        "about_title": "О приложении",
        "about_text": (
            "CyberDeck\n\n"
            "Клиент для управления ПК по локальной сети.\n\n"
            "Автор:\n"
            "Overl1te\n"
            "https://github.com/Overl1te\n\n"
            "Репозиторий проекта:\n"
            "https://github.com/Overl1te/CyberDeck\n\n"
            "Лицензия GNU GPLv3\n"
            "https://github.com/Overl1te/CyberDeck/blob/main/LICENSE\n\n"
            "Условия использования\n"
            "https://github.com/Overl1te/CyberDeck/blob/main/TERMS_OF_USE.md\n\n"
            "CyberDeck Copyright (C) 2026  Overl1te\n\n"
            "Версия лаунчера: {version}"
        ),
        "tray_toggle": "Показать/скрыть",
        "tray_restart": "Перезапустить сервер",
        "tray_downloads": "Открыть Загрузки",
        "tray_help": "Справка",
        "tray_about": "О приложении",
        "tray_exit": "Выход",
        "qr_error": "QR ошибка",
    },
    "en": {
        "app_subtitle": "Control panel",
        "nav_home": "Home",
        "nav_devices": "Devices",
        "nav_settings": "Settings",
        "nav_support": "Support",
        "nav_help": "Help",
        "launcher_version": "Launcher version: {version}",
        "home_title": "System status",
        "server_placeholder": "Server: ...",
        "access_code": "Access code",
        "copy": "Copy",
        "refresh": "Refresh",
        "login_qr": "QR login",
        "qr_unavailable": "QR unavailable",
        "refresh_qr": "Refresh QR",
        "server_label": "Server",
        "version_placeholder": "Version: ...",
        "restart_server": "Restart server",
        "summary": "Summary",
        "devices_ratio": "Devices: {online}/{total}",
        "logs_off": "Logs: disabled",
        "logs_console": "Logs: console",
        "tray_mode_main": "Tray: primary mode",
        "tray_mode_window": "Tray: window mode",
        "logs_hint": "Tip: run with -c to see logs",
        "devices_title": "Devices",
        "hide_panel": "Hide panel",
        "show_panel": "Show panel",
        "updated_at": "Updated: {time}",
        "updated_offline": "Updated: offline",
        "show_offline": "Show offline",
        "target": "Target",
        "none": "None",
        "target_not_selected": "Target not selected",
        "disconnect": "Disconnect",
        "delete": "Delete",
        "delete_confirm": "Delete device \"{name}\"?\n\nIt will disappear from the list.",
        "alias": "Alias",
        "transfer": "Transfer",
        "transfer_profile": "Transfer profile",
        "chunk_kb": "Chunk size (KB)",
        "sleep_ms": "Pause (ms)",
        "note": "Note",
        "permissions": "Permissions",
        "perm_mouse": "Pointer control",
        "perm_keyboard": "Keyboard and media",
        "perm_stream": "Video stream (screen)",
        "perm_upload": "Files to PC (upload)",
        "perm_file_send": "Files to device (send)",
        "perm_power": "Power and lock",
        "save": "Save",
        "reset": "Reset",
        "send_file": "Send file",
        "choose_device": "> Select a device",
        "no_connections": "No connections",
        "status_online": "Online",
        "status_offline": "Offline",
        "profile": "profile",
        "settings_title": "Settings",
        "start_in_tray": "Start in tray",
        "show_on_start": "Show window on startup",
        "close_to_tray": "Close to tray",
        "always_on_top": "Always on top",
        "autostart": "Autostart with system",
        "hotkey": "Hotkey Ctrl+Alt+D",
        "debug_logs": "Debug server logs",
        "server_params_auto_restart": "Server params (auto-restart after apply)",
        "preferred_port": "Port (preferred)",
        "pairing_ttl_min": "PIN TTL, min (0 = unlimited)",
        "session_ttl_days": "Session TTL, days (0 = unlimited)",
        "session_idle_ttl_min": "Session idle TTL, min (0 = unlimited)",
        "max_sessions": "Max devices (0 = unlimited)",
        "pin_window_s": "PIN window, sec",
        "pin_max_fails": "PIN max fails in window",
        "pin_block_s": "PIN block, sec",
        "tls_https": "TLS (HTTPS)",
        "enable_tls": "Enable TLS",
        "cert_file": "Certificate (.crt/.pem)",
        "key_file": "Key (.key/.pem)",
        "ca_file": "CA (optional)",
        "qr_mode": "QR mode",
        "open_site": "Open website",
        "open_app": "Open app",
        "language": "Interface language",
        "app_config_title": "Application config ({name})",
        "allow_query_token": "Allow token login via URL (legacy mode)",
        "mdns_enable": "Enable mDNS discovery",
        "upload_max_bytes": "Upload max size (bytes, 0 = unlimited)",
        "upload_allowed_ext": "Allowed extensions (.txt,.zip), empty = any",
        "verbose_http": "Verbose HTTP logs",
        "verbose_ws": "Verbose WS logs",
        "verbose_stream": "Verbose stream logs",
        "open_app_config": "Open app config",
        "apply": "Apply",
        "about": "About",
        "settings_applied": "Settings applied",
        "settings_restart_launcher": "Settings applied. Restart launcher for full effect.",
        "tls_invalid": "TLS is enabled, but certificate or key path is missing.",
        "server_online_state": "Server: online",
        "server_offline_state": "Server: no connection",
        "server_version_line": "Server: {server} | Launcher: {launcher}",
        "device_not_selected": "> Device not selected",
        "choose_file": "Select file",
        "transfer_request": "> Sending request...",
        "transfer_started": "> Transfer started",
        "api_error": "> API error",
        "error_prefix": "> Error: {msg}",
        "toast_transfer_started": "File transfer started",
        "toast_transfer_error": "Transfer error: {msg}",
        "toast_api_error_transfer": "API error during file transfer",
        "toast_saving_error": "Save error: {msg}",
        "toast_save_failed": "Failed to save settings",
        "device_settings_saved": "> Settings saved",
        "toast_device_settings_saved": "Settings saved",
        "device_settings_dirty": "> Unsaved settings (click \"Save\")",
        "device_settings_no_changes": "> No changes",
        "unsaved_changes": "Unsaved changes",
        "save_error": "> Save error",
        "code_copied": "> Code copied",
        "toast_code_copied": "Access code copied",
        "toast_code_refreshing": "Refreshing access code",
        "toast_code_refresh_failed": "Failed to refresh access code",
        "transfer_msg_offline": "Device is offline",
        "transfer_msg_file_missing": "File not found",
        "transfer_msg_server_not_ready": "Server is not ready",
        "transfer_msg_transporter_missing": "transporter.py is missing",
        "transfer_msg_started": "Transfer started",
        "open_file_failed": "Failed to open {path}",
        "support_open_failed": "Failed to open support page",
        "help_title": "Help",
        "help_text": (
            "CyberDeck Launcher {version}\n\n"
            "Main sections:\n"
            "1. Home: PIN, QR, server address.\n"
            "2. Devices: pick device, permissions, file transfer.\n"
            "3. Settings: launcher and server parameters.\n\n"
            "Docker tests:\n"
            "docker compose -f docker-compose.tests.yml build\n"
            "docker compose -f docker-compose.tests.yml run --rm tests\n"
        ),
        "about_title": "About",
        "about_text": (
            "CyberDeck\n\n"
            "Client for controlling a PC over local network.\n\n"
            "Author:\n"
            "Overl1te\n"
            "https://github.com/Overl1te\n\n"
            "Project repository:\n"
            "https://github.com/Overl1te/CyberDeck\n\n"
            "License GNU GPLv3\n"
            "https://github.com/Overl1te/CyberDeck/blob/main/LICENSE\n\n"
            "Terms of use\n"
            "https://github.com/Overl1te/CyberDeck/blob/main/TERMS_OF_USE.md\n\n"
            "CyberDeck Copyright (C) 2026  Overl1te\n\n"
            "Launcher version: {version}"
        ),
        "tray_toggle": "Show/Hide",
        "tray_restart": "Restart server",
        "tray_downloads": "Open Downloads",
        "tray_help": "Help",
        "tray_about": "About",
        "tray_exit": "Exit",
        "qr_error": "QR error",
    },
}


def tr(lang: str, key: str, **kwargs) -> str:
    """Translate a localization key using the active language."""
    c = normalize_language(lang)
    text = _T.get(c, {}).get(key)
    if text is None:
        text = _T.get("ru", {}).get(key, key)
    try:
        return str(text).format(**kwargs)
    except Exception:
        return str(text)
