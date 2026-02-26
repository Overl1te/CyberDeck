from __future__ import annotations

from typing import Dict
import json
import os


LANG_CHOICES = (
    ("ru", "Русский"),
    ("en", "English"),
)


def _i18n_json_path() -> str:
    """Return absolute path to i18n JSON dictionary file."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "i18n.json")


def _load_translations() -> Dict[str, Dict[str, str]]:
    """Load translations from JSON with safe fallback."""
    path = _i18n_json_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return {}
        out: Dict[str, Dict[str, str]] = {}
        for lang, mapping in payload.items():
            if not isinstance(mapping, dict):
                continue
            lang_key = str(lang or "").strip().lower()
            if not lang_key:
                continue
            out[lang_key] = {str(k): str(v) for k, v in mapping.items()}
        return out
    except Exception:
        return {}


_T: Dict[str, Dict[str, str]] = _load_translations()


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
