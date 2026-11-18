"""Pick the best setting per system by mean validation macro-F1 and write results/tuning/best.json.

Reads only validation columns (val_macro_f1). Test scores are never used here.
Run after tune_baselines.sh and tune_fed.sh: python select_best.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

RESULTS = Path(__file__).resolve().parent.parent / "results"
OUT = RESULTS / "tuning"


def baseline_rows() -> list[dict]:
    rows = []
    for f in RESULTS.glob("baselines/*_lr*_bs*/results.csv"):
        cfg = f.parent.name.split("_lr", 1)[1]              # e.g. 0.001_bs128
        d = pd.read_csv(f)
        if "val_macro_f1" not in d:
            continue
        per_seed = d.groupby(["setup", "seed"])["val_macro_f1"].mean().reset_index()
        for setup, g in per_seed.groupby("setup"):
            rows.append(dict(system=setup, config=f"lr{cfg}", seed=None,
                             val=g["val_macro_f1"].mean(), seeds=len(g)))
    return rows


def federated_rows() -> list[dict]:
    rows = []
    for f in RESULTS.glob("harness/tune_fed_*_s*/metrics.csv"):
        name = f.parent.name
        cfg = re.sub(r"_s\d+$", "", name)[len("tune_fed_"):]
        m = pd.read_csv(f)
        last = m[m["round"] == m["round"].max()]            # the final model, after all rounds
        v = last["val_macro_f1"].dropna()
        if v.empty:
            continue
        rows.append(dict(system="federated", config=cfg, seed=name, val=v.mean(), seeds=1))
    return rows


def main() -> None:
    rows = baseline_rows()
    fed = pd.DataFrame(federated_rows())
    if len(fed):
        fed = fed.groupby("config").agg(val=("val", "mean"), seeds=("seeds", "sum")).reset_index()
        fed.insert(0, "system", "federated")
        rows += fed.to_dict("records")
    table = pd.DataFrame(rows)
    if table.empty:
        raise SystemExit("no validation results found: run tune_baselines.sh and tune_fed.sh first")
    table = table.sort_values(["system", "val"], ascending=[True, False]).round(4)
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "validation_summary.csv", index=False)
    print(table.to_string(index=False))

    best = {}
    for system, g in table.groupby("system"):
        top = g.iloc[0]
        best[system] = dict(config=top["config"], val_mean_f1=float(top["val"]), seeds=int(top["seeds"]))
    (OUT / "best.json").write_text(json.dumps(best, indent=2))
    print(f"\nbest per system written to {OUT / 'best.json'}")
    for system, b in best.items():
        if b["seeds"] < 5:
            print(f"warning: {system} {b['config']} has {b['seeds']} seed(s), expected 5")


if __name__ == "__main__":
    main()
