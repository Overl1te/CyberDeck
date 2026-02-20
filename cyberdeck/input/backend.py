"""Input backend factory that selects platform-specific implementations."""

import os

from .backends.base import _BaseInputBackend, _NullBackend, _session_kind
from .backends.linux import _WaylandBackend, _X11Backend
from .backends.windows import _PyAutoGuiBackend
from ..logging_config import log


def _is_linux_platform() -> bool:
    """Return whether current runtime should use Linux fallback paths."""
    return os.name != "nt"


def _create_backend_for_session(kind: str) -> _BaseInputBackend:
    """Instantiate backend implementation that matches detected session kind."""
    if kind == "windows":
        return _PyAutoGuiBackend()
    if kind == "x11":
        return _X11Backend()
    if kind == "wayland":
        return _WaylandBackend()
    return _PyAutoGuiBackend()


def _needs_linux_fallback(backend: _BaseInputBackend) -> bool:
    """Return whether selected backend requires Linux initialization fallback."""
    return _is_linux_platform() and isinstance(backend, (_X11Backend, _WaylandBackend))


def _build_backend() -> _BaseInputBackend:
    """Build and configure runtime input backend with safe fallbacks."""
    kind = _session_kind()
    backend = _create_backend_for_session(kind)

    # Linux sessions can degrade to pyautogui when specialized stacks are unavailable.
    if _needs_linux_fallback(backend):
        try:
            if not backend._ensure():
                backend = _PyAutoGuiBackend()
        except Exception:
            backend = _PyAutoGuiBackend()

    try:
        if isinstance(backend, _PyAutoGuiBackend) and not backend._ensure():
            backend = _NullBackend()
    except Exception:
        backend = _NullBackend()

    try:
        backend.configure()
    except Exception:
        # Do not abort startup if backend-specific configure fails.
        log.exception("Input backend configure failed: %s", getattr(backend, "name", "unknown"))
        backend = _NullBackend()
        try:
            backend.configure()
        except Exception:
            pass
    log.info("Input backend: %s (session=%s)", backend.name, kind)
    return backend


INPUT_BACKEND = _build_backend()
