#!/usr/bin/env bash
# All 28 homes: one replay, then FedAvg and FedProx (mu 0.1), five local epochs each.
cd "$(dirname "$0")"
export TF_CPP_MIN_LOG_LEVEL=2
pkill -f gateway.py; pkill -f recorder.py; python brokers.py stop
HOMES=$(cat ../audit/mappings/selected_homes.txt)
DATA=../data/processed/cap60_noother

cat > scenarios/all28_fedavg.json <<'JSON'
{"name": "all28_fedavg", "rounds": 60, "fraction": 1.0, "local_epochs": 5, "batch_size": 128,
 "client_lr": 0.05, "deadline_s": 600, "min_clients": 2, "max_retries": 2, "dropout_p": 0.0, "seed": 0, "mu": 0.0}
JSON
sed 's/all28_fedavg/all28_prox0.1/; s/"mu": 0.0/"mu": 0.1/' scenarios/all28_fedavg.json > scenarios/all28_prox0.1.json

date
python brokers.py start --homes $HOMES
python gateway.py --dataset $DATA --homes $HOMES & GW=$!
python recorder.py --run all28_fedavg & REC=$!
sleep 15
python replay.py --homes $HOMES --speed 0
python verify_windows.py --dataset $DATA --homes $HOMES --wait
python coordinator.py --dataset $DATA --scenario scenarios/all28_fedavg.json
python coordinator.py --dataset $DATA --scenario scenarios/all28_prox0.1.json
kill $GW $REC; wait 2>/dev/null
python brokers.py stop
date
