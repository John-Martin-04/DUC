#!/usr/bin/env bash
# The whole sweep, nothing skipped. Run from harnessv2:
#   bash run_full_sweep.sh 2>&1 | tee -a ../all_runs.log
# Federated runs need gateways on the matching dataset, so the script pauses before each
# federated phase. In another terminal, start those gateways and run the replay, then press Enter.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export TF_CPP_MIN_LOG_LEVEL=2 PYTHONUNBUFFERED=1
DS_OLD="$ROOT/data/processed/cap60_noother"
DS_CTX="$ROOT/data/processed/cap60_noother_ctx"
step() { echo; echo "##### $1  $(date +%T)"; }
homes() { python -c "import json,sys; print(' '.join(json.load(open(sys.argv[1]))['homes']))" "$1/schema.json"; }
gateway_pause() {
  local ds="$1"
  echo; echo "----- Start gateways on $(basename "$ds") and replay, then press Enter -----"
  echo "  python gateway.py --dataset $ds --homes \$HOMES            (leave running)"
  echo "  python replay.py --homes \$HOMES --speed 0                 (wait until it finishes)"
  echo "  HOMES=\$(python -c \"import json; print(' '.join(json.load(open('$ds/schema.json'))['homes']))\")"
  read -r -p "Ready? " _
}

# A. Baselines, no federation, no gateways needed.
step "A1 baselines, original inputs"
(cd "$ROOT/pipelinev2" && python baselines.py --data "$DS_OLD" --setups local central finetune)
step "A2 baselines, context inputs"
(cd "$ROOT/pipelinev2" && python baselines.py --data "$DS_CTX" --setups local central finetune)

# B. Federated, context inputs.
cd "$ROOT/harnessv2"
gateway_pause "$DS_CTX"
step "B1 FedAvg context, seeds 0 to 4"
bash run_ctx_batch.sh "$DS_CTX" scenarios/all28_ctx.json scenarios/all28_ctx_s1.json \
  scenarios/all28_ctx_s2.json scenarios/all28_ctx_s3.json scenarios/all28_ctx_s4.json
step "B2 FedAvg context, 150 rounds"
bash run_ctx_batch.sh "$DS_CTX" scenarios/all28_ctx_r150.json
step "B3 FedAvg context with local fine-tuning"
bash run_ctx_batch.sh "$DS_CTX" scenarios/all28_ctx_pers.json

# C. Federated, original inputs: FedAvg and FedProx (mu 0.1).
gateway_pause "$DS_OLD"
step "C FedAvg and FedProx, original inputs"
bash run_ctx_batch.sh "$DS_OLD" scenarios/all28_fedavg.json scenarios/all28_prox0.1.json

# D. Fine-tuning learning-rate sweep, context inputs.
cd "$ROOT/pipelinev2"
step "D1 fine-tuning lr/10"
python baselines.py --data "$DS_CTX" --setups finetune --ft-div 10
step "D2 fine-tuning lr/1"
python baselines.py --data "$DS_CTX" --setups finetune --ft-div 1

# E. Context ablation: build the 5-minute and 15-minute datasets, then run the baselines.
step "E1 build 5-minute context"
DUC_CTX_MIN=5 python build_dataset.py --cap-days 60 --context --name cap60_noother_ctx5
step "E2 build 15-minute context"
DUC_CTX_MIN=15 python build_dataset.py --cap-days 60 --context --name cap60_noother_ctx15
step "E3 baselines, 5-minute context"
python baselines.py --data "$ROOT/data/processed/cap60_noother_ctx5" --setups local central finetune
step "E4 baselines, 15-minute context"
python baselines.py --data "$ROOT/data/processed/cap60_noother_ctx15" --setups local central finetune

# F. Collect every run into the index, then draw the charts.
cd "$ROOT/harnessv2"
step "F1 collect results"
python collect_results.py
step "F2 plots"
python plot_results.py
step "done: index in $ROOT/results/index.csv, charts in $ROOT/results/plots"
