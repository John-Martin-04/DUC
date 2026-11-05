"""Parse raw CASAS event files into one tidy table per home.

It reads the two layouts you will meet:

  UCI release (dataset 506), 8 fields per line:
      date time sensor location1 location2 message sensor_type activity
  Classic CASAS / Zenodo release (Aruba, Milan, ...), 4 or 6 fields per line:
      date time sensor value [label begin|end]

The layout is detected per file. Output: data/interim/events/<home>.parquet
with one row per event, plus reports/parse_log.csv with what went wrong.

Usage
  python scripts/parse_casas.py FILE [FILE ...]
  python scripts/parse_casas.py --glob "data/raw/uci/**/*.ann.txt"
  python scripts/parse_casas.py --home aruba data/raw/zenodo/aruba/data
  python scripts/parse_casas.py --format classic FILE     # override detection
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

MARKERS = {"begin", "end"}
GENERIC_STEMS = {"data", "annotated", "ann", "events", "rawdata"}

# Classic files encode the sensor type in the ID prefix. This mapping is a
# heuristic: check it against the dataset documentation for each home.
CLASSIC_PREFIX_TYPES = {
    "M": "motion",
    "MA": "motion_area",
    "D": "door",
    "T": "temperature",
    "L": "light",
    "LL": "light",
    "LS": "light_sensor",
    "I": "item",
    "AD": "analog",
    "E": "electricity",
    "BATP": "battery",
    "BATV": "battery",
}

UCI_TYPE_ALIASES = {
    "motionarea": "motion_area",
    "lightsensor": "light_sensor",
    "batterypercent": "battery",
    "battery": "battery",
    "radio": "radio",
}


def home_name(path: Path) -> str:
    stem = path.name.split(".")[0]
    if stem.lower() in GENERIC_STEMS:
        stem = path.parent.name
    return re.sub(r"[^a-z0-9_-]+", "_", stem.lower()).strip("_") or "home"


def detect_format(path: Path, probe: int = 300) -> str:
    counts = {"uci": 0, "classic": 0}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            tokens = line.split()
            if len(tokens) < 4:
                continue
            if len(tokens) >= 7 and "-" in tokens[6]:
                counts["uci"] += 1
            else:
                counts["classic"] += 1
            if sum(counts.values()) >= probe:
                break
    return "uci" if counts["uci"] > counts["classic"] else "classic"


def classic_type(sensor: str) -> str:
    m = re.match(r"^([A-Za-z]+)\d", sensor)
    prefix = m.group(1).upper() if m else sensor.upper()
    return CLASSIC_PREFIX_TYPES.get(prefix, "unknown")


def uci_type(raw: str) -> str:
    t = raw.lower()
    t = t.split("-", 1)[1] if "-" in t else t
    return UCI_TYPE_ALIASES.get(t, t)


def parse_file(path: Path, home: str, fmt: str) -> tuple[pd.DataFrame, dict]:
    log = {"home": home, "file": str(path), "format": fmt, "lines": 0,
           "bad_lines": 0, "unmatched_end": 0, "unclosed_begin": 0,
           "repeated_begin": 0, "point_labels": 0}
    rows = []
    open_labels: list[str] = []

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line_no, line in enumerate(fh, start=1):
            tokens = line.split()
            if not tokens:
                continue
            log["lines"] += 1
            if len(tokens) < 4:
                log["bad_lines"] += 1
                continue
            ts = f"{tokens[0]} {tokens[1]}"
            sensor = tokens[2]

            if fmt == "uci":
                if len(tokens) < 7:
                    log["bad_lines"] += 1
                    continue
                activity = "_".join(tokens[7:]) or None
                rows.append((line_no, ts, sensor, tokens[5], tokens[6],
                             uci_type(tokens[6]), tokens[3], tokens[4],
                             activity, False))
                continue

            # classic layout: track begin/end markers in file order
            value = tokens[3]
            rest = tokens[4:]
            marker, label = None, None
            if rest and rest[-1].lower() in MARKERS:
                marker = rest[-1].lower()
                label = "_".join(rest[:-1]) or None
            elif rest:
                label = "_".join(rest)

            if marker == "begin" and label:
                if label in open_labels:  # begun again without an end
                    open_labels.remove(label)
                    log["repeated_begin"] += 1
                open_labels.append(label)
                activity = label
            elif marker == "end" and label:
                activity = label
                match = [i for i, l in enumerate(open_labels) if l == label] or \
                        [i for i, l in enumerate(open_labels) if l.lower() == label.lower()]
                if match:
                    open_labels.pop(match[-1])
                else:
                    log["unmatched_end"] += 1
            elif label:
                activity = label
                log["point_labels"] += 1
            else:
                activity = open_labels[-1] if open_labels else None
            overlap = len(open_labels) > 1
            rows.append((line_no, ts, sensor, value, "", classic_type(sensor),
                         "", "", activity, overlap))

    log["unclosed_begin"] = len(open_labels)
    df = pd.DataFrame(rows, columns=["line_no", "ts_raw", "sensor", "value",
                                     "sensor_type_raw", "sensor_type", "loc1",
                                     "loc2", "activity", "overlap"])
    df["ts"] = pd.to_datetime(df["ts_raw"], format="mixed", errors="coerce")
    bad_ts = int(df["ts"].isna().sum())
    log["bad_lines"] += bad_ts
    df = df[df["ts"].notna()].drop(columns="ts_raw")

    log["out_of_order"] = int((df["ts"].diff() < pd.Timedelta(0)).sum())
    df = df.sort_values(["ts", "line_no"], kind="stable").reset_index(drop=True)
    df["value_num"] = pd.to_numeric(df["value"], errors="coerce")
    df.insert(0, "home", home)
    log["events"] = len(df)
    return df, log


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--glob", help="glob pattern for input files (quote it)")
    ap.add_argument("--home", help="home name, only with a single file")
    ap.add_argument("--format", choices=["auto", "uci", "classic"], default="auto")
    args = ap.parse_args()

    files = list(args.files)
    if args.glob:
        files += [Path(p) for p in glob.glob(args.glob, recursive=True)]
    files = [f for f in files if f.is_file()]
    if not files:
        ap.error("no input files found")
    if args.home and len(files) != 1:
        ap.error("--home works with exactly one file")

    config.EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    logs = []
    for path in sorted(files):
        home = args.home or home_name(path)
        fmt = detect_format(path) if args.format == "auto" else args.format
        df, log = parse_file(path, home, fmt)
        out = config.EVENTS_DIR / f"{home}.parquet"
        df.to_parquet(out, index=False)
        logs.append(log)
        print(f"{home:<12} {fmt:<8} {log['events']:>9,} events  "
              f"bad={log['bad_lines']} unmatched_end={log['unmatched_end']} "
              f"unclosed_begin={log['unclosed_begin']} -> {out.name}")

    log_path = config.REPORTS_DIR / "parse_log.csv"
    new = pd.DataFrame(logs)
    if log_path.exists():
        old = pd.read_csv(log_path)
        new = pd.concat([old[~old["home"].isin(new["home"])], new])
    new.sort_values("home").to_csv(log_path, index=False)
    print(f"\nParse log: {log_path}")


if __name__ == "__main__":
    main()
