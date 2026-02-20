# Вклад в CyberDeck

<p align="left">
  <a href="CONTRIBUTING_EN.md">English version</a> •
  <a href="README.md">README</a> •
  <a href="CODE_OF_CONDUCT.md">Code of Conduct</a> •
  <a href="SECURITY.md">Security</a>
</p>

Документ описывает, как устроен проект и как вносить изменения так, чтобы они были предсказуемыми, проверяемыми и безопасными.

## Принципы

- Изменения должны быть воспроизводимыми и покрытыми тестами.
- Безопасность важнее «удобного хака».
- Предпочтение модульным изменениям вместо монолитных правок.
- Документация и код должны обновляться синхронно.

## Технологический стек

- Python 3.11+
- FastAPI + Uvicorn
- CustomTkinter (launcher UI)
- WebSocket для live input
- Pillow / qrcode / mss для графики и стриминга
- unittest + pytest (часть сценариев)

## Карта проекта

| Путь | Назначение |
|---|---|
| `launcher.py` | Оркестрация лаунчера: UI, запуск сервера, трэй, QR, настройки |
| `cyberdeck/launcher/ui/home.py` | Экран «Сводка» |
| `cyberdeck/launcher/ui/devices.py` | Экран «Устройства», пермишены и профили передачи |
| `cyberdeck/launcher/ui/settings.py` | Экран «Настройки», app config, TLS, runtime-параметры |
| `main.py` | Точка входа сервера |
| `cyberdeck/server.py` | Сборка FastAPI-приложения и подключение роутеров |
| `cyberdeck/api/core.py` | Публичный API (handshake/upload/protocol/stats) |
| `cyberdeck/api/local.py` | Локальный API для лаунчера (`/api/local/*`) |
| `cyberdeck/api/system.py` | Системные действия и управление звуком |
| `cyberdeck/ws/mouse.py` | WebSocket-канал ввода |
| `cyberdeck/video/` | Потоковое видео и backend-адаптация |
| `cyberdeck/input/` | Выбор и реализация backend-ов ввода |
| `cyberdeck/platform/wayland_setup.py` | Wayland runtime/setup проверки |
| `cyberdeck/transfer.py` | Отправка файлов с хоста на устройство |
| `cyberdeck/sessions.py` | Хранение, TTL и очистка сессий |
| `tests/` | Набор unit/behavioral тестов |

## Рабочий процесс

1. Создайте ветку от `main`.
2. Внесите изменения минимальным связным набором.
3. Обновите/добавьте тесты.
4. Обновите документацию при изменении поведения.
5. Откройте PR с понятным описанием.

Рекомендуемое именование веток:

- `feat/<short-name>`
- `fix/<short-name>`
- `refactor/<short-name>`
- `docs/<short-name>`

## Локальная разработка

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements-dev.txt
# при тестировании/разработке desktop-ввода:
pip install -r requirements-desktop-input.txt
```

## Установка и запуск из исходников

Базовая установка:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Установка только core (без desktop-ввода):

```bash
pip install -r requirements-core.txt
```

Запуск приложения (лаунчер):

```bash
python launcher.py
```

Запуск только сервера:

```bash
python main.py
```

## API (техническая часть)

Публичные эндпоинты:

- `POST /api/handshake` — сопряжение по PIN.
- `GET /api/stats` — статистика сервера.
- `POST /api/file/upload` — загрузка файла на ПК.
- `WS /ws/mouse` — канал удаленного ввода.
- `GET /video_feed` — MJPEG поток.
- `GET /video_h264` — H.264 поток.
- `GET /video_h265` — H.265 поток.
- `GET /api/stream_offer` — рекомендации транспорта/codec fallback.
- `POST /system/*` и `POST /volume/{up|down|mute}` — системные действия.

Локальные эндпоинты (только `127.0.0.1`):

- `GET /api/local/info`
- `GET /api/local/stats`
- `GET|POST /api/local/device_settings`
- `POST /api/local/device_disconnect`
- `POST /api/local/device_delete`
- `POST /api/local/regenerate_code`
- `POST /api/local/trigger_file`

## Тесты

Базовый прогон:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Точечный прогон:

```bash
pytest -q tests/test_launcher_shared_behavior.py
```

Docker-прогон:

```bash
docker compose -f docker-compose.tests.yml build
docker compose -f docker-compose.tests.yml run --rm tests
```

Примечание: Docker-тесты используют `requirements-dev.txt` (без `requirements-desktop-input.txt`).

## Сборка

Windows (Nuitka):

```powershell
pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows_nuitka.ps1
```

Linux (Arch helper script):

```bash
bash ./scripts/build_arch_linux.sh
```

## Стандарты кода

- Используйте понятные имена и короткие функции.
- Избегайте неявного глобального состояния.
- Для сложной логики добавляйте лаконичные комментарии по мотивации, не по синтаксису.
- Любая проверка прав доступа должна быть централизована и тестируема.
- При рефакторинге предпочитайте dependency injection вместо hardcoded зависимостей.

## Пермишены устройств

Система поддерживает granular-права на устройство:

- `perm_mouse`
- `perm_keyboard`
- `perm_upload`
- `perm_file_send`
- `perm_stream`
- `perm_power`

Любое изменение, затрагивающее разрешения, должно включать:

1. Проверку на уровне API/WS.
2. Негативный тест (доступ запрещен).
3. Позитивный тест (доступ разрешен).

## Конфигурация

- `launcher_settings.json` — настройки лаунчера и части server runtime.
- `cyberdeck_app_config.json` — отдельный конфиг приложения (не `.env`).
- `cyberdeck_sessions.json` — сессии устройств.

Если меняете формат конфигов:

- сохраняйте обратную совместимость;
- добавляйте sane default;
- документируйте новые поля.

## Чеклист PR

- [ ] Изменение решает конкретную проблему и не ломает существующий сценарий.
- [ ] Добавлены/обновлены тесты.
- [ ] Обновлены `README*`/`CONTRIBUTING*` при изменении UX/API.
- [ ] Проверены edge-case сценарии (offline, invalid input, permission denied).
- [ ] Нет лишних логов/дебаг-кода.

## Отчеты о проблемах

Для багов и feature-запросов используйте Issues:

- <https://github.com/Overl1te/CyberDeck/issues>

Для вопросов по безопасности:

- `SECURITY.md`

Для вопросов по поддержке:

- `SUPPORT.md`
