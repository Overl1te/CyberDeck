from __future__ import annotations

import asyncio
from typing import Optional

from .sessions import DeviceManager


device_manager = DeviceManager()
device_manager.load_sessions()

running_loop: Optional[asyncio.AbstractEventLoop] = None

