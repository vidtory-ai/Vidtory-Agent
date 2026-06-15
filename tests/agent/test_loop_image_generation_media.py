from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.config.loader import set_config_path
from nanobot.config.schema import ImageGenerationToolConfig, ProviderConfig, ToolsConfig
from nanobot.providers.base import LLMResponse, ToolCallRequest
from nanobot.providers.image_generation import GeneratedImageResponse

PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


class FakeImageClient:
    generate_calls = 0

    def __init__(self, **kwargs: Any) -> None:
        pass

    async def generate(self, **kwargs: Any) -> GeneratedImageResponse:
        type(self).generate_calls += 1
        return GeneratedImageResponse(images=[PNG_DATA_URL], content="", raw={})


@pytest.mark.asyncio
async def test_outbound_delivers_generated_media_once_when_llm_does_not_send_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loop falls back to one final attachment when the LLM omits message()."""
    set_config_path(tmp_path / "config.json")
    FakeImageClient.generate_calls = 0
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "openrouter" else None,
    )
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation.max_tokens = 4096
    provider.chat_with_retry = AsyncMock(
        side_effect=[
            LLMResponse(
                content="",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCallRequest(
                        id="call_img",
                        name="generate_image",
                        arguments={"prompt": "draw a tiny icon"},
                    )
                ],
            ),
            LLMResponse(content="Done", finish_reason="stop"),
        ]
    )
    provider.chat_stream_with_retry = AsyncMock()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
        tools_config=ToolsConfig(
            image_generation=ImageGenerationToolConfig(enabled=True, provider="openrouter"),
        ),
        image_generation_provider_config=ProviderConfig(api_key="sk-or-test"),
    )
    loop.consolidator.maybe_consolidate_by_tokens = AsyncMock(return_value=False)  # type: ignore[method-assign]

    result = await loop._process_message(
        InboundMessage(
            channel="websocket",
            sender_id="user",
            chat_id="chat-image",
            content="edit this image",
            metadata={"original_user_content": "edit this image"},
        )
    )

    assert result is not None
    # When generate_image tool includes a delivery.message, the loop uses it as
    # the outbound content (overriding the LLM's final "Done" response).
    assert "Đã tạo ảnh" in result.content
    assert len(result.media) == 1
    assert FakeImageClient.generate_calls == 1
    # "Tạo biến thể" button must NOT appear — only the feedback pair.
    assert result.buttons == [["Đúng ý", "Cần chỉnh"]]


@pytest.mark.asyncio
async def test_loop_preserves_original_request_for_image_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_config_path(tmp_path / "config.json")
    FakeImageClient.generate_calls = 0
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "openrouter" else None,
    )
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation.max_tokens = 4096
    provider.chat_with_retry = AsyncMock(
        side_effect=[
            LLMResponse(
                content="",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCallRequest(
                        id="call_img",
                        name="generate_image",
                        arguments={
                            "prompt": (
                                "Poster tuyển dụng Backend Engineer với mã nguồn "
                                "và sơ đồ hệ thống"
                            )
                        },
                    )
                ],
            ),
            LLMResponse(
                content=(
                    "BE có thể là Backend Engineer hoặc thương hiệu be. "
                    "Bạn muốn hướng nào?"
                ),
                finish_reason="stop",
            ),
        ]
    )
    provider.chat_stream_with_retry = AsyncMock()
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
        tools_config=ToolsConfig(
            image_generation=ImageGenerationToolConfig(enabled=True, provider="openrouter"),
        ),
        image_generation_provider_config=ProviderConfig(api_key="sk-or-test"),
    )
    loop.consolidator.maybe_consolidate_by_tokens = AsyncMock(return_value=False)  # type: ignore[method-assign]

    result = await loop._process_message(
        InboundMessage(
            channel="websocket",
            sender_id="user",
            chat_id="chat-image",
            content="tạo ảnh poster quảng cáo BE cho tôi",
        )
    )

    assert result is not None
    assert "Bạn muốn hướng nào?" in result.content
    assert FakeImageClient.generate_calls == 0


def test_assemble_outbound_does_not_reattach_historical_generated_media(
    tmp_path: Path,
) -> None:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation.max_tokens = 4096
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
        tools_config=ToolsConfig(),
    )
    old_image = tmp_path / "old-result.png"
    old_image.write_bytes(b"old")
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "create an image"},
        {
            "role": "tool",
            "name": "generate_image",
            "content": json.dumps({"artifacts": [{"path": str(old_image)}]}),
        },
        {"role": "assistant", "content": "image completed"},
        {"role": "user", "content": "hello again"},
        {"role": "assistant", "content": "hello"},
    ]

    outbound = loop._assemble_outbound(
        InboundMessage(
            channel="telegram",
            sender_id="user",
            chat_id="123",
            content="hello again",
        ),
        "hello",
        messages,
        "stop",
        False,
        None,
        turn_message_start=4,
    )

    assert outbound is not None
    assert outbound.media == []


def test_assemble_outbound_uses_structured_image_delivery_message(
    tmp_path: Path,
) -> None:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation.max_tokens = 4096
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
        tools_config=ToolsConfig(),
    )
    image = tmp_path / "result.png"
    image.write_bytes(b"image")
    delivery_message = (
        "Đã ghép 2 linh vật thành ảnh quảng bá rồi nhé ✅\n\n"
        "Design note:\n"
        "• Giữ cá tính riêng của từng linh vật.\n\n"
        "Nếu muốn, mình làm tiếp 3 biến thể:\n"
        "1️⃣ Tối giản cao cấp\n"
        "2️⃣ Lifestyle chân thực\n"
        "3️⃣ Năng động nổi bật"
    )
    messages = [
        {"role": "user", "content": "ghép hai ảnh"},
        {
            "role": "tool",
            "name": "generate_image",
            "content": json.dumps(
                {
                    "artifacts": [{"path": str(image)}],
                    "delivery": {"message": delivery_message},
                },
                ensure_ascii=False,
            ),
        },
        {"role": "assistant", "content": "Đây là bản ghép theo hướng cinematic."},
    ]

    outbound = loop._assemble_outbound(
        InboundMessage(
            channel="telegram",
            sender_id="user",
            chat_id="123",
            content="ghép hai ảnh",
        ),
        "Đây là bản ghép theo hướng cinematic.",
        messages,
        "stop",
        False,
        None,
    )

    assert outbound is not None
    assert outbound.content == delivery_message
    assert outbound.media == [str(image)]
