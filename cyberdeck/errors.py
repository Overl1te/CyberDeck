"""Centralized error catalog and response shaping for CyberDeck API."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


@dataclass(frozen=True)
class ErrorTemplate:
    code: str
    number: int
    slug: str
    title: str
    hint: str
    status: int
    tags: tuple[str, ...] = ()

    def to_catalog_item(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "number": int(self.number),
            "slug": self.slug,
            "title": self.title,
            "hint": self.hint,
            "status": int(self.status),
            "tags": list(self.tags),
        }


_CATALOG: dict[str, ErrorTemplate] = {
    "validation_error": ErrorTemplate(
        code="CD-1000",
        number=1000,
        slug="validation_error",
        title="Некорректные входные данные",
        hint="Проверьте формат и обязательные поля запроса.",
        status=422,
        tags=("request", "validation", "payload"),
    ),
    "token_required": ErrorTemplate(
        code="CD-1101",
        number=1101,
        slug="token_required",
        title="Отсутствует токен",
        hint="Передайте токен в Authorization: Bearer <token> или через поддерживаемый параметр.",
        status=400,
        tags=("auth", "token"),
    ),
    "session_not_found": ErrorTemplate(
        code="CD-1102",
        number=1102,
        slug="session_not_found",
        title="Сессия не найдена",
        hint="Повторите сопряжение устройства и используйте новый токен.",
        status=404,
        tags=("auth", "session"),
    ),
    "unauthorized": ErrorTemplate(
        code="CD-1401",
        number=1401,
        slug="unauthorized",
        title="Неавторизованный запрос",
        hint="Проверьте токен и заголовок Authorization.",
        status=403,
        tags=("auth", "token"),
    ),
    "permission_denied": ErrorTemplate(
        code="CD-1403",
        number=1403,
        slug="permission_denied",
        title="Недостаточно прав",
        hint="Разрешите нужный permission в настройках устройства на ПК.",
        status=403,
        tags=("auth", "permission"),
    ),
    "pin_rate_limited": ErrorTemplate(
        code="CD-2001",
        number=2001,
        slug="pin_rate_limited",
        title="Слишком много попыток PIN",
        hint="Подождите Retry-After и повторите попытку позже.",
        status=429,
        tags=("pairing", "pin", "rate-limit"),
    ),
    "invalid_code": ErrorTemplate(
        code="CD-2002",
        number=2002,
        slug="invalid_code",
        title="Неверный PIN-код",
        hint="Проверьте актуальный PIN в лаунчере и введите его заново.",
        status=403,
        tags=("pairing", "pin"),
    ),
    "pairing_expired": ErrorTemplate(
        code="CD-2003",
        number=2003,
        slug="pairing_expired",
        title="Срок действия PIN истек",
        hint="Сгенерируйте новый PIN-код и повторите сопряжение.",
        status=403,
        tags=("pairing", "pin", "ttl"),
    ),
    "qr_token_required": ErrorTemplate(
        code="CD-2101",
        number=2101,
        slug="qr_token_required",
        title="Не передан QR-токен",
        hint="Отсканируйте актуальный QR-код заново.",
        status=400,
        tags=("pairing", "qr"),
    ),
    "invalid_or_expired_qr_token": ErrorTemplate(
        code="CD-2102",
        number=2102,
        slug="invalid_or_expired_qr_token",
        title="QR-токен недействителен или истек",
        hint="Обновите QR в лаунчере и повторите вход.",
        status=403,
        tags=("pairing", "qr", "ttl"),
    ),
    "approval_pending": ErrorTemplate(
        code="CD-2103",
        number=2103,
        slug="approval_pending",
        title="Ожидается подтверждение на ПК",
        hint="Подтвердите запрос устройства в лаунчере CyberDeck на ПК.",
        status=202,
        tags=("pairing", "approval"),
    ),
    "upload_extension_not_allowed": ErrorTemplate(
        code="CD-3001",
        number=3001,
        slug="upload_extension_not_allowed",
        title="Расширение файла запрещено",
        hint="Добавьте расширение в whitelist загрузки или отправьте другой файл.",
        status=415,
        tags=("upload", "file"),
    ),
    "upload_too_large": ErrorTemplate(
        code="CD-3002",
        number=3002,
        slug="upload_too_large",
        title="Файл слишком большой",
        hint="Уменьшите размер файла или увеличьте limit upload_max_bytes на сервере.",
        status=413,
        tags=("upload", "file", "limit"),
    ),
    "upload_checksum_mismatch": ErrorTemplate(
        code="CD-3003",
        number=3003,
        slug="upload_checksum_mismatch",
        title="Контрольная сумма не совпала",
        hint="Повторите загрузку файла; проверьте сеть и целостность файла.",
        status=400,
        tags=("upload", "checksum"),
    ),
    "upload_failed": ErrorTemplate(
        code="CD-3004",
        number=3004,
        slug="upload_failed",
        title="Ошибка загрузки файла",
        hint="Проверьте права записи в FILES_DIR и свободное место на диске.",
        status=500,
        tags=("upload", "storage"),
    ),
    "device_not_found": ErrorTemplate(
        code="CD-4001",
        number=4001,
        slug="device_not_found",
        title="Устройство не найдено",
        hint="Обновите список устройств и повторите действие.",
        status=404,
        tags=("device", "session"),
    ),
    "device_id_required": ErrorTemplate(
        code="CD-4002",
        number=4002,
        slug="device_id_required",
        title="Не передан device_id",
        hint="Передайте device_id в теле запроса.",
        status=400,
        tags=("device", "request"),
    ),
    "delete_failed": ErrorTemplate(
        code="CD-4003",
        number=4003,
        slug="delete_failed",
        title="Не удалось удалить устройство",
        hint="Повторите позже и проверьте доступ к файлу сессий.",
        status=500,
        tags=("device", "storage"),
    ),
    "approve_failed": ErrorTemplate(
        code="CD-4004",
        number=4004,
        slug="approve_failed",
        title="Не удалось изменить статус подтверждения",
        hint="Повторите действие и проверьте состояние сессий.",
        status=500,
        tags=("device", "approval"),
    ),
    "rename_failed": ErrorTemplate(
        code="CD-4005",
        number=4005,
        slug="rename_failed",
        title="Не удалось сохранить alias/note",
        hint="Проверьте файл сессий и повторите попытку.",
        status=500,
        tags=("device", "storage"),
    ),
    "shutdown_failed": ErrorTemplate(
        code="CD-5001",
        number=5001,
        slug="shutdown_failed",
        title="Команда выключения не выполнена",
        hint="Проверьте системные права процесса CyberDeck.",
        status=500,
        tags=("system", "power"),
    ),
    "restart_failed": ErrorTemplate(
        code="CD-5002",
        number=5002,
        slug="restart_failed",
        title="Команда перезагрузки не выполнена",
        hint="Проверьте системные права процесса CyberDeck.",
        status=500,
        tags=("system", "power"),
    ),
    "logoff_failed": ErrorTemplate(
        code="CD-5003",
        number=5003,
        slug="logoff_failed",
        title="Команда выхода из сессии не выполнена",
        hint="Проверьте доступность утилит logoff/loginctl.",
        status=500,
        tags=("system", "session"),
    ),
    "logoff_not_supported_on_this_system": ErrorTemplate(
        code="CD-5004",
        number=5004,
        slug="logoff_not_supported_on_this_system",
        title="Выход из сессии не поддерживается",
        hint="Используйте lock/shutdown/restart для этой ОС.",
        status=400,
        tags=("system", "session"),
    ),
    "lock_not_supported_on_this_system": ErrorTemplate(
        code="CD-5005",
        number=5005,
        slug="lock_not_supported_on_this_system",
        title="Блокировка экрана не поддерживается",
        hint="Проверьте установленный desktop environment и утилиты lock.",
        status=400,
        tags=("system", "lock"),
    ),
    "sleep_failed": ErrorTemplate(
        code="CD-5006",
        number=5006,
        slug="sleep_failed",
        title="Не удалось перевести систему в сон",
        hint="Проверьте поддержку sleep/hibernate в ОС и права процесса.",
        status=500,
        tags=("system", "power"),
    ),
    "hibernate_failed": ErrorTemplate(
        code="CD-5007",
        number=5007,
        slug="hibernate_failed",
        title="Не удалось перевести систему в гибернацию",
        hint="Проверьте поддержку hibernate в ОС и права процесса.",
        status=500,
        tags=("system", "power"),
    ),
    "unknown_action": ErrorTemplate(
        code="CD-5008",
        number=5008,
        slug="unknown_action",
        title="Неизвестное действие",
        hint="Проверьте параметр action в запросе.",
        status=400,
        tags=("system", "request"),
    ),
    "keyboard_input_unavailable": ErrorTemplate(
        code="CD-5009",
        number=5009,
        slug="keyboard_input_unavailable",
        title="Клавиатурный backend недоступен",
        hint="Проверьте разрешения ввода и настройки backend на сервере.",
        status=501,
        tags=("system", "input"),
    ),
    "internal_error": ErrorTemplate(
        code="CD-9000",
        number=9000,
        slug="internal_error",
        title="Внутренняя ошибка сервера",
        hint="Повторите запрос позже и проверьте логи сервера.",
        status=500,
        tags=("internal",),
    ),
}

_DETAIL_ALIASES: dict[str, str] = {
    "validation_error": "validation_error",
    "invalid code": "invalid_code",
    "pairing_expired": "pairing_expired",
    "pin_rate_limited": "pin_rate_limited",
    "token_required": "token_required",
    "session_not_found": "session_not_found",
    "unauthorized": "unauthorized",
    "upload_extension_not_allowed": "upload_extension_not_allowed",
    "upload_too_large": "upload_too_large",
    "upload_checksum_mismatch": "upload_checksum_mismatch",
    "upload_failed": "upload_failed",
    "qr_token_required": "qr_token_required",
    "invalid_or_expired_qr_token": "invalid_or_expired_qr_token",
    "device_not_found": "device_not_found",
    "device_id_required": "device_id_required",
    "delete_failed": "delete_failed",
    "approve_failed": "approve_failed",
    "rename_failed": "rename_failed",
    "shutdown_failed": "shutdown_failed",
    "restart_failed": "restart_failed",
    "logoff_failed": "logoff_failed",
    "logoff_not_supported_on_this_system": "logoff_not_supported_on_this_system",
    "lock_not_supported_on_this_system": "lock_not_supported_on_this_system",
    "sleep_failed": "sleep_failed",
    "hibernate_failed": "hibernate_failed",
    "unknown_action": "unknown_action",
    "keyboard_input_unavailable": "keyboard_input_unavailable",
    "approval_pending": "approval_pending",
    "not found": "session_not_found",
}


def _normalize_detail(detail: Any) -> str:
    if detail is None:
        return "internal_error"
    if isinstance(detail, str):
        value = detail.strip()
        return value or "internal_error"
    try:
        return str(detail).strip() or "internal_error"
    except Exception:
        return "internal_error"


def _incident_id() -> str:
    return f"CDI-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6].upper()}"


def _permission_template(detail: str) -> dict[str, Any]:
    template = _CATALOG["permission_denied"]
    perm = ""
    if ":" in detail:
        perm = detail.split(":", 1)[1].strip()
    hint = template.hint
    if perm:
        hint = f"{hint} Требуется: {perm}."
    return {
        **template.to_catalog_item(),
        "hint": hint,
    }


def _template_payload(detail: str, status_code: int) -> dict[str, Any]:
    normalized = detail.strip()
    low = normalized.lower()
    if low.startswith("permission_denied:"):
        payload = _permission_template(normalized)
        payload["status"] = int(status_code or payload.get("status") or 403)
        return payload

    alias = _DETAIL_ALIASES.get(low)
    if alias and alias in _CATALOG:
        t = _CATALOG[alias].to_catalog_item()
        t["status"] = int(status_code or t.get("status") or 500)
        return t

    fallback = _CATALOG["internal_error"].to_catalog_item()
    fallback["status"] = int(status_code or 500)
    return fallback


def build_error_response(
    *,
    detail: Any,
    status_code: int,
    path: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    detail_text = _normalize_detail(detail)
    payload = _template_payload(detail_text, int(status_code or 500))
    code = str(payload.get("code") or _CATALOG["internal_error"].code)
    error_block = {
        "code": code,
        "number": int(payload.get("number") or _CATALOG["internal_error"].number),
        "slug": str(payload.get("slug") or _CATALOG["internal_error"].slug),
        "title": str(payload.get("title") or _CATALOG["internal_error"].title),
        "hint": str(payload.get("hint") or _CATALOG["internal_error"].hint),
        "status": int(status_code or payload.get("status") or 500),
        "incident_id": _incident_id(),
        "path": str(path or ""),
        "docs_url": f"/errors.html?code={code}",
        "tags": list(payload.get("tags") or []),
    }
    out = {
        "detail": detail_text,
        "error": error_block,
    }
    if extra:
        out.update(extra)
    return out


def catalog_items(*, query: str = "", limit: int = 500) -> list[dict[str, Any]]:
    rows = [item.to_catalog_item() for item in _CATALOG.values()]
    rows.sort(key=lambda x: int(x.get("number") or 0))
    q = str(query or "").strip().lower()
    if q:
        filtered: list[dict[str, Any]] = []
        for item in rows:
            haystack_parts: Iterable[str] = (
                str(item.get("code") or ""),
                str(item.get("slug") or ""),
                str(item.get("title") or ""),
                str(item.get("hint") or ""),
                " ".join([str(x) for x in (item.get("tags") or [])]),
            )
            haystack = " ".join(haystack_parts).lower()
            if q in haystack:
                filtered.append(item)
        rows = filtered
    lim = max(1, min(2000, int(limit or 500)))
    return rows[:lim]
