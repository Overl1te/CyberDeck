from __future__ import annotations

from .launcher_shared import *
from .launcher_app_startup import AppStartupMixin
from .launcher_app_runtime import AppRuntimeMixin
from .launcher_app_devices import AppDevicesMixin
from .launcher_app_ui import AppUiMixin
from .launcher_app_navigation import AppNavigationMixin


class App(AppStartupMixin, AppRuntimeMixin, AppDevicesMixin, AppUiMixin, AppNavigationMixin, ctk.CTk):
    """Main launcher application assembled from focused mixins."""
    pass
