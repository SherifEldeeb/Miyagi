# INTENT: why Miyagi exists

> This file records **why** the project exists and **what we decided**, so future work
> (by people or AI agents) stays pointed in the same direction. It changes rarely and
> deliberately. *How* things work belongs in [DESIGN.md](DESIGN.md); how to *use* the app
> belongs in [README.md](README.md).

## Problem

On video calls, people slip into unconscious habits: stroking a beard, touching the chin,
face or neck, fiddling with hair, rocking, looking away. Others read these as doubt,
boredom or anxiety. The person doing it almost never notices in the moment, and feedback
after the meeting ("you kept touching your face") is too late to build awareness.

## What we're building

A **real-time, private, gentle mirror**: a local web app that watches the webcam during a
meeting and gives a small, glanceable cue at the moment a habit happens, plus a short
coaching summary afterwards.

## Who it's for

Primarily the author: a bearded professional who wants to stop beard stroking and chin
touching on calls. Secondarily, anyone who presents or interviews over video and wants
low-effort feedback on their non-verbal habits.

## Current focus

**Beard & chin**: `beard_stroke` (moving hand on beard/chin) and `chin_touch` (hand resting
on chin/jaw, or propping the head). Tuning effort goes here first.

Also on by default (D10): `face_touch`, `neck_touch`, `leaning_in`, `slouching`. Every habit
uses the red **border** cue and the **sound** cue (audible once *Sounds* is on, D14) by default.
The remaining habits exist and can be switched on.

## Goals

1. **Catch the focus habits reliably in real meetings**: few misses, few false alarms,
   with a cue within about 1 s of the habit starting.
2. **Be usable *during* a call.** The cue is visible while another app has focus (pop-out
   window), unobtrusive, and never needs interaction.
3. **Private by default.** Video never leaves the machine and is never stored. Nothing else
   leaves it either: there are no cloud APIs (D13).
4. **Personalisable.** People do habits differently; the user can teach the app *their*
   version in about a minute.
5. **Extensible.** Adding or enabling a habit is cheap and doesn't destabilise others.

## Non-goals (for now)

- Judging emotions, personality, or "engagement". We flag concrete, observable behaviours only.
- Recording or uploading video, or analysing *other* participants.
- Being a meeting bot, transcription tool, or speech coach (voice is out of scope for now).
- Cloud hosting or multi-user accounts. It's a single-user local app.
- Training or fine-tuning large vision models (see decision D5).

## Principles

- **Local-first and privacy-first.** Frames are processed in memory on the user's machine,
  and the report is written there too. The only network access is the one-time download of
  the vision models.
- **No cloud services.** Detection uses open, local models (MediaPipe); no part of the app
  depends on a hosted AI API or an API key (D13).
- **Gentle, not shaming.** Cues are playful (Mr. Miyagi the avatar) and escalate only with repetition.
- **Explainable.** Rule detectors are readable geometry; debug overlays show why something fired.
- **Focus, then expand.** Make one habit area excellent before broadening.

## Decision log

Append new decisions; don't rewrite history. If a decision is reversed, add a new entry
that supersedes the old one.

| # | Date | Decision | Why |
|---|---|---|---|
| D1 | 2026-11-06 | Python backend (FastAPI + MediaPipe); the browser only captures and draws | User asked for a Python app; keeps the AI in one testable place |
| D2 | 2026-11-06 | Real-time perception uses MediaPipe landmarkers locally | Fast on CPU, open, private; the landmarks make the rules explainable |
| D3 | 2026-11-06 | The LLM is used only for the end-of-session report, behind a provider interface | The user doesn't want to be tied to one vendor; a real-time LLM would be slow, costly and a privacy risk |
| D4 | 2026-11-06 | **Gemini is the default LLM** for testing and dev, via an API key *or* Vertex AI with ADC; OpenAI-compatible (incl. local) and Anthropic are optional extras; offline rules are the fallback | User request |
| D5 | 2026-11-06 | "Specialised model" = a per-user Teach mode (a small classifier on landmark features), not fine-tuning a video model | Needs about 150 frames, not thousands of clips; runs on CPU; no images stored |
| D6 | 2026-11-06 | Use **uv** for env, run and dev tasks | User request |
| D7 | 2026-11-06 | **Focus area = beard & chin**; every other habit is off by default but one click away | User request: start narrow, add more later |
| D8 | 2026-11-06 | `beard_stroke` takes precedence over `chin_touch` (motion decides) | One gesture must never be counted twice |
| D9 | 2026-11-06 | UI follows **Material Design 3** in Google style: the Google Material 3 blue scheme, Google colors, Google Sans Flex, Material Symbols; light and dark; fonts bundled locally | User request; bundling keeps the UI offline-capable and free of third-party requests |
| D10 | 2026-11-06 | Also enable by default: touching face, touching neck, too close to camera, slouching; the red **border** cue is on for every habit by default. The focus area (tuning priority) stays beard & chin. Supersedes D7's "everything else off" | User request |
| D11 | 2026-11-06 | Default Gemini model is pinned to **`gemini-3.8-flash`** (not a `-latest` alias); override with `MIYAGI_LLM_MODEL` | User request: a pinned model gives predictable behaviour |
| D12 | 2026-11-06 | Project renamed **Miyagi** and moved to `SherifEldeeb/Miyagi`, replacing an earlier prototype there; only its mascot was kept (as the logo). Package `miyagi`, command `miyagi`, env vars `MIYAGI_*` | User request: this implementation is the one going forward |
| D13 | 2026-11-06 | **Remove all cloud LLM support** (Gemini, OpenAI-compatible, Anthropic): no `llm.py`, no `google-genai` dependency or LLM extras, no `MIYAGI_LLM*` or API-key env vars. The end-of-session report is always the on-device summary. Supersedes D3, D4 and D11 | User request: the models run locally, so the cloud APIs added nothing but dependencies, keys and an off-device path |
| D14 | 2026-11-06 | The **sound** cue is on for every habit by default; the global *Sounds* setting (off by default) is the one switch that makes it audible. The beep becomes a soft chime, one note per severity level | User request: turning on Sounds did nothing, because each habit's sound cue was off. Keeping the global switch off by default means nothing chimes during a call until the user asks for it |

## Success criteria

- In a 30-minute real call with deliberate beard and chin touches, at least 90% are flagged
  and there are at most 2 false alarms (to be measured; see the open questions).
- First run to first alert in under 2 minutes with `uv sync && uv run miyagi`.
- Zero network traffic carrying frames (verifiable in the browser devtools).

## Open questions / next steps

- Validate the focus detectors on real bearded faces; tune the beard zone and the stroke-speed threshold.
- Build a small labelled evaluation set (landmark recordings, no video) to measure the success criteria.
- Make it work as a virtual camera (cues baked into the outgoing video)? It might be useful, but it shows cues to others.
- Offline auto-labelling of recordings with a vision-language model to bootstrap Teach mode.
