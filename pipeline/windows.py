"""Window rules shared by the offline dataset (build_dataset.py) and the live
gateways (harness/gateway.py). Both import these functions, so a gateway that
windows a stream must end up with exactly the rows the offline build produced.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

import settings as S

TIME_FEATURES = ["tod_sin", "tod_cos", "weekend"]


def clean(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(name)).strip("_") or "unknown"


def feature_name(sensor_type: str, room: str) -> str:
    return "n_" + clean(sensor_type) + "__" + clean(room)


def load_inventory() -> pd.DataFrame:
    inv = pd.read_csv(S.INVENTORY, dtype=str, keep_default_na=False)
    for c in ("home", "sensor", "sensor_type", "loc1", "room", "keep"):
        inv[c] = inv[c].str.strip()
    inv["keep"] = inv["keep"].str.lower()
    return inv


def device_registry(inv: pd.DataFrame, home: str) -> dict[tuple[str, str, str], str]:
    """One home's kept sensors: (sensor, type, location) -> feature column.

    A sensor is kept with keep=yes in sensor_inventory.csv and a type not
    excluded in audit/config.py. The room is the inventory's room, or the
    source location when that is blank."""
    kept = inv[(inv["home"] == home) & (inv["keep"] == "yes")]
    kept = kept[~kept["sensor_type"].isin(S.SYSTEM_SENSOR_TYPES)]
    reg = {}
    for r in kept.itertuples(index=False):
        reg.setdefault((r.sensor, r.sensor_type, r.loc1),
                       feature_name(r.sensor_type, r.room or r.loc1))
    return reg


def shared_label(raw, label_map: dict[str, str]) -> str | None:
    """Raw activity -> shared class; None when unlabelled, unmapped or 'exclude'."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    lab = label_map.get(str(raw).lower())
    return None if lab is None or lab == S.EXCLUDE else lab


def majority(votes: dict[str, int]) -> str:
    """Most common label; ties go to the alphabetically first."""
    return min(votes, key=lambda k: (-votes[k], k))


def finalize(win: pd.DataFrame, cap_days: int | None, keep_other: bool) -> pd.DataFrame:
    """Labelled windows (window_start, label, feature counts) -> dataset rows.

    Order matters and is the same everywhere: cap to the first N labelled
    days, split by time, then drop 'other'. Adds the time features."""
    win = win.sort_values("window_start").reset_index(drop=True)
    if cap_days:
        days = win["window_start"].dt.normalize()
        win = win[days.isin(np.sort(days.unique())[:cap_days])].reset_index(drop=True)
    n = len(win)
    a, b = int(n * S.SPLITS[0]), int(n * (S.SPLITS[0] + S.SPLITS[1]))
    win["split"] = ["train"] * a + ["val"] * (b - a) + ["test"] * (n - b)
    if not keep_other:
        win = win[win["label"] != "other"].reset_index(drop=True)
    minute = win["window_start"].dt.hour * 60 + win["window_start"].dt.minute
    win["tod_sin"] = np.sin(2 * np.pi * minute / 1440).astype("float32")
    win["tod_cos"] = np.cos(2 * np.pi * minute / 1440).astype("float32")
    win["weekend"] = (win["window_start"].dt.dayofweek >= 5).astype("int8")
    return win


def to_schema(win: pd.DataFrame, home: str, features: list[str], classes: list[str]) -> pd.DataFrame:
    """Give a home's rows the shared column layout and class index."""
    index = {c: i for i, c in enumerate(classes)}
    f = win.reindex(columns=["window_start", "split", "label"] + features + TIME_FEATURES)
    f[features] = f[features].fillna(0).astype("int32")
    f.insert(0, "home", home)
    f.insert(4, "y", f["label"].map(index).astype("int16"))
    return f
