#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYINSTALLER_SCRIPT="${SCRIPT_DIR}/build_arch_linux_pyinstaller.sh"
LEGACY_SCRIPT="${REPO_ROOT}/build_arch_linux.sh"

if [[ -f "${PYINSTALLER_SCRIPT}" ]]; then
  exec bash "${PYINSTALLER_SCRIPT}" "$@"
fi

if [[ -x "${LEGACY_SCRIPT}" ]]; then
  exec "${LEGACY_SCRIPT}" "$@"
fi

if [[ -f "${LEGACY_SCRIPT}" ]]; then
  exec bash "${LEGACY_SCRIPT}" "$@"
fi

echo "[ERR] Linux build script not found: ${PYINSTALLER_SCRIPT}" >&2
exit 1
