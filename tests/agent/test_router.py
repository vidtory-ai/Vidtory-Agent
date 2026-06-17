import pytest

from nanobot.agent.router import Intent, IntentRouter
from nanobot.providers.base import LLMResponse

class MockProvider:
    def __init__(self, mock_content="general"):
        self.mock_content = mock_content
        self.generation = type('obj', (object,), {'max_tokens': 100, 'temperature': 0.0, 'reasoning_effort': None})()

    async def chat_with_retry(self, **kwargs):
        return LLMResponse(content=self.mock_content, finish_reason="stop")


@pytest.mark.asyncio
async def test_intent_router_fashion():
    provider = MockProvider(mock_content="fashion")
    router = IntentRouter(provider, model="mock-model")
    intent = await router.classify("I want a new fashion design.")
    assert intent == Intent.FASHION


@pytest.mark.asyncio
async def test_intent_router_advertisement():
    provider = MockProvider(mock_content="advertisement")
    router = IntentRouter(provider, model="mock-model")
    intent = await router.classify("Make a marketing banner for me.")
    assert intent == Intent.ADVERTISEMENT


@pytest.mark.asyncio
async def test_intent_router_general():
    provider = MockProvider(mock_content="general")
    router = IntentRouter(provider, model="mock-model")
    intent = await router.classify("What time is it?")
    assert intent == Intent.GENERAL


@pytest.mark.asyncio
async def test_intent_router_empty_input():
    provider = MockProvider(mock_content="general")
    router = IntentRouter(provider, model="mock-model")
    intent = await router.classify("")
    assert intent == Intent.GENERAL

