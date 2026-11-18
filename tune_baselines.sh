#!/usr/bin/env bash
# Validation grid for the three baselines on the default context dataset.
# Learning rate 1e-3 or 3e-4, batch size 64 or 128. Each setting is scored on validation
# (results.csv, val_macro_f1). The test columns are written too but are not used for choosing.
# Needs data/processed/cap60_noother_ctx (run_from_scratch.sh stages 6 to 11).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/pipelinev2"
DS="../data/processed/cap60_noother_ctx"
for LR in 0.001 0.0003; do
  for BS in 64 128; do
    echo "=== lr $LR, batch $BS  $(date +%T)"
    python baselines.py --data "$DS" --setups local central finetune --lr "$LR" --batch-size "$BS"
  done
done
echo "Done. Results: results/baselines/cap60_noother_ctx_lr*_bs*/results.csv"
