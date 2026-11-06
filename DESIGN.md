# DESIGN: how Miyagi works

> The technical source of truth. Read it before changing behaviour, and update it in the
> same change when behaviour changes (see [AGENTS.md](AGENTS.md#keeping-docs-up-to-date)).
> For *why*, see [INTENT.md](INTENT.md). For *usage*, see [README.md](README.md).

## 1. Architecture

```
Browser (static/)                               Python (miyagi/)
─────────────────                               ───────────────────────
getUserMedia ─► 640px JPEG + ts ─(WebSocket /ws)─► server.py ─► engine.CoachSession
                                                                   │
                                     perception.py  MediaPipe Face (478 pts + blendshapes),
                                                    Hands (21 pts × 2), Pose (33 pts)
                                                                   │ observation.Observation
                                     features.py    zones, head pose, gaze, occlusion memory
                                                                   │ features.Features
                       detectors.py (rules) ──┐    learned.py (personal model)
                                              └──► engine.Tracker per habit: EMA → hysteresis →
                                                   min-duration → linger → cooldown → severity
canvas overlays · Mr. Miyagi · toast · PiP ◄─(JSON result per frame)───┘
End & report ─► report.py ─► llm.py (Gemini | OpenAI-compatible | Anthropic | none)
```

There is one `CoachSession` (and one set of MediaPipe landmarkers) per WebSocket
connection. The personal model is shared app-wide; it's a single-user local app.

## 2. Module map

| Module | Responsibility |
|---|---|
| `geometry.py` | `Box` and distance helpers; isotropic coordinates |
| `observation.py` | `Observation` / `HandObs`: raw per-frame landmarks |
| `models.py` | Download and cache MediaPipe `.task` files |
| `perception.py` | `MediaPipePerception`: runs the face, hand and pose landmarkers in VIDEO mode |
| `features.py` | Body zones, head yaw/pitch/roll, iris gaze, hand contact points, face memory |
| `conditions.py` | Habit catalogue (`ConditionConfig`), user-tunable settings, focus area |
| `detectors.py` | Rule detectors + `Context` (motion history, calibration baseline) |
| `learned.py` | Teach mode: feature vectors, `PersonalModel` (ExtraTrees), persistence |
| `engine.py` | `Tracker` debouncing state machine, `CoachSession`, stats |
| `llm.py` | Vendor-neutral LLM providers |
| `report.py` | Coaching report: LLM or rule-based fallback |
| `server.py` | FastAPI app, REST and WebSocket protocol |
| `__main__.py` | CLI entry point (`miyagi`) |
| `static/app.js` | Capture loop, socket, overlays, settings UI, Teach UI, PiP, report |
| `static/index.html` | Full UI: top app bar, camera stage, Live / Habits / Teach panels, report dialog |
| `static/coach.html` | Coach-only view (`/coach`): just the canvas; `body[data-mode=coach]` switches `app.js` into coach mode |
| `static/avatar.js` | Mr. Miyagi: canvas-drawn take on the mascot, one "mood" per habit id |
| `static/style.css` | Material Design 3 theme: color, type and shape tokens; M3 components |
| `static/brand/` | Miyagi mascot (logo): header, favicon, camera-off screen |
| `static/fonts/` | Bundled Google Sans Flex, Roboto Mono, Material Symbols Rounded (subset from `icons.txt`) |
| `scripts/fetch_fonts.py` | Re-downloads the bundled fonts and re-subsets the icons |
| `scripts/avatar_moods.html` | Mood sheet: every avatar mood side by side; renders `docs/miyagi-moods.png` |
| `scripts/screenshots.py` | Regenerates the README screenshots with Chrome's fake camera (stages a beard alert) |

## 3. Coordinates

All internal geometry is **isotropic**: `x` is multiplied by the frame aspect ratio, so one
unit equals one frame height on both axes. Distances are normalised by **face width `fw`**
(cheek 234 to cheek 454) or **face height `fh`** (forehead 10 to chin 152), which makes
thresholds independent of camera distance and resolution. Boxes go back to the client as
normalised `{x, y, w, h}` in `[0, 1]` of the *unmirrored* frame; the client mirrors them for display.

## 4. Zones (`features.face_features`)

| Zone | Extent (y down) |
|---|---|
| `hair` | forehead top − 0.5 fh → forehead + 0.12 fh; face box ± 0.18 fw |
| `face` | forehead + 0.12 fh → midway between nose and lower lip; face box ± 0.05 fw |
| `mouth` | around the lip corners and lips (± 0.08 fw) |
| `beard` | midway nose/lip → **chin + 0.2 fh**; face box ± 0.05 fw (generous below the chin, because beards extend past the jaw the mesh tracks) |
| `neck` | chin + 0.2 fh → chin + 0.95 fh; nose ± 0.55 fw |

**Hand → zone** (`detectors.hand_zone`): score each zone by the hand's contact points
inside it (fingertips weigh 1.0, distal joints 0.5; `mouth` × 1.6). The best positive score
wins, with ties going to the earlier zone in `ZONE_PRIORITY`. A **depth gate** rejects
hands whose size `hand.scale / fw > MAX_HAND_FACE_RATIO (1.2)`: such a hand is in front of
the face, not touching it.

**Face memory:** if the mesh drops out (often *because* a hand covers the face), the last
face is reused for `FACE_MEMORY_S = 0.8` s and marked `fresh=False`. Motion and pose
detectors ignore non-fresh faces.

## 5. Habits and detectors

On by default: the focus habits plus `conditions.DEFAULT_ON` (`face_touch`, `neck_touch`,
`leaning_in`, `slouching`). Every habit has the `border` cue by default.

`param` is interpolated from `param_hard` (sensitivity 0) to `param_easy` (sensitivity 100).

| id | Focus | Detector logic | `param` meaning |
|---|---|---|---|
| `beard_stroke` | ✅ | hand → `beard` zone **and** hand speed ≥ param | stroke speed (fw/s) |
| `chin_touch` | ✅ | hand → `beard` zone, or → `face` with the **wrist inside `beard`** (propping the head); suppressed while speed ≥ `beard_stroke.param` | zone scale |
| `face_touch` | | hand → `face` zone | zone scale |
| `hand_to_mouth` | | hand → `mouth` zone | zone scale |
| `neck_touch` | | hand → `neck` zone | zone scale |
| `hair_touch` | | hand → `hair` zone | zone scale |
| `excessive_movement` | | head path length over 3 s, resampled at 0.2 s to damp jitter | fw/s |
| `looking_away` | | yaw, pitch or iris gaze off the calibrated baseline | yaw threshold (pitch × 0.35, gaze × 0.4) |
| `slouching` | | neck ratio (shoulder-mid y − face y) / shoulder width below baseline × (1 − param) | fraction |
| `leaning_in` | | fw > baseline fw × (1 + param) | fraction |
| `frowning` | | mean of `browDownLeft`/`browDownRight` blendshapes > param | score |
| `out_of_frame` | | no face (after calibration) | – |
| `fidgeting` | | max hand speed over 3 s > param | fw/s |
| `arms_crossed` | | both wrists past the body midline on the opposite side (pose) | – |

**Calibration** (`Context`): the first `CALIBRATION_S = 3` s with a face (or a
`calibrate` message) collects median face width, yaw, pitch, gaze and neck ratio as the
`Baseline`. Posture-type detectors return inactive until a baseline exists.

## 6. Alert engine (`engine.Tracker`)

```
raw bool ─► EMA (τ = 0.25 s) ─► ≥ 0.6 for min_duration and cooldown elapsed ─► ALERT (counted once)
                               ◄─ < 0.3 for LINGER_S = 0.6 s ─ ends the alert, starts the cooldown
```

- **Severity** is the number of alerts in the last `ESCALATION_WINDOW_S = 300` s: up to 2 → 1, up to 5 → 2, otherwise 3.
  The UI makes cues louder with severity (thicker box, faster pulse, avatar backdrop green → yellow → red, flushed and sweating at 3).
- **Detection mode** per habit: `rules`, `learned` (personal model only) or `either` (OR).
  The learned signal fires when `p ≥ 0.85 − 0.5 × sensitivity/100`. Without a trained class,
  it falls back to the rules.
- During Teach recording, every habit is forced inactive.

## 7. Personal model (`learned.py`)

- **Features** (`FEATURE_DIMS = 67`): for up to 2 hands (sorted by x), the 10 contact points
  relative to the face centre / fw, plus hand scale and speed; head yaw, pitch, roll and gaze
  relative to the baseline; face scale; head speed; 12 blendshapes; neck ratio relative to the
  baseline. Returns `None` without a face.
- **Model:** `ExtraTreesClassifier(200, min_samples_leaf=2, class_weight="balanced")`.
  Training needs ≥ 20 samples of `neutral` and of at least one habit.
- **Evaluation:** hold out the *last 25%* of each class chronologically (a random split
  leaks between near-duplicate frames).
- **Storage:** `$MIYAGI_DATA_DIR` (default `~/.local/share/miyagi/`):
  `teach_samples.npz`, `personal_model.joblib`. Files with a mismatched `FEATURE_DIMS` are
  ignored, so **changing the feature vector invalidates saved models**: note that in the PR.

## 8. Wire protocol (`/ws`)

Client → server:
- **binary:** `<f8` little-endian timestamp in ms (client monotonic clock), followed by the JPEG bytes.
  At most one frame is in flight: the client waits for the result (3 s watchdog).
- **text JSON** control messages:

| `type` | Payload | Reply |
|---|---|---|
| `config` | `conditions: {id: {enabled, sensitivity, min_duration, cooldown, styles, mode}}`, `debug` | – |
| `calibrate` | – | – |
| `reset` | – | – |
| `report` | – | `report` (`markdown`, `source`, `note?`, `stats`) |
| `teach` | `label` (habit id or `neutral`), `seconds` | progress arrives in `result.teach` |
| `train` | – | `trained` (`ok`, `classes`, `holdout_accuracy`, `personal`) |
| `teach_clear` | `label` or `null` (all) | `personal` |
| `status` | – | `personal` |

Server → client per frame: `result` with `alerts[]` (`id, label, emoji, tip, styles,
severity, count, new, box`), `face_box`, `calibrating`, `calibrated`, `counts`, `elapsed`,
an optional `teach`, and with `debug` on, `debug` (zones, hand points, head) and `learned` (probabilities).
Errors arrive as `{type: "error", message}`.

Pages: `GET /` serves the full UI, `GET /coach` the coach-only view.

REST: `GET /api/conditions` returns the defaults, `focus_area`, styles, modes and personal-model status.

## 9. Frontend (`static/`)

- A **Web Worker ticker** (~30 Hz) drives capture *and* drawing, because `requestAnimationFrame`
  stops in background tabs and during calls the app lives in the PiP window.
- **Pop out** = `canvas.captureStream()` → hidden `<video>` → Picture-in-Picture. Everything
  shown in the PiP window must be drawn on the main canvas (including the corner Mr. Miyagi and the toast).
- **Cues** (`ALERT_STYLES`): `box`, `mask` (emoji over `face_box`), `border`, `avatar`,
  `toast`, `sound` (WebAudio, gated by the Sounds toggle).
- **Settings** are saved per browser in `localStorage` (`miyagi.settings.v1`); the
  `focus` flag always comes from the server.
- **Mr. Miyagi:** `avatar.js` has one `MOODS` entry per habit id. A new habit should get a mood
  (otherwise it falls back to idle). He is drawn from canvas primitives in head-radius units
  (bald head, cloud beard, blue gi, hands on sleeves) on a backdrop disc that clips the gi.
  To review moods, serve the repo root (`uv run python -m http.server 8001`) and open
  `/scripts/avatar_moods.html` (`?t=1.3&sev=1..3&r=44&cols=8`); `docs/miyagi-moods.png` is a headless
  Chrome screenshot of `?t=1.3&sev=1` at 1197×388, device scale 2.

- **Coach-only mode** (`/coach`, `miyagi --coach`): the same `app.js`, guarded by
  `COACH = body.dataset.mode === "coach"`. It auto-starts the camera, never renders the panels,
  has no visible controls (keyboard: P pop out, C calibrate, Space pause, F full screen, M mirror,
  H help), and shows messages as an on-canvas banner (`notice()`) instead of a snackbar. Settings
  come from the same `localStorage` key, so they're shared with the full UI **per origin (host:port)**.
  Any new DOM access in `app.js` must be null-safe or skipped in coach mode.

### 9.1 Theme: Material Design 3, Google style

- **Color:** M3 color roles as CSS custom properties (`--md-sys-color-*`) in `style.css`, using
  Google's Material 3 blue baseline scheme (primary `#0B57D0` light / `#A8C7FA` dark,
  surfaces `#F8FAFD` / `#131314`). Dark mode follows `prefers-color-scheme`. Google brand
  accents (`--g-blue #4285F4`, `--g-red #EA4335`, `--g-yellow #FBBC04`, `--g-green #34A853`)
  are reserved for status, alerts and Mr. Miyagi. Components use **roles, never raw hex**.
- **Type:** Google Sans Flex (variable) for every role in the M3 type scale (`.title-large`,
  `.label-large`, `.body-medium`, …), with Roboto Mono for numbers and timestamps.
- **Shape:** the M3 shape scale (`--md-sys-shape-xs…full`): cards 16–28 px, chips 8 px, buttons fully rounded.
- **Icons:** Material Symbols Rounded via ligatures (`<span class="icon">name</span>`), with the
  variable axes FILL/wght/GRAD/opsz used for selected states. The font is **subset**: every icon
  name must be listed in `static/fonts/icons.txt`; then run `uv run python scripts/fetch_fonts.py`.
- **Components** (hand-built, no framework): top app bar, filled/tonal/outlined/text buttons,
  assist chip (status), primary tabs, M3 switch, filter chips (cues), segmented button
  (detect mode), slider, lists with badges, dialog, snackbar. State layers use 8% hover / 10% pressed.
- **On-video (canvas) cues** use the same language: a red `#EA4335` rounded box and label chip, an
  inverse-surface snackbar for tips (accent bar blue → yellow → red by severity), a pill banner
  with a Material Symbol, and Mr. Miyagi on a Google tonal backdrop (idle blue; green, yellow, red by severity).
- **Brand:** the Miyagi mascot (a friendly bearded coach with a hand under his chin, matching the
  beard & chin focus) is the logo, favicon and camera-off art. The source is `docs/brand/miyagi-mascot.png`
  (1254 px RGBA); the sized copies (`static/brand/miyagi-192.png`, `miyagi-64.png`, `favicon-32.png`) are made
  with OpenCV `INTER_AREA`. It is original AI-generated artwork carried over from the earlier Miyagi prototype,
  not the Google logo. Mr. Miyagi, the animated habit-acting companion, is a canvas-drawn version of the same character
  (no image assets, so he also renders in the Picture-in-Picture window).
- **Privacy:** fonts are vendored, so the page makes **no third-party requests** (tested).

## 10. LLM layer (`llm.py`, `report.py`)

`get_provider()` reads `MIYAGI_LLM` (default `DEFAULT_PROVIDER = "gemini"`). The providers are:
`GeminiProvider` (model `GEMINI_DEFAULT_MODEL = "gemini-3.8-flash"`, pinned rather than a `-latest` alias; API key `GEMINI_API_KEY`/`GOOGLE_API_KEY`, or Vertex AI with ADC when
`GOOGLE_GENAI_USE_VERTEXAI=true` + `GOOGLE_CLOUD_PROJECT` [+ `GOOGLE_CLOUD_LOCATION`]),
`OpenAICompatibleProvider` (`OPENAI_API_KEY`, `OPENAI_BASE_URL`) and `AnthropicProvider`
(`ANTHROPIC_API_KEY`, server-side refusal fallback enabled). SDKs are imported lazily.
Any `LLMError` (missing key, auth, network, refusal) falls back to `rule_based_report`
with a `note`. **Only `CoachSession.stats()` output is ever sent.**

## 11. Testing

- `tests/synth.py` builds synthetic face meshes and hands, so detectors and the engine are tested without a camera.
- `test_detectors.py`: zones, each detector, focus-area behaviour, debouncing, escalation.
- `test_learned_and_server.py`: teach → train → learned mode, persistence, WebSocket round-trip with a fake perception, report fallback.
- `test_llm.py`: provider selection and configuration; a MediaPipe smoke test (skipped if the models are missing).
- `test_docs.py`: **checks that the docs match the code** (habits, defaults, env vars, protocol, modules).

## 12. Extending

**Add a habit:** add a `ConditionConfig` in `conditions.py` (set `focus=True` only if it
joins the focus area) → add a detector and register it in `detectors.DETECTORS` → add a
`MOODS` entry in `avatar.js` and its id in `PRIORITY` in `app.js` → add tests with
`synth.py` → update the habit tables in README.md and §5 here. Teach mode, stats, the report
and the settings UI pick it up automatically.

**Add an LLM backend:** add a class with `name`, `model` and `async complete()` raising `LLMError`,
register it in `PROVIDERS`, add an optional extra in `pyproject.toml`, and document its env vars in the README.

## 13. Known limitations

- 2-D landmarks can't resolve depth fully; the depth gate is a heuristic.
- Thick beards, glasses and low light can degrade the face mesh, especially around the jaw.
- Thresholds were tuned on synthetic data only and still need real-world validation (INTENT open questions).
- One perception instance per connection; not designed for multiple simultaneous users.
