"""Aggregation maths, in plain NumPy so the harness and any other runner share it."""

from __future__ import annotations

import numpy as np


def fedavg(updates: list[tuple[int, list[np.ndarray]]]) -> list[np.ndarray]:
    """Federated Averaging: average each array, weighted by the client's sample count."""
    total = float(sum(n for n, _ in updates))
    if total <= 0:
        raise ValueError("no samples to aggregate")
    out = [np.zeros_like(a, dtype="float64") for a in updates[0][1]]
    for n, arrays in updates:
        for o, a in zip(out, arrays):
            o += (n / total) * a
    return [o.astype("float32") for o in out]
