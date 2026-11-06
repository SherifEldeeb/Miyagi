"""Vendor-neutral LLM layer (used only for the end-of-session coaching report).

Pick a backend with ``MEETING_COACH_LLM``:

    gemini     (default) Google Gemini, via API key (``GEMINI_API_KEY`` /
               ``GOOGLE_API_KEY``) or Vertex AI with Application Default
               Credentials (``GOOGLE_GENAI_USE_VERTEXAI=true`` +
               ``GOOGLE_CLOUD_PROJECT``)
    openai     any OpenAI-compatible server: OpenAI, Ollama, LM Studio, vLLM,
               Groq, Together... (``OPENAI_BASE_URL`` / ``OPENAI_API_KEY``)
    anthropic  Claude (``ANTHROPIC_API_KEY``)
    none       rule-based report, fully offline

If the chosen backend is not configured (no key / credentials), the report
falls back to the offline rule-based version and says why.

``MEETING_COACH_LLM_MODEL`` overrides the model name for any backend. SDKs
are optional extras and imported lazily, so you only install what you use.
Only aggregate statistics are ever sent - never images or landmarks.
"""

from __future__ import annotations

import os
from typing import Protocol


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete(self, system: str, prompt: str, max_tokens: int = 4000) -> str: ...


def _env_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _model(default: str | None) -> str:
    model = os.environ.get("MEETING_COACH_LLM_MODEL") or default
    if not model:
        raise LLMError("Set MEETING_COACH_LLM_MODEL to the model name your server serves.")
    return model


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        try:
            import anthropic
        except ImportError as e:
            raise LLMError("pip install 'meeting-coach[anthropic]'") from e
        self._anthropic = anthropic
        self.client = anthropic.AsyncAnthropic()
        self.model = _model("claude-opus-5-5")

    async def complete(self, system: str, prompt: str, max_tokens: int = 4000) -> str:
        a = self._anthropic
        try:
            # Server-side refusal fallback is enabled ("default" routing).
            resp = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except a.AuthenticationError as e:
            raise LLMError("Anthropic: invalid or missing API key") from e
        except a.RateLimitError as e:
            raise LLMError("Anthropic: rate limited, try again shortly") from e
        except a.APIStatusError as e:
            raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except a.APIConnectionError as e:
            raise LLMError("Anthropic: network error") from e
        if resp.stop_reason == "refusal":
            raise LLMError("Anthropic: the model declined this request")
        return "".join(b.text for b in resp.content if b.type == "text").strip()


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(self) -> None:
        try:
            import openai
        except ImportError as e:
            raise LLMError("pip install 'meeting-coach[openai]'") from e
        self._openai = openai
        # Reads OPENAI_API_KEY / OPENAI_BASE_URL. Local servers (Ollama etc.)
        # usually accept any non-empty key.
        base_url = os.environ.get("OPENAI_BASE_URL")
        api_key = os.environ.get("OPENAI_API_KEY") or ("local" if base_url else None)
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = _model(None if base_url else "gpt-4o-mini")

    async def complete(self, system: str, prompt: str, max_tokens: int = 4000) -> str:
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            )
        except self._openai.APIError as e:
            raise LLMError(f"OpenAI-compatible API error: {e}") from e
        return (resp.choices[0].message.content or "").strip()


class GeminiProvider:
    """Gemini via the Gemini API (API key) or Vertex AI (ADC)."""

    name = "gemini"

    def __init__(self) -> None:
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise LLMError("pip install 'meeting-coach[gemini]'") from e
        self._types = types
        self._errors = genai.errors
        if _env_true("GOOGLE_GENAI_USE_VERTEXAI"):
            project = os.environ.get("GOOGLE_CLOUD_PROJECT")
            if not project:
                raise LLMError("Vertex AI: set GOOGLE_CLOUD_PROJECT (and run `gcloud auth application-default login`)")
            location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
            # No api_key: google-auth resolves Application Default Credentials.
            self.client = genai.Client(vertexai=True, project=project, location=location)
            self.backend = f"vertex:{project}/{location}"
        else:
            key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not key:
                raise LLMError("Gemini: set GEMINI_API_KEY, or GOOGLE_GENAI_USE_VERTEXAI=true for Vertex AI + ADC")
            self.client = genai.Client(api_key=key)
            self.backend = "gemini-api"
        self.model = _model(GEMINI_DEFAULT_MODEL)

    async def complete(self, system: str, prompt: str, max_tokens: int = 4000) -> str:
        try:
            resp = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens),
            )
        except self._errors.APIError as e:
            raise LLMError(f"Gemini API error {e.code}: {e.message}") from e
        except Exception as e:  # e.g. google.auth DefaultCredentialsError
            raise LLMError(f"Gemini: {e}") from e
        return (resp.text or "").strip()


DEFAULT_PROVIDER = "gemini"  # default for testing & development
GEMINI_DEFAULT_MODEL = "gemini-3.8-flash"  # pinned (not a "-latest" alias)

PROVIDERS = {
    "anthropic": AnthropicProvider,
    "claude": AnthropicProvider,
    "openai": OpenAICompatibleProvider,
    "ollama": OpenAICompatibleProvider,
    "gemini": GeminiProvider,
    "vertex": GeminiProvider,
}


def get_provider(name: str | None = None) -> LLMProvider | None:
    name = (name or os.environ.get("MEETING_COACH_LLM", DEFAULT_PROVIDER)).strip().lower()
    if name in ("", "none", "off", "rules"):
        return None
    if name == "vertex":
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
    if name not in PROVIDERS:
        raise LLMError(f"Unknown MEETING_COACH_LLM={name!r}; choose one of none, {', '.join(sorted(set(PROVIDERS)))}")
    return PROVIDERS[name]()
