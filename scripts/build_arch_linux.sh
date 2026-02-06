#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install -U pip
pip install -r requirements.txt

python -m nuitka launcher.py \
  --standalone \
  --enable-plugin=tk-inter \
  --include-data-dir=static=static \
  --include-data-file=icon.png=icon.png \
  --include-data-file=icon.ico=icon.ico \
  --include-package=customtkinter \
  --include-package-data=customtkinter \
  --output-dir=dist-nuitka \
  --output-filename=CyberDeck

echo
echo "Built: $REPO_ROOT/dist-nuitka/CyberDeck.dist/CyberDeck"
