"""Точка входа для обратной совместимости.

Лаунчер/PyInstaller ожидают, что `main.app` существует.
Вся реализация теперь находится в `cyberdeck.server`.
"""

from cyberdeck.server import app, run


if __name__ == "__main__":
    run()
