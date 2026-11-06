# 🎯 Meeting Coach

A local, AI-powered web app that watches your webcam **during video meetings** and gently
alerts you when you slip into unconscious habits.

**Current focus: 🧔 beard stroking and 🤔 chin touching** (on by default). Twelve more habits
(touching face or neck, hair, hand at mouth, rocking, looking away, slouching, frowning...)
are built in and switched off; tick them under *Habits → More habits* when you want them.

When a habit is detected you get a visual cue of your choice: a **red rectangle**
around the spot, an **emoji mask** over your face, a **glowing border**, a little
cartoon **avatar ("Coachy") that acts out what you're doing** (it grows a beard,
turns into a giraffe, gets dizzy...), a **toast** with a tip, or a soft **sound**.
At the end you get a **coaching report**.

![Coachy, the avatar, acting out each habit](docs/coachy-moods.png)

> 🔒 **Privacy:** video frames are analysed on your machine and never stored. The
> optional LLM report only ever receives aggregate counts, never images.

## Quick start (uv)

```bash
uv sync                       # creates .venv and installs everything
uv run meeting-coach          # downloads the vision models on first run, opens http://localhost:8000
```

Click **Start camera** and sit naturally for 3 seconds while it calibrates your baseline.
Then click **Pop out** to get a floating, always-on-top coach window to keep next to your
Zoom/Meet/Teams window.

Options: `uv run meeting-coach --port 8080 --no-browser`. Dev: `uv run pytest`, `uv run ruff check`.

> **Linux:** MediaPipe needs EGL/GLES libraries (`sudo apt install libegl1 libgles2`).
>
> **Camera sharing:** macOS and Linux let the browser and your meeting app use the
> camera at the same time. On Windows, some drivers allow only one app at a time; route the
> camera through OBS Virtual Camera if needed.

## How it works

```
Browser                                   Python (FastAPI)
───────                                   ────────────────
getUserMedia ─► 640px JPEG ─(WebSocket)─► MediaPipe Face (478 pts + blendshapes)
                                          MediaPipe Hands (21 pts × 2)
                                          MediaPipe Pose  (33 pts)
                                                 │
                                          features.py  body zones: hair / face / mouth / beard / neck,
                                                       head yaw/pitch, iris gaze, motion history
                                                 │
                                          detectors.py rules  ──┐
                                          learned.py personal ──┴► engine.py  EMA + hysteresis +
                                                                   min-duration + cooldown + escalation
canvas overlays, avatar, PiP ◄─(JSON alerts)─────────────────────────────┘
```

Design choices worth knowing:

* **Contact ≠ overlap.** A hand *in front of* your face overlaps it in 2-D. We compare
  hand size to face size: a hand much larger than "same depth as the face" is closer to the
  camera, so it isn't touching.
* **Occlusion memory.** A hand over your face often makes the face detector lose you, which
  is exactly when you need it. The last face is remembered for 0.8 s.
* **Stroking vs. touching (the focus area).** Both look at the *beard zone*: lower cheeks,
  jaw, chin, and a generous band below the chin, because beards extend past the jaw line the
  face mesh tracks. If the hand is *moving* there, it's `beard_stroke`. If it's resting there,
  or you're propping your head (fingers up the cheek, heel of the palm on the jaw), it's
  `chin_touch`. Stroking takes precedence, so one gesture is never counted twice.
* **Debouncing.** Each habit must hold for `min_duration` seconds, brief dropouts are bridged,
  and each habit has a `cooldown` so one long touch counts once. The more often a habit
  repeats in a 5-minute window, the stronger the cue (severity 1 to 3: the avatar goes green, then orange, then red and sweaty).
* **Calibration.** Posture-type habits (slouching, too close, looking away) are measured
  relative to *your* baseline, captured automatically at start or with **Calibrate**.
* **Works in the background.** Capture is driven by a Web Worker clock, so it keeps running
  while your meeting app has focus and the coach lives in the Picture-in-Picture window.

## Habits

| Habit | Default | Signal |
|---|---|---|
| 🧔 **Stroking beard** | **on (focus)** | hand *moving* in the beard/chin zone |
| 🤔 **Touching chin** | **on (focus)** | hand resting on chin/jaw/beard, or propping the head |
| 🙈 Touching face | off | fingertips in the eyes/nose/cheeks zone |
| 🤐 Hand at mouth | off | fingertips on the lips |
| 🦒 Touching neck | off | fingertips below the beard zone |
| 💇 Playing with hair | off | fingertips above the forehead |
| 🌀 Moving / rocking a lot | off | head speed (face-widths/s) over 3 s |
| 👀 Looking away | off | head yaw/pitch or iris gaze vs. baseline |
| 🐢 Slouching | off | neck length / shoulder width vs. baseline (pose) |
| 🔍 Too close to camera | off | face size vs. baseline |
| 😠 Frowning | off | brow-down blendshapes |
| 🫥 Out of frame | off | no face for a while |
| 🫨 Restless hands | off | sustained hand speed |
| 🙅 Arms crossed | off | wrists crossed over the body midline (pose) |

The focus area is defined in `meeting_coach/conditions.py` (`focus=True`). To change what's on
out of the box, flip that flag. Adding a brand-new habit means one `ConditionConfig` entry plus a
detector function registered in `detectors.DETECTORS`. The UI, stats, report and Teach mode pick it
up automatically.

Each habit has its own sensitivity, hold time, cooldown, detection mode and set of cues
(Habits tab; saved in the browser).

## A specialised model: Teach mode

Rules are a zero-shot baseline, but everybody's habits look a bit different. The
**Teach** tab trains a **personal model**:

1. Record **Neutral** (sit and talk normally) for about 10 s, then record a habit the way *you* do it for about 10 s.
   For the focus area: record *Stroking beard* and *Touching chin* separately, with a few variations each.
2. Click **Train**. A small ExtraTrees classifier is fitted on CPU in under a second,
   using ~67 face-relative, scale-normalised landmark features (no pixels).
3. Set that habit's mode to `learned` (model only) or `either` (rules OR model).

The reported accuracy is measured on the *last* 25% of each recording, not on a random
split, because neighbouring frames are near-duplicates and a random split would inflate it.
Samples and model live in `~/.local/share/meeting_coach/` (override with `MEETING_COACH_DATA_DIR`).

Why not fine-tune a video model? Action-recognition networks (VideoMAE, X3D...) need
thousands of labelled clips and a GPU, and still generalise poorly to one person's quirks.
Landmarks + a tiny classifier get personalisation from about 150 frames. A natural next step
is using a vision-language model *offline* to auto-label recorded landmark sessions.

## Coaching report: pick any LLM (vendor-neutral)

Set `MEETING_COACH_LLM`. If the chosen backend isn't configured, you get the offline
rule-based report and a note explaining why. Override the model with `MEETING_COACH_LLM_MODEL`.

| Backend | `MEETING_COACH_LLM` | Setup |
|---|---|---|
| **Google Gemini, API key** (default) | `gemini` | `GEMINI_API_KEY=...` (or `GOOGLE_API_KEY`) |
| **Gemini on Vertex AI, ADC** | `gemini` (or `vertex`) | `gcloud auth application-default login`, then `GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=my-proj` (optional `GOOGLE_CLOUD_LOCATION`, default `global`) |
| OpenAI / any OpenAI-compatible server (Ollama, LM Studio, vLLM, Groq...) | `openai` | `uv sync --extra openai`; `OPENAI_API_KEY`, optionally `OPENAI_BASE_URL` + `MEETING_COACH_LLM_MODEL` |
| Anthropic Claude | `anthropic` | `uv sync --extra anthropic`; `ANTHROPIC_API_KEY` |
| Offline rules only | `none` | - |

Example with a local model:

```bash
uv sync --extra openai
MEETING_COACH_LLM=openai OPENAI_BASE_URL=http://localhost:11434/v1 MEETING_COACH_LLM_MODEL=llama3.2 uv run meeting-coach
```

## Environment variables

| Variable | Purpose |
|---|---|
| `MEETING_COACH_LLM`, `MEETING_COACH_LLM_MODEL` | report backend and model (see above) |
| `MEETING_COACH_MODEL_DIR` | where MediaPipe `.task` models are cached (default `~/.cache/meeting_coach/models`) |
| `MEETING_COACH_DATA_DIR` | Teach-mode samples and personal model |

## Project layout

```
meeting_coach/
  perception.py  MediaPipe landmarkers (VIDEO mode)
  features.py    zones, head pose, gaze
  detectors.py   rule detectors + calibration/motion context
  learned.py     Teach mode: feature vectors, personal classifier
  engine.py      debouncing state machine, session, stats
  llm.py         Gemini (API key / Vertex ADC), OpenAI-compatible, Anthropic
  report.py      LLM or rule-based coaching report
  server.py      FastAPI + WebSocket protocol
  static/        UI: app.js (capture, overlays, PiP), avatar.js (Coachy)
tests/           synthetic-landmark tests for detectors, engine, teach mode, server, LLM config
```

## Limitations

Detection is heuristic: 2-D landmarks can't fully resolve depth, beards and glasses can
affect the face mesh, and the thresholds are starting points. Use the sensitivity sliders,
the **Debug overlay** (shows zones, hand points, head pose) and Teach mode to tune it for you.
