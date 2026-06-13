#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VENV_DIR="${MAHANAI_VENV:-$ROOT_DIR/.mahanai-venv}"
PYTHON_VERSION="${MAHANAI_PYTHON_VERSION:-3.12}"

BLUE=''
GREEN=''
YELLOW=''
BOLD=''
RESET=''

if [ -t 1 ]; then
  BLUE=$(printf '\033[36m')
  GREEN=$(printf '\033[32m')
  YELLOW=$(printf '\033[33m')
  BOLD=$(printf '\033[1m')
  RESET=$(printf '\033[0m')
fi

banner() {
  printf '%s\n' "========================================"
  printf '%s\n' "        MahanAI Get Started"
  printf '%s\n' "========================================"
}

say() {
  printf '%s%s%s\n' "$1" "$2" "$RESET"
}

step() {
  printf '%s[%s]%s %s\n' "$BOLD" "$1" "$RESET" "$2"
}

banner
say "$BLUE" "Bootstrapping a local MahanAI environment in: $VENV_DIR"

if command -v uv >/dev/null 2>&1; then
  step "1/4" "uv already installed"
else
  step "1/4" "Installing uv"
  if ! command -v curl >/dev/null 2>&1; then
    say "$YELLOW" "curl is required to install uv."
    exit 1
  fi
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
  export PATH
fi

step "2/4" "Installing Python $PYTHON_VERSION through uv"
uv python install "$PYTHON_VERSION"

if [ -x "$VENV_DIR/bin/python" ]; then
  step "3/4" "Reusing the existing virtual environment and installing mahanai"
else
  step "3/4" "Creating a fresh virtual environment and installing mahanai"
fi
if [ ! -x "$VENV_DIR/bin/python" ]; then
  uv venv --python "$PYTHON_VERSION" "$VENV_DIR"
fi
uv pip install --python "$VENV_DIR/bin/python" mahanai

step "4/4" "Starting MahanAI"
say "$GREEN" "Ready. Launching MahanAI now."
exec "$VENV_DIR/bin/mahanai" "$@"
