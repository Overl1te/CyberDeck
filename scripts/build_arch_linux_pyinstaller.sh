#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install -U pip
pip install -r requirements.txt

pyinstaller --clean --noconfirm CyberDeck.spec

echo
echo "Built: $REPO_ROOT/dist/CyberDeck/CyberDeck"
