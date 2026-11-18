"""A household gateway: the federated client. One process per home.

Inside the home (home broker)
  - subscribes to its own home's events and labels, nothing else
  - drops duplicates (QoS 1 delivers at least once), filters sensors with the
    home's device registry, and cuts 60 s windows by the time inside each event
  - stores every closed window in a local SQLite file; raw events are not kept
  - once it holds a model, classifies each new window and publishes the
    prediction on home/<id>/predictions (stays inside the home)

Towards the server (federation broker)
  - announces online/offline (offline is its last-will message)
  - on each global model: scores it on the local test windows and reports the
    metrics; if selected, trains locally and sends back the new weights
  - nothing else leaves: no events, no windows, no labels

The window rules, model, inputs and metric are imported from pipelinev2/, the
same code the offline dataset and baselines use.

Usage (from DUC/harness)
  python gateway.py --dataset ../data/processed/cap60_noother --homes csh101 csh102
"""

from __future__ import annotations

import argparse
import json
import queue
import random
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd

import hconfig as H
import messages as M
import windows as W
from common import build_model, class_weights, macro_f1, set_seed, xy

WINDOW_US = H.S.WINDOW_SECONDS * 1_000_000


class WindowBuilder:
    """Turns the two ordered streams (events, labels) into closed windows.

    A window closes when both streams have moved `lateness` past its end, so a
    slightly out-of-order event still lands in the right window. Anything
    later than that is counted in `late` and dropped."""

    def __init__(self, registry: dict, label_map: dict, lateness_s: int):
        self.reg, self.lm = registry, label_map
        self.lateness = lateness_s * 1_000_000
        self.reset()

    def reset(self) -> None:
        self.open: dict[int, tuple[dict, dict]] = {}     # window -> (counts, votes)
        self.kept: dict[int, int | None] = {}            # seq -> window of a kept event, awaiting its label
        self.pending: dict[int, object] = {}             # seq -> activity, awaiting its event
        self.wm_event = self.wm_label = -1
        self.closed_upto = -1
        self.late = 0

    def _slot(self, w: int):
        if w <= self.closed_upto:
            self.late += 1
            return None
        return self.open.setdefault(w, ({}, {}))

    def _vote(self, w: int | None, activity) -> None:
        lab = W.shared_label(activity, self.lm) if w is not None else None
        if lab:
            slot = self._slot(w)
            if slot:
                slot[1][lab] = slot[1].get(lab, 0) + 1

    def on_event(self, seq: int, t: int, sensor: str, stype: str, loc: str) -> None:
        self.wm_event = max(self.wm_event, t)
        feat = self.reg.get((sensor, stype, loc))
        w = None
        if feat:
            w = t // WINDOW_US * WINDOW_US
            slot = self._slot(w)
            if slot:
                slot[0][feat] = slot[0].get(feat, 0) + 1
        if seq in self.pending:
            self._vote(w, self.pending.pop(seq))
        else:
            self.kept[seq] = w

    def on_label(self, seq: int, t: int, activity) -> None:
        self.wm_label = max(self.wm_label, t)
        if seq in self.kept:
            self._vote(self.kept.pop(seq), activity)
        else:
            self.pending[seq] = activity

    def close(self, everything: bool = False) -> list[tuple[int, str | None, dict]]:
        limit = float("inf") if everything else min(self.wm_event, self.wm_label) - self.lateness
        done = sorted(w for w in self.open if w + WINDOW_US <= limit)
        out = []
        for w in done:
            counts, votes = self.open.pop(w)
            out.append((w, W.majority(votes) if votes else None, counts))
        if done:
            self.closed_upto = max(self.closed_upto, done[-1])
        return out


def before_send(header: dict, arrays: list[np.ndarray]) -> tuple[dict, list[np.ndarray]]:
    """Last step before an update leaves the home. Does nothing yet; clipping and
    noise (differential privacy), masking (secure aggregation) or compression go here."""
    return header, arrays


class Gateway:
    def __init__(self, home: str, dataset: Path, lateness_s: int, keep_store: bool = False):
        self.home = home
        self.schema = json.loads((dataset / "schema.json").read_text())
        self.features, self.classes = self.schema["features"], self.schema["classes"]
        self.builder = WindowBuilder(W.device_registry(W.load_inventory(), home),
                                     H.S.load_label_map(), lateness_s)
        self.q: queue.Queue = queue.Queue()
        self.subscribed = threading.Event()
        self.stream, self.last_seq, self.eos = None, {}, set()
        self.dups = self.n_events = self.bad = 0
        self.model, self.model_round = None, None
        self.frame, self.frame_n = None, -1
        self.last_job = None

        H.GATEWAY_DIR.mkdir(parents=True, exist_ok=True)
        path = H.GATEWAY_DIR / f"{home}.sqlite"
        if not keep_store:
            path.unlink(missing_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            create table if not exists windows (window_us integer primary key, label text, counts text);
            create table if not exists predictions (window_us integer primary key, label text, confidence real, round integer);
            create table if not exists meta (key text primary key, value text);""")
        n = self.db.execute("select count(*) from windows").fetchone()[0]
        if n:
            self.log(f"reusing {n} stored windows from an earlier replay")

        self.home_c = H.client(home, f"gw-{home}-home")
        self.home_c.on_connect = self._home_connect
        self.home_c.on_subscribe = lambda *a: self.subscribed.set()
        self.home_c.on_message = lambda c, u, m: self.q.put(("home", m.topic, m.payload))
        self.fed_c = H.client(home, f"gw-{home}-fed")
        self.fed_c.will_set(H.T_STATUS.format(home=home), "offline", qos=1, retain=True)
        self.fed_c.on_connect = self._fed_connect
        self.fed_c.on_message = lambda c, u, m: self.q.put(("fed", m.topic, m.payload))

    def log(self, *a) -> None:
        print(f"[{self.home}]", *a, flush=True)

    def _home_connect(self, c, u, flags, rc, props) -> None:
        c.subscribe([(H.T_EVENTS.format(home=self.home), 1), (H.T_LABELS.format(home=self.home), 1)])

    def _fed_connect(self, c, u, flags, rc, props) -> None:
        c.subscribe(H.T_GLOBAL, qos=1)
        c.publish(H.T_STATUS.format(home=self.home), "online", qos=1, retain=True)

    def meta(self, key: str, value) -> None:
        self.db.execute("insert or replace into meta values (?, ?)", (key, json.dumps(value)))
        self.db.commit()

    # ---- inside the home -------------------------------------------------

    def on_home(self, topic: str, payload: bytes) -> None:
        m = json.loads(payload)
        kind = "events" if topic.endswith("/events") else "labels"
        if m["stream"] != self.stream:                 # a new replay: restart duplicate tracking
            self.stream, self.last_seq, self.eos = m["stream"], {}, set()
            self.builder.reset()
            self.n_events = self.dups = 0
        if m.get("eos"):
            self.eos.add(kind)
            if self.eos == {"events", "labels"}:
                self.store(self.builder.close(everything=True))
                n, n_lab = self.db.execute("select count(*), count(label) from windows").fetchone()
                self.meta("ingest_done", {"events": self.n_events, "duplicates": self.dups,
                                          "late": self.builder.late, "windows": n, "labelled": n_lab})
                self.log(f"stream ended: {self.n_events} events, {n} windows ({n_lab} labelled), "
                         f"{self.dups} duplicates, {self.builder.late} late")
            return
        if m["seq"] <= self.last_seq.get(kind, -1):
            self.dups += 1
            return
        self.last_seq[kind] = m["seq"]
        if kind == "events":
            self.n_events += 1
            self.builder.on_event(m["seq"], m["t"], m["sensor"], m["type"], m["loc"])
            if self.n_events % 2000 == 0:
                self.store(self.builder.close())
        else:
            self.builder.on_label(m["seq"], m["t"], m["activity"])

    def store(self, closed: list) -> None:
        if not closed:
            return
        self.db.executemany("insert or replace into windows values (?, ?, ?)",
                            [(w, lab, json.dumps(counts)) for w, lab, counts in closed])
        self.db.commit()
        if self.model is not None:
            self.predict(closed)

    def window_x(self, closed: list) -> np.ndarray:
        """Model inputs for newly closed windows, with context from the local store."""
        lookback = closed[0][0] - W.MAX_GAP_MINUTES * 60_000_000
        rows = self.db.execute("select window_us, counts from windows where window_us >= ? "
                               "order by window_us", (lookback,)).fetchall()
        counts = stored_counts(rows)
        if self.schema.get("context"):
            counts = counts.join(W.add_context(counts))
        win = counts.reset_index(drop=True)
        win.insert(0, "window_start", counts.index)
        win = W.add_time(win)
        win = win[win["window_start"].isin(pd.to_datetime([w for w, _, _ in closed], unit="us"))]
        win = win.reindex(columns=self.features + W.TIME_FEATURES).fillna(0)
        return np.hstack([np.log1p(win[self.features].to_numpy(dtype="float32")),
                          win[W.TIME_FEATURES].to_numpy(dtype="float32")])

    def predict(self, closed: list) -> None:
        p = self.model.predict(self.window_x(closed), batch_size=4096, verbose=0)
        rows = [(w, self.classes[int(k)], float(c), self.model_round)
                for (w, _, _), k, c in zip(closed, p.argmax(axis=1), p.max(axis=1))]
        self.db.executemany("insert or replace into predictions values (?, ?, ?, ?)", rows)
        self.db.commit()
        for w, lab, conf, rnd in rows:
            self.home_c.publish(H.T_PREDICTIONS.format(home=self.home), json.dumps(
                {"v": M.VERSION, "t": w, "label": lab, "confidence": round(conf, 3), "round": rnd}))

    # ---- towards the server ----------------------------------------------

    def dataset(self) -> pd.DataFrame:
        """The home's stored windows as dataset rows, by the shared rules."""
        n = self.db.execute("select count(*) from windows").fetchone()[0]
        if n != self.frame_n:
            self.frame, self.frame_n = load_frame(self.db, self.home, self.schema), n
        return self.frame

    def add_val(self, df, metrics: dict) -> None:
        """Validation scores, reported next to the test scores. Used to choose settings, never to report."""
        x_va, y_va = xy(df[df.split == "val"], self.schema)
        metrics["val_n"] = int(len(y_va))
        if len(y_va):
            pred = self.model.predict(x_va, batch_size=4096, verbose=0).argmax(axis=1)
            metrics.update(val_macro_f1=macro_f1(y_va, pred), val_accuracy=float(np.mean(pred == y_va)))

    def personalise(self, header: dict, weights: list, df) -> None:
        """Local fine-tuning: train a copy of the final shared model on this home's training
        windows and report its test score. The weights are not sent anywhere."""
        rnd = header["round"]
        self.model.set_weights(weights)
        self.prox_mu.assign(0.0)
        x_tr, y_tr = xy(df[df.split == "train"], self.schema)
        x_te, y_te = xy(df[df.split == "test"], self.schema)
        if len(y_tr) and header.get("personalise_epochs", 0) > 0:
            set_seed(header["seed"] + rnd)
            self.model.optimizer.learning_rate.assign(header["client_lr"] / header.get("personalise_div", 3.0))
            self.model.fit(x_tr, y_tr, epochs=header["personalise_epochs"],
                           batch_size=header["batch_size"], verbose=0)
        metrics = {"v": M.VERSION, "run": header["run"], "round": rnd, "home": self.home,
                   "n_test": int(len(y_te)), "classes_in_test": int(len(np.unique(y_te)))}
        if len(y_te):
            pred = self.model.predict(x_te, batch_size=4096, verbose=0).argmax(axis=1)
            metrics.update(macro_f1=macro_f1(y_te, pred), accuracy=float(np.mean(pred == y_te)))
        self.add_val(df, metrics)
        self.fed_c.publish(H.T_METRICS.format(round=rnd, home=self.home), json.dumps(metrics), qos=1)
        self.model.set_weights(weights)

    def on_global(self, payload: bytes) -> None:
        header, weights = M.unpack(payload)
        job = (header["run"], header["round"], header.get("attempt", 0), header["phase"])
        if job == self.last_job:
            return
        self.last_job = job
        if self.model is None:
            import tensorflow as tf
            self.model = build_model(len(self.features) + 3, len(self.classes))
            # FedProx: penalise moving away from the model the server sent (strength mu; 0 = FedAvg).
            self.prox_mu = tf.Variable(0.0, trainable=False)
            self.prox_ref = [tf.Variable(w, trainable=False) for w in self.model.trainable_weights]
            self.model.add_loss(lambda: 0.5 * self.prox_mu * tf.add_n(
                [tf.reduce_sum(tf.square(w - g)) for w, g in zip(self.model.trainable_weights, self.prox_ref)]))
            self.model.compile(optimizer=tf.keras.optimizers.SGD(header["client_lr"]),
                               loss="sparse_categorical_crossentropy")
        self.model.set_weights(weights)
        self.model_round = header["round"]
        for ref, w in zip(self.prox_ref, self.model.trainable_weights):
            ref.assign(w)
        self.prox_mu.assign(header.get("mu", 0.0))
        df = self.dataset()
        rnd = header["round"]

        if header["phase"] == "personalise":
            self.personalise(header, weights, df)
            return
        x_te, y_te = xy(df[df.split == "test"], self.schema)
        metrics = {"v": M.VERSION, "run": header["run"], "round": rnd, "home": self.home,
                   "n_test": int(len(y_te)), "classes_in_test": int(len(np.unique(y_te)))}
        if len(y_te):
            pred = self.model.predict(x_te, batch_size=4096, verbose=0).argmax(axis=1)
            metrics.update(macro_f1=macro_f1(y_te, pred), accuracy=float(np.mean(pred == y_te)))
        self.add_val(df, metrics)
        self.fed_c.publish(H.T_METRICS.format(round=rnd, home=self.home), json.dumps(metrics), qos=1)

        if header["phase"] != "train" or self.home not in header["selected"]:
            return
        if random.Random(f"{header['seed']}-{self.home}-{job}").random() < header.get("dropout_p", 0):
            self.log(f"round {rnd}: simulated dropout")
            return
        x_tr, y_tr = xy(df[df.split == "train"], self.schema)
        if not len(y_tr):
            self.log(f"round {rnd}: no training windows, skipping")
            return
        set_seed(header["seed"] + rnd)
        self.model.optimizer.learning_rate.assign(header["client_lr"])
        t0 = time.time()
        cw = class_weights(y_tr, len(self.classes)) if header.get("class_weight") else None
        self.model.fit(x_tr, y_tr, epochs=header["local_epochs"], batch_size=header["batch_size"],
                       class_weight=cw, verbose=0)
        up, arrays = before_send({"run": header["run"], "round": rnd, "attempt": job[2],
                                  "home": self.home, "n_train": int(len(y_tr)),
                                  "train_seconds": round(time.time() - t0, 2)},
                                 self.model.get_weights())
        self.fed_c.publish(H.T_UPDATE.format(round=rnd, home=self.home), M.pack(up, arrays), qos=1)
        self.model.set_weights(weights)        # keep predicting with the shared model

    def run(self) -> None:
        host, port = H.home_broker(self.home)
        self.home_c.connect(host, port, keepalive=60)
        self.home_c.loop_start()
        if not self.subscribed.wait(30):
            sys.exit(f"[{self.home}] could not subscribe on the home broker {host}:{port}")
        self.meta("ready", 1)
        self.home_c.publish(H.T_HOME_STATUS.format(home=self.home), "ready", qos=1, retain=True)
        self.fed_c.connect(*H.addr(H.FED_BROKER), keepalive=60)
        self.fed_c.loop_start()
        self.log("online")
        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *a: stop.set())
        try:
            while not stop.is_set():
                try:
                    side, topic, payload = self.q.get(timeout=1)
                except queue.Empty:
                    self.store(self.builder.close())
                    continue
                try:
                    if side == "home":
                        self.on_home(topic, payload)
                    else:
                        self.on_global(payload)
                except (ValueError, KeyError, TypeError) as e:      # malformed message: skip it
                    self.bad += 1
                    self.log(f"ignored a malformed message on {topic}: {e!r}")
        except KeyboardInterrupt:
            pass
        self.fed_c.publish(H.T_STATUS.format(home=self.home), "offline", qos=1, retain=True
                           ).wait_for_publish(timeout=5)
        self.home_c.publish(H.T_HOME_STATUS.format(home=self.home), "stopped", qos=1, retain=True
                            ).wait_for_publish(timeout=5)
        for c in (self.home_c, self.fed_c):
            c.loop_stop()
            c.disconnect()


def stored_counts(rows: list) -> pd.DataFrame:
    """(window_us, counts json) rows -> one row per window, indexed by window start."""
    counts = pd.DataFrame([json.loads(c) for _, c in rows]).fillna(0)
    counts.index = pd.to_datetime([w for w, _ in rows], unit="us")
    return counts


def load_frame(db: sqlite3.Connection, home: str, schema: dict) -> pd.DataFrame:
    """Stored windows -> rows in the shared dataset layout."""
    rows = db.execute("select window_us, label, counts from windows order by window_us").fetchall()
    counts = stored_counts([(w, c) for w, _, c in rows])
    if schema.get("context"):                      # context uses every window, labelled or not
        counts = counts.join(W.add_context(counts))
    win = counts.reset_index(drop=True)
    win.insert(0, "label", [l for _, l, _ in rows])
    win.insert(0, "window_start", counts.index)
    win = win[win["label"].notna()].reset_index(drop=True)
    win = W.finalize(win, schema["cap_days"], schema["keep_other"])
    win = win[win["label"].isin(schema["classes"])].reset_index(drop=True)
    return W.to_schema(win, home, schema["features"], schema["classes"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True, type=Path,
                    help="folder made by build_dataset.py; its schema.json fixes features, classes, cap")
    ap.add_argument("--homes", nargs="+", required=True)
    ap.add_argument("--lateness", type=int, default=120,
                    help="seconds of event time a window stays open for out-of-order events")
    ap.add_argument("--keep-store", action="store_true",
                    help="reuse the windows stored by an earlier replay instead of starting empty")
    args = ap.parse_args()

    if len(args.homes) == 1:
        Gateway(args.homes[0], args.dataset, args.lateness, args.keep_store).run()
        return
    # Several homes: one process each, like separate devices.
    logs = H.RESULTS_DIR / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    procs = [subprocess.Popen([sys.executable, __file__, "--dataset", str(args.dataset), "--homes", h,
                               "--lateness", str(args.lateness)]
                              + (["--keep-store"] if args.keep_store else []),
                              stdout=open(logs / f"gateway_{h}.log", "w"), stderr=subprocess.STDOUT)
             for h in args.homes]
    print(f"{len(procs)} gateways started; logs in {logs}", flush=True)
    signal.signal(signal.SIGTERM, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait()


if __name__ == "__main__":
    main()
