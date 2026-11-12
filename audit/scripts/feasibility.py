"""Can each home be a federated client? Count labelled windows per shared
class in each home's train, validation and test periods.

Steps per home
  1. drop housekeeping events (battery, radio) and sensors marked keep=no
     in mappings/sensor_inventory.csv, if that file exists
  2. map raw labels to shared labels with mappings/label_map.csv
  3. cut time into non-overlapping windows (config.WINDOW_SECONDS); a window's
     label is the most common shared label among its labelled events
  4. split each home's labelled windows by time: earliest 70% train,
     next 10% validation, last 20% test
  5. with --drop-other, drop windows labelled 'other' (after steps 3 and 4,
     so labels and split periods are the same in both settings)
  6. count windows per class and split

Then
  * a class is kept if enough homes have it in their test period
  * a home passes if it has enough kept classes in its test period

Writes reports/feasibility_counts.csv, reports/class_presence.csv,
reports/home_decisions.csv and reports/feasibility.md. The decisions are a
PROPOSAL: review them, then record the final choice in the audit report.

Usage
  python scripts/feasibility.py
  python scripts/feasibility.py --drop-other      # drop windows labelled 'other'
  python scripts/feasibility.py --window 120
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402
from scripts.utils import EXCLUDE, load_label_map, md_table  # noqa: E402


def dropped_sensors() -> set[tuple[str, str]]:
    path = config.MAPPINGS_DIR / "sensor_inventory.csv"
    if not path.exists():
        return set()
    inv = pd.read_csv(path)
    inv = inv[inv["keep"].astype(str).str.lower().str.strip() == "no"]
    return set(zip(inv["home"].astype(str), inv["sensor"].astype(str)))


def windows_for_home(df: pd.DataFrame, lm: dict[str, str], window_s: int,
                     drop_other: bool, drop: set[tuple[str, str]]) -> tuple[pd.DataFrame, list[str]]:
    home = df["home"].iat[0]
    df = df[~df["sensor_type"].isin(config.SYSTEM_SENSOR_TYPES)]
    if drop:
        df = df[[(home, s) not in drop for s in df["sensor"].astype(str)]]
    raw = df["activity"].dropna().unique()
    unmapped = sorted(r for r in raw if str(r).lower() not in lm)
    shared = df["activity"].str.lower().map(lm)
    shared = shared.where(shared != EXCLUDE)
    df = df.assign(label=shared, window=df["ts"].dt.floor(f"{window_s}s"))

    # Label every window with 'other' still in the vote, so a minute that is
    # mostly 'other' stays 'other' instead of taking a minority label.
    lab = df.dropna(subset=["label"])
    counts = lab.groupby(["window", "label"]).size().rename("n").reset_index()
    counts = (counts.sort_values(["window", "n", "label"], ascending=[True, False, True])
              .drop_duplicates("window", keep="first"))
    win = counts[["window", "label"]].sort_values("window").reset_index(drop=True)

    # Split before dropping 'other', so both settings share the same periods.
    n = len(win)
    a, b = int(n * config.SPLITS[0]), int(n * (config.SPLITS[0] + config.SPLITS[1]))
    win["split"] = ["train"] * a + ["val"] * (b - a) + ["test"] * (n - b)
    if drop_other:
        win = win[win["label"] != "other"].reset_index(drop=True)
    win.insert(0, "home", home)
    return win, unmapped


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--window", type=int, default=config.WINDOW_SECONDS)
    ap.add_argument("--drop-other", action="store_true")
    ap.add_argument("--homes", nargs="*")
    args = ap.parse_args()

    lm = load_label_map()
    if not lm:
        sys.exit("mappings/label_map.csv is missing or empty.")
    paths = sorted(config.EVENTS_DIR.glob("*.parquet"))
    if args.homes:
        paths = [p for p in paths if p.stem in set(args.homes)]
    if not paths:
        sys.exit("No parsed homes found. Run scripts/parse_casas.py first.")

    drop = dropped_sensors()
    all_win, unmapped_by_home = [], {}
    for p in paths:
        win, unmapped = windows_for_home(pd.read_parquet(p), lm, args.window,
                                         args.drop_other, drop)
        all_win.append(win)
        if unmapped:
            unmapped_by_home[p.stem] = unmapped
    win = pd.concat(all_win, ignore_index=True)
    homes = sorted(win["home"].unique())

    counts = (win.groupby(["home", "split", "label"]).size().rename("windows")
              .reset_index())
    counts.to_csv(config.REPORTS_DIR / "feasibility_counts.csv", index=False)

    test = counts[counts["split"] == "test"].pivot(index="home", columns="label",
                                                   values="windows").fillna(0).astype(int)
    test = test.reindex(homes, fill_value=0)
    present = test >= config.MIN_TEST_WINDOWS_PER_CLASS
    presence = pd.DataFrame({
        "homes_with_class": present.sum(),
        "share_of_homes": (present.mean()).round(2),
        "total_test_windows": test.sum(),
    })
    presence["keep_class"] = presence["share_of_homes"] >= config.MIN_HOME_SHARE_FOR_CLASS
    presence = presence.sort_values("share_of_homes", ascending=False)
    presence.rename_axis("class").reset_index().to_csv(
        config.REPORTS_DIR / "class_presence.csv", index=False)
    kept = list(presence.index[presence["keep_class"]])

    tot = win.groupby(["home", "split"]).size().unstack(fill_value=0)
    dec = pd.DataFrame(index=homes)
    dec["train_windows"] = tot.get("train", 0)
    dec["test_windows"] = tot.get("test", 0)
    dec["kept_classes_in_test"] = present[kept].sum(axis=1) if kept else 0
    dec["missing_kept_classes"] = [", ".join(c for c in kept if not present.at[h, c])
                                   for h in homes]
    dec["passes"] = dec["kept_classes_in_test"] >= config.MIN_CLASSES_PER_HOME
    summary_path = config.REPORTS_DIR / "home_summary.csv"
    if summary_path.exists():
        s = pd.read_csv(summary_path).set_index("home")
        dec = dec.join(s[["labelled_days", "label_coverage_events"]])
        ok_days = dec["labelled_days"] >= config.MIN_LABELLED_DAYS
        ok_cov = dec["label_coverage_events"] >= config.MIN_LABEL_COVERAGE
        dec["passes"] = dec["passes"] & ok_days & ok_cov
    dec = dec.rename_axis("home").reset_index()
    dec.to_csv(config.REPORTS_DIR / "home_decisions.csv", index=False)

    lines = ["# Feasibility", "",
             f"Window {args.window} s, splits {config.SPLITS}, a class counts in a home "
             f"if its test period has at least {config.MIN_TEST_WINDOWS_PER_CLASS} windows. "
             + ("Windows labelled 'other' (majority vote with 'other' included) dropped "
                "after the split." if args.drop_other else "'other' kept as a class."), "",
             "## Classes", "",
             f"Kept if present in at least {config.MIN_HOME_SHARE_FOR_CLASS:.0%} of homes.", "",
             md_table(presence.rename_axis("class").reset_index()), "",
             "## Homes", "",
             f"A home passes with at least {config.MIN_CLASSES_PER_HOME} kept classes in its "
             "test period (and the day and coverage thresholds, if profiled).", "",
             md_table(dec), ""]
    if unmapped_by_home:
        lines += ["## Unmapped labels (treated as unlabelled)", ""]
        lines += [f"- **{h}**: {', '.join(u)}" for h, u in unmapped_by_home.items()]
    (config.REPORTS_DIR / "feasibility.md").write_text("\n".join(lines) + "\n")

    print(presence.to_string())
    print()
    print(dec[["home", "train_windows", "test_windows", "kept_classes_in_test",
               "passes"]].to_string(index=False))
    print(f"\n{int(dec['passes'].sum())} of {len(dec)} homes pass. "
          f"Details in {config.REPORTS_DIR / 'feasibility.md'}")
    if unmapped_by_home:
        print("Unmapped labels found; run scripts/inventory.py and update label_map.csv.")


if __name__ == "__main__":
    main()
