"""Train the two reference setups for RQ1 on the windowed dataset.

  local       one model per home, trained only on that home's training windows
  central     one model trained on all homes' training windows pooled

Both use the same MLP (common.py) and are tested on each home's own test
windows, so the federated model can later be compared home by home. Training
stops early when the validation loss stops improving.

Writes results/baselines/<dataset name>/
  results.csv   one row per setup, seed and home: macro-F1, accuracy, sizes
  summary.md    mean, median and worst home per setup, over seeds

Usage (from DUC/pipeline)
  python baselines.py --data ../data/processed/cap60_noother
  python baselines.py --data ../data/processed/cap60_noother --seeds 0          # quick, one seed
  python baselines.py --data ../data/processed/cap60_noother --setups local
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

import settings as S
from settings import md_table
from common import build_model, class_weights, compile_model, load_dataset, macro_f1, set_seed, xy


USE_CLASS_WEIGHTS = False
FT_DIV = 3.0                            # fine-tuning learning rate = LEARNING_RATE / FT_DIV
PREDICTIONS: dict[str, list] = {}       # setup -> [(y_true, y_pred), ...] over homes and seeds


def fit(model, x_tr, y_tr, x_va, y_va, epochs: int, verbose: int):
    import tensorflow as tf
    callbacks, val = [], None
    if len(y_va):
        val = (x_va, y_va)
        callbacks.append(tf.keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=S.PATIENCE, restore_best_weights=True))
    cw = class_weights(y_tr, model.output_shape[-1]) if USE_CLASS_WEIGHTS else None
    hist = model.fit(x_tr, y_tr, validation_data=val, epochs=epochs, class_weight=cw,
                     batch_size=S.BATCH_SIZE, callbacks=callbacks, verbose=verbose)
    return len(hist.history["loss"])


def evaluate(model, x, y, setup: str) -> tuple[float, float]:
    if not len(y):
        return float("nan"), float("nan")
    pred = model.predict(x, batch_size=4096, verbose=0).argmax(axis=1)
    PREDICTIONS.setdefault(setup, []).append((y, pred))
    return macro_f1(y, pred), float(np.mean(pred == y))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, type=Path, help="a folder made by build_dataset.py")
    ap.add_argument("--setups", nargs="+", default=["local", "central"], choices=["local", "central", "finetune"])
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    ap.add_argument("--epochs", type=int, default=S.MAX_EPOCHS)
    ap.add_argument("--homes", nargs="*")
    ap.add_argument("--verbose", type=int, default=0)
    ap.add_argument("--class-weight", action="store_true",
                    help="weight rare classes more during training; results go to a separate folder")
    ap.add_argument("--ft-div", type=float, default=3.0,
                    help="fine-tune at LEARNING_RATE / this value; results go to a separate folder if not 3")
    ap.add_argument("--hidden", nargs="+", type=int,
                    help="hidden layer sizes for a capacity check, e.g. --hidden 512 256; "
                         "results go to a separate folder")
    args = ap.parse_args()

    schema, data = load_dataset(args.data, args.homes)
    global USE_CLASS_WEIGHTS
    USE_CLASS_WEIGHTS = args.class_weight
    global FT_DIV
    FT_DIV = args.ft_div
    tag = "_cw" if args.class_weight else ""
    if args.ft_div != 3.0:
        tag += f"_ftdiv{args.ft_div:g}"
    if args.hidden:
        S.HIDDEN_UNITS = tuple(args.hidden)
        tag += "_hidden" + "x".join(map(str, args.hidden))
    n_classes = len(schema["classes"])
    split = {h: {s: xy(df[df.split == s], schema) for s in ("train", "val", "test")}
             for h, df in data.items()}
    n_inputs = next(iter(split.values()))["train"][0].shape[1]
    out_dir = S.RESULTS_DIR / "baselines" / (schema["name"] + tag)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{schema['name']}: {len(data)} homes, {n_classes} classes, {n_inputs} inputs")

    rows = []
    for seed in args.seeds:
        if "local" in args.setups:
            t0 = time.time()
            for h, d in split.items():
                set_seed(seed)
                model = build_model(n_inputs, n_classes)
                compile_model(model)
                (x_tr, y_tr), (x_va, y_va), (x_te, y_te) = d["train"], d["val"], d["test"]
                epochs = fit(model, x_tr, y_tr, x_va, y_va, args.epochs, args.verbose)
                f1, acc = evaluate(model, x_te, y_te, "local")
                rows.append(dict(setup="local", seed=seed, home=h, n_train=len(y_tr), n_test=len(y_te),
                                 classes_in_test=len(np.unique(y_te)), macro_f1=f1, accuracy=acc,
                                 epochs=epochs))
            print(f"seed {seed} local: {time.time() - t0:.0f} s")

        if "central" in args.setups or "finetune" in args.setups:
            t0 = time.time()
            set_seed(seed)
            model = build_model(n_inputs, n_classes)
            compile_model(model)
            x_tr = np.vstack([d["train"][0] for d in split.values()])
            y_tr = np.concatenate([d["train"][1] for d in split.values()])
            x_va = np.vstack([d["val"][0] for d in split.values()])
            y_va = np.concatenate([d["val"][1] for d in split.values()])
            epochs = fit(model, x_tr, y_tr, x_va, y_va, args.epochs, args.verbose)
            for h, d in split.items():
                x_te, y_te = d["test"]
                f1, acc = evaluate(model, x_te, y_te, "central")
                rows.append(dict(setup="central", seed=seed, home=h, n_train=len(d["train"][1]),
                                 n_test=len(y_te), classes_in_test=len(np.unique(y_te)),
                                 macro_f1=f1, accuracy=acc, epochs=epochs))
            print(f"seed {seed} central: {time.time() - t0:.0f} s, {epochs} epochs")

        if "finetune" in args.setups:
            # Personalisation: start from the centralised model, then train briefly on one home.
            t0, shared = time.time(), model.get_weights()
            for h, d in split.items():
                set_seed(seed)
                ft = build_model(n_inputs, n_classes)
                compile_model(ft)
                ft.set_weights(shared)
                ft.optimizer.learning_rate.assign(S.LEARNING_RATE / FT_DIV)
                (x_tr, y_tr), (x_va, y_va), (x_te, y_te) = d["train"], d["val"], d["test"]
                epochs = fit(ft, x_tr, y_tr, x_va, y_va, args.epochs, args.verbose)
                f1, acc = evaluate(ft, x_te, y_te, "finetune")
                rows.append(dict(setup="finetune", seed=seed, home=h, n_train=len(y_tr), n_test=len(y_te),
                                 classes_in_test=len(np.unique(y_te)), macro_f1=f1, accuracy=acc,
                                 epochs=epochs))
            print(f"seed {seed} finetune: {time.time() - t0:.0f} s")

    res = pd.DataFrame(rows)
    res.to_csv(out_dir / "results.csv", index=False)

    # Per seed: mean, median and worst home; then mean and spread over seeds.
    per_seed = (res.groupby(["setup", "seed"])["macro_f1"]
                .agg(mean="mean", median="median", worst="min").reset_index())
    summary = per_seed.groupby("setup").agg(
        mean_f1=("mean", "mean"), mean_f1_sd=("mean", "std"),
        median_f1=("median", "mean"), worst_home_f1=("worst", "mean")).round(3)
    worst = (res.groupby(["setup", "home"])["macro_f1"].mean().reset_index()
             .sort_values(["setup", "macro_f1"]).groupby("setup").head(3))

    lines = [f"# Baselines: {schema['name']}", "",
             f"{len(data)} homes, {n_classes} classes, seeds {args.seeds}. Macro-F1 per home over the "
             "classes in its test period; mean, median and worst home per seed, averaged over seeds "
             "(sd = spread of the mean over seeds).", "",
             md_table(summary.reset_index()),
             "", "Weakest homes (macro-F1 averaged over seeds):", "",
             md_table(worst.round(3))]
    # Per-class view, pooled over all homes and seeds.
    classes, per, f1_table = schema["classes"], [], {}
    for setup, pairs in PREDICTIONS.items():
        y = np.concatenate([a for a, _ in pairs])
        p = np.concatenate([b for _, b in pairs])
        conf = np.zeros((n_classes, n_classes), dtype=int)
        np.add.at(conf, (y, p), 1)
        for i, c in enumerate(classes):
            tp, fp, fn = conf[i, i], conf[:, i].sum() - conf[i, i], conf[i].sum() - conf[i, i]
            prec = tp / (tp + fp) if tp + fp else 0.0
            rec = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
            per.append(dict(setup=setup, cls=c, precision=round(prec, 3), recall=round(rec, 3),
                            f1=round(f1, 3), test_windows=int(conf[i].sum() / len(args.seeds))))
            f1_table.setdefault(c, {})[setup] = round(f1, 3)
        share = conf / np.maximum(conf.sum(axis=1, keepdims=True), 1)
        pd.DataFrame(share.round(3), index=classes, columns=classes).to_csv(
            out_dir / f"confusion_{setup}.csv", index_label="true \\ predicted")
    per = pd.DataFrame(per).rename(columns={"cls": "class"})
    per.to_csv(out_dir / "per_class.csv", index=False)
    f1_by_class = pd.DataFrame(f1_table).T.rename_axis("class").reset_index()
    f1_by_class["test_windows"] = [int(per[per["class"] == c]["test_windows"].iloc[0]) for c in f1_by_class["class"]]
    lines += ["", "F1 per class, pooled over homes and seeds (confusion_<setup>.csv shows what each "
              "class is mistaken for):", "", md_table(f1_by_class)]
    print("\n" + f1_by_class.to_string(index=False))
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n" + summary.to_string())
    print(f"\nWritten to {out_dir}")



if __name__ == "__main__":
    main()
