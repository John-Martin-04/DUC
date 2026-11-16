# DUC: federated learning for smart-home activity recognition

Federated averaging (FedAvg) and FedProx on the CASAS smart-home dataset, with 28 homes.
Each home keeps its raw events. Only model weights and test scores leave a home.

## Folders

| Folder | What it holds | In git |
|---|---|---|
| `audit/` | Data audit scripts, mappings and reports. Raw files in `audit/data/raw/`, parsed events in `audit/data/interim/events/` | Code and reports yes; `data/` no |
| `pipelinev2/` | Builds the per-minute datasets and runs the local, centralised and fine-tuned baselines | yes |
| `harnessv2/` | The MQTT harness: replay, brokers, gateways, coordinator, recorder, checks, results tools | yes |
| `data/processed/` | The built datasets (`cap60_noother`, `cap60_noother_ctx`, and the rest) | no |
| `data/gateways/` | One SQLite store per home, written by the gateways during federated runs | no |
| `results/` | All outputs: baselines, harness runs, `index.csv`, `curves.csv`, `plots/`, `run_configs/` | no |
| `archive/` | Old versions (v1) and their results, kept for reference | yes |

## Setup (WSL2, Ubuntu)

Work from the DUC folder and use the virtual environment:

```
cd /mnt/d/Code/SU/PROJECTS/DUC
source .venv/bin/activate
uv pip install --python .venv/bin/python -r harnessv2/requirements.txt
uv pip install --python .venv/bin/python matplotlib
```

The environment is created with `uv`, so it has no `pip`. Use `uv pip` as above.

The setup steps need internet access (for `uv`, `apt` and the download). Once they are done, the pipeline runs offline: the brokers only use `127.0.0.1`, and all data is on the machine.

Check the install:

```
python -c "import tensorflow, tensorflow_federated, matplotlib; print('ok')"
```

**Broker settings: `harnessv2/duc.env`.** This file is not in git (it's listed in `.gitignore`). Create it with these lines:

```
DUC_HOME_BROKER=127.0.0.1:18830
DUC_FED_BROKER=127.0.0.1:18840
DUC_HOME_BIND=127.0.0.1
DUC_FED_BIND=127.0.0.1
DUC_SECRET=duc-
```

On a single machine these are the defaults. For a Raspberry Pi, use the Pi's address for the home broker, and the same `DUC_SECRET` on every machine.

**Raw data: `audit/data/raw/uci/`.** This is the UCI release (dataset 506), with one folder per home. The pipeline needs the annotated event files, `csh*.ann.txt`, one per home (30 files). Get the archive from https://archive.ics.uci.edu/dataset/506, and extract only those files:

```
unzip FILE.zip '*ann.txt' -d audit/data/raw/uci
```

Check the count with `find audit/data/raw/uci -name '*ann.txt' | wc -l`. It should print 30.

## Data flow

1. `audit/scripts/parse_casas.py` turns the raw files into one event table per home, in `audit/data/interim/events/`. The audit scripts also profile the homes and check which windows each home can provide.
2. `pipelinev2/build_dataset.py` builds one table per home, with one row per 60-second window, into `data/processed/`.
3. The gateways rebuild the same windows from a live replay of the events, and write them to `data/gateways/`. Each one must match the offline dataset.
4. The coordinator runs the federated rounds. Results go to `results/harness/<run>/`.

The baselines need only step 2 (`data/processed/`). The federated runs need steps 1 to 3, because the replay reads the event tables.

## Quick tests

Run these from `harnessv2/` unless noted.

| Test | Command | Time |
|---|---|---|
| Whole harness on fake homes | `bash run_sample.sh` | about 2 min |
| Broker access rules | `python check_access.py` | seconds |
| One baseline, one seed | `cd ../pipelinev2 && python baselines.py --data ../data/processed/cap60_noother --seeds 0` | about 3 min |

The sample run builds its own fake data in `sample_run/`, so it never touches the real results. It ends with "Sample run finished" when all three gateways match the offline windows and the federated rounds complete.

## Full runs

The full pipeline, from the raw files to the charts, is one script at the root:

```
cd /mnt/d/Code/SU/PROJECTS/DUC
bash run_from_scratch.sh
```

It runs 35 stages, in this order:

| Stages | What happens |
|---|---|
| 1 | Preflight: checks the environment and the raw files, applies the personalisation patch to `coordinator.py` and `gateway.py` (once), imports TensorFlow, TensorFlow Federated and matplotlib |
| 2 to 5 | Audit: parse the raw files, profile the homes, inventory the labels and sensors, feasibility per class and home |
| 6 to 11 | Datasets: `cap60_noother`, `cap60_noother_ctx`, `cap60_other`, `full_noother`, and the 5- and 15-minute context variants |
| 12 to 17 | Baselines on each of the six datasets: local, centralised and fine-tuned models, five seeds each |
| 18 to 19 | Fine-tune sweep: the fine-tuned model with the learning rate divided by 10 and by 1, on the context dataset. The baselines in stages 12 to 17 already fine-tune at the default rate (divided by 3); this sweep shows how much the result depends on that choice |
| 20 to 31 | Federated runs: brokers, gateways and a replay for each dataset, then the coordinator for each scenario, with a recorder for the traffic. Context: seeds 0 to 4, 150 rounds, and local fine-tuning. Original input: FedAvg and FedProx (mu 0.1) |
| 32 | Stop the brokers |
| 33 to 35 | Summary, results index, charts |

**Time.** The preflight takes about 1.5 minutes and the datasets a few minutes each. The baselines and the federated runs take most of the time. The whole run takes several hours on this laptop. Check the `stages.log` timings after the first few stages to get a better estimate.

**Before you start:**
- Plug the laptop in, and set sleep to Never while plugged in.
- Back up `data/processed/`, `data/gateways/` and `results/`, if you want to keep the current numbers. The run replaces the processed datasets, the gateway stores and the result folders with the same names.
- Keep the terminal open, or run it in tmux (below).

**Running it in tmux.** tmux keeps the run alive when the terminal closes. Install it once:

```
sudo apt install -y tmux
```

Start the run in a session:

```
tmux new -s duc
cd /mnt/d/Code/SU/PROJECTS/DUC
bash run_from_scratch.sh
```

Leave it running and close the window: press Ctrl+B, then D.

Other tmux commands:

| Task | Command |
|---|---|
| Come back to the run | `tmux attach -t duc` |
| List running sessions | `tmux ls` |
| Scroll back through the output | Ctrl+B, then `[`; use the arrow keys or Page Up; press `q` to return |
| Stop the run from inside the session | Ctrl+C, then `exit` |
| Stop the session from outside | `tmux kill-session -t duc` |

If you run the baselines separately, give them their own session (`tmux new -s baselines`), so they don't share a window with the full run.

**Watching progress.** From a second WSL window:

```
cd /mnt/d/Code/SU/PROJECTS/DUC
watch -n 30 'tail -n 5 results/run_configs/$(ls -t results/run_configs/ | head -n 1)/stages.log'
```

The `stages.log` shows each finished stage with its time and status. Each stage's full output is in the numbered log files in the same folder.

**Stopping a run.** Press Ctrl+B, then D to detach, or Ctrl+C in the window to stop it. If the window was closed or the process is stuck, run:

```
pkill -f run_from_scratch.sh
cd harnessv2 && python brokers.py stop && cd ..
ss -ltn | grep -E '18830|18840' || echo "no brokers listening"
```

`brokers.py stop` finds the brokers by their config files, so it also stops brokers left over from an interrupted run. Check that no brokers are listening before you start another run. A broker left over from an earlier run will block the new one.

**Results and reruns.** The baselines can be run on their own from `data/processed/` (see the commands in `pipelinev2/README.md`). To run a single federated scenario or a batch, against gateways that are already running:

```
bash run_ctx_batch.sh ../data/processed/cap60_noother_ctx scenarios/all28_ctx.json
```

Collect and plot the results at any time:

```
python collect_results.py
python plot_results.py
```

## Rules to remember

- The gateways must use the same dataset as the coordinator. Context runs need the `_ctx` dataset, and original-input runs need `cap60_noother`.
- After any gateway restart, run the replay again. Without it, the gateways have no windows and every round ends with zero updates.
- Each run's settings are saved in `results/harness/<run>/scenario.json`, and each full run saves its own configuration in `results/run_configs/`.
- Gateways delete their old store at start, unless they are started with `--keep-store`. A full run replaces `data/gateways/`.
- Brokers: the home broker is on port 18830, and the federation broker is on port 18840.
- Do not commit the changes that the preflight makes to `coordinator.py` and `gateway.py`, unless you intend to keep the personalisation step in the repo.

## Outputs

- `results/baselines/<dataset>/`: `results.csv`, `summary.md`, per-class and confusion tables
- `results/harness/<run>/`: `metrics.csv`, `rounds.csv`, `scenario.json`, and the traffic summary
- `results/index.csv`: one row per federated run and per baseline setup
- `results/curves.csv`: the score at every round
- `results/plots/`: the charts
- `results/run_configs/<timestamp>/`: one folder per full run, with `config.txt` (git commit, software versions, every settings file, every scenario used, dataset schemas, stage timings), one log per stage, and `stages.log`
