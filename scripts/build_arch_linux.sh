#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LEGACY_SCRIPT="${REPO_ROOT}/build_arch_linux.sh"

if [[ -x "${LEGACY_SCRIPT}" ]]; then
  exec "${LEGACY_SCRIPT}" "$@"
fi

if [[ -f "${LEGACY_SCRIPT}" ]]; then
  exec bash "${LEGACY_SCRIPT}" "$@"
fi

echo "[ERR] build_arch_linux.sh was not found in repository root: ${LEGACY_SCRIPT}" >&2
exit 1
