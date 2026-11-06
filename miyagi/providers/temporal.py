"""Optional vendor-neutral ONNX classifier over recent geometric features."""
import json
from collections import deque
from pathlib import Path

import numpy as np

from miyagi.engine import FEATURE_NAMES, LABELS, WINDOW_SIZE


class OnnxClassifier:
    def __init__(self, path: str):
        import onnxruntime as ort
        metadata = json.loads(Path(path).with_suffix(".json").read_text())
        if metadata["feature_names"] != FEATURE_NAMES or metadata["window_size"] != WINDOW_SIZE:
            raise ValueError("ONNX feature schema does not match Miyagi.")
        if metadata["labels"] != ["neutral", *LABELS]:
            raise ValueError("ONNX label order does not match Miyagi.")
        self.labels = metadata["labels"]
        self.class_indices = metadata.get("trained_class_indices", list(range(len(self.labels))))
        if (not self.class_indices or len(set(self.class_indices)) != len(self.class_indices)
                or any(i not in range(len(self.labels)) for i in self.class_indices)):
            raise ValueError("Invalid trained class indices")
        self.threshold = float(metadata.get("threshold", 0.7))
        if not 0 < self.threshold <= 1:
            raise ValueError("Invalid ONNX probability threshold")
        ort.disable_telemetry_events()
        self.session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        self.window = deque(maxlen=WINDOW_SIZE)
        self.input_name = self.session.get_inputs()[0].name

    def reset(self):
        self.window.clear()

    def predict(self, features: list[float]) -> list[str]:
        self.window.append(features)
        if len(self.window) < WINDOW_SIZE:
            return []
        array = np.asarray(self.window, dtype=np.float32).reshape(1, -1)
        probabilities = np.asarray(self.session.run(None, {self.input_name: array})[1])[0]
        if probabilities.shape != (len(self.class_indices),) or not np.all(np.isfinite(probabilities)):
            raise ValueError("Invalid ONNX probability output")
        index = int(np.argmax(probabilities))
        label = self.labels[self.class_indices[index]]
        return [label] if label != "neutral" and probabilities[index] >= self.threshold else []
