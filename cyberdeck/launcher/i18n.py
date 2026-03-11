from __future__ import annotations

from typing import Dict
import json
import os
import re


LANG_CHOICES = (
    ("ru", "Русский"),
    ("en", "English"),
)


def _i18n_json_path() -> str:
    """Return absolute path to i18n JSON dictionary file."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "i18n.json")


_MOJIBAKE_PATTERN = re.compile(r"(Р.|С.|вЂ.|Ð.|Ñ.|Â.)")


def _repair_text(value: str) -> str:
    """Best-effort repair for common mojibake sequences in translation strings."""
    text = str(value or "")
    if not text:
        return ""
    if not _MOJIBAKE_PATTERN.search(text):
        return text

    candidates = [text]
    for enc in ("cp1251", "latin1"):
        try:
            candidates.append(text.encode(enc).decode("utf-8"))
        except Exception:
            continue

    def _score(s: str) -> int:
        good = 0
        bad = 0
        for ch in s:
            if ("A" <= ch <= "Z") or ("a" <= ch <= "z") or ("А" <= ch <= "я") or ch in "ёЁ":
                good += 1
        for marker in ("Р", "С", "вЂ", "Â", "Ð", "Ñ"):
            bad += s.count(marker)
        return good - (bad * 3)

    best = text
    best_score = _score(text)
    for item in candidates[1:]:
        score = _score(item)
        if score > best_score + 4:
            best = item
            best_score = score
    return best


def _load_translations() -> Dict[str, Dict[str, str]]:
    """Load translations from JSON with safe fallback and encoding repair."""
    path = _i18n_json_path()
    raw = b""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception:
        return {}

    payload = None
    for enc in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            payload = json.loads(raw.decode(enc))
            break
        except Exception:
            continue
    if not isinstance(payload, dict):
        return {}

    out: Dict[str, Dict[str, str]] = {}
    for lang, mapping in payload.items():
        if not isinstance(mapping, dict):
            continue
        lang_key = str(lang or "").strip().lower()
        if not lang_key:
            continue
        fixed: Dict[str, str] = {}
        for k, v in mapping.items():
            fixed[str(k)] = _repair_text(str(v))
        out[lang_key] = fixed
    return out


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
