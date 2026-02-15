import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from . import config


def setup_logging() -> logging.Logger:
    """Set up logging."""
    os.makedirs(config.BASE_DIR, exist_ok=True)
    logger = logging.getLogger("cyberdeck")
    logger.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)

    if not config.LOG_ENABLED:
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            ul = logging.getLogger(name)
            ul.handlers.clear()
            ul.propagate = False
            ul.setLevel(logging.CRITICAL)
        return logger

    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = RotatingFileHandler(config.LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)
    logger.addHandler(file_handler)

    console = None
    if config.CONSOLE_LOG:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        console.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)
        logger.addHandler(console)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        ul = logging.getLogger(name)
        ul.handlers.clear()
        ul.propagate = False
        ul.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)
        ul.addHandler(file_handler)
        if console is not None:
            ul.addHandler(console)

    return logger


log = setup_logging()


def reload_logging() -> logging.Logger:
    """Reload logger level and handlers from current configuration."""
    logger = logging.getLogger("cyberdeck")
    try:
        logger.handlers.clear()
    except Exception:
        pass
    try:
        logger.propagate = True
    except Exception:
        pass

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        ul = logging.getLogger(name)
        try:
            ul.handlers.clear()
        except Exception:
            pass
        try:
            ul.propagate = True
        except Exception:
            pass

    return setup_logging()
