"""Audit settings. Fix these BEFORE you look at the profiles, so the home
selection cannot be tuned to the results. Change them only with a written
reason in the audit report."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# AUDIT_SAMPLE=1 sends every output to sample_run/ so test runs on fake data
# never mix with the real audit (see run_sample.sh).
BASE = ROOT / "sample_run" if os.environ.get("AUDIT_SAMPLE") == "1" else ROOT
RAW_DIR = ROOT / "data" / "raw"            # downloaded files (never edited)
EVENTS_DIR = BASE / "data" / "interim" / "events"   # one parquet per home
MAPPINGS_DIR = BASE / "mappings"
REPORTS_DIR = BASE / "reports"
SHARED_LABEL_MAP = ROOT / "mappings" / "label_map.csv"

# Windowing and splits (from the project plan)
WINDOW_SECONDS = 60
SPLITS = (0.70, 0.10, 0.20)          # train, validation, test, by time

# Home selection criteria (thresholds are proposals; set your own)
MIN_LABELLED_DAYS = 14               # days with at least one labelled event
MIN_LABEL_COVERAGE = 0.30            # share of sensor events that carry a label
MIN_TEST_WINDOWS_PER_CLASS = 10      # a class "exists" in a home's test period
MIN_CLASSES_PER_HOME = 5             # shared classes a home must have in test
MIN_HOME_SHARE_FOR_CLASS = 0.5       # keep a class only if this share of homes has it

# Event handling
# Sensor types that are device housekeeping, not human activity
SYSTEM_SENSOR_TYPES = {"battery", "radio", "system", "light_sensor", "temperature"}
# Intervals longer than this are treated as gaps when measuring labelled time
MAX_INTERVAL_SECONDS = 1800
# Gaps worth flagging in the profile
GAP_FLAG_HOURS = (1, 24)
# A sensor with fewer events than this over the whole recording is suspicious
MIN_EVENTS_PER_SENSOR = 20
