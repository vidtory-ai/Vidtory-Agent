"""Tests for Vidtory skills integration."""

from __future__ import annotations

from pathlib import Path
from nanobot.agent.skills import SkillsLoader, BUILTIN_SKILLS_DIR


def test_vidtory_skills_exist_and_load() -> None:
    # Set up a loader pointing to our actual codebase workspace and builtin directory
    workspace = Path(__file__).parent.parent.parent
    loader = SkillsLoader(workspace, builtin_skills_dir=BUILTIN_SKILLS_DIR)

    # 1. List all available skills
    skills = loader.list_skills(filter_unavailable=False)
    skill_names = {entry["name"] for entry in skills}

    # Verify that the Vidtory skills are part of the listed skills
    assert "vidtory-video-generation" in skill_names
    assert "vidtory-audio-generation" in skill_names
    assert "vidtory-creative-workflow" in skill_names

    # 2. Verify metadata and always-active status for all three
    always_skills = loader.get_always_skills()
    assert "vidtory-video-generation" in always_skills
    assert "vidtory-audio-generation" in always_skills
    assert "vidtory-creative-workflow" in always_skills

    # 3. Load contents and verify they are formatted and non-empty
    for skill_name in ["vidtory-video-generation", "vidtory-audio-generation", "vidtory-creative-workflow"]:
        content = loader.load_skill(skill_name)
        assert content is not None
        assert skill_name in content
        
        # Verify YAML frontmatter is present
        assert content.startswith("---")
        
        # Verify we can strip frontmatter correctly
        stripped = loader._strip_frontmatter(content)
        assert not stripped.startswith("---")
        assert len(stripped) > 50
