# Поддержка

<p align="left">
  <a href="SUPPORT_EN.md">English version</a> •
  <a href="README.md">README</a> •
  <a href="SECURITY.md">Security</a>
</p>

## Куда писать

| Запрос | Канал |
|---|---|
| Баг-репорт | <https://github.com/Overl1te/CyberDeck/issues/new> |
| Feature request | <https://github.com/Overl1te/CyberDeck/issues/new> |
| Общий вопрос | <https://github.com/Overl1te/CyberDeck/discussions> |

## Перед созданием issue

- Проверьте `README.md`.
- Проверьте `CONTRIBUTING.md`.
- Убедитесь, что проблема воспроизводится на актуальной версии.
- Поискать дубликаты в Issues.

## Что приложить

- ОС и версия;
- версия Python;
- версия проекта/коммит;
- точные шаги воспроизведения;
- ожидаемое и фактическое поведение;
- логи/скриншоты/трейсы.

## Быстрая самопроверка

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
# при необходимости desktop-ввода:
pip install -r requirements-desktop-input.txt
python -m unittest discover -s tests -p "test_*.py"
```

Docker-проверка:

```bash
docker compose -f docker-compose.tests.yml build
docker compose -f docker-compose.tests.yml run --rm tests
```

## Вопросы безопасности

Для уязвимостей используйте приватный канал из `SECURITY.md`.
