#!/usr/bin/env bash
set -euo pipefail

APP_NAME="CyberDeck"
ENTRY="launcher.py"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${ROOT_DIR}/dist-nuitka"
OUT_DIR="${DIST_DIR}/${APP_NAME}"
VERSION="1.3.1"
TARBALL="${ROOT_DIR}/cyberdeck-${VERSION}.tar.gz"

ICON_PNG="${ROOT_DIR}/icon.png"
ICON_ICO="${ROOT_DIR}/icon.ico"
STATIC_DIR="${ROOT_DIR}/static"

echo "[1/6] Проверка файлов..."
[[ -f "${ROOT_DIR}/${ENTRY}" ]] || { echo "Нет ${ENTRY}"; exit 1; }
[[ -f "${ICON_PNG}" ]] || { echo "Нет icon.png"; exit 1; }
[[ -d "${STATIC_DIR}" ]] || { echo "Нет папки static/"; exit 1; }

echo "[2/6] Чистка старых сборок..."
rm -rf "${DIST_DIR}"
mkdir -p "${DIST_DIR}"

echo "[3/6] Сборка Nuitka..."
python -m nuitka "${ROOT_DIR}/${ENTRY}" \
  --standalone \
  --enable-plugin=tk-inter \
  --include-data-dir="${STATIC_DIR}=static" \
  --include-data-file="${ICON_PNG}=icon.png" \
  --include-data-file="${ICON_ICO}=icon.ico" \
  --include-package=customtkinter \
  --include-package-data=customtkinter \
  --output-dir="${DIST_DIR}" \
  --output-filename="${APP_NAME}"

echo "[4/6] Приводим к одной папке (всё внутри ${OUT_DIR}/)..."
BIN_PATH="${DIST_DIR}/${APP_NAME}"
DEFAULT_DIST="${DIST_DIR}/launcher.dist"

[[ -f "${BIN_PATH}" ]] || { echo "Не найден бинарник: ${BIN_PATH}"; exit 1; }
[[ -d "${DEFAULT_DIST}" ]] || { echo "Не найдена папка Nuitka: ${DEFAULT_DIST}"; exit 1; }

rm -rf "${OUT_DIR}"
mkdir -p "${OUT_DIR}"

# Переносим бинарь внутрь папки
mv "${BIN_PATH}" "${OUT_DIR}/${APP_NAME}"

# Переносим содержимое .dist внутрь папки (как ты и хотел)
mv "${DEFAULT_DIST}/"* "${OUT_DIR}/"
rmdir "${DEFAULT_DIST}" || true

# На всякий случай докладываем иконку рядом
cp -f "${ICON_PNG}" "${OUT_DIR}/icon.png"

echo "[5/6] Делаем tar.gz для PKGBUILD..."
rm -f "${TARBALL}"
tar -czf "${TARBALL}" -C "${DIST_DIR}" "${APP_NAME}"
echo "Создан: ${TARBALL}"

echo "[6/6] Готово."
echo "Папка сборки: ${OUT_DIR}"
echo "Запуск: ${OUT_DIR}/${APP_NAME}"
