# Miyagi

A private, Python-powered meeting coach. Notice your hand drifting toward your chin or beard, receive a quiet visual nudge, and return to the conversation.

**Chin/beard touching is the only enabled habit by default.** Face touching, neck touching, and repeated movement can be enabled individually. Detection estimates proximity; it does not establish physical contact or reliably distinguish beard stroking from resting your chin.

## Run with uv

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/), a webcam, and a current browser. Python 3.12 is selected by `.python-version`.

```sh
git clone https://github.com/SherifEldeeb/Miyagi.git
cd Miyagi
uv sync --frozen
uv run miyagi download-models
uv run miyagi serve
```

Open **http://127.0.0.1:8000**. Click **Start my camera**, grant camera access, and sit naturally for three seconds. No API key is required for local coaching. The cue preview works without a webcam or downloaded models and is explicitly simulated.

Keep Miyagi beside your meeting or select focus view. It is a companion browser window, not a Zoom/Meet/Teams plugin or an overlay across other applications. Some camera drivers cannot share the camera with another meeting app. A shared entire desktop can reveal this window.

## What is implemented

- Browser camera capture → local Python MediaPipe face, hand, and pose inference.
- Face-size-normalized proximity rules, sustained-contact timing, and cooldowns.
- Red frame, animated mascot cue, or both; pause, recalibrate, and end-session controls.
- Optional face, neck, and movement habits; chin/beard is the starting focus.
- Gemini by default for optional cloud review, with OpenAI and Anthropic adapters.
- API keys, Gemini/Anthropic Vertex ADC, and Gemini Vertex API-key authentication where supported.
- Explicitly requested three-snapshot cloud reviews; no automatic camera uploads.
- Session-summary export and opt-in labeled feature-window export.
- A trainable binary chin classifier baseline, ONNX export, and optional local ONNX inference.
- Material 3 Expressive-inspired Google theme, self-hosted Google Sans Flex and Material Symbols, and an original AI-generated Miyagi mascot.

## Cloud models and authentication

Defaults checked against official model catalogs on **2026-11-06**:

| Provider | Default model | Supported authentication |
| --- | --- | --- |
| Gemini (development/testing default) | `gemini-3.8-flash` | Gemini API key, Vertex ADC, Vertex API key (express mode) |
| OpenAI | `gpt-6-luna` | OpenAI API key |
| Anthropic | `claude-haiku-5-5` | Anthropic API key or Vertex ADC |

These are selected efficient vision-capable models, not automatic rolling “latest” aliases. All model IDs can be overridden in the UI or environment. Account access, regional support, and billing still apply. The same Haiku model ID is currently documented for the Claude API and Google-managed Vertex route.

Set credentials in your shell, or copy `.env.example` to ignored `.env` and fill only the settings you need. Existing environment values take precedence. Never put keys in the browser, commit them, or include them in screenshots.

For direct APIs, use `GEMINI_API_KEY` (or `GOOGLE_API_KEY`), `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`. For Gemini Vertex express mode, use `VERTEX_API_KEY`; this is separate from the Gemini Developer API key.

For Vertex ADC:

```sh
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_CLOUD_LOCATION=global
uv run miyagi serve
```

Select **Vertex ADC** under Authentication. Google Cloud must have billing/API/model access enabled and an identity with permission to invoke the selected model. Managed deployments can use attached service-account credentials instead of a local login. ADC is **not** an authentication method for the direct OpenAI API. See [provider details](docs/architecture.md).

Enable snapshot sharing and click **Ask Gemini** (or the selected provider) to send three camera snapshots about one second apart. The fast local loop continues independently. Provider changes reset sharing consent. A single cloud review can return a gentle cue; it cannot reliably establish a habitual action from sparse snapshots.

## Development and checks

```sh
uv sync --frozen --all-extras
uv run --all-extras pytest
node --check miyagi/static/app.js

# Optional live checks: send a synthetic gray image and consume provider quota.
uv run python scripts/check_providers.py
uv run python scripts/check_providers.py --provider openai
uv run python scripts/check_providers.py --provider anthropic
uv run python scripts/check_providers.py --provider gemini --auth vertex_adc
```

The automated suite does not need API credentials, camera access, or downloaded vision weights. It covers timing/occlusion behavior, image limits, cross-origin rejection, provider/auth routing, response validation, WebSocket lifecycle, and synthetic train→ONNX→inference compatibility. Synthetic training results establish plumbing correctness, not real-world accuracy.

## Specialized model path

Start by training **neutral vs chin/beard contact** using the Model lab exports. The included trainer holds out whole participants, writes validation metrics, and exports a portable ONNX classifier. No trained behavior model or claimed detection benchmark is bundled. Read the [training plan](docs/model-training.md) for collection, evaluation, and the next step toward detecting actual beard stroking.

```sh
uv run --extra train python scripts/train.py data/windows.jsonl --output models/chin.onnx
MIYAGI_ONNX_MODEL=models/chin.onnx uv run --extra onnx miyagi serve
```

## Data boundaries and current limits

The server binds to loopback. Frames are processed in memory and are not recorded. There is no microphone capture, identity recognition, emotion scoring, or meeting transcript. Miyagi adds no analytics integration, but the bundled MediaPipe SDK may send usage and performance metrics to Google; Google states that camera input stays on-device. See the [MediaPipe privacy notice](https://developers.google.com/edge/mediapipe/solutions/privacy). Model and font downloads are setup-time network requests; optional cloud review sends images to the chosen provider under its data policies. `store=False` is set for OpenAI responses, but is not a claim of zero provider retention.

This is a single-user local app, without production authentication or multi-tenant isolation. Do not expose it as an unauthenticated hosted service. Occlusion, lighting, camera angles, hands passing in front of the face, and other people in frame can produce misses or false cues. Keep one person in view. Treat cues as optional reminders, never as a judgment of professionalism or a behavioral diagnosis.

## Design and references

- [Architecture and extension points](docs/architecture.md)
- [Specialized model research and tuning](docs/model-training.md)
- [Design system and mascot generation prompt](docs/design.md)
- [Verification record](docs/verification.md)
- [Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash), [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [Claude Haiku 5.5](https://platform.claude.com/docs/en/models/haiku-5-5/overview)

Third-party font and symbol licenses are included in `miyagi/static/fonts/`. Downloaded MediaPipe weights are untracked, with their source URLs and locally computed SHA-256 values in `models/manifest.json`.
