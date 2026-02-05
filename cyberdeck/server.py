import asyncio
import os
import socket
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .discovery import start_udp_discovery
from .stdio import ensure_null_stdio

from .api_core import router as core_router
from .api_local import router as local_router
from .api_system import router as system_router
from .video import router as video_router
from .ws_mouse import router as ws_router
from .mdns import start_mdns


ensure_null_stdio()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import cyberdeck.context as ctx

    ctx.running_loop = asyncio.get_running_loop()
    yield


app = FastAPI(title=f"CyberDeck {config.VERSION}", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(core_router)
app.include_router(local_router)
app.include_router(system_router)
app.include_router(video_router)
app.include_router(ws_router)

start_udp_discovery()

if os.path.exists(config.STATIC_DIR):
    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")


def _port_available(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((config.HOST, int(port)))
            return True
    except Exception:
        return False


def run() -> None:
    log_level = "debug" if config.DEBUG else "info"
    access_log = config.DEBUG
    if not config.LOG_ENABLED:
        log_level = "critical"
        access_log = False

    port = int(config.PORT)
    if getattr(config, "PORT_AUTO", False) and not _port_available(port):
        try:
            from .net import find_free_port

            port = int(find_free_port())
            config.PORT = port
        except Exception:
            pass

    if config.MDNS_ENABLED:
        try:
            start_mdns()
        except Exception:
            pass

    ssl_kwargs = {}
    if getattr(config, "TLS_ENABLED", False):
        ssl_kwargs = {"ssl_certfile": config.TLS_CERT, "ssl_keyfile": config.TLS_KEY}

    uvicorn.run(app, host=config.HOST, port=port, log_level=log_level, access_log=access_log, **ssl_kwargs)
