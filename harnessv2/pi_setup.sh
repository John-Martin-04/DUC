#!/usr/bin/env bash
# One-time setup on the Raspberry Pi (64-bit Raspberry Pi OS). Run from DUC/harnessv2.
set -euo pipefail
cd "$(dirname "$0")"
if [ "$(uname -m)" != "aarch64" ] && [ "$(uname -m)" != "x86_64" ]; then
  echo "This needs a 64-bit system (uname -m shows $(uname -m)). Install 64-bit Raspberry Pi OS."; exit 1
fi
sudo apt-get update
sudo apt-get install -y mosquitto
sudo systemctl disable --now mosquitto 2>/dev/null || true   # we start our own brokers
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv venv -p 3.11 ../.venv
VIRTUAL_ENV=../.venv uv pip install -r requirements-pi.txt
../.venv/bin/python -c "import tensorflow as tf, paho.mqtt; print('TensorFlow', tf.__version__, 'ready')"
echo "Setup finished. Start the home with: bash pi_run.sh"
