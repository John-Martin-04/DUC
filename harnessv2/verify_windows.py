"""Check that each gateway built exactly the rows of the offline dataset.

Compares a gateway's local store (windows cut from the live stream) with
data/processed/<dataset>/<home>.parquet (built offline from the same events):
same windows, labels, splits and feature values. A full replay is needed; a
partial one (--days) cannot match.

Usage (from DUC/harness)
  python verify_windows.py --dataset ../data/processed/cap60_noother --homes csh101 csh102 --wait
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

import hconfig as H
from gateway import load_frame


def ingest_info(home: str, wait: float) -> dict | None:
    db, end = H.GATEWAY_DIR / f"{home}.sqlite", time.time() + wait
    while True:
        try:
            with sqlite3.connect(db) as con:
                row = con.execute("select value from meta where key='ingest_done'").fetchone()
            if row:
                return json.loads(row[0])
        except sqlite3.Error:
            pass
        if time.time() >= end:
            return None
        time.sleep(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--homes", nargs="+", required=True)
    ap.add_argument("--wait", nargs="?", type=float, const=3600, default=0,
                    help="wait up to this many seconds for the replay to finish")
    args = ap.parse_args()
    schema = json.loads((args.dataset / "schema.json").read_text())

    failed = 0
    for h in args.homes:
        info = ingest_info(h, args.wait)
        if info is None:
            print(f"{h}: FAIL  the gateway has not finished ingesting")
            failed += 1
            continue
        with sqlite3.connect(H.GATEWAY_DIR / f"{h}.sqlite") as con:
            live = load_frame(con, h, schema)
        offline = pd.read_parquet(args.dataset / f"{h}.parquet")
        try:
            pd.testing.assert_frame_equal(live, offline, check_dtype=False)
            print(f"{h}: PASS  {len(live)} rows identical "
                  f"({info['events']} events, {info['duplicates']} duplicates, {info['late']} late)")
        except AssertionError as e:
            failed += 1
            both = live.merge(offline, on="window_start", how="outer", suffixes=("_live", "_off"), indicator=True)
            print(f"{h}: FAIL  live {len(live)} rows, offline {len(offline)}; "
                  f"only live {(both._merge == 'left_only').sum()}, only offline "
                  f"{(both._merge == 'right_only').sum()}, {info['late']} late events")
            print("   ", str(e).splitlines()[0])
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
