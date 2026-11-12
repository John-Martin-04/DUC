#!/usr/bin/env bash
# Smoke test on fake data: the audit's sample run, then the dataset and both
# baselines. Takes about a minute. Outputs go to pipeline/sample_run/ only.
set -euo pipefail
cd "$(dirname "$0")"
export AUDIT_SAMPLE=1 TF_CPP_MIN_LOG_LEVEL=2
(cd ../audit && bash run_sample.sh > /dev/null)
rm -rf sample_run
python build_dataset.py --cap-days 20
python baselines.py --data sample_run/data/processed/cap20_noother --seeds 0 --epochs 3
echo
echo "Sample run finished: both baselines trained and were scored per home."
