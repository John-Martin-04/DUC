"""Profile every parsed home: size, sensors, label coverage, gaps, quality.

Reads data/interim/events/*.parquet (from parse_casas.py) and writes
  reports/home_summary.csv       one row per home, the audit table
  reports/activity_by_home.csv   raw activity labels per home
  reports/sensors_by_home.csv    every sensor with its event count
  reports/audit_profile.md       readable summary with flags
  mappings/home_metadata.csv     template for facts the data cannot tell
                                 you (residents, pets): fill it in by hand

Usage
  python scripts/profile_homes.py
  python scripts/profile_homes.py --homes csh101 csh102 aruba
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402
from scripts.utils import md_table  # noqa: E402


def load_homes(names: list[str] | None) -> dict[str, pd.DataFrame]:
    paths = sorted(config.EVENTS_DIR.glob("*.parquet"))
    if names:
        paths = [p for p in paths if p.stem in set(names)]
    if not paths:
        sys.exit("No parsed homes found. Run scripts/parse_casas.py first.")
    return {p.stem: pd.read_parquet(p) for p in paths}


def episodes(df: pd.DataFrame) -> pd.DataFrame:
    """Contiguous runs of the same activity label (in time order)."""
    lab = df[["ts", "activity"]].copy()
    run = (lab["activity"] != lab["activity"].shift()).cumsum().rename("run")
    g = lab.groupby(run)
    ep = pd.DataFrame({"activity": g["activity"].first(),
                       "start": g["ts"].first(), "end": g["ts"].last()})
    ep = ep[ep["activity"].notna()]
    ep["minutes"] = (ep["end"] - ep["start"]).dt.total_seconds() / 60
    return ep


def profile(home: str, df: pd.DataFrame) -> tuple[dict, pd.DataFrame, pd.DataFrame, list[str]]:
    flags = []
    sensors_all = df
    df = df[~df["sensor_type"].isin(config.SYSTEM_SENSOR_TYPES)].copy()
    start, end = df["ts"].min(), df["ts"].max()
    span_days = (end - start).total_seconds() / 86400

    # time between consecutive events; long silences are gaps, not time
    dt = df["ts"].diff().shift(-1).dt.total_seconds().fillna(0)
    capped = dt.clip(upper=config.MAX_INTERVAL_SECONDS)
    labelled = df["activity"].notna()
    other = df["activity"].fillna("").str.lower().str.contains("other")

    gap_h = dt / 3600
    duplicates = int(df.duplicated(["ts", "sensor", "value"]).sum())
    labelled_days = df.loc[labelled, "ts"].dt.date.nunique()

    per_sensor = (sensors_all.groupby(["sensor", "sensor_type", "loc1", "loc2"], dropna=False)
                  .agg(n_events=("ts", "size"), first=("ts", "min"), last=("ts", "max"))
                  .reset_index())
    per_sensor.insert(0, "home", home)
    real = per_sensor[~per_sensor["sensor_type"].isin(config.SYSTEM_SENSOR_TYPES)]
    few = real[real["n_events"] < config.MIN_EVENTS_PER_SENSOR]
    stops_early = real[(end - real["last"]).dt.days > 7]

    ep = episodes(df)
    acts = (df[labelled].groupby("activity").size().rename("n_events").to_frame()
            .join(ep.groupby("activity").agg(n_episodes=("minutes", "size"),
                                             total_hours=("minutes", lambda m: m.sum() / 60),
                                             median_minutes=("minutes", "median")))
            .reset_index())
    acts.insert(0, "home", home)

    types = df["sensor_type"].value_counts()
    row = {
        "home": home,
        "start": start.date(), "end": end.date(), "span_days": round(span_days, 1),
        "events": len(df),
        "events_per_day": round(len(df) / max(span_days, 1e-9), 1),
        "system_events": len(sensors_all) - len(df),
        "sensors": real["sensor"].nunique(),
        "motion_sensors": int(real["sensor_type"].isin(["motion", "motion_area"]).sum()),
        "door_sensors": int((real["sensor_type"] == "door").sum()),
        "unknown_type_events": int(types.get("unknown", 0)),
        "has_locations": bool(df["loc1"].replace("", pd.NA).notna().any()),
        "label_coverage_events": round(labelled.mean(), 3),
        "label_coverage_time": round(capped[labelled].sum() / max(capped.sum(), 1), 3),
        "other_share_of_labelled": round((other & labelled).sum() / max(labelled.sum(), 1), 3),
        "labelled_days": labelled_days,
        "raw_labels": df.loc[labelled, "activity"].nunique(),
        "overlap_events": int(df["overlap"].sum()),
        "gaps_over_1h": int((gap_h > config.GAP_FLAG_HOURS[0]).sum()),
        "gaps_over_24h": int((gap_h > config.GAP_FLAG_HOURS[1]).sum()),
        "longest_gap_h": round(gap_h.max(), 1),
        "duplicate_events": duplicates,
        "sensors_few_events": len(few),
        "sensors_stop_early": len(stops_early),
    }

    if labelled_days < config.MIN_LABELLED_DAYS:
        flags.append(f"only {labelled_days} labelled days (min {config.MIN_LABELLED_DAYS})")
    if row["label_coverage_events"] < config.MIN_LABEL_COVERAGE:
        flags.append(f"label coverage {row['label_coverage_events']:.0%} "
                     f"(min {config.MIN_LABEL_COVERAGE:.0%})")
    if row["other_share_of_labelled"] > 0.5:
        flags.append(f"{row['other_share_of_labelled']:.0%} of labelled events are 'Other'")
    if row["unknown_type_events"]:
        flags.append(f"{row['unknown_type_events']} events from sensors of unknown type")
    if row["overlap_events"]:
        flags.append(f"{row['overlap_events']} events during overlapping activities")
    if row["gaps_over_24h"]:
        flags.append(f"{row['gaps_over_24h']} recording gaps over 24 h "
                     f"(longest {row['longest_gap_h']} h)")
    if len(few):
        flags.append(f"{len(few)} sensors with < {config.MIN_EVENTS_PER_SENSOR} events")
    if len(stops_early):
        flags.append(f"{len(stops_early)} sensors go silent > 7 days before the end")
    if duplicates:
        flags.append(f"{duplicates} duplicate events")
    return row, acts, per_sensor, flags


def write_metadata_template(homes: list[str]) -> None:
    path = config.MAPPINGS_DIR / "home_metadata.csv"
    cols = ["home", "residents", "pets", "source_release", "notes"]
    existing = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=cols)
    missing = [h for h in homes if h not in set(existing["home"])]
    if missing:
        add = pd.DataFrame({"home": missing})
        pd.concat([existing, add])[cols].to_csv(path, index=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--homes", nargs="*")
    args = ap.parse_args()

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    config.MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)
    rows, acts, sensors, all_flags = [], [], [], {}
    for home, df in load_homes(args.homes).items():
        row, a, s, flags = profile(home, df)
        rows.append(row), acts.append(a), sensors.append(s)
        all_flags[home] = flags

    summary = pd.DataFrame(rows)
    summary["flags"] = summary["home"].map(lambda h: len(all_flags[h]))
    summary.to_csv(config.REPORTS_DIR / "home_summary.csv", index=False)
    pd.concat(acts).to_csv(config.REPORTS_DIR / "activity_by_home.csv", index=False)
    pd.concat(sensors).to_csv(config.REPORTS_DIR / "sensors_by_home.csv", index=False)
    write_metadata_template(list(summary["home"]))

    cols = ["home", "span_days", "labelled_days", "events", "sensors",
            "label_coverage_events", "other_share_of_labelled", "raw_labels", "flags"]
    lines = ["# Audit profile", "",
             "Generated by scripts/profile_homes.py. Thresholds come from config.py.", "",
             md_table(summary[cols]), "", "## Flags per home", ""]
    for home, flags in all_flags.items():
        lines.append(f"**{home}**: " + ("; ".join(flags) if flags else "no flags"))
        lines.append("")
    lines += ["## Still to fill in by hand", "",
              "Residents and pets per home go in `mappings/home_metadata.csv`, "
              "from the dataset documentation. The data alone cannot tell you this."]
    (config.REPORTS_DIR / "audit_profile.md").write_text("\n".join(lines))
    print(summary[cols].to_string(index=False))
    print(f"\nReports written to {config.REPORTS_DIR}")


if __name__ == "__main__":
    main()
