#!/usr/bin/env bash
# Run one simulated home on this device: brokers, gateway, sensor replay, window check.
# Then the gateway stays online and waits for the coordinator on the laptop.
#   bash pi_run.sh            replay as fast as possible
#   bash pi_run.sh 3600       replay at one hour of data per second
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./duc.env; set +a
[ -f ../.venv/bin/activate ] && . ../.venv/bin/activate
export TF_CPP_MIN_LOG_LEVEL=2
SPEED="${1:-0}"

python brokers.py start --homes ${PI_ALL_HOMES//,/ }
python gateway.py --dataset "$PI_DATASET" --homes "$PI_HOME" & GW=$!
trap 'kill $GW 2>/dev/null || true; wait $GW 2>/dev/null || true; python brokers.py stop' EXIT

python replay.py --homes "$PI_HOME" --speed "$SPEED"
python verify_windows.py --dataset "$PI_DATASET" --homes "$PI_HOME" --wait 600
echo
echo "Home $PI_HOME is online at $(hostname -I | awk '{print $1}'). Start the coordinator on the laptop."
echo "Press Ctrl+C to stop this home."
wait $GW
