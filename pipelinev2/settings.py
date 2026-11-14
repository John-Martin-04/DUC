"""Paths and settings for phase 2. Window length, splits and excluded sensor
types come from audit/config.py, so the audit and the dataset always agree.

AUDIT_SAMPLE=1 reads the audit's sample run and writes to pipeline/sample_run/.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent            # DUC/pipeline
REPO = ROOT.parent                                 # DUC
AUDIT_DIR = REPO / "audit"
SAMPLE = os.environ.get("AUDIT_SAMPLE") == "1"

sys.path.insert(0, str(AUDIT_DIR))
import config as audit  # noqa: E402  (audit/config.py)
from scripts.utils import EXCLUDE, load_label_map, md_table  # noqa: E402,F401

OUT_BASE = ROOT / "sample_run" if SAMPLE else REPO
PROCESSED_DIR = OUT_BASE / "data" / "processed"   # ignored by Git (data/)
RESULTS_DIR = OUT_BASE / "results"                # committed: small CSV and Markdown files

EVENTS_DIR = audit.EVENTS_DIR
INVENTORY = audit.MAPPINGS_DIR / "sensor_inventory.csv"
SELECTED_HOMES = audit.MAPPINGS_DIR / "selected_homes.txt"
WINDOW_SECONDS = audit.WINDOW_SECONDS
SPLITS = audit.SPLITS
SYSTEM_SENSOR_TYPES = audit.SYSTEM_SENSOR_TYPES

# Model and training defaults, identical for every setup (local, centralised, federated).
HIDDEN_UNITS = (128, 64)
DROPOUT = 0.2
LEARNING_RATE = 1e-3
BATCH_SIZE = 128
MAX_EPOCHS = 30
PATIENCE = 5
