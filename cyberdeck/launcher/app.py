from __future__ import annotations

from .shared import *
from .app_startup import AppStartupMixin
from .app_runtime import AppRuntimeMixin
from .app_devices import AppDevicesMixin
from .app_ui import AppUiMixin
from .app_navigation import AppNavigationMixin


class App(AppStartupMixin, AppRuntimeMixin, AppDevicesMixin, AppUiMixin, AppNavigationMixin, ctk.CTk):
    """Main launcher application assembled from focused mixins."""
    pass

