# Updates

- Сервер и API переработаны: выделены отдельные слои публичного, локального и системного API; добавлены handshake/stats/diagnostics/upload, протокольный endpoint и расширенные локальные операции управления устройствами.
- Добавлена QR-авторизация через одноразовый токен с обратной совместимостью по `nonce`.
- Усилена безопасность: granular permissions (`perm_mouse`, `perm_keyboard`, `perm_stream`, `perm_upload`, `perm_file_send`, `perm_power`), PIN rate limiting, ограничения по TTL/idle TTL/max sessions.
- Добавлены лимиты и правила загрузки файлов: max size + whitelist расширений.
- Переработан менеджмент сессий: персист, cleanup просроченных сессий, авто-eviction при лимите, безопасное сохранение.
- Полностью переработан видеостек: разнесение на специализированные модули, добавлены H.264/H.265 endpoint’ы, stream-offer с fallback-кандидатами, stream stats/backends/monitors.
- Улучшена работа в Wayland/X11 и fallback-логика стриминга.
- Обновлен WS-протокол: hello/heartbeat/ping-pong/capabilities, диагностика по сессиям, улучшенная обработка текста и виртуального курсора.
- Лаунчер перестроен на модульную архитектуру (startup/runtime/navigation/devices/ui), добавлены экраны Home/Devices/Settings, трэй-режим, хоткей, тосты, живое обновление UI.
- Добавлена локализация RU/EN для UI и настроек.
- Добавлен boot overlay/анимация старта и in-process запуск сервера в packaged-режиме для устранения рекурсивных перезапусков.
- Инпут-бэкенды разделены на base/linux/windows; улучшены Linux/Wayland setup-check и автоподготовка.
- Переработан file transfer host->device: одноразовый URL, token/IP-ограничения, Range, SHA-256, expiry.
- Добавлены и доработаны сборочные сценарии: Nuitka для Windows, обновленные Linux/Arch-скрипты, отдельный onefile portable script.
- Обновлен `setup.iss` под Nuitka layout, исправлен postinstall launch для UAC-admin exe (исправление ошибки 740).
- Вшита иконка в Windows exe (`--windows-icon-from-ico`), добавлены стабилизации для onefile-ресурсов иконок.
- Build-скрипты усилены: корректная очистка с ретраями, авто-остановка блокирующих процессов, более надежная диагностика путей артефактов.
- Документация расширена: README/CONTRIBUTING RU+EN, security/support/code-of-conduct/terms/citation, плюс CI/Docker тестовые артефакты и funding.
