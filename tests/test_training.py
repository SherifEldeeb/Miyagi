"""Synthetic data validates train/export/inference plumbing, never model accuracy."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("skl2onnx")
pytest.importorskip("onnxruntime")

from miyagi.engine import FEATURE_NAMES, WINDOW_SIZE
from miyagi.providers.temporal import OnnxClassifier


def test_binary_chin_training_exports_compatible_onnx(tmp_path):
    spec=importlib.util.spec_from_file_location("training",Path(__file__).parents[1]/"scripts"/"train.py")
    training=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(training)
    rng=np.random.default_rng(42)
    rows=[]
    for person in range(6):
        for i in range(12):
            label="chin_touch" if i%2 else "neutral"
            features=np.full((WINDOW_SIZE,len(FEATURE_NAMES)),3.0,dtype=np.float32)
            features[:,2]=.03 if i%2 else 3
            features+=rng.normal(0,.005,features.shape)
            rows.append({"version":1,"group":f"p{person}","label":label,"features":features.tolist()})
    source=tmp_path/"synthetic.jsonl"
    source.write_text("\n".join(json.dumps(row) for row in rows))
    output=tmp_path/"model.onnx"
    metadata=training.train(source,output)
    assert metadata["trained_class_indices"]==[0,3]
    classifier=OnnxClassifier(str(output))
    for frame in rows[1]["features"]:
        result=classifier.predict(frame)
    assert result==["chin_touch"]
    classifier.reset()
    assert classifier.predict(rows[0]["features"][0])==[]
    for frame in rows[0]["features"]:
        result=classifier.predict(frame)
    assert result==[]
