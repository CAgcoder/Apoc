from app import models


def test_provider_for_model_routes_by_prefix():
    assert models.provider_for_model("claude-opus-4-8") == "anthropic"
    assert models.provider_for_model("claude-haiku-4-5") == "anthropic"
    assert models.provider_for_model("deepseek-chat") == "deepseek"


def test_provider_for_model_unknown_falls_back_to_config_default(monkeypatch):
    monkeypatch.setattr(models.config, "PROVIDER", "deepseek", raising=False)
    assert models.provider_for_model("some-local-model") == "deepseek"


def test_capability_gates():
    # Opus 4.x: adaptive thinking + effort
    assert models.is_adaptive_thinking_model("claude-opus-4-8") is True
    assert models.supports_effort("claude-opus-4-8") is True
    # Haiku 4.5: neither (effort 400s; not an adaptive-thinking model)
    assert models.is_adaptive_thinking_model("claude-haiku-4-5") is False
    assert models.supports_effort("claude-haiku-4-5") is False
    # Sonnet 4.6: both
    assert models.supports_effort("claude-sonnet-4-6") is True
