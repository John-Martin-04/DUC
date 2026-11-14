#!/usr/bin/env bash
# Laptop side of a run with a home on a Raspberry Pi: optional local homes,
# the recorder and the coordinator. The Pi must already be running pi_run.sh.
#   bash server_run.sh <dataset folder> <scenario.json> [local homes...]
set -euo pipefail
cd "$(dirname "$0")"
DATA="$1"; SCENARIO="$2"; shift 2
LOCAL="$*"
export TF_CPP_MIN_LOG_LEVEL=2
RUN=$(python -c "import json,sys,pathlib; p=pathlib.Path(sys.argv[1]); print(json.loads(p.read_text()).get('name', p.stem))" "$SCENARIO")
PIDS=""
trap 'kill $PIDS 2>/dev/null || true; wait 2>/dev/null || true; [ -n "$LOCAL" ] && python brokers.py stop' EXIT

if [ -n "$LOCAL" ]; then
  python brokers.py start --only home --homes $LOCAL
  python gateway.py --dataset "$DATA" --homes $LOCAL & PIDS="$PIDS $!"
  python replay.py --homes $LOCAL --speed 0
  python verify_windows.py --dataset "$DATA" --homes $LOCAL --wait 3600
fi
python recorder.py --run "$RUN" & REC=$!; PIDS="$PIDS $REC"
python coordinator.py --dataset "$DATA" --scenario "$SCENARIO"
kill $REC; wait $REC 2>/dev/null || true
cat "$(python -c "import hconfig as H; print(H.RESULTS_DIR)")/$RUN/traffic_summary.md"
