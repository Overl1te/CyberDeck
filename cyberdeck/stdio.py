import os
import sys


def ensure_null_stdio() -> None:
    """В сборках с `--noconsole` sys.stdout/stderr могут быть None; подменяем их на безопасные «поглотители»."""
    try:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="ignore")
    except Exception:
        pass
    try:
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="ignore")
    except Exception:
        pass
