"""Adds local fine-tuning to the harness (run once, from harnessv2).

After the final global model, each home fine-tunes its own copy on its own
training windows and reports one test score. Weights stay on the home; only
the score is sent, as with every other message.

Scenario options (both optional):
  "personalise_epochs": 5     0 = off (default)
  "personalise_div": 3.0      fine-tuning lr = client_lr / this (default 3, as the baseline)
"""
import pathlib
import sys

EDITS = []   # (path, old, new)

def replace_once(path, old, new):
    EDITS.append((path, old, new))

def apply_all():
    for path in sorted({e[0] for e in EDITS}):
        s = pathlib.Path(path).read_text()
        if "personalise" in s:
            sys.exit(f"{path} already has local fine-tuning; nothing changed")
        for p, old, new in EDITS:
            if p != path:
                continue
            n = s.count(old)
            if n != 1:
                sys.exit(f"{path}: anchor found {n} times, expected 1. Nothing changed.")
            s = s.replace(old, new, 1)
        pathlib.Path(path).write_text(s)
        print(f"patched {path}")

# ---- coordinator.py ----
replace_once("coordinator.py",
 '"deadline_s": 120, "min_clients": 2, "max_retries": 2, "dropout_p": 0.0, "seed": 0, "mu": 0.0, "class_weight": False,\n            "homes": None}',
 '"deadline_s": 120, "min_clients": 2, "max_retries": 2, "dropout_p": 0.0, "seed": 0, "mu": 0.0, "class_weight": False,\n            "homes": None, "personalise_epochs": 0, "personalise_div": 3.0}')

replace_once("coordinator.py",
 '                          "deadline_s": sc["deadline_s"]}, weights)',
 '                          "deadline_s": sc["deadline_s"],\n                          "personalise_epochs": sc["personalise_epochs"],\n                          "personalise_div": sc["personalise_div"]}, weights)')

replace_once("coordinator.py",
 '    print(f"Written to {out}")\n',
 '''    # Local fine-tuning (optional): each home fine-tunes the final shared model on its own
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
''')

# ---- gateway.py ----
replace_once("gateway.py",
 '    def on_global(self, payload: bytes) -> None:\n',
 '''    def personalise(self, header: dict, weights: list, df) -> None:
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
        self.fed_c.publish(H.T_METRICS.format(round=rnd, home=self.home), json.dumps(metrics), qos=1)
        self.model.set_weights(weights)

    def on_global(self, payload: bytes) -> None:
''')

replace_once("gateway.py",
 '        x_te, y_te = xy(df[df.split == "test"], self.schema)\n        metrics = {"v": M.VERSION, "run": header["run"], "round": rnd, "home": self.home,',
 '''        if header["phase"] == "personalise":
            self.personalise(header, weights, df)
            return
        x_te, y_te = xy(df[df.split == "test"], self.schema)
        metrics = {"v": M.VERSION, "run": header["run"], "round": rnd, "home": self.home,''')

apply_all()
