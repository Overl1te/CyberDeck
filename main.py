"""Compatibility entrypoint.

Launcher/PyInstaller expect `main.app` to exist.
The server implementation lives in `cyberdeck.server`.
"""

from cyberdeck.server import app, run

__all__ = ["app", "run"]


if __name__ == "__main__":
    run()
