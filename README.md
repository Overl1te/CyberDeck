<p align="center">
  <img src="icon-qr-code.png" width="400" height="400" />
</p>

<h1 align="center">CyberDeck Control — удаленное управление ПК</h1>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License"></a>
  <a href="https://github.com/Overl1te/CyberDeck-Mobile"><img src="https://img.shields.io/badge/Mobile-CyberDeck--Mobile-00A7E1" alt="Mobile"></a>
  <a href="README_EN.md"><img src="https://img.shields.io/badge/lang-English-1f6feb" alt="English"></a>
</p>


<p align="center">
  Управление компьютером со смартфона в локальной сети: подключение по PIN/QR, ввод, видеопоток, передача файлов и разрешений для устройств.
</p>

<p align="center">
  <a href="#функции-приложения">Функции</a> •
  <a href="#сценарии-использования">Сценарий работы</a> •
  <a href="#базовые-жесты">Жесты</a> •
  <a href="#faq">FAQ</a>
</p>

<p align="center">
  <img src="https://repo-inspector.vercel.app/api?owner=Overl1te&repo=CyberDeck&kind=quality&format=svg&theme=midnight&locale=ru&card_width=760&animate=true&animation=all&duration=1400&cache_seconds=21601" alt="CyberDeck repository stats card" />
  
</p>
<p align="center">
  <img src="https://repo-inspector.vercel.app/api?owner=Overl1te&repo=CyberDeck&kind=repo&format=svg&theme=midnight&locale=ru&card_width=760&animate=true&animation=all&duration=1400&cache_seconds=21600&langs_count=4" alt="CyberDeck quality card" />
</p>

---

## ✨ Функции приложения

- Подключение устройства по PIN или QR.
- Удаленное управление мышью, клавиатурой и медиа-клавишами.
- Видеопоток экрана (MJPEG / H.264 / H.265 в зависимости от среды).
- Передача файлов между телефоном и ПК в обе стороны.
- Системные действия: питание/громкость.
- Лаунчер с локальным мониторингом статуса, устройств и QR.
- Раздельные права доступа для каждого устройства.

### Права устройства

- `perm_mouse` — управление мышью.
- `perm_keyboard` — управление клавиатурой/вводом.
- `perm_stream` — доступ к видеопотоку.
- `perm_upload` — загрузка файлов на ПК.
- `perm_file_send` — отправка файлов с ПК на устройство.
- `perm_power` — системные действия (питание/громкость).

---

## 📱 Сценарий использования

1. Запусти CyberDeck на ПК.
2. Открой мобильный клиент: <https://github.com/Overl1te/CyberDeck-Mobile>.
3. Подключись по QR или введи IP/порт/PIN.
4. Выбери устройство и управляй ПК.

---

## 🖐 Базовые жесты

| Жест | Действие |
|---|---|
| 1 палец (движение) | Перемещение курсора |
| 1 палец (тап) | ЛКМ |
| 2 пальца (движение) | Скролл |
| 2 пальца (тап) | ПКМ |
| Удержание + движение | Drag & Drop |

---

## 🧩 Платформы

- Windows / Linux / macOS.
- Доступные видео-кодеки и бэкенды зависят от окружения ОС.

---

## 📚 Техническая документация

В `README` оставлены только функции приложения и пользовательский сценарий.

Вся техническая часть перенесена в `CONTRIBUTING.md`:

- актуальная структура модулей: `cyberdeck/api`, `cyberdeck/video`, `cyberdeck/ws`, `cyberdeck/launcher`, `cyberdeck/input`, `cyberdeck/platform`;
- разделение зависимостей: `requirements-core.txt` и `requirements-desktop-input.txt`;

- установка из исходников;
- запуск в разных режимах;
- API и эндпоинты;
- тестирование;
- сборка и упаковка.

Практические гайды:

- Docker runtime: `docs/DOCKER.md`
- Диагностика стрима/аудио/паринга: `docs/STREAMING_TROUBLESHOOTING.md`

---

## ❓ FAQ

**В: Устройство не подключается.**  
О: Проверь, что ПК и смартфон в одной сети, а IP/порт/PIN актуальны.

**В: Можно ли ограничить доступ конкретному устройству?**  
О: Да, для каждого устройства задаются отдельные права (`perm_*`).

**В: Почему на разных ОС разное качество/тип видеопотока?**  
О: Путь стрима зависит от доступных системных бэкендов и кодеков.

---

**Лицензия:** GNU GPLv3 (`LICENSE`)  
**Автор:** Overl1te — <https://github.com/Overl1te>

