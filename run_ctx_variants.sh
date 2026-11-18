#!/usr/bin/env bash
# Federated runs for the context-5 and context-15 datasets, five seeds each,
# with the same settings as all28_ctx (60 rounds, FedAvg, 5 local epochs).
# Needs the datasets and their event tables already built (run_from_scratch.sh stages 2 to 11).
# Results: results/harness/all28_ctx5_s0..s4 and all28_ctx15_s0..s4, plus the index and charts.
#   bash run_ctx_variants.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROC="$ROOT/data/processed"
export TF_CPP_MIN_LOG_LEVEL=2
OUT="$ROOT/results/run_configs/ctx_variants_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"
cd "$ROOT/harnessv2"

homes_of() { python -c "import json,sys; print(' '.join(json.load(open(sys.argv[1]))['homes']))" "$1/schema.json"; }

cleanup() {
  pkill -f gateway.py 2>/dev/null || true
  pkill -f recorder.py 2>/dev/null || true
  python brokers.py stop || true
}
trap cleanup EXIT

for SET in cap60_noother_ctx5 cap60_noother_ctx15; do
  DS="$PROC/$SET"
  TAG="${SET#cap60_noother_}"          # ctx5 or ctx15
  HOMES="$(homes_of "$DS")"
  echo "=== $SET  $(date +%T)"

  python brokers.py start --homes $HOMES 2>&1 | tee "$OUT/brokers_$SET.log"
  pkill -f gateway.py 2>/dev/null || true
  python gateway.py --dataset "$DS" --homes $HOMES > "$OUT/gateways_$SET.log" 2>&1 &
  sleep 15
  python replay.py --homes $HOMES --speed 0 --max-rate ${MAX_RATE:-10000} 2>&1 | tee "$OUT/replay_$SET.log"
  python verify_windows.py --dataset "$DS" --homes $HOMES --wait 2>&1 | tee "$OUT/verify_$SET.log"

  for SEED in 0 1 2 3 4; do
    NAME="all28_${TAG}_s${SEED}"
    SC="scenarios/$NAME.json"
    python - "scenarios/all28_ctx.json" "$SC" "$NAME" "$SEED" <<'PY'
import json, sys
src, dst, name, seed = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
d = json.load(open(src))
d["name"], d["seed"] = name, seed
json.dump(d, open(dst, "w"), indent=1)
PY
    echo "--- $NAME  $(date +%T)"
    python recorder.py --run "$NAME" > "$OUT/recorder_$NAME.log" 2>&1 &
    REC=$!
    python coordinator.py --dataset "$DS" --scenario "$SC" 2>&1 | tee "$OUT/coord_$NAME.log"
    kill "$REC" 2>/dev/null || true
    wait "$REC" 2>/dev/null || true
  done

  pkill -f gateway.py 2>/dev/null || true
  python brokers.py stop || true
done

python summarize_runs.py
python collect_results.py
python plot_results.py
echo "Done. Logs: $OUT"
