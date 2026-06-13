from __future__ import annotations

from nanobot.bus.queue import MessageBus
from nanobot.cli.commands import _publish_runtime_model_update


def test_runtime_model_update_publisher_does_not_need_websocket_import() -> None:
    bus = MessageBus()

    _publish_runtime_model_update(bus, "openai/gpt-4.1", "fast")

    event = bus.outbound.get_nowait()
    assert event.channel == "websocket"
    assert event.chat_id == "*"
    assert event.metadata == {
        "_runtime_model_updated": True,
        "model": "openai/gpt-4.1",
        "model_preset": "fast",
    }
