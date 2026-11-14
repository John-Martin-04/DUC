"""Harness settings: brokers, accounts, topics and paths.

Two Mosquitto brokers mark the household boundary:
  home broker        sensor events, labels and predictions; never leaves a home
  federation broker  global models, updates, metrics; all that leaves a home

Network setup comes from environment variables, or from a duc.env file in
this folder (see pi_bundle.py). Defaults keep everything on one machine.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent             # DUC/harnessv2


def _load_env_file() -> None:
    """Read harnessv2/duc.env (KEY=VALUE lines) so every program on a machine
    shares one network setup. Real environment variables win."""
    f = ROOT / "duc.env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env_file()
sys.path.insert(0, str(ROOT.parent / "pipelinev2"))
import settings as S  # noqa: E402  (pipelinev2/settings.py)

# Where clients connect.
HOME_BROKER = os.environ.get("DUC_HOME_BROKER", "127.0.0.1:18830")
FED_BROKER = os.environ.get("DUC_FED_BROKER", "127.0.0.1:18840")
# Which network interface each broker listens on, when started on this machine.
# 127.0.0.1 = this machine only; 0.0.0.0 = reachable from the network.
HOME_BIND = os.environ.get("DUC_HOME_BIND", "127.0.0.1")
FED_BIND = os.environ.get("DUC_FED_BIND", "127.0.0.1")
BROKER_DIR = Path(os.environ.get("DUC_BROKER_DIR", "/tmp/duc-brokers"))
# Passwords are SECRET + user name. Set the same DUC_SECRET on every machine.
SECRET = os.environ.get("DUC_SECRET", "duc-")

OUT = (ROOT / "sample_run") if S.SAMPLE else S.REPO
GATEWAY_DIR = OUT / "data" / "gateways"            # each home's local store (ignored by Git)
RESULTS_DIR = OUT / "results" / "harness"

# Topics. One ordered stream per home: MQTT only guarantees order within a topic.
T_EVENTS = "home/{home}/events"
T_LABELS = "home/{home}/labels"            # annotation source, separate from sensors
T_PREDICTIONS = "home/{home}/predictions"
T_HOME_STATUS = "home/{home}/status"      # retained "ready" once the gateway listens
T_GLOBAL = "fl/global"                      # retained: the current round's model
T_UPDATE = "fl/round/{round}/update/{home}"
T_METRICS = "fl/round/{round}/metrics/{home}"
T_STATUS = "fl/status/{home}"              # retained; "offline" is the last-will message


def addr(spec: str) -> tuple[str, int]:
    host, port = spec.rsplit(":", 1)
    return host, int(port)


def home_broker(home: str) -> tuple[str, int]:
    return addr(os.environ.get(f"DUC_HOME_BROKER_{home.upper()}", HOME_BROKER))


def password(user: str) -> str:
    return SECRET + user


def client(user: str, client_id: str | None = None):
    """A paho-mqtt 2.x client logged in as `user`."""
    import paho.mqtt.client as mqtt
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id or user)
    c.username_pw_set(user, password(user))
    return c
