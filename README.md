<div align="center">

# CyberDeck Control — удалённое управление ПК

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.95+-009688.svg)
![Windows](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20-lightgrey.svg)
![License](https://img.shields.io/badge/license-%20%20GNU%20GPLv3%20-green)

**Пульт управления компьютером со смартфона в стиле Cyberpunk**

[Особенности](#-особенности) • [Установка](#-установка) • [Запуск](#-запуск) • [Использование](#-использование) • [API](#-api) • [FAQ](#-faq)

</div>

---

## ✨ Особенности

- 🔒 Сопряжение по 4‑значному PIN
- 🖱️ Тачпад и жесты (WebSocket)
- ⌨️ Ввод текста + хоткеи/медиа‑кнопки
- 📺 Трансляция экрана (MJPEG)
- 📊 Системная статистика
- 🧩 Лаунчер (трей, список устройств, управление правами/настройками)

---

## 🚀 Установка

### Требования

- Windows 10/11 или Linux
- Python 3.9+
- ПК и телефон в одной сети Wi‑Fi/LAN

Примечания для Linux:
- Для GUI-лаунчера обычно нужен пакет `tk`/`python3-tk`.
- Трей/автостарт зависят от окружения рабочего стола (поддержка может отличаться).
- Команды питания (`shutdown/reboot/suspend/hibernate`) выполняются через `systemctl` и могут требовать прав/Polkit.

### Из исходников

```bash
git clone https://github.com/Overl1te/CyberDeck.git
cd CyberDeck

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

---

## ▶️ Запуск

### Вариант 1 (рекомендуется): лаунчер

```bash
python launcher.py
```

Лаунчер запускает сервер и показывает данные для подключения (IP/порт/PIN), а также даёт локальные инструменты управления устройствами.

### Вариант 2: только сервер

```bash
python main.py
```

---

## 🧰 Сборка бинарника (Arch Linux)

Nuitka/PyInstaller **не кросс-компилируют**: бинарник для Linux нужно собирать **на Linux** (например, на Arch в нативной системе/VM).

### 1) Поставить системные зависимости (минимум)

```bash
sudo pacman -S --needed python python-pip tk gcc patchelf
```

Опционально:
- `base-devel` — если `pip` начнёт собирать зависимости из исходников
- `ffmpeg` — для `/video_h264` и `/video_h265`
- `libx11`, `libxtst`, `libxrandr`, `libxinerama`, `libxfixes` — если в минимальной системе не хватает X11 библиотек (ввод/захват экрана)
- Для трея/иконки в некоторых окружениях может понадобиться GTK/AppIndicator (на Arch это зависит от DE/панели).

### 2) Собрать через Nuitka (рекомендуется)

```bash
git clone https://github.com/Overl1te/CyberDeck.git
cd CyberDeck

python -m venv .venv
source .venv/bin/activate

python -m pip install -U pip
pip install -r requirements-build.txt
./scripts/build_arch_linux.sh
```

Результат будет в `dist-nuitka/CyberDeck.dist/` (запуск: `./dist-nuitka/CyberDeck.dist/CyberDeck`).

Если у скрипта нет права на запуск: `chmod +x scripts/build_arch_linux.sh`.

### 3) Fallback: PyInstaller

Если нужно собрать старым способом:

```bash
pip install pyinstaller
./scripts/build_arch_linux_pyinstaller.sh
```

---

## 🪟 Сборка бинарника (Windows, Nuitka)

Нужно установить **Visual Studio Build Tools** (C++ build tools + Windows SDK), иначе Nuitka не соберёт проект.

Сборка:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\\scripts\\build_windows_nuitka.ps1
```

Результат: `dist-nuitka-win\\CyberDeck.dist\\CyberDeck.exe`.

## 🎮 Использование

1. Запусти `launcher.py` (или `main.py`).
2. Открой **CyberDeck Mobile** на смартфоне.
3. Введи IP‑адрес/порт ПК и PIN‑код сопряжения.
4. Подключись и управляй ПК.

### Жесты тачпада (Web & Mobile)

| Жест | Действие |
| --- | --- |
| 👆 1 палец (движение) | Перемещение курсора |
| 👆 1 палец (тап) | ЛКМ |
| ✌️ 2 пальца (движение) | Скролл |
| ✌️ 2 пальца (тап) | ПКМ |
| 👆 удержание + тянуть | Drag & Drop |

---

## 📱 Мобильное приложение

Официальный клиент: **[CyberDeck Mobile](https://github.com/Overl1te/CyberDeck-Mobile)**.

---

## 🧱 Структура проекта

```
CyberDeck/
├── main.py                # совместимый entrypoint (экспортирует main.app)
├── launcher.py            # GUI-лаунчер (трей)
├── cyberdeck/             # серверные модули (FastAPI/WebSocket/логика)
├── static/                # статическая страница (fallback)
├── transporter.py         # однофайловая отдача при отправке файла на устройство
└── requirements.txt
```

---

## 🔌 API

### Публичные

- `POST /api/handshake` — сопряжение (PIN → token)
- `GET /api/stats` — CPU/RAM
- `POST /api/file/upload` — загрузка файла на ПК (в `~/Downloads`)
- `WS /ws/mouse` — управление мышью/клавиатурой (включая текст/хоткеи/медиа)
- `GET /video_feed` — MJPEG‑стрим экрана
- `GET /video_h264` — H.264‑стрим (требует `ffmpeg`)
- `GET /video_h265` — H.265‑стрим (требует `ffmpeg`)
- `GET /api/monitors` — список мониторов
- `GET /api/stream_stats` — диагностика стримера
- `POST /system/shutdown` / `POST /system/lock` / `POST /system/sleep`
- `POST /system/restart` / `POST /system/logoff` / `POST /system/hibernate`
- `POST /volume/{up|down|mute}`

### Локальные (только `127.0.0.1`)

- `GET /api/local/info` — IP/порт/PIN/устройства/лог‑файл
- `GET /api/local/stats` — расширенная локальная статистика
- `GET|POST /api/local/device_settings` — настройки/права устройства
- `POST /api/local/device_disconnect` — отключить устройство (WS close)
- `POST /api/local/device_delete` — удалить сессию устройства
- `POST /api/local/regenerate_code` — обновить PIN
- `POST /api/local/trigger_file` — отправить файл на устройство (через WebSocket + `transporter.py`)

---

## 🔎 Discovery и TLS

- UDP discovery остаётся доступным, дополнительно включён **mDNS** (`_cyberdeck._tcp.local`).
- Для H.264/H.265 нужен установленный `ffmpeg` в `PATH`.
- TLS (HTTPS) можно включить через лаунчер или ENV:
  - `CYBERDECK_TLS=1`
  - `CYBERDECK_TLS_CERT=...`
  - `CYBERDECK_TLS_KEY=...`

## 📷 QR и deep link

- QR режим можно переключать в лаунчере:
  - **Открывать сайт**: `http(s)://<ip>:<port>/?ip=...&port=...&code=...`
  - **Открывать приложение**: `cyberdeck://pair?...` (нужна поддержка схемы в CyberDeck Mobile)

---

## 🐛 FAQ

**В: Не подключается к серверу.**  
О: Проверь брандмауэр Windows и что ПК/смартфон в одной сети. Разреши входящие подключения для `Python`/`CyberDeck` (TCP `8080`, UDP `5555` по умолчанию).
Если TCP `8080` занят, сервер/лаунчер автоматически выберет другой свободный порт — смотри актуальный порт в лаунчере, QR или через discovery.

**В: Где посмотреть PIN‑код?**  
О: В `launcher.py` (он берёт данные через локальный `/api/local/info`). Можно также обновить PIN через `/api/local/regenerate_code`.

---

## 🤝 Вклад

PR приветствуются. Для крупных изменений — лучше сначала обсудить идею в Issues.

---

**📄 Лицензия**: GNU GPL v3 (см. `LICENSE`)  
**Автор**: Overl1te • [GitHub](https://github.com/Overl1te)
