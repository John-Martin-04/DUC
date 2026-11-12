#!/usr/bin/env bash
# Smoke test on fake data, about two minutes: brokers, three gateways, a full
# replay, the identical-windows check, then federated rounds with traffic recorded.
set -euo pipefail
cd "$(dirname "$0")"
export AUDIT_SAMPLE=1 TF_CPP_MIN_LOG_LEVEL=2
HOMES="csh901 home_a home_b"
DATA=../pipeline/sample_run/data/processed/full_noother

(cd ../audit && bash run_sample.sh > /dev/null)
(cd ../pipeline && python build_dataset.py > /dev/null)
rm -rf sample_run
python brokers.py start --homes $HOMES
python gateway.py --dataset $DATA --homes $HOMES & GW=$!
python recorder.py --run sample & REC=$!
trap 'kill $GW $REC 2>/dev/null || true; wait 2>/dev/null || true; python brokers.py stop' EXIT

python replay.py --homes $HOMES --speed 0
python verify_windows.py --dataset $DATA --homes $HOMES --wait 120
python coordinator.py --dataset $DATA --scenario scenarios/sample.json
kill $REC; wait $REC 2>/dev/null || true
echo
cat sample_run/results/harness/sample/traffic_summary.md | sed -n '5,12p'
echo
echo "Sample run finished: windows identical, federated rounds completed."
