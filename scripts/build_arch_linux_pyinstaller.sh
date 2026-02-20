#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f "requirements-build.txt" ]]; then
  echo "[ERR] requirements-build.txt not found in repo root" >&2
  exit 1
fi

if [[ $DRY_RUN -eq 1 ]]; then
  echo "[DRY-RUN] Linux build command:"
  echo "pyinstaller --clean --noconfirm CyberDeck.spec"
  exit 0
fi

python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install -U pip
pip install -r requirements-build.txt

pyinstaller --clean --noconfirm CyberDeck.spec

echo
if [[ -f "$REPO_ROOT/dist/CyberDeck" ]]; then
  echo "Built: $REPO_ROOT/dist/CyberDeck"
elif [[ -f "$REPO_ROOT/dist/CyberDeck/CyberDeck" ]]; then
  echo "Built: $REPO_ROOT/dist/CyberDeck/CyberDeck"
else
  echo "[WARN] Build finished, but expected output was not detected in dist/" >&2
fi
