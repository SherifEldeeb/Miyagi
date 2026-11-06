"""Train a small, portable temporal baseline from user-labeled feature windows.

uv run --extra train python scripts/train.py data/windows.jsonl --output models/chin.onnx
"""
import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from skl2onnx import to_onnx

from miyagi.engine import FEATURE_NAMES, LABELS, WINDOW_SIZE


def train(source: Path, output: Path):
    rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    labels = ["neutral", *LABELS]
    if len(rows) < 20:
        raise ValueError("Collect at least 20 labeled windows; this minimum is not an accuracy guarantee.")
    x = np.asarray([row["features"] for row in rows], dtype=np.float32)
    if x.shape != (len(rows), WINDOW_SIZE, len(FEATURE_NAMES)) or not np.all(np.isfinite(x)):
        raise ValueError("Expected finite [N, 16, 6] features.")
    if any(row.get("version") != 1 or not str(row.get("group", "")).strip() for row in rows):
        raise ValueError("Each window needs version=1 and a nonempty participant group.")
    y = np.array([labels.index(row["label"]) for row in rows], dtype=np.int64)
    groups = [row["group"] for row in rows]
    if len(set(groups)) < 3:
        raise ValueError("Use at least 3 participants so validation can hold out people.")
    x = x.reshape(len(rows), -1)
    train_index, test_index = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=42).split(x, y, groups))
    if len(set(y[train_index])) < 2 or 0 not in y[train_index]:
        raise ValueError("The training split needs neutral examples and at least one target behavior.")
    if set(y[test_index]) != set(y[train_index]):
        raise ValueError("Collect all target classes in both participant splits before training.")
    pipeline = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=2000, random_state=42))
    pipeline.fit(x[train_index], y[train_index])
    predictions = pipeline.predict(x[test_index])
    present = sorted(int(value) for value in set(y[train_index]))
    report = classification_report(y[test_index], predictions, labels=present,
                                   target_names=[labels[i] for i in present], output_dict=True, zero_division=0)
    model = to_onnx(pipeline, x[:1], options={id(pipeline[-1]): {"zipmap": False}}, target_opset=17)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(model.SerializeToString())
    metadata = {"version": 1, "feature_names": FEATURE_NAMES, "window_size": WINDOW_SIZE,
                "labels": labels, "trained_class_indices": present, "threshold": .7,
                "training_windows": len(train_index), "validation_windows": len(test_index),
                "split": "participant-held-out; random_state=42", "validation": report,
                "confusion_matrix": confusion_matrix(y[test_index], predictions, labels=present).tolist()}
    output.with_suffix(".json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps({"model": str(output), "validation": report}, indent=2))
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("models/chin.onnx"))
    args = parser.parse_args()
    train(args.source, args.output)
