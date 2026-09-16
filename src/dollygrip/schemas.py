"""Request bodies. Responses stay plain dicts - Resolve's API returns loosely
shaped data and we pass it through rather than pretending it is stricter."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class OpenProject(BaseModel):
    name: str


class SetPage(BaseModel):
    page: Literal["media", "cut", "edit", "fusion", "color", "fairlight", "deliver"]


class ProjectSettings(BaseModel):
    settings: Dict[str, str]


class SetFolder(BaseModel):
    path: str = Field(description="Bin path from the root, e.g. 'Reels/R8-assets'")
    create: bool = Field(default=False, description="Create missing folders along the path")


class ImportMedia(BaseModel):
    paths: List[str] = Field(description="Absolute file paths on the machine running Resolve")


class CreateTimeline(BaseModel):
    name: str
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = Field(default=None, description="Timeline frame rate, e.g. 30")
    extra_video_tracks: int = Field(default=0, ge=0, le=20)
    extra_audio_tracks: int = Field(default=0, ge=0, le=20)


class SetCurrentTimeline(BaseModel):
    name: str


class AppendItem(BaseModel):
    clip_name: str = Field(description="Media pool clip name, looked up in the CURRENT bin")
    start_frame: Optional[int] = Field(
        default=None,
        description="Source in-point, in SOURCE-fps frames (a 24fps clip on a 30fps "
        "timeline is trimmed in 24fps frames - the classic trap)",
    )
    end_frame: Optional[int] = Field(default=None, description="Source out-point, source-fps frames")
    track_index: int = Field(default=1, ge=1)
    record_frame: Optional[int] = Field(
        default=None,
        description="Where the clip lands on the timeline, 0-based from the timeline start "
        "(the gateway adds Resolve's internal start-frame offset for you)",
    )
    media_type: Optional[Literal["video", "audio"]] = Field(
        default=None, description="Restrict to one stream of an A/V clip"
    )


class AppendItems(BaseModel):
    items: List[AppendItem]


class AddTrack(BaseModel):
    track_type: Literal["video", "audio", "subtitle"]
    subtype: Optional[str] = Field(default=None, description="Audio only: 'mono', 'stereo', '5.1', ...")


class RenderJob(BaseModel):
    format: Optional[str] = Field(default=None, description="e.g. 'mp4', 'mov' - see GET /render/formats")
    codec: Optional[str] = Field(default=None, description="e.g. 'H264'")
    settings: Dict = Field(
        default_factory=dict,
        description="Passed to SetRenderSettings, e.g. {'TargetDir': ..., 'CustomName': ..., "
        "'SelectAllFrames': True, 'FormatWidth': 1080, 'FormatHeight': 1920}",
    )
    start: bool = Field(default=True, description="Start rendering immediately after queueing")


class ExecCode(BaseModel):
    code: str = Field(
        description="Python executed against the live scripting objects. Namespace: "
        "resolve, project_manager, project, media_pool, timeline (may be None), "
        "and a `result` variable you can assign for a structured return."
    )
