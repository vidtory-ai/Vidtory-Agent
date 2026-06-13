"""Tests for lazy provider exports from nanobot.providers."""

from __future__ import annotations

import importlib
import sys

import pytest


def test_importing_providers_package_is_lazy(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "nanobot.providers", raising=False)
    monkeypatch.delitem(sys.modules, "nanobot.providers.anthropic_provider", raising=False)
    monkeypatch.delitem(sys.modules, "nanobot.providers.openai_compat_provider", raising=False)

    providers = importlib.import_module("nanobot.providers")

    assert "nanobot.providers.anthropic_provider" not in sys.modules
    assert "nanobot.providers.openai_compat_provider" not in sys.modules
    assert providers.__all__ == [
        "LLMProvider",
        "LLMResponse",
        "AnthropicProvider",
        "OpenAICompatProvider",
    ]


def test_explicit_provider_import_still_works(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "nanobot.providers", raising=False)
    monkeypatch.delitem(sys.modules, "nanobot.providers.anthropic_provider", raising=False)

    namespace: dict[str, object] = {}
    exec("from nanobot.providers import AnthropicProvider", namespace)

    assert namespace["AnthropicProvider"].__name__ == "AnthropicProvider"
    assert "nanobot.providers.anthropic_provider" in sys.modules


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("azure-openai", "deployment-name"),
        ("bedrock", "anthropic.claude-sonnet"),
        ("github-copilot", "github-copilot/gpt-4.1"),
        ("openai-codex", "openai-codex/gpt-5"),
    ],
)
def test_removed_provider_backends_fail_with_actionable_error(provider, model) -> None:
    from nanobot.config.schema import Config
    from nanobot.providers.factory import make_provider

    config = Config.model_validate({
        "agents": {"defaults": {"provider": provider, "model": model}},
    })

    normalized = provider.replace("-", "_")
    with pytest.raises(ValueError, match=rf"{normalized}.*not available"):
        make_provider(config)
