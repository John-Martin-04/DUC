"""Replay CASAS homes as live sensor streams on the home broker.

This is the CASAS adapter: it translates the audit's parsed events into the
standard event format and publishes them in file order, as a sensor network
would. Sensor events go to home/<id>/events; the activity annotations go to
home/<id>/labels, because a real gateway would not get labels from sensors.

Timing: --speed is event-seconds per wall-second (3600 = one hour of data per
second). 0 means as fast as the rate cap allows. Gateways window by the time
inside each event, so speed never changes the result.

Also writes results/harness/replay_bytes.csv: the payload bytes published per
home, which is what uploading the raw data to a central server would cost.

Usage (from DUC/harness)
  python replay.py --homes csh101 csh102 --speed 0
  python replay.py --homes csh101 --days 3 --speed 3600
"""

from __future__ import annotations

import argparse
import sqlite3
import threading
import time
import uuid

import pandas as pd

import hconfig as H
import messages as M


def wait_ready(home: str, timeout: float) -> None:
    """Wait until the home's gateway has subscribed (it marks its local store)."""
    db, end = H.GATEWAY_DIR / f"{home}.sqlite", time.time() + timeout
    while time.time() < end:
        try:
            with sqlite3.connect(db) as con:
                if con.execute("select 1 from meta where key='ready'").fetchone():
                    time.sleep(0.5)
                    return
        except sqlite3.Error:
            pass
        time.sleep(0.3)
    raise SystemExit(f"{home}: gateway not ready after {timeout:.0f} s. Start gateway.py first.")


def replay_home(home: str, args, stream: str, out: dict) -> None:
    ev = pd.read_parquet(H.S.EVENTS_DIR / f"{home}.parquet",
                         columns=["sensor", "sensor_type", "loc1", "value", "activity", "ts"])
    if args.days:
        ev = ev[ev["ts"] < ev["ts"].min().normalize() + pd.Timedelta(days=args.days)]
    t_us = (ev["ts"].astype("int64") // 1000).to_numpy()
    sensor = ev["sensor"].astype(str).to_numpy()
    stype = ev["sensor_type"].astype(str).to_numpy()
    loc = ev["loc1"].fillna("").astype(str).str.strip().to_numpy()
    value = ev["value"].astype(object).where(ev["value"].notna(), None).to_numpy()
    activity = ev["activity"].astype(object).where(ev["activity"].notna(), None).to_numpy()

    host, port = H.home_broker(home)
    c = H.client("replay", f"replay-{home}")
    c.connect(host, port, keepalive=60)
    c.loop_start()
    t_ev, t_lab = H.T_EVENTS.format(home=home), H.T_LABELS.format(home=home)
    n_bytes, start, first = 0, time.time(), int(t_us[0])
    info = None
    for i in range(len(t_us)):
        if args.speed > 0:
            due = start + (int(t_us[i]) - first) / 1e6 / args.speed
            delay = due - time.time()
            if delay > 0:
                time.sleep(delay)
        e = M.event(stream, i, int(t_us[i]), sensor[i], stype[i], loc[i], value[i])
        l = M.label(stream, i, int(t_us[i]), activity[i])
        c.publish(t_ev, e, qos=1)
        info = c.publish(t_lab, l, qos=1)
        n_bytes += len(e) + len(l)
        if i % 500 == 499:                       # back-pressure and rate cap
            info.wait_for_publish(timeout=60)
            ahead = (i + 1) / args.max_rate - (time.time() - start)
            if ahead > 0:
                time.sleep(ahead)
    last = len(t_us) - 1
    c.publish(t_ev, M.end_of_stream(stream, last), qos=1)
    c.publish(t_lab, M.end_of_stream(stream, last), qos=1).wait_for_publish(timeout=60)
    c.loop_stop()
    c.disconnect()
    out[home] = {"home": home, "events": len(t_us), "payload_bytes": n_bytes,
                 "seconds": round(time.time() - start, 1)}
    print(f"{home}: {len(t_us)} events, {n_bytes / 1e6:.1f} MB in {out[home]['seconds']} s", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--homes", nargs="+", required=True)
    ap.add_argument("--speed", type=float, default=0, help="event-seconds per second; 0 = no pacing")
    ap.add_argument("--max-rate", type=float, default=3000, help="events per second per home, at most")
    ap.add_argument("--days", type=int, help="replay only each home's first N days")
    ap.add_argument("--no-wait", action="store_true", help="do not wait for the gateways")
    ap.add_argument("--stream", help="stream id; repeat one to test duplicate handling")
    args = ap.parse_args()

    stream = args.stream or uuid.uuid4().hex[:8]   # a new id lets gateways tell replays apart
    if not args.no_wait:
        for h in args.homes:
            wait_ready(h, 60)
    out, threads = {}, []
    for h in args.homes:
        t = threading.Thread(target=replay_home, args=(h, args, stream, out))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    H.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([out[h] for h in args.homes if h in out]).to_csv(
        H.RESULTS_DIR / "replay_bytes.csv", index=False)


if __name__ == "__main__":
    main()
