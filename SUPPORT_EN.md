# Support

<p align="left">
  <a href="SUPPORT.md">Русская версия</a> •
  <a href="README_EN.md">README</a> •
  <a href="SECURITY_EN.md">Security</a>
</p>

## Where to ask

| Request type | Channel |
|---|---|
| Bug report | <https://github.com/Overl1te/CyberDeck/issues/new> |
| Feature request | <https://github.com/Overl1te/CyberDeck/issues/new> |
| General question | <https://github.com/Overl1te/CyberDeck/discussions> |

## Before opening an issue

- Check `README_EN.md`.
- Check `CONTRIBUTING_EN.md`.
- Verify the issue on the latest version.
- Search existing issues first.

## Include in your report

- OS and version;
- Python version;
- project version/commit;
- exact reproduction steps;
- expected vs actual behavior;
- logs/screenshots/traces.

## Quick self-check

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
python -m unittest discover -s tests -p "test_*.py"
```

Docker check:

```bash
docker compose -f docker-compose.tests.yml run --rm tests
```

## Security issues

For vulnerabilities, use private reporting from `SECURITY_EN.md`.
