# AGENTS.md

Instructions for AI coding agents **and** human contributors working on this repo.
Read this first, then [INTENT.md](INTENT.md) (why) and [DESIGN.md](DESIGN.md) (how).

## Project in one paragraph

Meeting Coach is a local Python web app (FastAPI + MediaPipe) that watches the webcam
during video calls and gives real-time visual cues when the user slips into unconscious
habits. **Current focus: beard stroking (`beard_stroke`) and chin touching (`chin_touch`).**
Every other habit exists but is off by default. Frames stay on the machine; an optional,
vendor-neutral LLM (Gemini by default) writes an end-of-session report from aggregate stats only.

## Setup and commands (always use uv)

```bash
uv sync                                  # install (add --extra openai / --extra anthropic as needed)
uv run meeting-coach                     # run the app → http://localhost:8000
uv run meeting-coach --no-browser --port 8765
uv run pytest                            # all tests (must pass)
uv run ruff check . && uv run ruff format --check .   # lint (must pass)
```

- Don't use `pip install` or bare `python`; use `uv add <pkg>` / `uv add --dev <pkg>` so
  `pyproject.toml` and `uv.lock` stay in sync. Commit `uv.lock`.
- Linux needs `libegl1 libgles2` for MediaPipe. MediaPipe models download on first run to
  `~/.cache/meeting_coach/models` (`MEETING_COACH_MODEL_DIR` overrides it).
- To test the UI headlessly: Chromium with `--use-fake-device-for-media-stream
  --use-fake-ui-for-media-stream` (the fake camera has no face, so it only proves the pipeline and UI wiring).

## Where things are

See the module map in [DESIGN.md §2](DESIGN.md#2-module-map). In short: `perception` →
`features` → `detectors` / `learned` → `engine` → `server` → `static/app.js` (+ `avatar.js`).
The habit catalogue is `conditions.py`; the LLM backends are `llm.py`.

## Rules that must not be broken

1. **Privacy:** never persist, log or transmit video frames or images. Never send landmarks,
   feature vectors or anything identifying to an LLM. Only `CoachSession.stats()` may leave the machine.
2. **Vendor-neutral:** no provider SDK may be imported at module top level outside its
   provider class in `llm.py`. Every LLM failure must fall back to the rule-based report.
3. **Focus area:** only `focus=True` habits are enabled by default. Don't enable others by
   default without a decision entry in INTENT.md.
4. **No double counting:** one physical gesture must map to at most one habit (e.g. stroking beats touching).
5. **Real-time budget:** per-frame Python work beyond MediaPipe must stay well under 10 ms.
   No network calls on the frame path.
6. **Tests use synthetic landmarks** (`tests/synth.py`), never real images of people.
7. **Saved personal models:** changing `learned.feature_vector` (or `FEATURE_DIMS`)
   invalidates users' saved models. Call that out in the commit/PR.

## Coding conventions

- Python ≥ 3.11, type hints, small pure functions; detectors are stateless (state lives in `Context`/`Tracker`).
- Geometry is isotropic and normalised by face width/height (DESIGN §3). Never use raw pixels in detectors.
- Tunable constants are UPPER_CASE at module top, documented in DESIGN.md.
- Frontend: plain JS, no build step, no frameworks. Everything visible in Pop-out must be drawn on the main canvas.
- **UI theme is Material Design 3, Google style** (DESIGN §9.1). Use the `--md-sys-*` tokens and the
  M3 type-scale classes; don't hard-code colors or fonts in components (raw hex only in the `:root`
  token blocks and for Google accents on the canvas). Match M3 component anatomy when adding UI.
- **Icons:** Material Symbols Rounded only. To use a new icon, add its name to
  `meeting_coach/static/fonts/icons.txt` and run `uv run python scripts/fetch_fonts.py` (the font is
  subset, so unlisted icons render as text). `test_docs.py` checks this.
- **No third-party requests from the page** (no CDNs, no Google Fonts URLs). Vendor any asset.
- Prefer adding a test in `tests/` with every behaviour change; a detector change needs a positive *and* a negative case.

## Keeping docs up to date

Docs are part of the change, not a follow-up. **Update the docs in the same commit as the code.**

| If you change… | Update |
|---|---|
| How to install, run or configure; env vars; CLI flags; user-visible features or UI | **README.md** |
| Architecture, a module's responsibility, zones, detector logic, thresholds/constants, engine behaviour, wire protocol, storage format, the extension steps | **DESIGN.md** (the relevant section) |
| Goals, non-goals, focus area, principles, a significant product/tech decision (new dependency category, new default, reversing a decision) | **INTENT.md**: append a row to the *Decision log* (never rewrite old rows) and update *Current focus* / *Open questions* |
| Commands, workflow, conventions, invariants, the doc rules themselves | **AGENTS.md** |
| Adding/removing a habit | README habit table **and** DESIGN §5 table **and** `avatar.js` `MOODS` + `app.js` `PRIORITY` |
| Adding a module | DESIGN §2 module map |
| Adding a WS message type | DESIGN §8 table |
| Theme tokens, components, fonts, icons | DESIGN §9.1 (and `icons.txt` + `scripts/fetch_fonts.py` for icons) |

What enforces this:

- `tests/test_docs.py` fails if the docs drift from the code: every habit (with the right
  on/off default) must be in the README table, every habit id in DESIGN §5, every env var the code
  reads in the README, every WS message type and every module in DESIGN, the focus habits in INTENT,
  every icon used in the UI in `icons.txt`, and no external URLs in the static files.
  **If it fails, fix the docs; don't weaken the test.**
- The PR template (`.github/pull_request_template.md`) has a docs checklist.
- Before finishing any task, agents must re-read the diff and ask: *"Would README, DESIGN, INTENT or AGENTS now say something false or incomplete?"* If yes, fix it.

Style: keep docs concise and factual, show real commands, and keep the "why" in INTENT,
the "how" in DESIGN and the "use" in README. Don't duplicate long explanations; link instead.

## Definition of done

- [ ] `uv run pytest` passes (including `test_docs.py`)
- [ ] `uv run ruff check .` passes
- [ ] New or changed behaviour has tests (positive and negative)
- [ ] Docs updated per the table above; decision log appended if a decision was made
- [ ] No frames, images or landmarks persisted or sent off-device
- [ ] UI changes checked in a browser (or headless with the fake camera) with no console errors

## Commits and PRs

- Imperative, descriptive subject; the body explains *why*. Mention doc updates and any
  invalidation of saved personal models.
- Don't commit `.venv/`, model `.task` files, `*.bundle`, or Teach-mode data.
