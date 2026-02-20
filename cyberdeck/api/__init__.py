"""API routers package."""

from .core import router as core_router
from .local import router as local_router
from .system import router as system_router

__all__ = ["core_router", "local_router", "system_router"]
