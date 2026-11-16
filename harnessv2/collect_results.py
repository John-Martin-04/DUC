"""Collect every finished run into one index, so results survive across runs.

Reads results/harness/<run>/ (federated) and results/baselines/<name>/ (baselines).
Writes:
  results/index.csv    one row per federated run, and one row per baseline setup
  results/curves.csv   mean and worst macro-F1 at every federated round, per run

  python collect_results.py          (re-run after every batch; it rebuilds both files)
"""
import json
import re
from pathlib import Path

import pandas as pd

RES = Path(__file__).resolve().parent.parent / "results"


def federated_runs():
    index, curves = [], []
    for d in sorted((RES / "harness").glob("*")):
        if not (d / "metrics.csv").exists() or not (d / "rounds.csv").exists():
            continue
        sc = json.loads((d / "scenario.json").read_text()) if (d / "scenario.json").exists() else {}
        m = pd.read_csv(d / "metrics.csv")
        r = pd.read_csv(d / "rounds.csv")
        final = int(r["round"].max())                       # the final-evaluation row
        for rnd, g in m.dropna(subset=["macro_f1"]).groupby("round"):
            curves.append(dict(run=d.name, round=int(rnd), mean_f1=g.macro_f1.mean(),
                               worst_f1=g.macro_f1.min(), homes=len(g)))
        last = m[m["round"] == final].dropna(subset=["macro_f1"])
        pers = m[m["round"] == final + 1].dropna(subset=["macro_f1"])
        traffic = (pd.to_numeric(r["down_bytes"], errors="coerce").fillna(0)
                   + pd.to_numeric(r["up_bytes"], errors="coerce").fillna(0)).sum() / 1e6
        index.append(dict(kind="federated", name=d.name, group=re.sub(r"_s\d+$", "", d.name),
                          setup="fedavg" if not sc.get("mu") else f"fedprox_mu{sc['mu']}",
                          seeds=1, rounds=final - 1, mean_f1=round(last.macro_f1.mean(), 4),
                          median_f1=round(last.macro_f1.median(), 4), worst_f1=round(last.macro_f1.min(), 4),
                          sd_f1=None, traffic_MB=round(traffic, 1),
                          personalised_mean_f1=round(pers.macro_f1.mean(), 4) if len(pers) else None,
                          dataset=sc.get("dataset", ""), local_epochs=sc.get("local_epochs"),
                          client_lr=sc.get("client_lr"), mu=sc.get("mu"), fraction=sc.get("fraction"),
                          dropout_p=sc.get("dropout_p"), seed=sc.get("seed")))
    return index, curves


def baseline_rows():
    index = []
    for d in sorted((RES / "baselines").glob("*")):
        f = d / "results.csv"
        if not f.exists():
            continue
        b = pd.read_csv(f)
        per = b.groupby(["setup", "seed"])["macro_f1"].agg(["mean", "median", "min"]).reset_index()
        for setup, g in per.groupby("setup"):
            index.append(dict(kind="baseline", name=d.name, group=d.name, setup=setup, seeds=len(g),
                              rounds=None, mean_f1=round(g["mean"].mean(), 4),
                              median_f1=round(g["median"].mean(), 4), worst_f1=round(g["min"].mean(), 4),
                              sd_f1=round(g["mean"].std(ddof=1), 4) if len(g) > 1 else None,
                              traffic_MB=None, personalised_mean_f1=None, dataset=d.name))
    return index


def main():
    fed, curves = federated_runs()
    index = pd.DataFrame(fed + baseline_rows())
    index.to_csv(RES / "index.csv", index=False)
    pd.DataFrame(curves).to_csv(RES / "curves.csv", index=False)
    print(index[["kind", "name", "setup", "seeds", "mean_f1", "sd_f1", "worst_f1"]].to_string(index=False))
    print(f"\nwritten: {RES / 'index.csv'} ({len(index)} rows), {RES / 'curves.csv'}")


if __name__ == "__main__":
    main()
