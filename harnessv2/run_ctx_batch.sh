#!/usr/bin/env bash
# Runs a list of federated scenarios one after another against the gateways
# that are already online (start them first with your run_all28.sh setup).
#   bash run_ctx_batch.sh ../data/processed/cap60_noother_ctx scenarios/all28_ctx_s1.json [more...]
# Each run writes results/harness/<name>/ and is resumable: re-run with --resume
# by hand if a run stops, since the batch stops on the first failure.
set -euo pipefail
cd "$(dirname "$0")"
export TF_CPP_MIN_LOG_LEVEL=2
DATA="$1"; shift
for SC in "$@"; do
  RUN=$(python -c "import json,sys,pathlib; p=pathlib.Path(sys.argv[1]); print(json.loads(p.read_text()).get('name', p.stem))" "$SC")
  echo "=== $RUN  $(date +%T)"
  python coordinator.py --dataset "$DATA" --scenario "$SC" 2>&1 | tee "run_${RUN}.log"
done
python summarize_runs.py "$@"
