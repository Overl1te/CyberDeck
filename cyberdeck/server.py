import asyncio
import os
import socket
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .discovery import start_udp_discovery
from .stdio import ensure_null_stdio
from .wayland_setup import ensure_wayland_ready, format_wayland_issues, is_linux_wayland_session
from .logging_config import log

from .api_core import router as core_router
from .api_local import router as local_router
from .api_system import router as system_router
from .video import router as video_router
from .ws_mouse import router as ws_router
from .mdns import start_mdns


ensure_null_stdio()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize process-wide runtime context shared by request handlers."""
    import cyberdeck.context as ctx

    ctx.running_loop = asyncio.get_running_loop()
    yield


app = FastAPI(title=f"CyberDeck {config.VERSION}", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(getattr(config, "CORS_ORIGINS", ["*"])),
    allow_credentials=bool(getattr(config, "CORS_ALLOW_CREDENTIALS", False)),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sanitize_url_for_log(url: str) -> str:
    """Redact sensitive URL query values before HTTP access logging."""
    try:
        p = urlsplit(str(url or ""))
        qs = parse_qsl(p.query, keep_blank_values=True)
        out = []
        for k, v in qs:
            lk = str(k or "").lower()
            if lk in ("token", "t", "authorization", "auth"):
                out.append((k, "***"))
            else:
                sv = str(v or "")
                if len(sv) > 64:
                    sv = sv[:64] + "..."
                out.append((k, sv))
        q = urlencode(out, doseq=True)
        return p.path + (f"?{q}" if q else "")
    except Exception:
        return str(url or "")


@app.middleware("http")
async def http_log_middleware(request: Request, call_next):
    """Log HTTP request latency with selective verbosity and privacy filtering."""
    started = time.perf_counter()
    method = str(request.method or "")
    target = _sanitize_url_for_log(str(request.url or ""))
    try:
        response = await call_next(request)
    except Exception:
        if bool(getattr(config, "VERBOSE_HTTP_LOG", True)):
            log.exception("HTTP %s %s -> 500", method, target)
        raise

    dt_ms = (time.perf_counter() - started) * 1000.0
    status = int(getattr(response, "status_code", 0) or 0)
    should_log = bool(getattr(config, "VERBOSE_HTTP_LOG", True))
    if not should_log:
        should_log = dt_ms >= 1000.0 or target.startswith("/video_")
    if should_log:
        log.info("HTTP %s %s -> %s in %.1fms", method, target, status, dt_ms)
    return response


app.include_router(core_router)
app.include_router(local_router)
app.include_router(system_router)
app.include_router(video_router)
app.include_router(ws_router)

start_udp_discovery()

if os.path.exists(config.STATIC_DIR):
    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")


def _port_available(port: int) -> bool:
    """Return True when configured host/port can be bound successfully."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((config.HOST, int(port)))
            return True
    except Exception:
        return False


def run() -> None:
    """Start FastAPI server with optional Wayland bootstrap, mdns, and TLS settings."""
    if is_linux_wayland_session():
        auto_setup = os.environ.get("CYBERDECK_WAYLAND_AUTO_SETUP", "1") == "1"
        ok, issues, attempted, reason = ensure_wayland_ready(
            config.BASE_DIR,
            auto_install=auto_setup,
            log=lambda line: log.info("[wayland-setup] %s", line),
        )
        if ok:
            if issues:
                log.warning(
                    "Wayland environment is ready with limitations (%s): %s",
                    reason,
                    format_wayland_issues(issues),
                )
            else:
                log.info("Wayland environment is ready.")
        else:
            log.warning(
                "Wayland environment is not ready (%s): %s",
                reason,
                format_wayland_issues(issues),
            )

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
