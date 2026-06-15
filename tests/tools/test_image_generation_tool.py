from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nanobot.agent.tools.image_generation import ImageGenerationTool
from nanobot.config.loader import set_config_path
from nanobot.config.schema import ImageGenerationToolConfig, ProviderConfig
from nanobot.providers.image_generation import GeneratedImageResponse

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02"
    b"\x00\x00\x00\x0bIDATx\xdacd\xfc\xff\x1f\x00\x03\x03"
    b"\x02\x00\xef\xbf\xa7\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)
PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


class FakeImageClient:
    instances: list["FakeImageClient"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.calls: list[dict[str, Any]] = []
        self.instances.append(self)

    async def generate(self, **kwargs: Any) -> GeneratedImageResponse:
        self.calls.append(kwargs)
        return GeneratedImageResponse(images=[PNG_DATA_URL], content="", raw={})


@pytest.mark.asyncio
async def test_generate_image_tool_stores_artifact_and_source_images(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_config_path(tmp_path / "config.json")
    FakeImageClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "openrouter" else None,
    )
    ref = tmp_path / "ref.png"
    ref.write_bytes(PNG_BYTES)
    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(
            enabled=True,
            provider="openrouter",
            model="openai/gpt-5.4-image-2",
            max_images_per_turn=2,
        ),
        provider_configs={"openrouter": ProviderConfig(api_key="sk-or-test")},
    )

    result = await tool.execute(
        prompt="make this blue",
        reference_images=["ref.png"],
        aspect_ratio="16:9",
        image_size="2K",
        count=2,
    )

    payload = json.loads(result)
    artifacts = payload["artifacts"]
    assert len(artifacts) == 2
    assert Path(artifacts[0]["path"]).is_file()
    assert artifacts[0]["source_images"] == [str(ref.resolve())]
    assert artifacts[0]["model"] == "openai/gpt-5.4-image-2"

    fake = FakeImageClient.instances[0]
    assert fake.kwargs["api_key"] == "sk-or-test"
    assert len(fake.calls) == 2
    assert fake.calls[0]["aspect_ratio"] == "16:9"
    assert fake.calls[0]["image_size"] == "2K"


@pytest.mark.asyncio
async def test_generate_image_tool_reports_missing_key(tmp_path: Path) -> None:
    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(enabled=True),
        provider_configs={"vidtory": ProviderConfig()},
    )

    result = await tool.execute(prompt="draw")

    assert result.startswith("Error: Vidtory API key is not configured")


@pytest.mark.asyncio
async def test_generate_image_tool_selects_aihubmix_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_config_path(tmp_path / "config.json")
    FakeImageClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "aihubmix" else None,
    )
    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(
            enabled=True,
            provider="aihubmix",
            model="gpt-image-2-free",
        ),
        provider_configs={
            "openrouter": ProviderConfig(api_key="sk-or-test"),
            "aihubmix": ProviderConfig(api_key="sk-ahm-test", extra_body={"quality": "low"}),
        },
    )

    result = await tool.execute(prompt="draw a poster", aspect_ratio="3:4")

    payload = json.loads(result)
    assert len(payload["artifacts"]) == 1
    fake = FakeImageClient.instances[0]
    assert fake.kwargs["api_key"] == "sk-ahm-test"
    assert fake.kwargs["extra_body"] == {"quality": "low"}
    assert fake.calls[0]["model"] == "gpt-image-2-free"
    assert fake.calls[0]["aspect_ratio"] == "3:4"


@pytest.mark.asyncio
async def test_generate_image_tool_reports_missing_aihubmix_key(tmp_path: Path) -> None:
    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(enabled=True, provider="aihubmix"),
        provider_configs={"aihubmix": ProviderConfig()},
    )

    result = await tool.execute(prompt="draw")

    assert result.startswith("Error: AIHubMix API key is not configured")


@pytest.mark.asyncio
async def test_generate_image_tool_allows_ollama_without_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_config_path(tmp_path / "config.json")
    FakeImageClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "ollama" else None,
    )
    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(
            enabled=True,
            provider="ollama",
            model="x/z-image-turbo",
        ),
        provider_configs={"ollama": ProviderConfig(api_base="http://localhost:11434/v1")},
    )

    result = await tool.execute(prompt="draw a cat")

    payload = json.loads(result)
    assert len(payload["artifacts"]) == 1

    fake = FakeImageClient.instances[0]
    assert fake.kwargs["api_key"] is None
    assert fake.kwargs["api_base"] == "http://localhost:11434/v1"
    assert fake.calls[0]["aspect_ratio"] == "1:1"
    assert fake.calls[0]["image_size"] == "1K"


@pytest.mark.asyncio
async def test_generate_image_tool_reports_missing_zhipu_key(tmp_path: Path) -> None:
    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(
            enabled=True,
            provider="zhipu",
            model="glm-image",
        ),
        provider_configs={"zhipu": ProviderConfig(api_base="https://open.bigmodel.cn/api/paas/v4")},
    )

    result = await tool.execute(prompt="draw a cat")

    assert result.startswith("Error: Zhipu API key is not configured")


@pytest.mark.asyncio
async def test_generate_image_tool_rejects_reference_outside_workspace(tmp_path: Path) -> None:
    set_config_path(tmp_path / "config.json")
    outside = tmp_path.parent / "outside.png"
    outside.write_bytes(PNG_BYTES)
    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(enabled=True),
        provider_config=ProviderConfig(api_key="sk-or-test"),
    )

    result = await tool.execute(prompt="edit", reference_images=[str(outside)])

    assert "reference_images must be inside the workspace" in result


def test_detect_language() -> None:
    from nanobot.agent.tools.image_generation import detect_language
    assert detect_language("Một con vịt vàng dễ thương") == "vi"
    assert detect_language("Một con vit vang de thuong") == "vi"
    assert detect_language("A cute yellow duck on the grass") == "en"
    assert detect_language("画像内に表示される文字やテキスト") == "ja"
    assert detect_language("이미지에 표시되는 모든 텍스트나 글자") == "ko"


def test_get_target_text_language() -> None:
    from nanobot.agent.tools.image_generation import get_target_text_language
    assert get_target_text_language("Một con vịt vàng ghi chữ tiếng Anh") == "en"
    assert get_target_text_language("A cute duck write in Vietnamese") == "vi"
    assert get_target_text_language("Một con vịt vàng", customer_lang="en") == "vi"


def test_extract_quoted_texts() -> None:
    from nanobot.agent.tools.image_generation import extract_quoted_texts
    assert extract_quoted_texts('Vẽ một con vịt có chữ "Hello"') == ["Hello"]
    assert extract_quoted_texts("Vẽ một con vịt có chữ 'Cà phê muối'") == ["Cà phê muối"]
    assert extract_quoted_texts("Vẽ một con vịt có chữ “Thơm ngon”") == ["Thơm ngon"]


def test_apply_customer_context_language_injection() -> None:
    tool = ImageGenerationTool(
        workspace=Path("."),
        config=ImageGenerationToolConfig(enabled=True),
        provider_config=ProviderConfig(api_key="sk-or-test"),
    )
    # Simple Vietnamese prompt
    enriched, _, _ = tool._apply_customer_context("Vẽ con vịt")
    assert "Mọi chữ xuất hiện trong ảnh phải bằng tiếng Việt" in enriched
    assert "All text" not in enriched
    assert "DESIGN LAYOUT STANDARD" not in enriched

    # Simple Japanese prompt
    enriched_ja, _, _ = tool._apply_customer_context("アヒルの絵を描く")
    assert "画像内のすべての文字やテキストは日本語で記述してください" in enriched_ja

    # Vietnamese prompt with quotes
    enriched_quotes, _, _ = tool._apply_customer_context('Vẽ con vịt có chữ "Hello"')
    assert "Hiển thị chính xác nguyên văn: “Hello”" in enriched_quotes
    assert "Render the exact text" not in enriched_quotes


def test_is_revision_prompt() -> None:
    from nanobot.agent.tools.image_generation import _is_revision_prompt
    assert _is_revision_prompt("sửa lại ảnh vừa tạo") is True
    assert _is_revision_prompt("từ ảnh trên hãy chèn thêm chữ") is True
    assert _is_revision_prompt("tạo ảnh mới hoàn toàn") is False


def test_prompt_requests_no_logo() -> None:
    from nanobot.agent.tools.image_generation import _prompt_requests_no_logo
    assert _prompt_requests_no_logo("tạo ảnh không logo") is True
    assert _prompt_requests_no_logo("không cần logo nhé") is True
    assert _prompt_requests_no_logo("tạo ảnh có logo") is False


@pytest.mark.asyncio
async def test_find_last_generated_image_from_metadata(tmp_path: Path) -> None:
    from nanobot.agent.tools.context import RequestContext
    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(enabled=True),
    )
    # Set context with media in metadata
    ctx = RequestContext(
        channel="telegram",
        chat_id="123",
        message_id="msg_1",
        session_key="telegram:123",
        metadata={"media": ["https://example.com/some/image.png"]}
    )
    tool.set_context(ctx)
    last_img = tool._find_last_generated_image()
    assert last_img == "https://example.com/some/image.png"


@pytest.mark.asyncio
async def test_find_last_generated_image_from_session_history(tmp_path: Path) -> None:
    from nanobot.agent.tools.context import RequestContext
    from nanobot.session.manager import Session
    
    # Create fake session with tool response containing generated image
    session = Session(key="telegram:123")
    tool_resp_content = json.dumps({
        "artifacts": [
            {"path": "generated/img1.png", "remote_url": "http://example.com/img1.png"}
        ]
    })
    session.add_message("tool", tool_resp_content, name="generate_image")
    
    # Mock sessions manager
    class FakeSessions:
        def get_or_create(self, key: str):
            return session
            
    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(enabled=True),
        sessions=FakeSessions()
    )
    
    ctx = RequestContext(
        channel="telegram",
        chat_id="123",
        message_id="msg_2",
        session_key="telegram:123",
        metadata={}
    )
    tool.set_context(ctx)
    
    last_img = tool._find_last_generated_image()
    assert last_img == "generated/img1.png"


def test_apply_customer_context_logo_blending_and_preservation(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = ImageGenerationTool(
        workspace=Path("."),
        config=ImageGenerationToolConfig(enabled=True, provider="vidtory"),
    )
    
    # Mock telegram_customer_profile to return a profile
    fake_profile = {
        "telegramUserId": "user123",
        "preferences": {"communicationLanguage": "vi"},
        "brand": {
            "businessName": "Vidtory",
            "logoUrl": "http://example.com/logo.png"
        }
    }
    from nanobot.utils.context_vars import telegram_customer_profile
    token = telegram_customer_profile.set(fake_profile)
    
    # Mock DB get_logo_url
    class FakeDB:
        def get_logo_url(self, uid):
            return "http://example.com/logo.png"
    
    monkeypatch.setattr("nanobot.db.customer_db.get_db", FakeDB)
    
    try:
        # Test 1: Brand logo blending instructions are injected regardless of provider
        enriched, _, logo_url = tool._apply_customer_context("Vẽ ảnh", is_vidtory_provider=False)
        assert logo_url == "http://example.com/logo.png"
        assert "Logo thương hiệu là ảnh tham chiếu cuối cùng" in enriched
        assert "Bố cục sạch, thoáng, chuyên nghiệp" in enriched
        assert "IMPORTANT BRAND LOGO INSTRUCTION" not in enriched
        
        # Test 2: Skip logo injection when prompt explicitly requests no logo
        enriched_no_logo, _, logo_url_no_logo = tool._apply_customer_context("Vẽ ảnh không logo", is_vidtory_provider=False)
        assert logo_url_no_logo is None
        assert "Logo thương hiệu là ảnh tham chiếu cuối cùng" not in enriched_no_logo
    finally:
        telegram_customer_profile.reset(token)


@pytest.mark.asyncio
async def test_execute_with_multiple_reference_images(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_config_path(tmp_path / "config.json")
    FakeImageClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "openrouter" else None,
    )
    ref1 = tmp_path / "ref1.png"
    ref1.write_bytes(PNG_BYTES)
    ref2 = tmp_path / "ref2.png"
    ref2.write_bytes(PNG_BYTES)
    
    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(
            enabled=True,
            provider="openrouter",
            model="openai/gpt-5.4-image-2",
        ),
        provider_configs={"openrouter": ProviderConfig(api_key="sk-or-test")},
    )

    await tool.execute(
        prompt="Combine these two",
        reference_images=["ref1.png", "ref2.png"],
    )

    fake = FakeImageClient.instances[0]
    assert len(fake.calls) == 1
    call_prompt = fake.calls[0]["prompt"]
    assert "Combine these two" in call_prompt
    assert "Use every content reference image" in call_prompt


@pytest.mark.asyncio
async def test_execute_auto_injects_last_generated_image_on_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.agent.tools.context import RequestContext
    from nanobot.session.manager import Session
    
    set_config_path(tmp_path / "config.json")
    FakeImageClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "openrouter" else None,
    )
    
    ref = tmp_path / "last_art.png"
    ref.write_bytes(PNG_BYTES)
    
    session = Session(key="telegram:123")
    session.add_message("assistant", "Here is your image", media=[str(ref.resolve())])
    
    class FakeSessions:
        def get_or_create(self, key: str):
            return session
            
    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(
            enabled=True,
            provider="openrouter",
            model="openai/gpt-5.4-image-2",
        ),
        provider_configs={"openrouter": ProviderConfig(api_key="sk-or-test")},
        sessions=FakeSessions()
    )
    
    ctx = RequestContext(
        channel="telegram",
        chat_id="123",
        message_id="msg_3",
        session_key="telegram:123",
        metadata={}
    )
    tool.set_context(ctx)

    await tool.execute(
        prompt="Sửa lại ảnh trên để nó sáng hơn",
        reference_images=None,
    )

    fake = FakeImageClient.instances[0]
    assert len(fake.calls) == 1
    assert fake.calls[0]["reference_images"] == [str(ref.resolve())]


@pytest.mark.asyncio
async def test_execute_revision_uses_previous_user_image_from_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.agent.tools.context import RequestContext
    from nanobot.session.manager import Session

    set_config_path(tmp_path / "config.json")
    FakeImageClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "openrouter" else None,
    )

    ref = tmp_path / "previous-upload.png"
    ref.write_bytes(PNG_BYTES)
    session = Session(key="telegram:123")
    session.add_message("user", "Ảnh nguồn", media=[str(ref.resolve())])
    session.add_message("assistant", "Mình đã nhận ảnh.")

    class FakeSessions:
        def get_or_create(self, key: str):
            return session

    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(
            enabled=True,
            provider="openrouter",
            model="openai/gpt-5.4-image-2",
        ),
        provider_configs={"openrouter": ProviderConfig(api_key="sk-or-test")},
        sessions=FakeSessions(),
    )
    tool.set_context(
        RequestContext(
            channel="telegram",
            chat_id="123",
            message_id="msg_history",
            session_key="telegram:123",
            metadata={},
        )
    )

    await tool.execute(prompt="Từ ảnh trên hãy thêm tiêu đề", reference_images=None)

    assert FakeImageClient.instances[0].calls[0]["reference_images"] == [
        str(ref.resolve())
    ]


@pytest.mark.asyncio
async def test_execute_revision_merges_all_request_media_ahead_of_llm_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.agent.tools.context import RequestContext

    set_config_path(tmp_path / "config.json")
    FakeImageClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "openrouter" else None,
    )

    replied = tmp_path / "replied.png"
    replied.write_bytes(PNG_BYTES)
    attached = tmp_path / "attached.png"
    attached.write_bytes(PNG_BYTES)
    llm_selected = tmp_path / "llm-selected.png"
    llm_selected.write_bytes(PNG_BYTES)

    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(
            enabled=True,
            provider="openrouter",
            model="openai/gpt-5.4-image-2",
        ),
        provider_configs={"openrouter": ProviderConfig(api_key="sk-or-test")},
    )
    tool.set_context(
        RequestContext(
            channel="telegram",
            chat_id="123",
            message_id="msg_4",
            session_key="telegram:123",
            metadata={
                "reply_media": [str(replied)],
                "current_media": [str(attached)],
                "media": [str(replied), str(attached)],
            },
        )
    )

    await tool.execute(
        prompt="Chỉnh sửa ảnh này và thêm tiêu đề mới",
        reference_images=[str(llm_selected), str(replied)],
    )

    refs = FakeImageClient.instances[0].calls[0]["reference_images"]
    assert refs == [
        str(replied.resolve()),
        str(attached.resolve()),
        str(llm_selected.resolve()),
    ]


@pytest.mark.asyncio
async def test_auto_delivery_includes_lazy_feedback_buttons(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.agent.tools.context import RequestContext

    set_config_path(tmp_path / "config.json")
    FakeImageClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "openrouter" else None,
    )
    sent = []

    async def capture(message):
        sent.append(message)

    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(
            enabled=True,
            provider="openrouter",
            model="openai/gpt-5.4-image-2",
        ),
        provider_configs={"openrouter": ProviderConfig(api_key="sk-or-test")},
        send_callback=capture,
    )
    tool.set_context(
        RequestContext(
            channel="telegram",
            chat_id="123",
            message_id="msg_feedback",
            session_key="telegram:123",
            metadata={},
        )
    )

    await tool.execute(prompt="Tạo ảnh sản phẩm")

    assert sent[-1].buttons == [["Đúng ý", "Cần chỉnh"], ["Tạo biến thể"]]


