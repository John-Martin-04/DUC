"""Shared by the baselines and, in phase 3, the federated runs: loading the
dataset, the model, and the metrics. Keeping them in one place guarantees that
every setup trains the same model on the same inputs."""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import pandas as pd

import settings as S


def load_dataset(path: Path, homes: list[str] | None = None) -> tuple[dict, dict[str, pd.DataFrame]]:
    schema = json.loads((path / "schema.json").read_text())
    homes = homes or schema["homes"]
    return schema, {h: pd.read_parquet(path / f"{h}.parquet") for h in homes}


def xy(df: pd.DataFrame, schema: dict) -> tuple[np.ndarray, np.ndarray]:
    """Inputs: log(1 + count) per feature, plus the time features.

    log1p keeps busy minutes from dominating and needs no statistics from the
    data, so no home has to share means or variances with anyone."""
    counts = np.log1p(df[schema["features"]].to_numpy(dtype="float32"))
    time = df[schema["time_features"]].to_numpy(dtype="float32")
    return np.hstack([counts, time]), df["y"].to_numpy(dtype="int32")


def set_seed(seed: int) -> None:
    import tensorflow as tf
    random.seed(seed)
    np.random.seed(seed)
    tf.keras.utils.set_random_seed(seed)


def build_model(n_inputs: int, n_classes: int):
    """The small MLP used by every setup."""
    import tensorflow as tf
    layers = [tf.keras.layers.InputLayer(input_shape=(n_inputs,))]
    for units in S.HIDDEN_UNITS:
        layers += [tf.keras.layers.Dense(units, activation="relu"),
                   tf.keras.layers.Dropout(S.DROPOUT)]
    layers.append(tf.keras.layers.Dense(n_classes, activation="softmax"))
    return tf.keras.Sequential(layers)


def compile_model(model) -> None:
    import tensorflow as tf
    model.compile(optimizer=tf.keras.optimizers.Adam(S.LEARNING_RATE),
                  loss="sparse_categorical_crossentropy", metrics=["accuracy"])


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Macro-F1 over the classes present in y_true (this home's test period)."""
    scores = []
    for c in np.unique(y_true):
        tp = np.sum((y_pred == c) & (y_true == c))
        fp = np.sum((y_pred == c) & (y_true != c))
        fn = np.sum((y_pred != c) & (y_true == c))
        denom = 2 * tp + fp + fn
        scores.append(2 * tp / denom if denom else 0.0)
    return float(np.mean(scores)) if scores else float("nan")
