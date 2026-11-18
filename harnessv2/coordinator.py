"""The coordination server: runs the federated rounds over the federation broker.

Each round is a fixed sequence, saved after every round so a run can resume:
  select clients -> publish the global model -> collect updates until all
  selected clients answered or the deadline passed -> aggregate (FedAvg,
  weighted by sample count) -> save

Consistency rules
  - one update per home per round; duplicates and updates from an earlier
    round or attempt are ignored
  - fewer than min_clients updates by the deadline: the round is retried
  - only clients that are online (fl/status) are selected

Every online gateway also reports the global model's score on its own test
windows each round, so results are per home without any data leaving it.

Writes results/harness/<run>/: rounds.csv, metrics.csv, checkpoint.npz, state.json

Usage (from DUC/harness)
  python coordinator.py --dataset ../data/processed/cap60_noother --scenario scenarios/pilot.json
  python coordinator.py ... --resume
"""

from __future__ import annotations

import argparse
import csv
import json
import queue
import random
import time
from pathlib import Path

import numpy as np

import hconfig as H
import messages as M
from aggregation import fedavg
from common import build_model, set_seed

DEFAULTS = {"rounds": 20, "fraction": 1.0, "local_epochs": 1, "batch_size": 128, "client_lr": 0.05,
            "deadline_s": 120, "min_clients": 2, "max_retries": 2, "dropout_p": 0.0, "seed": 0, "mu": 0.0, "class_weight": False,
            "homes": None, "personalise_epochs": 0, "personalise_div": 3.0}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, type=Path, help="folder with the shared schema.json")
    ap.add_argument("--scenario", required=True, type=Path)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--wait-clients", type=float, default=60, help="seconds to wait for gateways")
    args = ap.parse_args()

    sc = {**DEFAULTS, **json.loads(args.scenario.read_text())}
    schema = json.loads((args.dataset / "schema.json").read_text())
    homes = sc["homes"] or schema["homes"]
    run = sc.get("name", args.scenario.stem)
    out = H.RESULTS_DIR / run
    out.mkdir(parents=True, exist_ok=True)
    (out / "scenario.json").write_text(json.dumps({**sc, "dataset": schema["name"]}, indent=2))

    q: queue.Queue = queue.Queue()
    online: set[str] = set()

    def on_message(c, u, m) -> None:
        parts = m.topic.split("/")
        if parts[1] == "status":
            (online.add if m.payload == b"online" else online.discard)(parts[2])
        else:
            q.put((parts[3], int(parts[2]), parts[4], m.payload))    # kind, round, home, payload

    c = H.client("coordinator")
    c.on_connect = lambda c, u, f, rc, p: c.subscribe(
        [("fl/status/+", 1), ("fl/round/+/update/+", 1), ("fl/round/+/metrics/+", 1)])
    c.on_message = on_message
    c.connect(*H.addr(H.FED_BROKER), keepalive=60)
    c.loop_start()

    end = time.time() + args.wait_clients
    while time.time() < end and not set(homes) <= online:
        time.sleep(0.5)
    print(f"{run}: {len(online & set(homes))} of {len(homes)} gateways online", flush=True)
    if len(online & set(homes)) < sc["min_clients"]:
        raise SystemExit("Too few gateways online. Start gateway.py and the brokers first.")

    # Initial model, or the last saved one.
    start = 1
    if args.resume and (out / "state.json").exists():
        start = json.loads((out / "state.json").read_text())["next_round"]
        with np.load(out / "checkpoint.npz") as z:
            weights = [z[k] for k in sorted(z.files, key=lambda k: int(k[1:]))]
        for name in ("rounds.csv", "metrics.csv"):          # drop rows from the resumed round on
            if (out / name).exists():
                rows = list(csv.DictReader(open(out / name)))
                keep = [r for r in rows if int(r["round"]) < start]
                with open(out / name, "w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [])
                    if rows:
                        w.writeheader()
                        w.writerows(keep)
        print(f"resuming at round {start}")
    else:
        set_seed(sc["seed"])
        weights = build_model(len(schema["features"]) + len(schema["time_features"]),
                              len(schema["classes"])).get_weights()
        for name in ("rounds.csv", "metrics.csv"):
            (out / name).unlink(missing_ok=True)
    rng = random.Random(sc["seed"] * 1000 + start)

    def append(name: str, row: dict) -> None:
        new = not (out / name).exists()
        with open(out / name, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row))
            if new:
                w.writeheader()
            w.writerow(row)

    def publish(rnd: int, attempt: int, phase: str, selected: list[str]) -> int:
        payload = M.pack({"run": run, "round": rnd, "attempt": attempt, "phase": phase,
                          "selected": selected, "local_epochs": sc["local_epochs"],
                          "batch_size": sc["batch_size"], "client_lr": sc["client_lr"],
                          "dropout_p": sc["dropout_p"], "seed": sc["seed"], "mu": sc["mu"],
                          "class_weight": sc["class_weight"],
                          "deadline_s": sc["deadline_s"],
                          "personalise_epochs": sc["personalise_epochs"],
                          "personalise_div": sc["personalise_div"]}, weights)
        c.publish(H.T_GLOBAL, payload, qos=1, retain=True).wait_for_publish(timeout=30)
        return len(payload)

    def collect(rnd: int, attempt: int, selected: list[str], want_metrics: set[str], deadline: float):
        """Gather this round's updates and metrics until complete or the deadline."""
        updates, metrics, up_bytes, ignored = {}, {}, 0, 0
        while time.time() < deadline and not (set(selected) <= set(updates) and want_metrics <= set(metrics)):
            try:
                kind, r, home, payload = q.get(timeout=0.2)
            except queue.Empty:
                continue
            if kind == "metrics":
                try:
                    m = json.loads(payload)
                except ValueError:
                    continue
                if r == rnd and m.get("run") == run and home not in metrics:
                    metrics[home] = m
                continue
            try:
                header, arrays = M.unpack(payload)
            except (ValueError, KeyError):
                ignored += 1                      # malformed
                continue
            ok = (r == rnd and header["run"] == run and header["attempt"] == attempt
                  and header["home"] == home and home in selected and home not in updates)
            if ok:
                updates[home] = (header["n_train"], arrays)
                up_bytes += len(payload)
            else:
                ignored += 1                      # duplicate, stale or unrequested
        return updates, metrics, up_bytes, ignored

    def record_metrics(rnd: int, metrics: dict) -> list[float]:
        for h in sorted(metrics):
            m = metrics[h]
            append("metrics.csv", {"round": rnd, "home": h, "n_test": m["n_test"],
                                   "classes_in_test": m["classes_in_test"],
                                   "macro_f1": m.get("macro_f1", ""), "accuracy": m.get("accuracy", ""),
                                   "val_macro_f1": m.get("val_macro_f1", ""),
                                   "val_accuracy": m.get("val_accuracy", "")})
        return [m["macro_f1"] for m in metrics.values() if "macro_f1" in m]

    for rnd in range(start, sc["rounds"] + 1):
        for attempt in range(sc["max_retries"] + 1):
            t0 = time.time()
            avail = sorted(online & set(homes))
            k = max(sc["min_clients"], round(sc["fraction"] * len(avail)))
            selected = sorted(rng.sample(avail, min(k, len(avail))))
            down = publish(rnd, attempt, "train", selected)
            updates, metrics, up_bytes, ignored = collect(
                rnd, attempt, selected, set(avail), t0 + sc["deadline_s"])
            if len(updates) >= sc["min_clients"]:
                break
            print(f"round {rnd}: only {len(updates)} updates, retrying", flush=True)
        else:
            raise SystemExit(f"round {rnd}: too few updates after {sc['max_retries']} retries")
        f1 = record_metrics(rnd, metrics)
        weights = fedavg(list(updates.values()))
        np.savez(out / "checkpoint.npz", **{f"w{i}": a for i, a in enumerate(weights)})
        (out / "state.json").write_text(json.dumps({"next_round": rnd + 1}))
        row = {"round": rnd, "attempts": attempt + 1, "selected": len(selected), "updates": len(updates),
               "ignored_messages": ignored, "mean_f1_before": round(float(np.mean(f1)), 4) if f1 else "",
               "worst_f1_before": round(min(f1), 4) if f1 else "",
               "down_bytes": down * len(avail), "up_bytes": up_bytes,
               "seconds": round(time.time() - t0, 1)}
        append("rounds.csv", row)
        print(f"round {rnd:>3}: {len(updates)}/{len(selected)} updates, "
              f"mean F1 {row['mean_f1_before']}, worst {row['worst_f1_before']}, "
              f"{(row['down_bytes'] + up_bytes) / 1e6:.2f} MB, {row['seconds']} s", flush=True)

    # Score the final model on every online home.
    final = sc["rounds"] + 1
    avail = sorted(online & set(homes))
    down = publish(final, 0, "eval", [])
    _, metrics, _, _ = collect(final, 0, [], set(avail), time.time() + sc["deadline_s"])
    f1 = record_metrics(final, metrics)
    append("rounds.csv", {"round": final, "attempts": 1, "selected": 0, "updates": 0, "ignored_messages": 0,
                          "mean_f1_before": round(float(np.mean(f1)), 4) if f1 else "",
                          "worst_f1_before": round(min(f1), 4) if f1 else "",
                          "down_bytes": down * len(avail), "up_bytes": 0, "seconds": ""})
    if f1:
        print(f"final model: mean macro-F1 {np.mean(f1):.3f}, worst home {min(f1):.3f} "
              f"over {len(f1)} homes")
    # Local fine-tuning (optional): each home fine-tunes the final shared model on its own
    # training windows and reports a score. Only scores come back, no weights.
    if sc["personalise_epochs"] > 0:
        p = final + 1
        avail = sorted(online & set(homes))
        publish(p, 0, "personalise", [])
        _, pm, _, _ = collect(p, 0, [], set(avail), time.time() + sc["deadline_s"])
        pf = record_metrics(p, pm)
        if pf:
            print(f"local fine-tuning ({sc['personalise_epochs']} epochs): mean macro-F1 "
                  f"{np.mean(pf):.3f}, worst home {min(pf):.3f} over {len(pf)} homes", flush=True)
    print(f"Written to {out}")
    c.loop_stop()
    c.disconnect()


if __name__ == "__main__":
    main()
