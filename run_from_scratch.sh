#!/usr/bin/env bash
# Full pipeline from the raw CASAS files to every table and chart in the report.
# Put this file at the repository root (DUC/run_from_scratch.sh) and run it from there:
#   bash run_from_scratch.sh
#
# On screen: an overall progress bar, the current stage, its elapsed time and its latest output line.
# On disk: results/run_configs/<timestamp>/ holds
#   config.txt     git commit, software versions, every settings file, every scenario used,
#                  dataset schemas and the stage table with timings and exit status
#   NN_<stage>.log the full output of each stage
#   stages.log     one line per stage as it finishes
#
# Stages: preflight, audit, datasets, baselines, fine-tune sweep, federated runs, results.
#
# To restart after an interruption and skip the stages that already finished:
#   RESUME_DIR=results/run_configs/<old timestamp> bash run_from_scratch.sh
set -euo pipefail
trap 'echo "ERROR: stopped at line $LINENO: $BASH_COMMAND" >&2' ERR

ROOT="$(cd "$(dirname "$0")" && pwd)"
export TF_CPP_MIN_LOG_LEVEL=2 PYTHONUNBUFFERED=1
PROC="$ROOT/data/processed"
STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$ROOT/results/run_configs/$STAMP"
CFG="$RUN_DIR/config.txt"
STAGES_LOG="$RUN_DIR/stages.log"
TOTAL=35          # number of stages; keep in step with the run_stage calls below
DONE=0
T0=$(date +%s)
mkdir -p "$RUN_DIR"
: > "$STAGES_LOG"

# ---------------------------------------------------------------- helpers
bar() {  # bar <done> <total>: 30-character bar with percentage
  local d=$1 t=$2 w=30
  local n=$(( d * w / t )) pct=$(( d * 100 / t ))
  printf "[%s%s] %3d%%" "$(printf '%*s' "$n" '' | tr ' ' '#')" "$(printf '%*s' $((w - n)) '' | tr ' ' '-')" "$pct"
}

homes_of() { python -c "import json,sys; print(' '.join(json.load(open(sys.argv[1]))['homes']))" "$1/schema.json"; }

run_stage() {  # run_stage "label" "shell command"
  local label="$1" cmd="$2"
  if [ -n "${RESUME_DIR:-}" ] && grep -qF "$label | ok |" "$RESUME_DIR/stages.log" 2>/dev/null; then
    DONE=$((DONE + 1))
    printf "\r\033[K%s  %2d/%d  %-28s skipped (done in %s)\n" "$(bar "$DONE" "$TOTAL")" "$DONE" "$TOTAL" "${label:0:28}" "$(basename "$RESUME_DIR")"
    printf "%s | skipped | 0s | %s\n" "$label" "$cmd" >> "$STAGES_LOG"
    return 0
  fi
  local slug; slug="$(echo "$label" | tr -c 'A-Za-z0-9' '_' | cut -c1-50)"
  local log; log="$RUN_DIR/$(printf '%02d' $((DONE + 1)))_${slug}.log"
  local start; start=$(date +%s)
  bash -c "$cmd" > "$log" 2>&1 &
  local pid=$! status=0
  while kill -0 "$pid" 2>/dev/null; do
    local last=""; last="$(tail -n 1 "$log" 2>/dev/null | tr -d '\r' | cut -c1-50)" || true
    printf "\r\033[K%s  %2d/%d  %-28s %5ds  %s" "$(bar "$DONE" "$TOTAL")" "$((DONE + 1))" "$TOTAL" \
      "${label:0:28}" "$(( $(date +%s) - start ))" "$last"
    sleep 1
  done
  wait "$pid" || status=$?
  local secs=$(( $(date +%s) - start ))
  DONE=$((DONE + 1))
  local state="ok"; [ "$status" -eq 0 ] || state="FAILED (exit $status)"
  printf "\r\033[K%s  %2d/%d  %-28s %s in %ds\n" "$(bar "$DONE" "$TOTAL")" "$DONE" "$TOTAL" "${label:0:28}" "$state" "$secs"
  printf "%s | %s | %ds | %s\n" "$label" "$state" "$secs" "$cmd" >> "$STAGES_LOG"
  if [ "$status" -ne 0 ]; then
    echo "Stage failed. Last lines of $log:"; tail -n 25 "$log"
    write_config_end
    exit "$status"
  fi
}

# The federated scenarios need a gateway and recorder alongside the coordinator.
fed_scenario() {  # fed_scenario <dataset dir> <scenario json>
  local ds="$1" sc="$2"
  local run; run=$(python -c "import json,sys,pathlib; p=pathlib.Path(sys.argv[1]); print(json.loads(p.read_text()).get('name', p.stem))" "$sc")
  run_stage "fed $run" "cd \"$ROOT/harnessv2\"; python recorder.py --run $run > \"$RUN_DIR/recorder_$run.log\" 2>&1 & REC=\$!; python coordinator.py --dataset \"$ds\" --scenario \"$sc\"; RC=\$?; kill \$REC 2>/dev/null; wait \$REC 2>/dev/null; exit \$RC"
}

GW_PIDS=()
cleanup() {
  for p in "${GW_PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done
  pkill -f "recorder.py" 2>/dev/null || true
  if [ "${BROKERS_UP:-0}" = 1 ]; then (cd "$ROOT/harnessv2" && python brokers.py stop) || true; fi
}
trap cleanup EXIT

section() {  # section <title>: append a heading to config.txt
  { echo; echo "== $1"; } >> "$CFG"
}
show_file() {  # show_file <path relative to repo>
  section "$1"
  if [ -f "$ROOT/$1" ]; then cat "$ROOT/$1" >> "$CFG"; else echo "(missing)" >> "$CFG"; fi
}

write_config_start() {
  {
    echo "DUC: full run configuration"
    echo "Started: $(date '+%Y-%m-%d %H:%M:%S %Z')   host: $(hostname)   $(uname -sr)"
    echo "Repository: $ROOT"
    echo "Git commit: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo 'not a git checkout')"
    echo "Uncommitted changes:"
    git -C "$ROOT" status --short 2>/dev/null | sed 's/^/  /' || true
  } > "$CFG"
  section "Software versions"
  python - >> "$CFG" <<'PY'
import sys
from importlib.metadata import version, PackageNotFoundError
print("python", sys.version.split()[0])
for pkg in ["numpy", "pandas", "pyarrow", "tensorflow", "tensorflow-federated", "paho-mqtt", "matplotlib"]:
    try:
        print(pkg, version(pkg))
    except PackageNotFoundError:
        print(pkg, "not installed")
PY
  show_file "audit/config.py"
  show_file "pipelinev2/settings.py"
  show_file "harnessv2/hconfig.py"
  section "harnessv2/duc.env (secrets removed)"
  grep -v -i -E 'secret|pass|key|token' "$ROOT/harnessv2/duc.env" >> "$CFG" 2>/dev/null || echo "(missing)" >> "$CFG"
  section "Scenarios used in this run"
  for f in all28_ctx all28_ctx_s1 all28_ctx_s2 all28_ctx_s3 all28_ctx_s4 all28_ctx_r150 all28_ctx_pers all28_fedavg all28_prox0.1; do
    echo "-- harnessv2/scenarios/$f.json" >> "$CFG"
    cat "$ROOT/harnessv2/scenarios/$f.json" >> "$CFG" 2>/dev/null || echo "(missing)" >> "$CFG"
    echo >> "$CFG"
  done
  section "Build settings per dataset (environment variable DUC_CTX_MIN where set)"
  cat >> "$CFG" <<'TXT'
cap60_noother       --cap-days 60                       (no context)
cap60_noother_ctx   --cap-days 60 --context              (5 and 15 minutes, DUC_CTX_MIN default 5,15)
cap60_other         --cap-days 60 --keep-other           ('Other' class kept)
full_noother        no cap                               (full volume, RQ2)
cap60_noother_ctx5  --cap-days 60 --context, DUC_CTX_MIN=5
cap60_noother_ctx15 --cap-days 60 --context, DUC_CTX_MIN=15
TXT
  section "Stages (timings are added as each stage finishes)"
}

write_config_end() {
  {
    section "Stage table"
    echo "label | status | seconds | command"
    cat "$STAGES_LOG"
    echo
    echo "Total time: $(( $(date +%s) - T0 ))s   stages done: $DONE of $TOTAL"
    section "Dataset schemas"
    for ds in cap60_noother cap60_noother_ctx cap60_other full_noother cap60_noother_ctx5 cap60_noother_ctx15; do
      echo "-- data/processed/$ds/schema.json"
      cat "$PROC/$ds/schema.json" 2>/dev/null || echo "(not built)"
      echo
    done
    section "Result summaries"
    echo "-- results/index.csv"; cat "$ROOT/results/index.csv" 2>/dev/null || echo "(not written)"
  } >> "$CFG"
}

# ---------------------------------------------------------------- 0. preflight (checks before anything runs)
[ -d "$ROOT/.venv" ] || { echo "No .venv at $ROOT. Create it first (see audit/README.md)."; exit 1; }
source "$ROOT/.venv/bin/activate"
[ -f "$ROOT/harnessv2/duc.env" ] || { echo "Missing harnessv2/duc.env (ports, not in Git)."; exit 1; }
[ -n "$(ls -A "$ROOT/audit/data/raw/uci" 2>/dev/null)" ] || { echo "Missing raw UCI files in audit/data/raw/uci."; exit 1; }
for f in harnessv2/collect_results.py harnessv2/plot_results.py harnessv2/add_personalisation.py \
         harnessv2/scenarios/all28_ctx_pers.json harnessv2/scenarios/all28_fedavg.json \
         harnessv2/scenarios/all28_prox0.1.json harnessv2/scenarios/all28_ctx_r150.json; do
  [ -f "$ROOT/$f" ] || { echo "Missing $f. Copy it from the scratch folder or pull the latest commit."; exit 1; }
done

write_config_start
echo "Run folder: $RUN_DIR"
echo "Config:     $CFG"
echo

# ---------------------------------------------------------------- 1. preflight stage: patch and imports
run_stage "preflight: patch and imports" "cd \"$ROOT/harnessv2\" && (grep -q personalise coordinator.py || python add_personalisation.py) && python -c 'import tensorflow, tensorflow_federated, matplotlib; print(\"TF\", tensorflow.__version__, \"TFF\", tensorflow_federated.__version__)'"

# ---------------------------------------------------------------- 2. audit
run_stage "audit: parse raw files"   "cd \"$ROOT/audit\" && python scripts/parse_casas.py --glob 'data/raw/uci/**/*.ann.txt'"
run_stage "audit: profile homes"     "cd \"$ROOT/audit\" && python scripts/profile_homes.py"
run_stage "audit: inventory"         "cd \"$ROOT/audit\" && python scripts/inventory.py"
run_stage "audit: feasibility"       "cd \"$ROOT/audit\" && python scripts/feasibility.py && python scripts/feasibility.py --drop-other"

# ---------------------------------------------------------------- 3. datasets
PB="cd \"$ROOT/pipelinev2\" &&"
run_stage "build cap60_noother"      "$PB python build_dataset.py --cap-days 60"
run_stage "build cap60_noother_ctx"  "$PB python build_dataset.py --cap-days 60 --context"
run_stage "build cap60_other"        "$PB python build_dataset.py --cap-days 60 --keep-other"
run_stage "build full_noother"       "$PB python build_dataset.py"
run_stage "build ctx 5 min"          "$PB DUC_CTX_MIN=5 python build_dataset.py --cap-days 60 --context --name cap60_noother_ctx5"
run_stage "build ctx 15 min"         "$PB DUC_CTX_MIN=15 python build_dataset.py --cap-days 60 --context --name cap60_noother_ctx15"

# ---------------------------------------------------------------- 4. baselines (five seeds each)
for DS in cap60_noother cap60_noother_ctx cap60_other full_noother cap60_noother_ctx5 cap60_noother_ctx15; do
  run_stage "baselines $DS" "$PB python baselines.py --data \"$PROC/$DS\" --setups local central finetune"
done

# ---------------------------------------------------------------- 5. fine-tune learning-rate sweep
run_stage "finetune lr/10 (ctx)" "$PB python baselines.py --data \"$PROC/cap60_noother_ctx\" --setups finetune --ft-div 10"
run_stage "finetune lr/1 (ctx)"  "$PB python baselines.py --data \"$PROC/cap60_noother_ctx\" --setups finetune --ft-div 1"

# ---------------------------------------------------------------- 6. federated runs
HARN="cd \"$ROOT/harnessv2\" &&"
HOMES_CTX="$(homes_of "$PROC/cap60_noother_ctx")"
run_stage "brokers start"  "$HARN python brokers.py start --homes $HOMES_CTX"
BROKERS_UP=1

start_gateways() {  # start_gateways <dataset dir>: background gateways, one per home
  local ds="$1" homes; homes="$(homes_of "$ds")"
  pkill -f "gateway.py" 2>/dev/null || true
  ( cd "$ROOT/harnessv2" && exec python gateway.py --dataset "$ds" --homes $homes ) \
    > "$RUN_DIR/gateways_$(basename "$ds").log" 2>&1 &
  GW_PIDS+=("$!")
}

# Gateways must match the dataset, and a replay must follow every gateway start.
# Otherwise the gateway stores are empty and the first round fails.
replay_stage() {  # replay_stage <dataset dir>
  local ds="$1" homes; homes="$(homes_of "$ds")"
  run_stage "replay and verify $(basename "$ds")" "$HARN sleep 15 && python replay.py --homes $homes --speed 0 && python verify_windows.py --dataset \"$ds\" --homes $homes --wait"
}

start_gateways "$PROC/cap60_noother_ctx"
replay_stage   "$PROC/cap60_noother_ctx"
for SC in all28_ctx all28_ctx_s1 all28_ctx_s2 all28_ctx_s3 all28_ctx_s4 all28_ctx_r150 all28_ctx_pers; do
  fed_scenario "$PROC/cap60_noother_ctx" "$ROOT/harnessv2/scenarios/$SC.json"
done
pkill -f "gateway.py" 2>/dev/null || true
GW_PIDS=()

start_gateways "$PROC/cap60_noother"
replay_stage   "$PROC/cap60_noother"
for SC in all28_fedavg all28_prox0.1; do
  fed_scenario "$PROC/cap60_noother" "$ROOT/harnessv2/scenarios/$SC.json"
done
pkill -f "gateway.py" 2>/dev/null || true
GW_PIDS=()

run_stage "brokers stop" "$HARN python brokers.py stop"
BROKERS_UP=0

# ---------------------------------------------------------------- 7. results
run_stage "summarise runs"   "$HARN python summarize_runs.py"
run_stage "collect results"  "$HARN python collect_results.py"
run_stage "plots"           "$HARN python plot_results.py"

write_config_end
echo
echo "Finished in $(( $(date +%s) - T0 ))s. Config and logs: $RUN_DIR"
echo "Index: $ROOT/results/index.csv   Charts: $ROOT/results/plots/"
