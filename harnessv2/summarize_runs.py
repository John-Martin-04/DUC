"""Summarise finished federated runs: final mean and worst-home macro-F1, traffic.

  python summarize_runs.py scenarios/all28_ctx_s1.json scenarios/all28_ctx_s2.json ...

Also prints mean and spread over the runs given, which is what the seed table needs.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import hconfig as H

rows = []
for arg in sys.argv[1:]:
    name = json.loads(Path(arg).read_text()).get("name", Path(arg).stem)
    d = H.RESULTS_DIR / name
    if not (d / "metrics.csv").exists():
        print(f"{name}: no results yet"); continue
    m = pd.read_csv(d / "metrics.csv")
    r = pd.read_csv(d / "rounds.csv")
    final = int(r["round"].max())
    last = m[m["round"] == final].dropna(subset=["macro_f1"])
    mb = (r["down_bytes"].fillna(0) + r["up_bytes"].fillna(0)).sum() / 1e6
    rows.append(dict(run=name, rounds=final - 1, mean_f1=round(last.macro_f1.mean(), 4),
                     median_f1=round(last.macro_f1.median(), 4), worst_f1=round(last.macro_f1.min(), 4),
                     homes=len(last), traffic_MB=round(mb, 1)))
df = pd.DataFrame(rows)
print(df.to_string(index=False))
if len(df) > 1:
    print(f"\nover {len(df)} runs: mean {df.mean_f1.mean():.4f}, sd {df.mean_f1.std():.4f}, "
          f"worst-home mean {df.worst_f1.mean():.4f}")
out = H.RESULTS_DIR / "summary_runs.csv"
df.to_csv(out, index=False)
print(f"written to {out}")
