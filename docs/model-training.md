# From chin proximity to a specialized behavior model

## Start with a narrow target

The first product target is “hand near chin/beard for a sustained interval.” That is observable enough for a useful baseline. “Unconscious mistake,” nervousness, and poor professionalism are not observable labels and should not be inferred.

The current baseline combines learned face/hand/pose landmarks with explicit geometry and time rules. It can confuse scratching, drinking, thinking with a hand on the chin, and actual beard grooming. A single still image cannot reliably distinguish these actions. Three cloud snapshots provide a second opinion, not continuous action recognition.

## Recommended progression

| Stage | Method | What it adds | Status |
| --- | --- | --- | --- |
| 1 | Landmarks + proximity + sustained hold | Low-latency local reminders and transparent tuning | Implemented |
| 2 | Standardized temporal features + logistic classifier | Learn a chin-vs-neutral boundary from personal/consented examples | Trainer and ONNX adapter implemented; no real dataset trained |
| 3 | Small temporal convolutional network on richer landmarks | Motion direction, repeated finger strokes, and distinction from chin resting | Proposed experiment |
| 4 | Compact video encoder fine-tuning or distillation | Appearance and motion when landmarks are ambiguous | Only if stage 3 evidence warrants the additional data/compute |

A hand-only gesture classifier is an imperfect fit: the same hand shape near the desk and near the beard has different meaning. The model needs hand-to-face position and temporal motion. MediaPipe's [Gesture Recognizer](https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer) is useful background for custom gesture pipelines, but is not evidence of a ready-made beard-stroking detector.

Start with the smaller classifier before fine-tuning an entire vision-language model. This is a design recommendation based on the narrow geometric task, not a published Miyagi benchmark. It keeps inference local and portable via [ONNX Runtime](https://onnxruntime.ai/docs/get-started/with-python.html).

## Collect usable examples

1. Recruit people who explicitly choose to participate. Include varied beard lengths, no beard, skin tones, glasses, camera angles, lighting, and hands.
2. In Model lab, enter an anonymous participant ID, run the real camera, select the observed label, and export a window after the behavior is visible. These exports contain only numeric features, not images.
3. Initially collect `neutral` and `chin_touch`. Include difficult negatives: chin resting, a cup, a headset adjustment, a hand passing in front of the face, and speaking gestures. Decide whether resting a chin is in-scope **before** labeling; stay consistent.
4. Combine exported JSONL records into an ignored `data/windows.jsonl` file. Do not commit raw examples, participant identities, or biometric recordings.
5. Use stable participant groups across all sessions. Do not random-split overlapping windows into train and validation sets.

The initial trainer requires at least 20 windows and three participant groups to catch obvious collection mistakes. Those are plumbing minimums, not sufficient evidence for a useful model. Plan a pilot with substantially more independent episodes and a held-out test population. If the objective is personalization to one person, use an explicitly separate session-held-out evaluation design; do not spoof participant IDs to satisfy this trainer.

## Feature and file contract

Each line is a JSON object:

```json
{"version":1,"group":"participant-01","label":"chin_touch","features":["16 rows of 6 finite numeric features"]}
```

The example abbreviates the numeric matrix; the real export contains exactly `[16, 6]` floats. Feature order is:

1. Minimum finger-to-face-region distance, normalized by face width.
2. Minimum finger-to-estimated-neck distance, normalized by face width.
3. Minimum finger-to-chin-region distance, normalized by face width.
4. Recent mean head displacement speed in face-widths/second.
5. Hand-presence indicator.
6. Shoulder/neck-region-presence indicator.

Absent distances use the bounded sentinel `4.0`; presence masks distinguish missing data. Frames are captured with backpressure, so 16 samples do not guarantee an exact duration. Keep hardware/sampling comparable for the baseline. A stronger temporal model should resample timestamped landmarks to a fixed clock and represent missing tracking explicitly.

## Train and run

```sh
uv sync --frozen --extra train
uv run --extra train python scripts/train.py data/windows.jsonl --output models/chin.onnx
MIYAGI_ONNX_MODEL=models/chin.onnx uv run --extra onnx miyagi serve
```

The trainer performs one participant-held-out validation split, fits preprocessing only on training data, and exports the fitted preprocessing and classifier together. A sidecar JSON file records the schema, class mapping, validation report, confusion matrix, and the inference threshold. Neutral plus chin-only training is supported; unrelated habits do not need training examples until you intentionally extend the classifier.

With an ONNX model configured, its predictions replace geometric condition decisions; the shared enabled-condition, dwell, and cooldown rules still apply. The baseline classifier selects one class per window. It is not a simultaneous multi-label detector. Use `uv run --extra onnx` so the optional runtime remains installed.

## Evaluate what the user experiences

Report episode precision/recall and false cues per hour in realistic seated sessions, detection latency after sustained contact, missed tracking, and the proportion of time the system abstains. Compare camera/lighting/beard-length groups where participants have consented to those evaluation attributes. Use a locked participant-held-out test set after tuning. Window-level classification metrics alone are insufficient because overlapping windows can inflate apparent performance.

Proposed initial product targets, to validate with users: fewer than two false cues per 30-minute session, at least 85% precision on target episodes, and a cue within three seconds of sustained contact on the target machine. These are **unmeasured goals**, not current results. Optimize toward fewer unnecessary interruptions, with a sensitivity control and clear opt-out.

To identify *stroking* specifically, introduce separate labels such as `beard_stroke`, `chin_rest`, `scratch`, and `neutral`; collect short, consented sequences that preserve finger trajectories and visual beard context. Extend the feature schema to include relative fingertip trajectories, velocities, region occupancy, and occlusion masks. Compare a small TCN against the baseline, then export the successful candidate to ONNX. Cloud models can assist annotation only when participants authorize transmission, and human labels should remain the evaluation reference.

No training job is launched against personal camera data automatically, and no provider fine-tuning service is required by this repository.
