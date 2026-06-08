"""CapCut/JianYing video draft creation tool."""

import os
import json
import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import (
    ArraySchema,
    NumberSchema,
    ObjectSchema,
    StringSchema,
    tool_parameters_schema,
)

VENDORS_DIR = Path(__file__).resolve().parent.parent.parent / "vendors" / "VectCutAPI"


def _load_draft_lib():
    """Lazy-load pyJianYingDraft to avoid module-level import crash."""
    try:
        from nanobot.vendors.VectCutAPI import pyJianYingDraft as _draft
        from nanobot.vendors.VectCutAPI.pyJianYingDraft import trange as _trange, Clip_settings as _Clip_settings
        return _draft, _trange, _Clip_settings
    except (ImportError, ModuleNotFoundError) as exc:
        raise ImportError(
            f"pyJianYingDraft library is not available: {exc}. "
            "Please ensure the VectCutAPI vendor package is correctly installed."
        ) from exc


@tool_parameters(
    tool_parameters_schema(
        draft_name=StringSchema("Name of the draft project to create"),
        videos=ArraySchema(
            ObjectSchema(
                properties={
                    "file_path": StringSchema("Absolute path to local video file"),
                    "start": NumberSchema("Start time of source video (seconds)"),
                    "end": NumberSchema("End time of source video (seconds)"),
                    "target_start": NumberSchema("Start time on timeline (seconds)"),
                    "volume": NumberSchema("Volume (0.0 to 1.0)"),
                },
                required=["file_path", "start", "end", "target_start"]
            ),
            description="Video clips to add to the main track"
        ),
        audios=ArraySchema(
            ObjectSchema(
                properties={
                    "file_path": StringSchema("Absolute path to local audio file"),
                    "start": NumberSchema("Start time of source audio (seconds)"),
                    "end": NumberSchema("End time of source audio (seconds)"),
                    "target_start": NumberSchema("Start time on timeline (seconds)"),
                    "volume": NumberSchema("Volume (0.0 to 1.0)"),
                },
                required=["file_path", "start", "end", "target_start"]
            ),
            description="Audio clips to add as background or voiceover"
        ),
        texts=ArraySchema(
            ObjectSchema(
                properties={
                    "content": StringSchema("Text content"),
                    "target_start": NumberSchema("Start time on timeline (seconds)"),
                    "target_end": NumberSchema("End time on timeline (seconds)"),
                },
                required=["content", "target_start", "target_end"]
            ),
            description="Text overlays to add to the video"
        ),
        required=["draft_name"]
    )
)
class CapCutDraftTool(Tool):
    """Programmatically assemble video, audio, and text into a CapCut/Jianying draft project.
    
    This tool creates a local CapCut draft folder containing the timeline. The draft can then
    be opened directly in the CapCut desktop app for preview and export.
    """

    @property
    def name(self) -> str:
        return "create_capcut_draft"

    @property
    def description(self) -> str:
        return "Create a CapCut/JianYing video draft from local video and audio files."

    async def execute(
        self,
        draft_name: str,
        videos: list[dict] | None = None,
        audios: list[dict] | None = None,
        texts: list[dict] | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            draft, trange, Clip_settings = _load_draft_lib()
            # Resolve workspace: Tool subclasses store workspace on self.workspace.
            # Fall back to cwd/drafts when running outside the standard nanobot context.
            if hasattr(self, "workspace") and self.workspace:
                workspace = Path(self.workspace).expanduser().resolve() / "drafts"
                workspace.mkdir(parents=True, exist_ok=True)
            else:
                workspace = Path(os.getcwd()) / "drafts"
                workspace.mkdir(parents=True, exist_ok=True)
                
            draft_id = draft_name.replace(" ", "_").lower()
            draft_dir = workspace / draft_id
            
            template_src = VENDORS_DIR / "template"
            if not template_src.exists():
                template_src = VENDORS_DIR / "template_jianying"
                
            if not template_src.exists():
                return f"Error: Template directory not found at {template_src}"
                
            if draft_dir.exists():
                shutil.rmtree(draft_dir)
                
            # Initialize draft from template
            shutil.copytree(template_src, draft_dir)
            script_path = draft_dir / "draft_info.json"
            script = draft.Script_file.load_template(str(script_path))
            
            # Add Videos
            if videos:
                script.add_track(draft.Track_type.video)
                for i, v in enumerate(videos):
                    file_path = v.get("file_path")
                    if not Path(file_path).exists():
                        logger.warning(f"Video file not found: {file_path}")
                        continue
                        
                    start_s = float(v.get("start", 0.0))
                    end_s = float(v.get("end", 5.0))
                    target_start = float(v.get("target_start", 0.0))
                    volume = float(v.get("volume", 1.0))
                    
                    duration_s = end_s - start_s
                    material_name = f"video_{i}_{Path(file_path).name}"
                    
                    video_material = draft.Video_material(
                        material_type="video",
                        replace_path=file_path,
                        remote_url="",
                        material_name=material_name,
                        duration=0, # CapCut will infer
                        width=0,
                        height=0
                    )
                    
                    source_timerange = trange(f"{start_s}s", f"{duration_s}s")
                    target_timerange = trange(f"{target_start}s", f"{duration_s}s")
                    
                    video_segment = draft.Video_segment(
                        video_material,
                        target_timerange=target_timerange,
                        source_timerange=source_timerange,
                        speed=1.0,
                        clip_settings=Clip_settings(transform_y=0, scale_x=1, scale_y=1, transform_x=0),
                        volume=volume
                    )
                    script.add_segment(video_segment)
                    
            # Add Audios
            if audios:
                script.add_track(draft.Track_type.audio)
                for i, a in enumerate(audios):
                    file_path = a.get("file_path")
                    if not Path(file_path).exists():
                        logger.warning(f"Audio file not found: {file_path}")
                        continue
                        
                    start_s = float(a.get("start", 0.0))
                    end_s = float(a.get("end", 5.0))
                    target_start = float(a.get("target_start", 0.0))
                    volume = float(a.get("volume", 1.0))
                    
                    duration_s = end_s - start_s
                    material_name = f"audio_{i}_{Path(file_path).name}"
                    
                    audio_material = draft.Audio_material(
                        material_type="audio",
                        replace_path=file_path,
                        remote_url="",
                        material_name=material_name,
                        duration=0
                    )
                    
                    source_timerange = trange(f"{start_s}s", f"{duration_s}s")
                    target_timerange = trange(f"{target_start}s", f"{duration_s}s")
                    
                    audio_segment = draft.Audio_segment(
                        audio_material,
                        target_timerange=target_timerange,
                        source_timerange=source_timerange,
                        speed=1.0,
                        volume=volume
                    )
                    script.add_segment(audio_segment)
                    
            # Add Texts
            if texts:
                script.add_track(draft.Track_type.text)
                for t in texts:
                    content = t.get("content", "")
                    target_start = float(t.get("target_start", 0.0))
                    target_end = float(t.get("target_end", 5.0))
                    duration_s = target_end - target_start
                    
                    timerange = trange(f"{target_start}s", f"{duration_s}s")
                    text_segment = draft.Text_segment(content, timerange)
                    script.add_segment(text_segment)
                    
            # Compute total duration
            max_duration = 0
            for track_name, track in script.tracks.items():
                for segment in track.segments:
                    if segment.target_timerange.end > max_duration:
                        max_duration = segment.target_timerange.end
            script.duration = max_duration
            
            # Save the script
            script.dump(str(script_path))
            
            return json.dumps({
                "status": "success",
                "message": f"Draft created successfully at {draft_dir}",
                "draft_dir": str(draft_dir)
            })
            
        except Exception as e:
            logger.exception("Failed to create CapCut draft")
            return f"Error creating draft: {e}"
