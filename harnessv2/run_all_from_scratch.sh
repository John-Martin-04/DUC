#!/usr/bin/env bash
# Rebuilds every result in the deck from an empty results folder.
# Assumes: data/processed/ and data/gateways/ exist, and the gateways are already
# online in another terminal (started with run_all28.sh). Runs stop on the first error.
#   bash run_all_from_scratch.sh 2>&1 | tee ../all_runs.log
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export TF_CPP_MIN_LOG_LEVEL=2 PYTHONUNBUFFERED=1
DS_OLD="$ROOT/data/processed/cap60_noother"
DS_CTX="$ROOT/data/processed/cap60_noother_ctx"

step() { echo; echo "##### $1  $(date +%T)"; }

# A. Baselines (no federation): original inputs and context inputs, five seeds each.
step "A1 baselines, original inputs"
(cd "$ROOT/pipelinev2" && python baselines.py --data "$DS_OLD" --setups local central finetune)
step "A2 baselines, context inputs"
(cd "$ROOT/pipelinev2" && python baselines.py --data "$DS_CTX" --setups local central finetune)

# B. Federated, context inputs: seed 0, seeds 1-4, then 150 rounds.
cd "$ROOT/harnessv2"
step "B1 FedAvg context, five seeds"
bash run_ctx_batch.sh "$DS_CTX" scenarios/all28_ctx.json scenarios/all28_ctx_s1.json \
  scenarios/all28_ctx_s2.json scenarios/all28_ctx_s3.json scenarios/all28_ctx_s4.json
step "B2 FedAvg context, 150 rounds"
bash run_ctx_batch.sh "$DS_CTX" scenarios/all28_ctx_r150.json

# C. Federated, original inputs: FedAvg and FedProx (mu 0.1), as on the slides.
step "C FedAvg and FedProx, original inputs"
bash run_ctx_batch.sh "$DS_OLD" scenarios/all28_fedavg.json scenarios/all28_prox0.1.json

# D. Fine-tuning learning-rate sweep, context inputs.
step "D1 fine-tuning lr/10"
(cd "$ROOT/pipelinev2" && python baselines.py --data "$DS_CTX" --setups finetune --ft-div 10)
step "D2 fine-tuning lr/1"
(cd "$ROOT/pipelinev2" && python baselines.py --data "$DS_CTX" --setups finetune --ft-div 1)

# E. Context ablation: 5-minute and 15-minute features alone.
step "E1 build 5-minute context"
(cd "$ROOT/pipelinev2" && DUC_CTX_MIN=5 python build_dataset.py --cap-days 60 --context --name cap60_noother_ctx5)
step "E2 build 15-minute context"
(cd "$ROOT/pipelinev2" && DUC_CTX_MIN=15 python build_dataset.py --cap-days 60 --context --name cap60_noother_ctx15)
step "E3 baselines, 5-minute context"
(cd "$ROOT/pipelinev2" && python baselines.py --data "$ROOT/data/processed/cap60_noother_ctx5" --setups local central finetune)
step "E4 baselines, 15-minute context"
(cd "$ROOT/pipelinev2" && python baselines.py --data "$ROOT/data/processed/cap60_noother_ctx15" --setups local central finetune)

step "done: all results in $ROOT/results"
