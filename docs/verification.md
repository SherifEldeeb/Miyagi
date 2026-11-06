# Verification — 2026-11-06

## Completed

- `uv sync --frozen --all-extras`: reproducible dependency resolution/install using Python 3.12 and the committed lockfile.
- `uv run --all-extras pytest`: 23 tests passed. Includes authentication routing for all six supported provider/auth combinations, timing/occlusion/cooldown behavior, request limits, same-origin enforcement, WebSocket resource cleanup, and binary chin-model train/export/ONNX inference.
- `node --check miyagi/static/app.js`: passed.
- Real MediaPipe model initialization and inference on a synthetic blank image: completed, with no face, hand, or shoulder detections.
- Browser live session: tracking and an actual chin/beard cue were observed. This is a functional check, not a labeled accuracy benchmark.
- Browser UI: cue preview, pause, expandable additional habits, provider-dependent authentication options, and the Material theme were checked. Camera footage was not saved in the repository.
- Live API-key checks with synthetic gray images: `gemini-3.8-flash`, `gpt-6-luna`, and `claude-haiku-5-5` all returned valid reviews with zero observations. No real camera image was used for these API checks.
- Generated mascot has an RGBA alpha channel with transparent pixels and is stored in the application assets.

## Limits

- MediaPipe emitted Clearcut usage-metric upload attempts during local testing. The UI and documentation disclose SDK metrics separately from camera input; there is no claim of zero outbound network activity.

- Vertex ADC and Vertex API-key paths are covered with SDK/auth mocks; no live Google Cloud project or regional entitlement was configured for this verification.
- No labeled real-world benchmark or specialized behavior model has been trained. The synthetic classifier test proves serialization/inference compatibility only.
- Browser background throttling, low-end hardware, mobile cameras, and simultaneous camera access with every meeting client have not been benchmarked.
- The macOS sandbox prevented native MediaPipe graphics initialization; the model smoke test succeeded with normal macOS graphics access. This is relevant to restrictive sandboxed execution, not a need for a hosted AI service.
- The installed Starlette test client emitted a dependency deprecation notice about its future HTTP client; tests pass with the locked dependencies.

## Repeat the checks

```sh
uv sync --frozen --all-extras
uv run --all-extras pytest
node --check miyagi/static/app.js
```

Live provider checks are opt-in and consume quota:

```sh
uv run python scripts/check_providers.py
uv run python scripts/check_providers.py --provider openai
uv run python scripts/check_providers.py --provider anthropic
```

Default models are a reviewed snapshot of the official catalogs on this date. Override them deliberately as new appropriate models become available; do not assume an account has access solely because a model is listed publicly.
