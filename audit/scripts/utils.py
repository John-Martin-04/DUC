"""Small helpers shared by the audit scripts."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

EXCLUDE = "exclude"


def md_table(df: pd.DataFrame) -> str:
    """Render a DataFrame as a Markdown table without extra dependencies."""
    cols = [str(c) for c in df.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        out.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |")
    return "\n".join(out)


def load_label_map(path: Path | None = None) -> dict[str, str]:
    """raw label (case-insensitive) -> shared label, from mappings/label_map.csv."""
    path = path or config.MAPPINGS_DIR / "label_map.csv"
    if not path.exists():
        path = config.SHARED_LABEL_MAP
    if not path.exists():
        return {}
    lm = pd.read_csv(path, comment="#").dropna(subset=["raw_label"])
    lm["shared_label"] = lm["shared_label"].fillna("").astype(str).str.strip()
    lm = lm[lm["shared_label"] != ""]
    return {str(r).strip().lower(): s for r, s in zip(lm["raw_label"], lm["shared_label"])}
