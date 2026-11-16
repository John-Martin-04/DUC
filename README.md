# DUC: federated learning for smart-home activity recognition

Federated averaging (FedAvg) and FedProx on the CASAS smart-home dataset, with 28 homes.
Each home keeps its raw events. Only model weights and test scores leave a home.

## Folders

| Folder | What it holds |
|---|---|
| `audit/` | Data audit: feasibility, inventory, the sample data for smoke tests |
| `pipelinev2/` | Builds the per-minute dataset, and runs the local, centralised and fine-tuned baselines |
| `harnessv2/` | The MQTT harness: replay, brokers, gateways, coordinator, recorder, checks, results tools |
| `data/` | Processed datasets and gateway stores (not in git) |
| `results/` | All outputs: baselines, harness runs, `index.csv`, `curves.csv`, `plots/` (not in git) |
| `archive/` | Old versions (v1), kept for reference |

## Setup (WSL2, Ubuntu)

```
cd /mnt/d/Code/SU/PROJECTS/DUC
source .venv/bin/activate
pip install -r harnessv2/requirements.txt
pip install matplotlib
```

The harness reads `harnessv2/duc.env` (broker addresses and the shared secret). This file is not in git.

## Data flow

1. `audit/` selects the homes and the sensors, and maps the labels to 10 classes.
2. `pipelinev2/build_dataset.py` builds one table per home, one row per minute.
3. The gateways and the replay read the same dataset, so the features match the offline run.
4. The coordinator runs the federated rounds. Results go to `results/harness/<run>/`.

## Quick tests

Run these from `harnessv2/` unless noted.

| Test | Command | Time |
|---|---|---|
| Whole harness on fake homes | `bash run_sample.sh` | about 2 min |
| Gateways rebuild the offline windows | `python verify_windows.py --dataset ../data/processed/cap60_noother_ctx --homes <homes>` | minutes |
| Broker access rules | `python check_access.py` | seconds |
| One baseline, one seed | `cd ../pipelinev2 && python baselines.py --data ../data/processed/cap60_noother --seeds 0` | about 3 min |

## Full runs

1. Start the brokers and the gateways, then run the replay. Use the dataset in the command, and the same homes in every step:
   ```
   HOMES=$(python -c "import json; print(' '.join(json.load(open('../data/processed/cap60_noother_ctx/schema.json'))['homes']))")
   python brokers.py start --homes $HOMES
   python gateway.py --dataset ../data/processed/cap60_noother_ctx --homes $HOMES     # leave running
   python replay.py --homes $HOMES --speed 0                                          # in another terminal
   ```
2. Run one federated scenario, or a batch:
   ```
   bash run_ctx_batch.sh ../data/processed/cap60_noother_ctx scenarios/all28_ctx.json
   ```
3. Run the whole sweep, which includes the baselines, the fine-tuning sweep, the ablation, and the charts:
   ```
   bash run_full_sweep.sh 2>&1 | tee -a ../all_runs.log
   ```
4. Collect and plot the results at any time:
   ```
   python collect_results.py
   python plot_results.py
   ```

## Rules to remember

- The gateways must use the same dataset as the coordinator. Context runs need the `_ctx` dataset, and original-input runs need `cap60_noother`.
- After any gateway restart, run the replay again. Without it, the gateways have no windows and every round ends with zero updates.
- Each run's settings are saved in `results/harness/<run>/scenario.json`.
- Brokers: the home broker is on port 18830, and the federation broker is on port 18840.

## Outputs

- `results/index.csv`: one row per federated run and per baseline setup
- `results/curves.csv`: the score at every round
- `results/plots/`: the charts
