"""Build the windowed feature dataset: one table per home, one row per window.

This is the table every model trains on: local-only, centralised and
federated. It reads the audit's outputs (parsed events, label map, sensor
inventory, selected homes) and writes

  data/processed/<name>/<home>.parquet   one row per window
  data/processed/<name>/schema.json      feature columns, classes, settings, counts

Each row holds
  home, window_start, split (train/val/test), label, y (class index)
  n_<type>__<room>   events of that sensor type in that room during the window
  tod_sin, tod_cos   time of day on a circle, so 23:59 and 00:00 are close
  weekend            1 on Saturday and Sunday

Steps per home
  1. keep events from sensors with keep=yes in sensor_inventory.csv and a
     type not excluded in audit/config.py
  2. map raw labels to shared classes (label_map.csv); 'exclude' labels give
     no vote, but their sensor events still count as activity
  3. cut time into windows (audit/config.py, 60 s); a window's label is the
     most common class among its events, with 'other' in the vote
  4. optional: keep only the first N labelled days (--cap-days)
  5. split by time: first 70% train, next 10% validation, last 20% test
  6. drop windows labelled 'other', unless --keep-other

Every home gets the same feature columns in the same order (the union over
all homes; a room a home lacks is 0), so all clients share one model input.

Usage (from DUC/pipeline, with the shared .venv active)
  python build_dataset.py --cap-days 60                 # main runs  -> cap60_noother
  python build_dataset.py --cap-days 60 --keep-other    # secondary  -> cap60_other
  python build_dataset.py                               # full volume (RQ2) -> full_noother
  python build_dataset.py --cap-days 60 --context       # with context features -> cap60_noother_ctx
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import settings as S
import windows as W


def home_windows(home: str, inv: pd.DataFrame, lm: dict[str, str], window_s: int,
                 cap_days: int | None, keep_other: bool, context: bool = False) -> tuple[pd.DataFrame, dict]:
    ev = pd.read_parquet(S.EVENTS_DIR / f"{home}.parquet",
                         columns=["sensor", "sensor_type", "loc1", "activity", "ts"])
    ev["sensor"] = ev["sensor"].astype(str)
    ev["loc1"] = ev["loc1"].fillna("").astype(str).str.strip()
    n_raw = len(ev)

    # 1. Kept sensors only, matched on sensor, type and location.
    reg = W.device_registry(inv, home)
    ev["feature"] = [reg.get(k) for k in zip(ev["sensor"], ev["sensor_type"], ev["loc1"])]
    ev = ev.dropna(subset=["feature"])

    # 2. Shared labels; 'exclude' gives no vote.
    ev["label"] = [W.shared_label(a, lm) for a in ev["activity"]]
    ev["window_start"] = ev["ts"].dt.floor(f"{window_s}s")

    # 3. Window labels: majority vote, 'other' included, ties broken alphabetically.
    lab = ev.dropna(subset=["label"])
    votes = lab.groupby(["window_start", "label"]).size().rename("n").reset_index()
    votes = (votes.sort_values(["window_start", "n", "label"], ascending=[True, False, True])
             .drop_duplicates("window_start", keep="first"))
    win = votes[["window_start", "label"]]

    # Features: event counts per (type, room) in each window, from all kept events.
    counts = ev.groupby(["window_start", "feature"]).size().unstack(fill_value=0)
    if context:
        counts = counts.join(W.add_context(counts))
    win = win.merge(counts, left_on="window_start", right_index=True, how="left")
    days_before = win["window_start"].dt.normalize().nunique()

    # 4-6. Cap, time split, drop 'other': shared with the gateways.
    win = W.finalize(win, cap_days, keep_other)
    info = {"events_raw": int(n_raw), "events_kept": int(len(ev)),
            "labelled_days": int(days_before),
            "days_used": int(win["window_start"].dt.normalize().nunique())}
    return win, info


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cap-days", type=int, default=None,
                    help="keep only each home's first N labelled days (main runs: 60)")
    ap.add_argument("--context", action="store_true",
                    help="add context features: events in the previous 5 and 15 minutes, "
                         "minutes since the last event, number of active sensors")
    ap.add_argument("--keep-other", action="store_true",
                    help="keep 'other' windows as an extra class (secondary run)")
    ap.add_argument("--homes", nargs="*", help="default: mappings/selected_homes.txt, else all")
    ap.add_argument("--name", help="output folder name (default from the options)")
    args = ap.parse_args()

    lm = S.load_label_map()
    if not lm:
        sys.exit("label_map.csv is missing or empty.")
    if not S.INVENTORY.exists():
        sys.exit(f"{S.INVENTORY} not found. Run the audit's inventory.py first.")
    inv = W.load_inventory()
    if args.homes:
        homes = args.homes
    elif S.SELECTED_HOMES.exists():
        homes = S.SELECTED_HOMES.read_text().split()
    else:
        homes = sorted(p.stem for p in S.EVENTS_DIR.glob("*.parquet"))
        print("No selected_homes.txt; using every parsed home.")
    missing = [h for h in homes if not (S.EVENTS_DIR / f"{h}.parquet").exists()]
    if missing:
        sys.exit(f"No parsed events for: {', '.join(missing)}")

    name = args.name or (f"cap{args.cap_days}" if args.cap_days else "full") + \
        ("_other" if args.keep_other else "_noother") + ("_ctx" if args.context else "")
    out = S.PROCESSED_DIR / name
    out.mkdir(parents=True, exist_ok=True)

    frames, infos = {}, {}
    for h in homes:
        frames[h], infos[h] = home_windows(h, inv, lm, S.WINDOW_SECONDS,
                                           args.cap_days, args.keep_other, args.context)
        f = frames[h]
        print(f"{h}: {len(f):>7} windows  "
              f"(train {int((f.split == 'train').sum())}, val {int((f.split == 'val').sum())}, "
              f"test {int((f.split == 'test').sum())}), {infos[h]['days_used']} days")

    # One shared column layout for every home.
    time_cols = W.TIME_FEATURES
    features = W.feature_order(c for f in frames.values() for c in f.columns)
    classes = sorted({l for f in frames.values() for l in f["label"].unique()} - {"other"})
    if args.keep_other:
        classes.append("other")
    for h, f in frames.items():
        frames[h] = W.to_schema(f, h, features, classes)
        frames[h].to_parquet(out / f"{h}.parquet", index=False)

    counts = {h: {s: int((f.split == s).sum()) for s in ("train", "val", "test")}
              for h, f in frames.items()}
    schema = {
        "name": name, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_seconds": S.WINDOW_SECONDS, "splits": list(S.SPLITS),
        "cap_days": args.cap_days, "keep_other": args.keep_other, "context": args.context,
        "homes": homes, "classes": classes, "features": features, "time_features": time_cols,
        "windows": counts, "home_info": infos,
    }
    (out / "schema.json").write_text(json.dumps(schema, indent=2))

    tot = {s: sum(c[s] for c in counts.values()) for s in ("train", "val", "test")}
    n_count = sum(c.startswith("n_") for c in features)
    print(f"\n{len(homes)} homes, {len(classes)} classes, {n_count} count features, "
          f"{len(features) - n_count} context features, {len(time_cols)} time features")
    print(f"Windows: train {tot['train']}, val {tot['val']}, test {tot['test']}")
    print(f"Written to {out}")


if __name__ == "__main__":
    main()
