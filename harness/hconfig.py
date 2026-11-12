"""Harness settings: brokers, accounts, topics and paths.

Two Mosquitto brokers mark the household boundary:
  home broker        sensor events, labels and predictions; never leaves a home
  federation broker  global models, updates, metrics; all that leaves a home

Each home's broker address can be overridden with DUC_HOME_BROKER_<HOME>
(host:port), so a home can later move to its own device without code changes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent             # DUC/harness
sys.path.insert(0, str(ROOT.parent / "pipeline"))
import settings as S  # noqa: E402  (pipeline/settings.py)

HOME_BROKER = os.environ.get("DUC_HOME_BROKER", "127.0.0.1:18830")
FED_BROKER = os.environ.get("DUC_FED_BROKER", "127.0.0.1:18840")
BROKER_DIR = Path(os.environ.get("DUC_BROKER_DIR", "/tmp/duc-brokers"))
PASSWORD_PREFIX = os.environ.get("DUC_PASSWORD_PREFIX", "duc-")   # simulation only

OUT = (ROOT / "sample_run") if S.SAMPLE else S.REPO
GATEWAY_DIR = OUT / "data" / "gateways"            # each home's local store (ignored by Git)
RESULTS_DIR = OUT / "results" / "harness"

# Topics. One ordered stream per home: MQTT only guarantees order within a topic.
T_EVENTS = "home/{home}/events"
T_LABELS = "home/{home}/labels"            # annotation source, separate from sensors
T_PREDICTIONS = "home/{home}/predictions"
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
    return PASSWORD_PREFIX + user


def client(user: str, client_id: str | None = None):
    """A paho-mqtt 2.x client logged in as `user`."""
    import paho.mqtt.client as mqtt
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id or user)
    c.username_pw_set(user, password(user))
    return c
