"""Draw charts from results/index.csv and results/curves.csv (run collect_results.py first).

Writes PNGs to results/plots/:
  federated_curves.png   macro-F1 per round, one line per federated group (band = min to max over seeds)
  federated_final.png    final mean macro-F1 per federated group, with the personalised score where it exists
  input_ablation.png     baselines by input: original, 5-minute context, 15-minute context, full context
  finetune_sweep.png     fine-tuning learning rate: divisor vs mean macro-F1 (error bars = seed sd)

  python plot_results.py
"""
from pathlib import Path
import re

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RES = Path(__file__).resolve().parent.parent / "results"
OUT = RES / "plots"
OUT.mkdir(parents=True, exist_ok=True)

idx = pd.read_csv(RES / "index.csv")
fed = idx[idx.kind == "federated"]


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=150)
    plt.close(fig)
    print("wrote", OUT / name)


# 1. Federated curves: mean per round over seeds, band = min..max across seeds.
if (RES / "curves.csv").exists() and len(fed):
    curves = pd.read_csv(RES / "curves.csv")
    curves["group"] = curves.run.str.replace(r"_s\d+$", "", regex=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for grp, g in curves.groupby("group"):
        s = g.groupby("round").mean_f1.agg(["mean", "min", "max"])
        ax.plot(s.index, s["mean"], label=f"{grp} (n={g.run.nunique()})")
        if g.run.nunique() > 1:
            ax.fill_between(s.index, s["min"], s["max"], alpha=0.2)
    ax.set_xlabel("round")
    ax.set_ylabel("mean macro-F1 across homes")
    ax.set_title("Federated runs: score per round")
    ax.grid(alpha=0.3)
    ax.legend()
    save(fig, "federated_curves.png")

# 2. Final federated scores, with the personalised score beside each where it exists.
if len(fed):
    f = fed.groupby("group").agg(mean_f1=("mean_f1", "mean"), worst_f1=("worst_f1", "mean"),
                                 pers=("personalised_mean_f1", "mean"), n=("name", "count"))
    x = np.arange(len(f))
    fig, ax = plt.subplots(figsize=(max(6, 1.6 * len(f)), 4.5))
    ax.bar(x - 0.2, f.mean_f1, 0.4, label="shared model (mean over homes)")
    ax.bar(x + 0.2, f.worst_f1, 0.4, label="shared model (worst home)")
    if f.pers.notna().any():
        ax.bar(x + 0.6, f.pers.fillna(0), 0.4, label="with local fine-tuning")
    ax.set_xticks(x, f.index, rotation=20, ha="right")
    ax.set_ylabel("macro-F1")
    ax.set_title("Federated runs: final scores")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    save(fig, "federated_final.png")

# 3. Input ablation: the baseline setups on each input variant.
base = idx[idx.kind == "baseline"]
variants = {"cap60_noother": "original", "cap60_noother_ctx5": "5-min context",
            "cap60_noother_ctx15": "15-min context", "cap60_noother_ctx": "5 + 15-min context"}
abl = base[base.name.isin(variants)]
if len(abl):
    setups = ["local", "central", "finetune"]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    w = 0.25
    for i, s in enumerate(setups):
        vals, errs, labels = [], [], []
        for name, lab in variants.items():
            row = abl[(abl.name == name) & (abl.setup == s)]
            vals.append(row.mean_f1.values[0] if len(row) else np.nan)
            errs.append(row.sd_f1.fillna(0).values[0] if len(row) else 0)
        ax.bar(np.arange(len(variants)) + (i - 1) * w, vals, w, yerr=errs, capsize=3, label=s)
    ax.set_xticks(np.arange(len(variants)), list(variants.values()))
    ax.set_ylabel("mean macro-F1 across homes")
    ax.set_title("Baselines by input (error bars: seed sd)")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    save(fig, "input_ablation.png")

# 4. Fine-tuning learning-rate sweep: divisor on the x-axis.
rows = []
for _, r in base[base.setup == "finetune"].iterrows():
    if not r["name"].startswith("cap60_noother_ctx") or re.search(r"ctx5|ctx15", r["name"]):
        continue
    m = re.search(r"_ftdiv([\d.]+)$", r["name"])
    rows.append(dict(div=float(m.group(1)) if m else 3.0, mean=r.mean_f1, sd=r.sd_f1 or 0))
if len(rows) > 1:
    s = pd.DataFrame(rows).sort_values("div")
    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    ax.errorbar(s["div"], s["mean"], yerr=s["sd"], marker="o", capsize=4)
    ax.set_xscale("log")
    ax.set_xticks(s["div"], [f"lr/{d:g}" for d in s["div"]])
    ax.set_xlabel("fine-tuning learning rate")
    ax.set_ylabel("mean macro-F1 across homes")
    ax.set_title("Fine-tuning learning-rate sweep (context input)")
    ax.grid(alpha=0.3)
    save(fig, "finetune_sweep.png")
