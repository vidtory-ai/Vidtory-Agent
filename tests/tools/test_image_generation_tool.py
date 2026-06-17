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
async def test_generate_image_tool_blocks_telegram_vidtory_fallback_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.agent.tools.context import RequestContext

    FakeImageClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "vidtory" else None,
    )
    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(enabled=True, provider="vidtory"),
        provider_configs={"vidtory": ProviderConfig(api_key="system-vidtory-key")},
    )
    tool.set_context(
        RequestContext(
            channel="telegram",
            chat_id="123",
            metadata={"user_api_key": ""},
        )
    )

    result = await tool.execute(prompt="draw")

    assert result.startswith("Error: Vidtory API key is not configured")
    assert FakeImageClient.instances == []


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


def test_extract_replacement_texts_preserves_unquoted_vietnamese_copy() -> None:
    from nanobot.agent.tools.image_generation import extract_replacement_texts

    assert extract_replacement_texts(
        "Sửa chữ Nguyễn Minh Toàn thành Luôn Luôn A+"
    ) == ["Luôn Luôn A+"]


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


def test_apply_customer_context_locks_replacement_text_from_original_request() -> None:
    from nanobot.agent.tools.context import RequestContext

    tool = ImageGenerationTool(
        workspace=Path("."),
        config=ImageGenerationToolConfig(enabled=True),
        provider_config=ProviderConfig(api_key="sk-or-test"),
    )
    tool.set_context(
        RequestContext(
            channel="telegram",
            chat_id="123",
            metadata={
                "original_user_content": (
                    "Sửa chữ Nguyễn Minh Toàn thành Luôn Luôn A+"
                )
            },
        )
    )

    enriched, _, _ = tool._apply_customer_context(
        "Replace the existing name with the requested new headline"
    )

    assert "Mọi chữ xuất hiện trong ảnh phải bằng tiếng Việt" in enriched
    assert "Hiển thị chính xác nguyên văn: “Luôn Luôn A+”" in enriched


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


def test_ambiguous_image_request_allows_explicitly_resolved_meaning() -> None:
    from nanobot.agent.tools.image_generation import (
        _ambiguous_image_request_clarification,
    )

    assert (
        _ambiguous_image_request_clarification(
            "Tạo poster tuyển dụng BE - Backend Engineer"
        )
        is None
    )
    assert (
        _ambiguous_image_request_clarification(
            "Tạo poster quảng cáo cho thương hiệu be"
        )
        is None
    )


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
async def test_execute_numbered_followup_uses_image_from_immediately_previous_turn(
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

    latest_ref = tmp_path / "latest-poster.png"
    latest_ref.write_bytes(PNG_BYTES)
    session = Session(key="telegram:123")
    session.add_message("user", "Tạo poster mùa hè xanh")
    session.add_message(
        "tool",
        json.dumps({"artifacts": [{"path": str(latest_ref.resolve())}]}),
        name="generate_image",
    )
    session.add_message(
        "assistant",
        "Muốn mình làm tiếp:\n1️⃣ Sáng hơn\n2️⃣ Ấm hơn\n3️⃣ Bản 16:9",
    )
    session.add_message("user", "1")

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
            message_id="msg_choice",
            session_key="telegram:123",
            metadata={"original_user_content": "1"},
        )
    )

    await tool.execute(
        prompt="Tăng ánh sáng tổng thể, giữ bố cục sạch và chuyên nghiệp",
        reference_images=None,
    )

    assert FakeImageClient.instances[0].calls[0]["reference_images"] == [
        str(latest_ref.resolve())
    ]


@pytest.mark.asyncio
async def test_numbered_followup_does_not_reuse_image_from_older_turn(
    tmp_path: Path,
) -> None:
    from nanobot.agent.tools.context import RequestContext
    from nanobot.session.manager import Session

    old_ref = tmp_path / "old-poster.png"
    old_ref.write_bytes(PNG_BYTES)
    session = Session(key="telegram:123")
    session.add_message("user", "Tạo poster cũ")
    session.add_message(
        "tool",
        json.dumps({"artifacts": [{"path": str(old_ref.resolve())}]}),
        name="generate_image",
    )
    session.add_message("assistant", "Đã tạo xong")
    session.add_message("user", "Tạo ảnh sự kiện mới")
    session.add_message(
        "assistant",
        "Bạn chọn hướng nào?\n1️⃣ Lifestyle\n2️⃣ Tối giản\n3️⃣ Năng động",
    )
    session.add_message("user", "1")

    class FakeSessions:
        def get_or_create(self, key: str):
            return session

    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(enabled=True),
        sessions=FakeSessions(),
    )
    tool.set_context(
        RequestContext(
            channel="telegram",
            chat_id="123",
            session_key="telegram:123",
            metadata={"original_user_content": "1"},
        )
    )

    assert tool._merge_revision_references(
        "Nhóm sinh viên tình nguyện ngoài trời",
        None,
    ) is None


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
async def test_execute_revision_uses_latest_session_image_over_stale_llm_reference(
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

    old_ref = tmp_path / "old-be-poster.png"
    old_ref.write_bytes(PNG_BYTES)
    latest_ref = tmp_path / "latest-be-poster.png"
    latest_ref.write_bytes(PNG_BYTES)

    session = Session(key="telegram:123")
    session.add_message(
        "tool",
        json.dumps({"artifacts": [{"path": str(old_ref.resolve())}]}),
        name="generate_image",
    )
    session.add_message(
        "tool",
        json.dumps({"artifacts": [{"path": str(latest_ref.resolve())}]}),
        name="generate_image",
    )

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
            message_id="msg_latest",
            session_key="telegram:123",
            metadata={},
        )
    )

    await tool.execute(
        prompt="Từ ảnh trên sửa chữ thành tuyển dụng FE",
        reference_images=[str(old_ref.resolve())],
    )

    assert FakeImageClient.instances[0].calls[0]["reference_images"] == [
        str(latest_ref.resolve())
    ]


@pytest.mark.asyncio
async def test_execute_blocks_ambiguous_original_request_before_generation(
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
            message_id="msg_ambiguous",
            session_key="telegram:123",
            metadata={"original_user_content": "tạo ảnh poster quảng cáo BE cho tôi"},
        )
    )

    result = await tool.execute(
        prompt=(
            "Poster tuyển dụng Backend Engineer với mã nguồn, sơ đồ hệ thống, "
            "phong cách công nghệ hiện đại"
        )
    )

    assert result.startswith("Clarification required:")
    assert "Backend Engineer" in result
    assert "thương hiệu be" in result
    assert FakeImageClient.instances == []


def test_apply_customer_context_uses_profile_logo_when_indexed_logo_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.utils.context_vars import telegram_customer_profile

    tool = ImageGenerationTool(
        workspace=Path("."),
        config=ImageGenerationToolConfig(enabled=True, provider="vidtory"),
    )
    profile = {
        "telegramUserId": "user123",
        "preferences": {"communicationLanguage": "vi"},
        "brand": {"logoUrl": "https://b2b.vidtory.net/assets/profile-logo.png"},
    }

    class FakeDB:
        def get_logo_url(self, uid):
            return None

    monkeypatch.setattr("nanobot.db.customer_db.get_db", FakeDB)
    token = telegram_customer_profile.set(profile)
    try:
        _, _, logo_url = tool._apply_customer_context("Tạo poster tuyển dụng")
    finally:
        telegram_customer_profile.reset(token)

    assert logo_url == "https://b2b.vidtory.net/assets/profile-logo.png"


@pytest.mark.asyncio
async def test_auto_delivery_leaves_followup_buttons_for_text_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.agent.tools.context import RequestContext
    from nanobot.agent.tools.message import MessageTool

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

    result = json.loads(await tool.execute(prompt="Tạo ảnh sản phẩm"))

    assert sent[-1].buttons == []
    assert "Do not send the artifact media again" in result["next_step"]

    message_tool = MessageTool(
        send_callback=capture,
        capability_profile="resident_designer",
    )
    message_tool.set_context(
        RequestContext(channel="telegram", chat_id="123", metadata={})
    )
    await message_tool.execute(
        content="Đã tạo xong.\n1️⃣ Sáng hơn\n2️⃣ Ấm hơn\n3️⃣ Bản 16:9",
        media=[result["artifacts"][0]["path"]],
    )

    assert sum(bool(message.media) for message in sent) == 1
    assert sent[-1].media == []
    assert sent[-1].buttons == [["1", "2", "3"]]


@pytest.mark.asyncio
async def test_generate_image_tool_sends_logo_reminder_after_third_logo_free_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.agent.tools.context import RequestContext
    from nanobot.bus.events import OutboundMessage
    from nanobot.db.customer_db import CustomerDatabase
    from nanobot.utils.context_vars import telegram_customer_profile
    from nanobot.utils.customer_profile import create_minimal_profile, load_profile, save_profile

    set_config_path(tmp_path / "config.json")
    FakeImageClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "openrouter" else None,
    )
    db = CustomerDatabase(tmp_path / "customers.db")
    monkeypatch.setattr("nanobot.db.customer_db._db_instance", db)

    profile = create_minimal_profile("12345", username="alice")
    profile["onboarding"]["status"] = "completed"
    save_profile("12345", profile)
    db.record_generation("12345", prompt="first")
    db.record_generation("12345", prompt="second")

    sent: list[OutboundMessage] = []

    async def capture(message: OutboundMessage) -> None:
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
            session_key="telegram:123",
            metadata={"user_api_key": "user-vidtory-key"},
        )
    )
    token = telegram_customer_profile.set(profile)
    try:
        await tool.execute(prompt="Draw a product poster")
    finally:
        telegram_customer_profile.reset(token)
    reminders = [
        msg for msg in sent
        if msg.buttons == [["Có, tôi sẽ gửi logo", "Chưa, nhắc sau"]]
    ]
    assert len(reminders) == 1
    assert "logo" in reminders[0].content.lower()
    assert load_profile("12345")["preferences"]["logoReminderAwaitingUpload"] is True
    db.close()
 
 
@pytest.mark.asyncio
async def test_execute_blocks_general_vague_request_before_generation(
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
            message_id="msg_vague",
            session_key="telegram:123",
            metadata={"original_user_content": "tạo ảnh poster tuyển vị trí kế toán cho công ty"},
        )
    )
 
    from nanobot.utils.context_vars import telegram_customer_profile
    token = telegram_customer_profile.set(None)
    try:
        result = await tool.execute(
            prompt="Poster tuyển dụng kế toán chuyên nghiệp cho công ty"
        )
    finally:
        telegram_customer_profile.reset(token)
 
    assert "tuyển dụng" in result
    assert "Chuyên nghiệp tin cậy" in result
    assert "trả lời theo mẫu" in result.lower()
    assert FakeImageClient.instances == []


# ── Export-variant follow-up: aspect-ratio change must use last generated image ──


def test_is_export_variant_prompt_detects_aspect_ratio_keywords() -> None:
    """_is_export_variant_prompt() must fire on every natural phrase a customer
    might use when asking for a different-ratio version of the just-generated image.
    """
    from nanobot.agent.tools.image_generation import _is_export_variant_prompt

    positives = [
        "xuất bản 4:3",
        "xuất bản 9:16",
        "xuất bản 16:9",
        "xuất bản 1:1",
        "xuất tiếp bản 4:3",
        "xuất thêm bản 9:16",
        "cho tôi bản 4:3",
        "bản 4:3 đi",
        "ra bản 9:16",
        "tỉ lệ 4:3",
        "tỉ lệ 9:16",
        "tỷ lệ 4:3",
        "tỷ lệ 9:16",
        "4:3 nhé",
        "9:16 nha",
        "đổi sang 4:3",
        "đổi tỉ lệ 9:16",
    ]
    for phrase in positives:
        assert _is_export_variant_prompt(phrase), (
            f"Expected _is_export_variant_prompt({phrase!r}) == True"
        )


def test_is_export_variant_prompt_ignores_unrelated_phrases() -> None:
    """Phrases that mention revisions without aspect-ratio intent must NOT fire."""
    from nanobot.agent.tools.image_generation import _is_export_variant_prompt

    negatives = [
        "sửa màu sắc",
        "thêm chữ tiêu đề",
        "chỉnh độ sáng",
        "1",  # numbered choice — handled separately
        "2",
        "chọn 3",
        "tạo ảnh mới",
        "",
    ]
    for phrase in negatives:
        assert not _is_export_variant_prompt(phrase), (
            f"Expected _is_export_variant_prompt({phrase!r}) == False"
        )


@pytest.mark.asyncio
async def test_export_variant_followup_uses_last_generated_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When user asks for an aspect-ratio variant ('xuất bản 4:3'),
    the system MUST pass the last generated image as reference — not the
    original uploaded source images still present in context.metadata['media'].

    Regression: before the fix, request_media from the original upload was
    returned before the export-variant branch ran, causing the wrong image.
    """
    from nanobot.agent.tools.context import RequestContext
    from nanobot.session.manager import Session

    set_config_path(tmp_path / "config.json")
    FakeImageClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "openrouter" else None,
    )

    original_upload = tmp_path / "original-upload.png"
    original_upload.write_bytes(PNG_BYTES)
    last_generated = tmp_path / "last-generated-poster.png"
    last_generated.write_bytes(PNG_BYTES)

    session = Session(key="telegram:123")
    session.add_message("user", "Tạo poster tuyển dụng", media=[str(original_upload.resolve())])
    session.add_message(
        "tool",
        json.dumps({"artifacts": [{"path": str(last_generated.resolve())}]}),
        name="generate_image",
    )
    session.add_message(
        "assistant",
        "Đã tạo xong! Muốn mình làm tiếp:\n1️⃣ Sáng hơn\n2️⃣ Ấm hơn\n3️⃣ Xuất bản 4:3",
    )
    session.add_message("user", "xuất bản 4:3")

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
    # context.metadata still carries original_upload in "media" — this is the
    # exact bug condition: Telegram context keeps the original media group alive.
    tool.set_context(
        RequestContext(
            channel="telegram",
            chat_id="123",
            session_key="telegram:123",
            metadata={
                "original_user_content": "xuất bản 4:3",
                "media": [str(original_upload.resolve())],
            },
        )
    )

    await tool.execute(
        prompt="Xuất ảnh poster tuyển dụng theo tỷ lệ 4:3, giữ nguyên nội dung và phong cách",
        aspect_ratio="4:3",
        reference_images=None,
    )

    refs = FakeImageClient.instances[0].calls[0]["reference_images"]
    assert refs == [str(last_generated.resolve())], (
        f"Expected last-generated image as reference, got: {refs}"
    )


@pytest.mark.asyncio
async def test_export_variant_followup_uses_last_generated_image_9_16(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same regression for 9:16 — the most common vertical format for Stories."""
    from nanobot.agent.tools.context import RequestContext
    from nanobot.session.manager import Session

    set_config_path(tmp_path / "config.json")
    FakeImageClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "openrouter" else None,
    )

    original_upload = tmp_path / "brand-photo.png"
    original_upload.write_bytes(PNG_BYTES)
    last_generated = tmp_path / "generated-banner.png"
    last_generated.write_bytes(PNG_BYTES)

    session = Session(key="telegram:456")
    session.add_message("user", "Tạo banner", media=[str(original_upload.resolve())])
    session.add_message(
        "tool",
        json.dumps({"artifacts": [{"path": str(last_generated.resolve())}]}),
        name="generate_image",
    )
    session.add_message("assistant", "Xong rồi nhé! Bạn muốn gì tiếp theo?")
    session.add_message("user", "tỉ lệ 9:16 nhé")

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
            chat_id="456",
            session_key="telegram:456",
            metadata={
                "original_user_content": "tỉ lệ 9:16 nhé",
                "media": [str(original_upload.resolve())],
            },
        )
    )

    await tool.execute(
        prompt="Xuất bản ảnh này theo tỷ lệ 9:16 cho Stories",
        aspect_ratio="9:16",
        reference_images=None,
    )

    refs = FakeImageClient.instances[0].calls[0]["reference_images"]
    assert refs == [str(last_generated.resolve())], (
        f"Expected last-generated image, got: {refs}"
    )


def test_merge_revision_references_export_variant_ignores_context_media(
    tmp_path: Path,
) -> None:
    """Unit test: _merge_revision_references() with an export-variant request
    must skip request_media from context and resolve to the last generated image.
    """
    from nanobot.agent.tools.context import RequestContext
    from nanobot.session.manager import Session

    gen_img = tmp_path / "gen.png"
    gen_img.write_bytes(PNG_BYTES)
    source_img = tmp_path / "source.png"
    source_img.write_bytes(PNG_BYTES)

    session = Session(key="telegram:789")
    session.add_message("user", "Tạo ảnh", media=[str(source_img.resolve())])
    session.add_message(
        "tool",
        json.dumps({"artifacts": [{"path": str(gen_img.resolve())}]}),
        name="generate_image",
    )
    session.add_message("assistant", "Xong!")
    session.add_message("user", "xuất bản 4:3")

    class FakeSessions:
        def get_or_create(self, key: str):
            return session

    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(enabled=True),
        sessions=FakeSessions(),
    )
    tool.set_context(
        RequestContext(
            channel="telegram",
            chat_id="789",
            session_key="telegram:789",
            metadata={
                "original_user_content": "xuất bản 4:3",
                # context.media still holds the original uploaded photo
                "media": [str(source_img.resolve())],
            },
        )
    )

    result = tool._merge_revision_references(
        "Xuất ảnh theo tỷ lệ 4:3, giữ nguyên nội dung",
        None,
    )
    # Must resolve to last generated, not the source upload
    assert result == [str(gen_img.resolve())]
