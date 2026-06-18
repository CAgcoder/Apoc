"""Model -> provider and model -> capability routing.

A single APoc run now mixes providers (DeepSeek research/candidates/reviews,
Haiku document writing, Opus judging), so the provider must be derived from the
model string per call rather than from the global ``config.PROVIDER``.
"""

from __future__ import annotations

from . import config

# Models that take adaptive thinking + the effort parameter. Haiku 4.5 takes
# NEITHER (effort returns 400; it is not an adaptive-thinking model), so it must
# be excluded — sending those params silently breaks every Haiku call.
_EFFORT_MODELS = ("claude-opus-4", "claude-sonnet-4-6", "claude-fable-5")
_ADAPTIVE_THINKING_MODELS = ("claude-opus-4", "claude-sonnet-4-6", "claude-fable-5")


def provider_for_model(model: str) -> str:
    m = (model or "").lower()
    if m.startswith("claude") or m.startswith("us.anthropic"):
        return "anthropic"
    if m.startswith("deepseek"):
        return "deepseek"
    return config.PROVIDER  # unknown -> configured default


def supports_effort(model: str) -> bool:
    m = (model or "").lower()
    return any(m.startswith(p) for p in _EFFORT_MODELS)


def is_adaptive_thinking_model(model: str) -> bool:
    m = (model or "").lower()
    return any(m.startswith(p) for p in _ADAPTIVE_THINKING_MODELS)
