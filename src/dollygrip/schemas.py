"""Request bodies. Responses stay plain dicts - Resolve's API returns loosely
shaped data and we pass it through rather than pretending it is stricter."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

TrackType = Literal["video", "audio", "subtitle"]
MarkType = Literal["video", "audio", "all"]
Page = Literal["media", "photo", "cut", "edit", "fusion", "color", "fairlight", "deliver"]

# --------------------------------------------------------------------------
# system
# --------------------------------------------------------------------------


class SetPage(BaseModel):
    page: Page


class NamedPreset(BaseModel):
    name: str


class ImportPreset(BaseModel):
    path: str = Field(description="Preset file on the Resolve machine")
    name: Optional[str] = Field(default=None, description="Name for the imported preset (defaults to the file name)")


class ExportPreset(BaseModel):
    path: str = Field(description="Destination file on the Resolve machine")


class KeyframeMode(BaseModel):
    mode: Literal["all", "color", "sizing"]


class Confirm(BaseModel):
    confirm: bool = Field(description="Must be true - guards destructive one-shots like quitting Resolve")


class StoragePaths(BaseModel):
    items: List[Union[str, "StorageSubclip"]] = Field(
        description="Absolute file/folder paths, or {media, start_frame, end_frame} objects for subclips"
    )


class StorageSubclip(BaseModel):
    media: str
    start_frame: int
    end_frame: int


class StoragePath(BaseModel):
    path: str


# --------------------------------------------------------------------------
# projects
# --------------------------------------------------------------------------


class OpenProject(BaseModel):
    name: str


class CreateProject(BaseModel):
    name: str
    media_location_path: Optional[str] = None


class RenameProject(BaseModel):
    name: str


class ProjectSettings(BaseModel):
    settings: Dict[str, str]


class ProjectFolder(BaseModel):
    name: str


class OpenProjectFolder(BaseModel):
    name: str = Field(description="Folder name; '..' = parent, '/' = root")


class ImportProjectFile(BaseModel):
    path: str = Field(description=".drp on the Resolve machine")
    name: Optional[str] = None


class ExportProjectFile(BaseModel):
    path: str
    with_stills_and_luts: bool = True


class ArchiveProjectFile(BaseModel):
    path: str = Field(description=".dra destination")
    source_media: bool = True
    render_cache: bool = True
    proxy_media: bool = False


class DatabaseInfo(BaseModel):
    db_type: Literal["Disk", "PostgreSQL"]
    db_name: str
    ip_address: Optional[str] = None


class SpeechGeneration(BaseModel):
    text: str = Field(max_length=350)
    voice_model: str = Field(default="Female 1", description="'Female 1', 'Male 1', 'Custom Voice', ...")
    custom_voice_file: Optional[str] = None
    speed: Optional[int] = None
    variation: Optional[int] = None
    pitch: Optional[int] = None
    generation_id: Optional[int] = None
    filename: Optional[str] = None
    add_to_timeline: bool = False
    audio_track: Optional[int] = None
    timecode: Optional[str] = Field(default=None, description="Where to place it when add_to_timeline is true")


class AudioAtPlayhead(BaseModel):
    path: str
    start_offset_samples: int = 0
    duration_samples: int


# --------------------------------------------------------------------------
# media pool
# --------------------------------------------------------------------------


class SetFolder(BaseModel):
    path: str = Field(description="Bin path from the root, e.g. 'Reels/R8-assets'")
    create: bool = Field(default=False, description="Create missing folders along the path")


class FolderPaths(BaseModel):
    paths: List[str]


class MoveFolders(BaseModel):
    paths: List[str]
    target: str = Field(description="Destination bin path")


class ExportBin(BaseModel):
    path: str = Field(default="", description="Bin path ('' = current bin)")
    file: str = Field(description="Destination .drb file")


class ImportBin(BaseModel):
    file: str = Field(description=".drb file to import into the current bin")
    source_clips_path: str = ""


class ImportMedia(BaseModel):
    paths: List[str] = Field(default_factory=list, description="Absolute file/folder paths on the machine running Resolve")
    sequences: List["ImageSequence"] = Field(default_factory=list, description="Numbered image sequences to import as single clips")


class ImageSequence(BaseModel):
    file_path: str = Field(description="Pattern with printf index, e.g. 'D:/frames/f_%04d.png'")
    start_index: int
    end_index: int


class ClipRefs(BaseModel):
    clips: List[str] = Field(description="Clip references: name in the current bin, or unique id / name anywhere")


class MoveClips(ClipRefs):
    target: str = Field(description="Destination bin path")


class RelinkClips(ClipRefs):
    folder_path: str = Field(description="Folder on disk that now holds the media")


class PatchClip(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = Field(default=None, description="Clip color name; '' clears")
    properties: Optional[Dict[str, str]] = Field(default=None, description="SetClipProperty pairs")
    metadata: Optional[Dict[str, str]] = Field(default=None, description="SetMetadata pairs")
    third_party_metadata: Optional[Dict[str, str]] = None


class Flag(BaseModel):
    color: str


class MarkInOut(BaseModel):
    in_frame: int = Field(alias="in")
    out_frame: int = Field(alias="out")
    type: MarkType = "all"

    model_config = {"populate_by_name": True}


class ProxyPath(BaseModel):
    path: str


class ReplaceClip(BaseModel):
    path: str
    preserve_subclip: bool = False


class Subclips(BaseModel):
    items: List[StorageSubclip]


class ClipMattes(BaseModel):
    paths: List[str]
    stereo_eye: Optional[Literal["left", "right"]] = None


class ExportMetadata(BaseModel):
    file: str = Field(description="CSV destination")
    clips: Optional[List[str]] = Field(default=None, description="Clip refs; omit for the whole media pool")


class SyncAudio(ClipRefs):
    mode: Literal["timecode", "waveform"] = "timecode"
    channel: Optional[int] = Field(default=None, description="Waveform mode: channel offset, -1 automatic, -2 mix")
    retain_embedded_audio: bool = False
    retain_video_metadata: bool = False


class StereoClip(BaseModel):
    left: str
    right: str


class Transcribe(BaseModel):
    speaker_detection: Optional[bool] = None


class Deblur(BaseModel):
    options: Dict[str, Any] = Field(default_factory=dict, description="Motion Deblur settings: FileName, Format, Codec, UseExtremeMode, ...")


class Intellisearch(BaseModel):
    identify_faces: bool = False
    better_mode: bool = False


class SlateAnalysis(BaseModel):
    marker_color: str = Field(default="BLUE", description="Marker color name, e.g. BLUE, GREEN (resolve.MARKER_*)")


# --------------------------------------------------------------------------
# timelines
# --------------------------------------------------------------------------


class CreateTimeline(BaseModel):
    name: str
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = Field(default=None, description="Timeline frame rate, e.g. 30")
    start_timecode: Optional[str] = Field(default=None, description="e.g. '00:00:00:00' (Resolve defaults to 01:00:00:00)")
    extra_video_tracks: int = Field(default=0, ge=0, le=20)
    extra_audio_tracks: int = Field(default=0, ge=0, le=20)


class SetCurrentTimeline(BaseModel):
    name: str


class PatchTimeline(BaseModel):
    name: Optional[str] = None
    start_timecode: Optional[str] = None


class DuplicateTimeline(BaseModel):
    name: Optional[str] = None


class AppendItem(BaseModel):
    clip_name: str = Field(description="Clip reference: name in the CURRENT bin, or unique id / name anywhere")
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
    media_type: Optional[Literal["video", "audio"]] = Field(default=None, description="Restrict to one stream of an A/V clip")


class AppendItems(BaseModel):
    items: List[AppendItem]


class TimelineFromClips(BaseModel):
    name: str
    items: List[AppendItem]


class ImportTimelineFile(BaseModel):
    path: str = Field(description="AAF/EDL/XML/FCPXML/DRT/ADL/OTIO file")
    timeline_name: Optional[str] = None
    import_source_clips: bool = True
    source_clips_path: Optional[str] = None
    source_clips_bins: Optional[List[str]] = Field(default=None, description="Bin paths to search when import_source_clips is false")
    interlace_processing: Optional[bool] = None


class ImportIntoTimeline(BaseModel):
    path: str = Field(description="AAF file")
    options: Dict[str, Any] = Field(default_factory=dict, description="ImportIntoTimeline options, passed through")


class ExportTimeline(BaseModel):
    path: str
    type: Literal[
        "aaf", "drt", "edl", "fcp_7_xml", "fcpxml_1_8", "fcpxml_1_9", "fcpxml_1_10", "hdr_10_profile_a",
        "hdr_10_profile_b", "text_csv", "text_tab", "dolby_vision_ver_2_9", "dolby_vision_ver_4_0",
        "dolby_vision_ver_5_1", "otio", "ale", "ale_cdl",
    ]
    subtype: Optional[Literal["none", "aaf_new", "aaf_existing", "cdl", "sdl", "missing_clips"]] = Field(
        default=None, description="Required for aaf (aaf_new/aaf_existing) and edl (cdl/sdl/missing_clips/none)"
    )


class AddTrack(BaseModel):
    track_type: TrackType
    subtype: Optional[str] = Field(default=None, description="Audio only: 'mono', 'stereo', '5.1', ...")
    index: Optional[int] = Field(default=None, ge=1, description="Insert position (appends if omitted)")


class PatchTrack(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    locked: Optional[bool] = None


class Timecode(BaseModel):
    timecode: str


class InsertGenerator(BaseModel):
    kind: Literal["generator", "fusion_generator", "ofx_generator", "title", "fusion_title", "fusion_composition"]
    name: Optional[str] = Field(default=None, description="Generator/title name, e.g. 'Solid Color', 'Text+'. Not needed for fusion_composition")
    text: Optional[str] = Field(default=None, description="fusion_title only: set the Text+ StyledText right away")


class ItemIds(BaseModel):
    item_ids: List[str]


class DeleteItems(ItemIds):
    ripple: bool = False


class LinkItems(ItemIds):
    linked: bool = True


class CompoundClip(ItemIds):
    name: Optional[str] = None
    start_timecode: Optional[str] = None


class GrabStills(BaseModel):
    all_clips: bool = Field(default=False, description="Grab from every clip instead of the current one")
    frame_source: Literal["first", "middle"] = "middle"


class AutoSubtitles(BaseModel):
    language: Optional[str] = Field(default=None, description="AUTO, ENGLISH, FRENCH, ... (resolve.AUTO_CAPTION_*)")
    preset: Optional[Literal["SUBTITLE_DEFAULT", "TELETEXT", "NETFLIX"]] = None
    chars_per_line: Optional[int] = Field(default=None, ge=1, le=60)
    line_break: Optional[Literal["SINGLE", "DOUBLE"]] = None
    gap: Optional[int] = Field(default=None, ge=0, le=10)


class VoiceIsolation(BaseModel):
    enabled: bool
    amount: int = Field(default=50, ge=0, le=100)


class DolbyVision(BaseModel):
    item_ids: List[str] = Field(default_factory=list, description="Empty = whole timeline")
    blend_shots: bool = False


# --------------------------------------------------------------------------
# markers
# --------------------------------------------------------------------------


class AddMarker(BaseModel):
    frame: int = Field(description="Offset in frames from the start of the timeline/clip")
    color: str = "Blue"
    name: str = ""
    note: str = ""
    duration: int = Field(default=1, ge=1)
    custom_data: str = ""


class MarkerCustomData(BaseModel):
    custom_data: str


# --------------------------------------------------------------------------
# timeline items
# --------------------------------------------------------------------------


class PatchItem(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    color: Optional[str] = Field(default=None, description="Clip color name; '' clears")
    properties: Optional[Dict[str, Any]] = Field(
        default=None,
        description="TimelineItem.SetProperty pairs: Pan, Tilt, ZoomX, ZoomY, RotationAngle, CropLeft..., Opacity, CompositeMode, RetimeProcess, Scaling, ...",
    )


class ItemProperties(BaseModel):
    properties: Dict[str, Any]


class RelocateItem(BaseModel):
    record_frame: Optional[int] = Field(default=None, description="New position, 0-based from the timeline start (default: keep)")
    track_index: Optional[int] = Field(default=None, ge=1, description="New track of the same type (default: keep)")
    start_frame: Optional[int] = Field(default=None, description="New source in-point, source-fps frames (default: keep)")
    end_frame: Optional[int] = Field(default=None, description="New source out-point, source-fps frames (default: keep)")
    ripple: bool = Field(default=False, description="Ripple-delete the old position")
    with_linked: bool = Field(default=False, description="Also move the items linked to this one (e.g. the audio of an A/V clip) by the same offset")


class RippleInsert(AppendItem):
    record_frame: Optional[int] = Field(default=None, description="Insertion frame, 0-based from the timeline start (default: the playhead)")
    all_tracks: bool = Field(default=True, description="Shift items on every track (false = only the target track)")


class SplitItem(BaseModel):
    frame: int = Field(description="Timeline frame to cut at, 0-based from the timeline start (must fall inside the item)")


class AddTake(BaseModel):
    clip: str = Field(description="Clip reference")
    start_frame: Optional[int] = None
    end_frame: Optional[int] = None


class MagicMask(BaseModel):
    mode: Literal["F", "B", "BI"] = "BI"


class CacheSettings(BaseModel):
    color_output: Optional[bool] = None
    fusion_output: Optional[Literal["auto", "on", "off"]] = None


# --------------------------------------------------------------------------
# color
# --------------------------------------------------------------------------

VersionType = Literal["local", "remote"]


class AddVersion(BaseModel):
    name: str
    type: VersionType = "local"


class RenameVersion(BaseModel):
    new_name: str
    type: VersionType = "local"


class CDL(BaseModel):
    node_index: int = Field(default=1, ge=1)
    slope: str = Field(default="1 1 1", description="Three floats, space separated")
    offset: str = "0 0 0"
    power: str = "1 1 1"
    saturation: str = "1"


class CopyGrades(BaseModel):
    target_item_ids: List[str]


class ExportLUT(BaseModel):
    path: str
    size: Literal["17", "33", "65", "panasonic_vlut"] = "33"


class NodeLUT(BaseModel):
    path: str = Field(description="Absolute path, or relative to Resolve's LUT folders (must be in the LUT list - see POST /color/luts/refresh)")


class NodeCache(BaseModel):
    mode: Literal["auto", "on", "off"]


class NodeEnabled(BaseModel):
    enabled: bool


class ApplyDRX(BaseModel):
    path: str
    mode: Literal["no_keyframes", "source_timecode_aligned", "start_frames_aligned"] = "no_keyframes"


class ColorGroupName(BaseModel):
    name: str


class AlbumCreate(BaseModel):
    kind: Literal["still", "powergrade"] = "still"
    name: Optional[str] = None


class AlbumRename(BaseModel):
    name: str


class StillPaths(BaseModel):
    paths: List[str]


class ExportStills(BaseModel):
    folder: str
    prefix: str = "still"
    format: Literal["dpx", "cin", "tif", "jpg", "png", "ppm", "bmp", "xpm", "drx"] = "png"
    indices: Optional[List[int]] = Field(default=None, description="1-based still indices; omit for all")


class StillIndices(BaseModel):
    indices: List[int]


class StillLabel(BaseModel):
    label: str


class ExportFrame(BaseModel):
    path: str = Field(description="Destination with a valid image extension, e.g. D:/out/frame.png")


# --------------------------------------------------------------------------
# fusion
# --------------------------------------------------------------------------


class AddComp(BaseModel):
    import_path: Optional[str] = Field(default=None, description="Import a .comp/.setting file instead of adding an empty comp")


class RenameComp(BaseModel):
    name: str


class CompExport(BaseModel):
    path: str


class AddTool(BaseModel):
    tool_id: str = Field(description="Fusion tool RegID, e.g. 'TextPlus', 'Merge', 'Transform', 'Background', 'Blur'")
    name: Optional[str] = Field(default=None, description="Rename the new tool")
    x: Optional[float] = None
    y: Optional[float] = None
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Initial input values")


class ToolInputs(BaseModel):
    inputs: Dict[str, Any] = Field(description="Input name -> value. Points as [x, y] lists become Fusion tables.")
    frame: Optional[int] = Field(default=None, description="Set at this comp time (creates/sets a keyframe)")


class ConnectInput(BaseModel):
    input: str = Field(description="Input name on this tool, e.g. 'Background', 'Foreground', 'Input'")
    source_tool: str = Field(description="Name of the tool whose output feeds it")


class Keyframe(BaseModel):
    frame: int
    value: Any


class ToolKeyframes(BaseModel):
    input: str
    keyframes: List[Keyframe]
    replace: bool = Field(default=True, description="Replace every existing key on the input (false = merge into the existing spline)")


class ToolExpression(BaseModel):
    input: str
    expression: Optional[str] = Field(default=None, description="Fusion expression, e.g. 'time/24' or 'Merge1.Blend'; null clears it")


class PatchTool(BaseModel):
    name: Optional[str] = None
    pass_through: Optional[bool] = Field(default=None, description="Bypass the tool (TOOLB_PassThrough)")
    locked: Optional[bool] = Field(default=None, description="Lock the tool (TOOLB_Locked)")
    position: Optional[List[float]] = Field(default=None, description="Node position in the flow view, [x, y]")
    tile_color: Optional[List[float]] = Field(default=None, description="Node tile colour [r, g, b] in 0..1; [] clears")


class CompAttrs(BaseModel):
    current_time: Optional[int] = None
    render_start: Optional[int] = None
    render_end: Optional[int] = None
    global_start: Optional[int] = None
    global_end: Optional[int] = None
    hiq: Optional[bool] = None
    motion_blur: Optional[bool] = None
    proxy: Optional[bool] = None
    raw: Optional[Dict[str, Any]] = Field(default=None, description="Any other COMP* attribute, passed to SetAttrs as-is")


class CompUndo(BaseModel):
    action: Literal["start", "end"]
    name: Optional[str] = Field(default=None, description="Undo label (start)")
    keep: bool = Field(default=True, description="end: keep the changes (false = revert the group)")


class PasteSettings(BaseModel):
    template: Optional[str] = Field(default=None, description="An Effects Library / Fusion template by name or kind/name (GET /fusion/templates), e.g. 'titles/Fade On', 'fusion/Particles/Snow'")
    path: Optional[str] = Field(default=None, description=".setting / .comp / macro file on the Resolve machine")
    settings_text: Optional[str] = Field(default=None, description="The text of a .setting file (a Lua settings table) instead of a file")
    inputs: Optional[Dict[str, Dict[str, Any]]] = Field(default=None, description="Per-tool input overrides applied after the paste: {tool_name: {input: value}}")
    detail: bool = Field(default=False, description="Return full input listings for the pasted tools")


class DuplicateTool(BaseModel):
    name: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Inputs to change on the copy")


class ToolSettingsPath(BaseModel):
    path: str


class ToolModifier(BaseModel):
    input: str
    modifier: Literal["BezierSpline", "Path", "XYPath", "Shake", "Calculation", "Offset", "Expression", "Probe", "KeyStretcher"] = "Shake"
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Inputs to set on the modifier itself")


class TextPlus(BaseModel):
    text: str
    tool: Optional[str] = Field(default=None, description="Text+ tool name; default = the first TextPlus tool in the comp")
    font: Optional[str] = None
    style: Optional[str] = Field(default=None, description="Font style, e.g. 'Bold'")
    size: Optional[float] = Field(default=None, description="Fusion size units (0.08 is the default title size)")
    color: Optional[List[float]] = Field(default=None, description="[r, g, b] or [r, g, b, a] in 0..1")
    center: Optional[List[float]] = Field(default=None, description="[x, y] in 0..1, (0.5, 0.5) is centred")
    shadow: Optional[bool] = Field(default=None, description="Enable the drop shadow shading element")
    outline: Optional[List[float]] = Field(default=None, description="Outline colour [r, g, b] (enables the outline element); use with outline_thickness")
    outline_thickness: Optional[float] = Field(default=None, description="Outline thickness, Fusion units (e.g. 0.02)")
    tracking: Optional[float] = Field(default=None, description="Character spacing (1.0 = normal)")
    line_spacing: Optional[float] = Field(default=None, description="Line spacing (1.0 = normal)")
    extra_inputs: Dict[str, Any] = Field(default_factory=dict)



class CompMarker(BaseModel):
    frame: int = Field(description="Comp frame the marker sits on")
    name: str
    note: Optional[str] = None
    duration: float = Field(default=0.0, description="Marker length in frames (0 = a point marker)")
    custom_data: Optional[str] = Field(default=None, description="Free-form tag stored on the marker (customData)")


class SetActiveTool(BaseModel):
    tool: str = Field(description="Tool name to make active (the one the Inspector shows)")


class CompHistoryStep(BaseModel):
    action: Literal["undo", "redo"]
    count: int = Field(default=1, ge=1, description="How many steps")


class SelectTools(BaseModel):
    tools: List[str] = Field(min_length=1, description="Tool names to select")
    exclusive: bool = Field(default=False, description="Deselect everything else first")


class DisconnectInput(BaseModel):
    input: str = Field(description="Input name on this tool whose upstream tool connection is cut, e.g. 'Background'")


class ResetInput(BaseModel):
    input: str = Field(description="Input name to reset to its default (numeric inputs only)")


class TextPlusLines(BaseModel):
    lines: List[str] = Field(min_length=1, description="Lines of text, joined with newlines into StyledText")
    comp: Optional[str] = Field(default=None, description="Comp name or 1-based index; default = the item's current comp")
    tool: Optional[str] = Field(default=None, description="Text+ tool name; default = the first TextPlus tool")

# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


class RenderJob(BaseModel):
    preset: Optional[str] = Field(default=None, description="Render preset to load first (see GET /render/presets)")
    format: Optional[str] = Field(default=None, description="e.g. 'mp4', 'mov' - see GET /render/formats")
    codec: Optional[str] = Field(default=None, description="e.g. 'H264'")
    mode: Optional[Literal["individual", "single"]] = Field(default=None, description="Individual clips or single clip")
    settings: Dict = Field(
        default_factory=dict,
        description="Passed to SetRenderSettings, e.g. {'TargetDir': ..., 'CustomName': ..., "
        "'SelectAllFrames': True, 'FormatWidth': 1080, 'FormatHeight': 1920}",
    )
    start: bool = Field(default=True, description="Start rendering immediately after queueing")


class StartRender(BaseModel):
    job_ids: List[str] = Field(default_factory=list, description="Empty = every queued job")
    interactive: bool = False


class RenderMode(BaseModel):
    mode: Literal["individual", "single"]


class QuickExport(BaseModel):
    preset: str
    target_dir: Optional[str] = None
    custom_name: Optional[str] = None
    video_quality: Optional[Union[int, str]] = None
    enable_upload: Optional[bool] = None


# --------------------------------------------------------------------------
# tools / exec
# --------------------------------------------------------------------------


class TimecodeConvert(BaseModel):
    fps: float
    frames: Optional[int] = None
    timecode: Optional[str] = None
    drop_frame: bool = False


class ExecCode(BaseModel):
    code: str = Field(
        description="Python executed against the live scripting objects. Namespace: "
        "resolve, fusion, project_manager, project, media_pool, media_storage, timeline (may be None), "
        "and a `result` variable you can assign for a structured return."
    )


StoragePaths.model_rebuild()
ImportMedia.model_rebuild()
