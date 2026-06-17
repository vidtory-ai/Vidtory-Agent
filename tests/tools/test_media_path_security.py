"""Path-boundary tests for creative media tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from nanobot.agent.tools.video_generation import (
    VideoGenerationError,
    VideoGenerationTool,
    VideoGenerationToolConfig,
)
from nanobot.agent.tools.watermark_removal import (
    WatermarkRemovalError,
    WatermarkRemovalTool,
    WatermarkRemovalToolConfig,
)

_PNG = b"\x89PNG\r\n\x1a\n" + b"test"


def test_video_reference_blocks_local_file_outside_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    media = tmp_path / "media"
    workspace.mkdir()
    media.mkdir()
    outside = tmp_path / "secret.png"
    outside.write_bytes(_PNG)
    monkeypatch.setattr(
        "nanobot.agent.tools.video_generation.get_media_dir",
        lambda: media,
    )
    tool = VideoGenerationTool(
        workspace=workspace,
        config=VideoGenerationToolConfig(),
    )

    with pytest.raises(VideoGenerationError, match="inside the workspace"):
        tool._resolve_reference_image(str(outside))


def test_video_reference_allows_uploaded_media(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    media = tmp_path / "media"
    workspace.mkdir()
    media.mkdir()
    uploaded = media / "upload.png"
    uploaded.write_bytes(_PNG)
    monkeypatch.setattr(
        "nanobot.agent.tools.video_generation.get_media_dir",
        lambda: media,
    )
    tool = VideoGenerationTool(
        workspace=workspace,
        config=VideoGenerationToolConfig(),
    )

    assert tool._resolve_reference_image(str(uploaded)) == str(uploaded.resolve())


def test_watermark_removal_blocks_local_file_outside_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    media = tmp_path / "media"
    workspace.mkdir()
    media.mkdir()
    outside = tmp_path / "secret.png"
    outside.write_bytes(_PNG)
    monkeypatch.setattr(
        "nanobot.agent.tools.watermark_removal.get_media_dir",
        lambda: media,
    )
    tool = WatermarkRemovalTool(
        workspace=workspace,
        config=WatermarkRemovalToolConfig(),
    )

    with pytest.raises(WatermarkRemovalError, match="inside the workspace"):
        tool._resolve_image_path(str(outside))
