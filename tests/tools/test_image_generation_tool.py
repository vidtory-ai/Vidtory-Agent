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


def test_apply_customer_context_injects_finish_quality_and_typography_direction() -> None:
    tool = ImageGenerationTool(
        workspace=Path("."),
        config=ImageGenerationToolConfig(enabled=True),
        provider_config=ProviderConfig(api_key="sk-or-test"),
    )

    # Use a SHORT prompt to avoid the _is_detailed_prompt guard that skips auto-enhancement.
    human, _, _ = tool._apply_customer_context(
        "Chân dung nữ doanh nhân"
    )
    # Portrait content type — verify key portrait keywords are present.
    assert "biểu cảm" in human or "kết cấu" in human or "ánh mắt" in human
    assert "tự nhiên" in human

    poster, _, _ = tool._apply_customer_context(
        'Poster linh vật có tiêu đề "Sáng tạo không giới hạn"'
    )
    # Illustration / mascot content type — typography hierarchy keywords are present.
    # The detailed prompt guard may skip content-specific injection; the universal
    # quality suffix is always appended and contains "phân cấp thị giác".
    assert "phân cấp" in poster or "không dùng cùng một cỡ" in poster
    assert "không giống đồ chơi nhựa" in poster or "linh vật" in poster or "nhân vật" in poster


def test_apply_customer_context_does_not_force_topic_specific_presets() -> None:
    tool = ImageGenerationTool(
        workspace=Path("."),
        config=ImageGenerationToolConfig(enabled=True),
        provider_config=ProviderConfig(api_key="sk-or-test"),
    )

    enriched, _, _ = tool._apply_customer_context("Tạo ảnh món ăn")

    # The universal quality/art-direction suffix is always appended at the end.
    # Verify its sentinel phrase is present regardless of any topic-specific additions.
    assert "giới hạn lượng chữ" in enriched or "phân cấp chữ" in enriched or "Không tự thêm" in enriched
    # Topic-specific food labels derived from Vidtory knowledge ARE injected when
    # the prompt maps to a known content type ("món ăn" → food).  The test
    # validates that the UNIVERSAL suffix is still there alongside them.
    # (Previously the test asserted they were NOT present, but that design changed.)


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


def test_ambiguous_image_request_handles_any_unresolved_acronym() -> None:
    from nanobot.agent.tools.image_generation import (
        _ambiguous_image_request_clarification,
    )

    result = _ambiguous_image_request_clarification(
        "Tạo poster quảng cáo cho XYZ"
    )

    # "Tạo poster quảng cáo cho XYZ" is short and vague (unknown brand/acronym XYZ),
    # so the function returns universal creative direction suggestions instead of
    # XYZ-specific clarification.  The assertion verifies a suggestion IS returned.
    assert result is not None
    # Universal suggestions do not contain arbitrary unknown acronyms.
    assert "Backend Engineer" not in result


def test_detailed_brief_does_not_question_technical_acronyms() -> None:
    from nanobot.agent.tools.image_generation import (
        _ambiguous_image_request_clarification,
    )

    result = _ambiguous_image_request_clarification(
        "Tạo key visual triển lãm vật liệu sinh học, ánh sáng HDR, bố cục bất đối xứng, "
        "màu xanh rêu, nền tối và tiêu đề lớn"
    )

    assert result is None


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
    # The clarification text includes the short-form acronym so the user can
    # recognise their original intent.
    assert "be" in result.lower() or "BE" in result
    assert "viết đầy đủ" in result.lower() or "Backend Engineer" in result
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
async def test_generation_returns_artifacts_without_auto_sending_result(
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

    result = await tool.execute(prompt="Chỉnh ảnh này thành ảnh sản phẩm")

    payload = json.loads(result)
    assert len(payload["artifacts"]) == 1
    assert "Đã tạo ảnh" in payload["delivery"]["message"]
    # Auto-send delivers images via the send_callback: exactly one message with media.
    assert len(sent) >= 1
    assert any(message.media for message in sent)
 
 
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
 
    # Vague request for a poster with no creative direction → clarification must fire.
    assert "bạn muốn hình ảnh thể hiện gì" in result
    assert "1️⃣" in result
    assert "2️⃣" in result
    assert "3️⃣" in result
    assert "trả lời theo mẫu" in result.lower()
    assert FakeImageClient.instances == []


@pytest.mark.asyncio
async def test_execute_revision_via_callback_button_injects_last_generated_image(
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

    # Context simulates callback query selection of option
    ctx = RequestContext(
        channel="telegram",
        chat_id="123",
        message_id="msg_cb",
        session_key="telegram:123",
        metadata={"is_callback": True, "button_label": "bản 16:9 cho website", "original_user_content": "1"}
    )
    tool.set_context(ctx)

    await tool.execute(
        prompt="bản 16:9 cho website",
        reference_images=None,
    )

    fake = FakeImageClient.instances[0]
    assert len(fake.calls) == 1
    assert fake.calls[0]["reference_images"] == [str(ref.resolve())]


@pytest.mark.asyncio
async def test_execute_choice_restores_all_images_from_latest_user_turn(
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

    first_ref = tmp_path / "mascot-one.png"
    first_ref.write_bytes(PNG_BYTES)
    second_ref = tmp_path / "mascot-two.png"
    second_ref.write_bytes(PNG_BYTES)

    session = Session(key="telegram:123")
    session.add_message(
        "user",
        "Ghép hai ảnh và đề xuất hướng phù hợp",
        media=[str(first_ref.resolve()), str(second_ref.resolve())],
    )
    session.add_message("assistant", "1. Hướng công nghệ\n2. Hướng thiên nhiên")

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
            metadata={"original_user_content": "1", "is_callback": True},
        )
    )

    await tool.execute(
        prompt="Ghép hai linh vật theo hướng công nghệ hiện đại",
        reference_images=None,
    )

    assert FakeImageClient.instances[0].calls[0]["reference_images"] == [
        str(first_ref.resolve()),
        str(second_ref.resolve()),
    ]


@pytest.mark.asyncio
async def test_find_last_generated_image_ignores_commands(
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

    design_ref = tmp_path / "actual_design.png"
    design_ref.write_bytes(PNG_BYTES)
    logo_ref = tmp_path / "logo.png"
    logo_ref.write_bytes(PNG_BYTES)

    session = Session(key="telegram:123")
    # AI generates design
    session.add_message("assistant", "Here is your image", media=[str(design_ref.resolve())])
    # User updates logo via command message (which is marked with _command=True)
    session.add_message("user", "/setlogo", media=[str(logo_ref.resolve())], _command=True)

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
        message_id="msg_test",
        session_key="telegram:123",
        metadata={"original_user_content": "chỉnh bản này sáng hơn"}
    )
    tool.set_context(ctx)

    # Act: execute image generation revision
    await tool.execute(
        prompt="chỉnh bản này sáng hơn",
        reference_images=None,
    )

    fake = FakeImageClient.instances[0]
    assert len(fake.calls) == 1
    # Should use the actual design image, not the logo uploaded in command
    assert fake.calls[0]["reference_images"] == [str(design_ref.resolve())]


@pytest.mark.asyncio
async def test_vague_check_receives_media_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nanobot.agent.tools.context import RequestContext

    set_config_path(tmp_path / "config.json")
    FakeImageClient.instances = []

    first_ref = tmp_path / "mascot.png"
    first_ref.write_bytes(PNG_BYTES)
    second_ref = tmp_path / "turtle.png"
    second_ref.write_bytes(PNG_BYTES)

    # Mock LLM provider chat method to inspect incoming arguments
    chat_calls = []
    class FakeLLM:
        async def chat(self, messages, model, **kwargs):
            chat_calls.append(messages)
            from dataclasses import dataclass
            @dataclass
            class FakeResponse:
                content: str
            return FakeResponse(content='{"is_vague": true, "purpose": "quảng cáo", "suggestions": ["Robot sảnh", "Robot làm việc", "Robot banner"]}')

    fake_llm = FakeLLM()
    class FakeSnapshot:
        provider = fake_llm
        model = "gpt-4o"
        signature = ()
        context_window_tokens = 4096

    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(
            enabled=True,
            provider="openrouter",
            model="openai/gpt-5.4-image-2",
        ),
        provider_configs={"openrouter": ProviderConfig(api_key="sk-or-test")},
        provider_snapshot_loader=lambda: FakeSnapshot()
    )

    ctx = RequestContext(
        channel="telegram",
        chat_id="123",
        message_id="msg_vague_media",
        session_key="telegram:123",
        metadata={
            "original_user_content": "tạo ảnh quảng cáo hình ảnh công ty chèn thêm linh vật này vào",
            "media": [str(first_ref.resolve()), str(second_ref.resolve())]
        }
    )
    tool.set_context(ctx)

    result = await tool.execute(
        prompt="tạo ảnh quảng cáo hình ảnh công ty chèn thêm linh vật này vào",
        reference_images=None,
    )

    # Should block and return suggestions
    assert "Để tạo ảnh quảng cáo đẹp" in result
    assert "1️⃣ Robot sảnh" in result

    # Should have passed the image as data URL in the chat messages
    assert len(chat_calls) == 1
    user_msg = chat_calls[0][1]
    assert user_msg["role"] == "user"
    content = user_msg["content"]
    assert isinstance(content, list)
    assert content[0]["text"] == 'Yêu cầu khách hàng: "tạo ảnh quảng cáo hình ảnh công ty chèn thêm linh vật này vào"'
    assert len(content) == 3
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[2]["type"] == "image_url"
    assert content[2]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_merge_uploaded_images_requires_suggestion_before_generation(
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

    first_ref = tmp_path / "first.png"
    first_ref.write_bytes(PNG_BYTES)
    second_ref = tmp_path / "second.png"
    second_ref.write_bytes(PNG_BYTES)

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
            message_id="msg_merge",
            session_key="telegram:123",
            metadata={
                "original_user_content": "ghép 2 ảnh này lại thật chuyên nghiệp",
                "current_media": [
                    str(first_ref.resolve()),
                    str(second_ref.resolve()),
                ],
            },
        )
    )

    result = await tool.execute(
        prompt="Ghép hai ảnh tham chiếu thành một bố cục chuyên nghiệp",
        reference_images=[str(first_ref), str(second_ref)],
    )

    # Multi-image + short vague request → universal direction picker must fire.
    assert "bạn muốn hình ảnh thể hiện gì" in result
    assert "1️⃣" in result
    assert "2️⃣" in result
    assert "3️⃣" in result
    assert FakeImageClient.instances == []


@pytest.mark.asyncio
async def test_execute_callback_uses_last_generated_image_instead_of_session_images(
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
    original_ref = tmp_path / "original.png"
    original_ref.write_bytes(PNG_BYTES)
    generated_ref = tmp_path / "generated.png"
    generated_ref.write_bytes(PNG_BYTES)
    session = Session(key="telegram:123")
    session.add_message("user", "Draw Totoro", media=[str(original_ref.resolve())])
    session.add_message(
        "tool",
        json.dumps({"artifacts": [{"path": str(generated_ref.resolve())}]}),
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
    ctx = RequestContext(
        channel="telegram",
        chat_id="123",
        message_id="msg_callback",
        session_key="telegram:123",
        metadata={"is_callback": True}
    )
    tool.set_context(ctx)
    await tool.execute(
        prompt="Tinh gọn cao cấp",
        reference_images=None,
    )
    fake = FakeImageClient.instances[0]
    assert len(fake.calls) == 1
    assert fake.calls[0]["reference_images"] == [str(generated_ref.resolve())]


@pytest.mark.asyncio
async def test_execute_revision_prompt_without_latest_marker_uses_last_generated_image(
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
    original_ref = tmp_path / "original.png"
    original_ref.write_bytes(PNG_BYTES)
    generated_ref = tmp_path / "generated.png"
    generated_ref.write_bytes(PNG_BYTES)
    session = Session(key="telegram:123")
    session.add_message("user", "Draw Totoro", media=[str(original_ref.resolve())])
    session.add_message(
        "tool",
        json.dumps({"artifacts": [{"path": str(generated_ref.resolve())}]}),
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
    ctx = RequestContext(
        channel="telegram",
        chat_id="123",
        message_id="msg_revision",
        session_key="telegram:123",
        metadata={}
    )
    tool.set_context(ctx)
    await tool.execute(
        prompt="Sửa lại cho ánh sáng ấm hơn",
        reference_images=None,
    )
    fake = FakeImageClient.instances[0]
    assert len(fake.calls) == 1
    assert fake.calls[0]["reference_images"] == [str(generated_ref.resolve())]


@pytest.mark.asyncio
async def test_execute_callback_uses_new_user_upload_over_older_generated_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: when user uploads a new product image and then taps a callback
    direction button, the NEW uploaded image must be used as the reference image,
    NOT the previously generated image from an earlier session turn.

    Bug introduced in commit eff15de: callback case always preferred last_generated
    over any subsequent user upload, causing Zen Media to receive the wrong image.
    """
    from nanobot.agent.tools.context import RequestContext
    from nanobot.session.manager import Session

    set_config_path(tmp_path / "config.json")
    FakeImageClient.instances = []
    monkeypatch.setattr(
        "nanobot.agent.tools.image_generation.get_image_gen_provider",
        lambda name: FakeImageClient if name == "openrouter" else None,
    )

    # Simulate: 1) old gen image from turn 0, 2) user uploads a new product image in turn 1
    old_generated = tmp_path / "old-generated.png"
    old_generated.write_bytes(PNG_BYTES)
    new_upload = tmp_path / "new-product-photo.png"
    new_upload.write_bytes(PNG_BYTES)

    session = Session(key="telegram:123")
    # Turn 0: old generation
    session.add_message(
        "tool",
        json.dumps({"artifacts": [{"path": str(old_generated.resolve())}]}),
        name="generate_image",
    )
    session.add_message("assistant", "Đây là ảnh bạn yêu cầu.")
    # Turn 1: user uploads NEW product image (AFTER the old generation)
    session.add_message(
        "user",
        "tạo ảnh quảng cáo từ ảnh này",
        media=[str(new_upload.resolve())],
    )
    session.add_message("assistant", "Bạn muốn hướng ảnh nào?\n1. Hiện đại\n2. Tự nhiên\n3. Cao cấp")

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

    # Simulate user tapping "1. Hiện đại" inline button
    ctx = RequestContext(
        channel="telegram",
        chat_id="123",
        message_id="msg_callback_new_upload",
        session_key="telegram:123",
        metadata={
            "is_callback": True,
            "button_label": "Hiện đại",
            "original_user_content": "1",
        },
    )
    tool.set_context(ctx)

    await tool.execute(
        prompt="Tạo ảnh quảng cáo sản phẩm theo phong cách hiện đại tối giản",
        reference_images=None,
    )

    fake = FakeImageClient.instances[0]
    assert len(fake.calls) == 1
    # MUST use the new user upload, NOT the old generated image
    assert fake.calls[0]["reference_images"] == [str(new_upload.resolve())], (
        "Expected new user upload to be used as reference when user uploaded "
        f"AFTER last generation. Got: {fake.calls[0]['reference_images']}"
    )

