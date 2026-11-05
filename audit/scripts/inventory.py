"""List every raw activity label and every sensor across homes, so you can
build the two mappings the audit needs.

Writes
  mappings/raw_labels.csv        each raw label: how many homes use it,
                                 its current shared label, mapped or not
  mappings/sensor_inventory.csv  each sensor per home with a 'room' column to
                                 fill in (pre-filled from the data where the
                                 release has location fields). If you have
                                 already edited this file, the new listing is
                                 written to sensor_inventory_latest.csv instead.

Usage
  python scripts/inventory.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402
from scripts.utils import load_label_map  # noqa: E402


def main() -> None:
    paths = sorted(config.EVENTS_DIR.glob("*.parquet"))
    if not paths:
        sys.exit("No parsed homes found. Run scripts/parse_casas.py first.")
    config.MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)
    frames = [pd.read_parquet(p, columns=["home", "sensor", "sensor_type", "loc1",
                                          "loc2", "activity"]) for p in paths]
    ev = pd.concat(frames, ignore_index=True)

    # Labels
    lm = load_label_map()
    lab = ev.dropna(subset=["activity"])
    labels = (lab.groupby("activity")
              .agg(n_homes=("home", "nunique"), n_events=("home", "size"),
                   homes=("home", lambda h: ";".join(sorted(set(h)))))
              .reset_index().rename(columns={"activity": "raw_label"}))
    labels["shared_label"] = labels["raw_label"].str.lower().map(lm)
    labels["status"] = labels["shared_label"].notna().map({True: "mapped", False: "UNMAPPED"})
    labels = labels.sort_values(["status", "n_homes", "n_events"], ascending=[True, False, False])
    labels.to_csv(config.MAPPINGS_DIR / "raw_labels.csv", index=False)

    unmapped = labels[labels["status"] == "UNMAPPED"]
    print(f"{len(labels)} raw labels across {ev['home'].nunique()} homes; "
          f"{len(unmapped)} not yet in mappings/label_map.csv")
    if len(unmapped):
        print(unmapped[["raw_label", "n_homes", "n_events"]].head(40).to_string(index=False))

    # Sensors
    sens = (ev.groupby(["home", "sensor", "sensor_type", "loc1", "loc2"], dropna=False)
            .size().rename("n_events").reset_index())
    loc = sens["loc1"].fillna("").astype(str)
    sens["room"] = loc.where(~loc.str.lower().isin(["", "ignore", "nan", "none"]), "")
    sens["keep"] = (~sens["sensor_type"].isin(config.SYSTEM_SENSOR_TYPES)).map({True: "yes", False: "no"})
    sens["note"] = ""
    target = config.MAPPINGS_DIR / "sensor_inventory.csv"
    if target.exists():
        target = config.MAPPINGS_DIR / "sensor_inventory_latest.csv"
        print(f"\nsensor_inventory.csv already exists (your edits are kept); "
              f"new listing in {target.name}")
    sens.to_csv(target, index=False)
    empty_rooms = sens[(sens["keep"] == "yes") & (sens["room"] == "")]
    print(f"\n{len(sens)} sensors; {len(empty_rooms)} kept sensors still need a room "
          f"(fill 'room' from the floor plans).")


if __name__ == "__main__":
    main()
