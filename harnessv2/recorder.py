"""Record everything that crosses the household boundary.

Subscribes to the whole federation broker and logs one line per message:
time, topic, kind, round, home, payload size and a hash. This is the measured
communication cost, and the record of what an honest-but-curious server could
see. --save-payloads also keeps the message bodies, for later analysis.

The broker's own byte counters ($SYS) are logged too; they include MQTT
protocol overhead, so they check the application-level numbers.

Writes results/harness/<run>/traffic.csv and traffic_summary.md when stopped.

Usage (from DUC/harness)
  python recorder.py --run pilot
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import signal
import threading
import time
from collections import defaultdict

import hconfig as H


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="results folder name; use the scenario's name")
    ap.add_argument("--save-payloads", action="store_true")
    args = ap.parse_args()

    out = H.RESULTS_DIR / args.run
    out.mkdir(parents=True, exist_ok=True)
    if args.save_payloads:
        (out / "payloads").mkdir(exist_ok=True)
    f = open(out / "traffic.csv", "w", newline="")
    w = csv.writer(f)
    w.writerow(["time", "topic", "kind", "round", "home", "payload_bytes", "retained", "sha256"])
    totals = defaultdict(lambda: [0, 0])          # kind -> [messages, bytes]
    sys_stats: dict[str, str] = {}
    lock, n = threading.Lock(), [0]

    def on_message(c, u, m) -> None:
        if m.topic.startswith("$SYS/"):
            sys_stats[m.topic] = m.payload.decode(errors="replace")
            return
        p = m.topic.split("/")
        kind = p[1] if p[1] != "round" else p[3]
        rnd = p[2] if p[1] == "round" else ""
        home = p[4] if p[1] == "round" else (p[2] if p[1] == "status" else "")
        digest = hashlib.sha256(m.payload).hexdigest()[:16]
        with lock:
            w.writerow([f"{time.time():.3f}", m.topic, kind, rnd, home, len(m.payload), int(m.retain), digest])
            if not m.retain:
                totals[kind][0] += 1
                totals[kind][1] += len(m.payload)
            n[0] += 1
            if args.save_payloads:
                (out / "payloads" / f"{n[0]:06d}_{kind}_{rnd}_{home}.bin").write_bytes(m.payload)

    c = H.client("recorder")
    c.on_connect = lambda c, u, fl, rc, p: c.subscribe(
        [("fl/#", 1), ("$SYS/broker/bytes/#", 0), ("$SYS/broker/messages/#", 0)])
    c.on_message = on_message
    c.connect(*H.addr(H.FED_BROKER), keepalive=60)
    c.loop_start()
    print("recording federation traffic", flush=True)

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *a: stop.set())
    try:
        while not stop.wait(1):
            pass
    except KeyboardInterrupt:
        pass
    time.sleep(2.5)                               # one more $SYS interval
    c.loop_stop()
    c.disconnect()
    f.close()

    lines = [f"# Federation traffic: {args.run}", "",
             "Everything that crossed the household boundary. Payload bytes, without MQTT overhead; "
             "retained re-deliveries excluded.", "",
             "| kind | direction | messages | payload_bytes |", "|---|---|---|---|"]
    direction = {"global": "server to homes (one publish; multiply by receivers)", "update": "home to server",
                 "metrics": "home to server", "status": "home to server"}
    for kind in sorted(totals):
        lines.append(f"| {kind} | {direction.get(kind, '')} | {totals[kind][0]} | {totals[kind][1]} |")
    lines += ["", "Kinds seen: " + ", ".join(sorted(totals)) + ". No sensor events, windows or labels.",
              "", "Broker counters, including protocol overhead (since the broker started):", ""]
    for k in sorted(sys_stats):
        lines.append(f"- `{k}`: {sys_stats[k]}")
    (out / "traffic_summary.md").write_text("\n".join(lines) + "\n")
    print(f"Written to {out}")


if __name__ == "__main__":
    main()
