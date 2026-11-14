# Phase 2: windowed dataset and baselines

```
settings.py        paths and model settings (window length and splits come from audit/config.py)
build_dataset.py   audit outputs -> one table per home, one row per 60 s window
windows.py        window rules shared with the harness gateways
common.py          loading, the MLP, macro-F1: shared by every setup, later federated too
baselines.py       local-only and centralised training, scored per home
run_sample.sh      smoke test on fake data
```

Put this folder at `DUC/pipeline`, next to `DUC/audit`. It uses the same
`.venv` as the audit; nothing new to install.

## Run

```bash
cd /mnt/d/Code/SU/PROJECTS/DUC && source .venv/bin/activate && cd pipeline
bash run_sample.sh                                    # about a minute; ends with "Sample run finished"

python build_dataset.py --cap-days 60                 # main runs        -> ../data/processed/cap60_noother
python build_dataset.py --cap-days 60 --keep-other    # secondary run    -> ../data/processed/cap60_other
python build_dataset.py                               # full volume, RQ2 -> ../data/processed/full_noother

python baselines.py --data ../data/processed/cap60_noother --seeds 0    # quick look, one seed
python baselines.py --data ../data/processed/cap60_noother              # the record: 5 seeds
```

The dataset goes to `DUC/data/processed/` (ignored by Git; rebuild it any
time). Results go to `DUC/results/baselines/<dataset>/`: `results.csv` (one
row per setup, seed and home) and `summary.md`. Commit the results.

TensorFlow prints "Unable to register cuDNN/cuFFT/cuBLAS factory" at start-up.
That only means there is no GPU; ignore it.

## What the dataset contains

One row per 60-second window per home: `home`, `window_start`, `split`
(train/val/test), `label`, `y` (class index), then one column per (sensor
type, room) pair counting that pair's events in the window, then `tod_sin`,
`tod_cos` (time of day on a circle) and `weekend`. Every home gets the same
columns in the same order, so all clients share one model input.
`schema.json` lists the columns, the classes, the settings and the window
counts per home and split.

Window labels, the time split and the handling of 'Other' are identical to
the audit's `feasibility.py`, so the counts match `feasibility_final.md`
(without the cap).

## Design choices to record in the report

- **Inputs:** log(1 + count) per feature plus the time features. No
  standardisation, so no home has to share means or variances.
- **Model:** MLP, 128 and 64 hidden units, dropout 0.2, Adam (learning rate
  0.001), batch 128, up to 30 epochs, early stopping on validation loss
  (patience 5). Identical for every setup; change it only in `settings.py`.
- **Metric:** macro-F1 per home over the classes present in that home's test
  period; reported as mean, median and worst home, averaged over seeds.
- **Cap:** `--cap-days 60` keeps each home's first 60 calendar days with
  labelled windows, before the split.
