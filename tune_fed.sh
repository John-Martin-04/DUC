#!/usr/bin/env bash
# Validation grid for FedAvg on the default context dataset.
# Settings: client learning rate 0.01 or 0.05, local epochs 1 or 5, FedProx mu 0 or 0.01.
# Five seeds each. Scores are written per round (val_macro_f1); selection uses validation only.
# Needs data/processed/cap60_noother_ctx (run_from_scratch.sh stages 6 to 11).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DS="$ROOT/data/processed/cap60_noother_ctx"
export TF_CPP_MIN_LOG_LEVEL=2
OUT="$ROOT/results/run_configs/tune_fed_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"
cd "$ROOT/harnessv2"

homes_of() { python -c "import json,sys; print(' '.join(json.load(open(sys.argv[1]))['homes']))" "$1/schema.json"; }
cleanup() {
  pkill -f gateway.py 2>/dev/null || true
  pkill -f recorder.py 2>/dev/null || true
  python brokers.py stop || true
}
trap cleanup EXIT

HOMES="$(homes_of "$DS")"
python brokers.py start --homes $HOMES 2>&1 | tee "$OUT/brokers.log"
pkill -f gateway.py 2>/dev/null || true
python gateway.py --dataset "$DS" --homes $HOMES > "$OUT/gateways.log" 2>&1 &
sleep 15
python replay.py --homes $HOMES --speed 0 --max-rate "${MAX_RATE:-10000}" 2>&1 | tee "$OUT/replay.log"
python verify_windows.py --dataset "$DS" --homes $HOMES --wait 2>&1 | tee "$OUT/verify.log"
if grep -q FAIL "$OUT/verify.log"; then echo "verification failed: see $OUT/verify.log"; exit 1; fi

for LR in 0.01 0.05; do
  for EP in 1 5; do
    for MU in 0.0 0.01; do
      for SEED in 0 1 2 3 4; do
        NAME="tune_fed_lr${LR}_ep${EP}_mu${MU}_s${SEED}"
        SC="scenarios/$NAME.json"
        python - "scenarios/all28_ctx.json" "$SC" "$NAME" "$SEED" "$LR" "$EP" "$MU" <<'PY'
import json, sys
src, dst, name, seed, lr, ep, mu = sys.argv[1:8]
d = json.load(open(src))
d.update(name=name, seed=int(seed), client_lr=float(lr), local_epochs=int(ep), mu=float(mu), personalise_epochs=0)
json.dump(d, open(dst, "w"), indent=1)
PY
        echo "--- $NAME  $(date +%T)"
        python recorder.py --run "$NAME" > "$OUT/recorder_$NAME.log" 2>&1 &
        REC=$!
        python coordinator.py --dataset "$DS" --scenario "$SC" 2>&1 | tee "$OUT/coord_$NAME.log"
        kill "$REC" 2>/dev/null || true
        wait "$REC" 2>/dev/null || true
      done
    done
  done
done

python select_best.py
echo "Done. Logs: $OUT"
