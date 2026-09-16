"""An in-memory fake of the Resolve scripting object graph.

Shaped like the real API (same method names, argument orders and return
shapes as Blackmagic's README) for the subset DollyGrip touches, so the whole
HTTP surface is testable without Resolve installed. Keep it honest: when a
real call returns a dict keyed by frame, so does the fake; when Resolve
returns False on failure, so does the fake.
"""

from __future__ import annotations

import itertools
import json

_ids = itertools.count(1)


def _uid(prefix):
    return f"{prefix}-{next(_ids)}"


# --------------------------------------------------------------------------
# mixins shared by MediaPoolItem / Timeline / TimelineItem
# --------------------------------------------------------------------------


class Markable:
    def _init_markers(self):
        self.markers = {}

    def AddMarker(self, frameId, color, name, note, duration, customData=""):
        key = float(frameId)
        if key in self.markers:
            return False
        self.markers[key] = {"color": color, "name": name, "note": note, "duration": float(duration), "customData": customData or ""}
        return True

    def GetMarkers(self):
        return dict(self.markers)

    def GetMarkerByCustomData(self, customData):
        for info in self.markers.values():
            if info["customData"] == customData:
                return dict(info)
        return {}

    def UpdateMarkerCustomData(self, frameId, customData):
        info = self.markers.get(float(frameId))
        if not info:
            return False
        info["customData"] = customData
        return True

    def GetMarkerCustomData(self, frameId):
        info = self.markers.get(float(frameId))
        return info["customData"] if info else ""

    def DeleteMarkersByColor(self, color):
        before = len(self.markers)
        self.markers = {k: v for k, v in self.markers.items() if color != "All" and v["color"] != color}
        return len(self.markers) != before or color == "All"

    def DeleteMarkerAtFrame(self, frameNum):
        return self.markers.pop(float(frameNum), None) is not None

    def DeleteMarkerByCustomData(self, customData):
        for k, v in list(self.markers.items()):
            if v["customData"] == customData:
                del self.markers[k]
                return True
        return False


class Flaggable:
    def _init_flags(self):
        self.flags = []
        self.clip_color = ""

    def AddFlag(self, color):
        self.flags.append(color)
        return True

    def GetFlagList(self):
        return list(self.flags)

    def ClearFlags(self, color):
        self.flags = [] if color == "All" else [f for f in self.flags if f != color]
        return True

    def GetClipColor(self):
        return self.clip_color

    def SetClipColor(self, colorName):
        self.clip_color = colorName
        return True

    def ClearClipColor(self):
        self.clip_color = ""
        return True


# --------------------------------------------------------------------------
# media pool
# --------------------------------------------------------------------------


class FakeClip(Markable, Flaggable):
    def __init__(self, name, props=None, frames=240):
        self._name = name
        self._id = _uid("mpi")
        self._props = props or {
            "Duration": "00:00:10:00",
            "Frames": str(frames),
            "FPS": "24",
            "Resolution": "1080x1920",
            "Type": "Video",
            "File Path": f"D:/media/{name}",
        }
        self.metadata = {"Description": ""}
        self.third_party = {}
        self.proxy = None
        self.mark = {}
        self.transcribed = False
        self.classified = False
        self.replaced_with = None
        self._init_markers()
        self._init_flags()

    def GetName(self):
        return self._name

    def SetName(self, name):
        self._name = name
        return True

    def GetUniqueId(self):
        return self._id

    def GetMediaId(self):
        return "media-" + self._id

    def GetClipProperty(self, key=None):
        return dict(self._props) if key is None else self._props.get(key, "")

    def SetClipProperty(self, key, value):
        self._props[key] = value
        return True

    def GetMetadata(self, key=None):
        return dict(self.metadata) if key is None else self.metadata.get(key, "")

    def SetMetadata(self, key, value=None):
        if isinstance(key, dict):
            self.metadata.update(key)
        else:
            self.metadata[key] = value
        return True

    def GetThirdPartyMetadata(self, key=None):
        return dict(self.third_party) if key is None else self.third_party.get(key, "")

    def SetThirdPartyMetadata(self, key, value=None):
        if isinstance(key, dict):
            self.third_party.update(key)
        else:
            self.third_party[key] = value
        return True

    def GetTimeline(self):
        return None

    def LinkProxyMedia(self, path):
        self.proxy = path
        return True

    def LinkFullResolutionMedia(self, path):
        self._props["File Path"] = path
        return True

    def UnlinkProxyMedia(self):
        self.proxy = None
        return True

    def ReplaceClip(self, path):
        self.replaced_with = path
        return True

    def ReplaceClipPreserveSubClip(self, path):
        self.replaced_with = ("preserve", path)
        return True

    def TranscribeAudio(self, useSpeakerDetection=None):
        self.transcribed = True
        return True

    def ClearTranscription(self):
        self.transcribed = False
        return True

    def PerformAudioClassification(self):
        self.classified = True
        return True

    def ClearAudioClassification(self):
        self.classified = False
        return True

    def GetAudioMapping(self):
        return json.dumps({"embedded_audio_channels": 2, "linked_audio": {}, "track_mapping": {"1": {"channel_idx": [1, 2], "mute": False, "type": "Stereo"}}})

    def GetMarkInOut(self):
        return dict(self.mark)

    def SetMarkInOut(self, i, o, kind="all"):
        for k in (["video", "audio"] if kind == "all" else [kind]):
            self.mark[k] = {"in": i, "out": o}
        return True

    def ClearMarkInOut(self, kind="all"):
        for k in (["video", "audio"] if kind == "all" else [kind]):
            self.mark.pop(k, None)
        return True

    def MonitorGrowingFile(self):
        return True

    def RemoveMotionBlur(self, options):
        return FakeClip(self._name.rsplit(".", 1)[0] + "_deblur.mov")

    def AnalyzeForIntellisearch(self, identifyFaces, isBetterMode):
        return True

    def AnalyzeForSlate(self, markerColor):
        return True


class FakeFolder:
    def __init__(self, name, clips=None, subfolders=None):
        self._name = name
        self._id = _uid("folder")
        self.clips = clips or []
        self.subfolders = subfolders or []
        self.exported_to = None
        self.transcribed = False

    def GetName(self):
        return self._name

    def GetUniqueId(self):
        return self._id

    def GetClipList(self):
        return list(self.clips)

    def GetSubFolderList(self):
        return list(self.subfolders)

    def GetIsFolderStale(self):
        return False

    def Export(self, path):
        self.exported_to = path
        return True

    def TranscribeAudio(self, useSpeakerDetection=None):
        self.transcribed = True
        return True

    def ClearTranscription(self):
        self.transcribed = False
        return True

    def PerformAudioClassification(self):
        return True

    def ClearAudioClassification(self):
        return True

    def RemoveMotionBlur(self, options):
        return [[c, FakeClip(c.GetName() + "_deblur")] for c in self.clips]

    def AnalyzeForIntellisearch(self, identifyFaces, isBetterMode):
        return True

    def AnalyzeForSlate(self, markerColor):
        return True


class FakeMediaStorage:
    def __init__(self, pool_getter):
        self._pool = pool_getter
        self.revealed = None

    def GetMountedVolumeList(self):
        return ["C:/", "D:/"]

    def GetSubFolderList(self, path):
        return [path.rstrip("/") + "/shoot", path.rstrip("/") + "/audio"]

    def GetFileList(self, path):
        return [path.rstrip("/") + "/a.mov", path.rstrip("/") + "/b.wav"]

    def RevealInStorage(self, path):
        self.revealed = path
        return True

    def AddItemListToMediaPool(self, items):
        pool = self._pool()
        out = []
        for it in items:
            path = it["media"] if isinstance(it, dict) else it
            clip = FakeClip(path.replace("\\", "/").rsplit("/", 1)[-1])
            if isinstance(it, dict):
                clip._props["Start"] = str(it.get("startFrame"))
                clip._props["End"] = str(it.get("endFrame"))
            pool.current.clips.append(clip)
            out.append(clip)
        return out

    def AddClipMattesToMediaPool(self, clip, paths, stereoEye=None):
        self._pool().mattes.setdefault(clip.GetUniqueId(), []).extend(paths)
        return True

    def AddTimelineMattesToMediaPool(self, paths):
        pool = self._pool()
        clips = [FakeClip(p.rsplit("/", 1)[-1]) for p in paths]
        pool.timeline_mattes.setdefault(pool.current.GetUniqueId(), []).extend(clips)
        return clips


class FakeMediaPool:
    def __init__(self, root, project):
        self.root = root
        self.current = root
        self.project = project
        self.appended = []
        self.mattes = {}
        self.timeline_mattes = {}
        self.selected = []
        self.relinked = []
        self.unlinked = []
        self.deleted = []
        self.synced = None
        self.exported_metadata = None
        self.imported_folders = []
        self._id = _uid("pool")

    def GetUniqueId(self):
        return self._id

    def GetRootFolder(self):
        return self.root

    def GetCurrentFolder(self):
        return self.current

    def SetCurrentFolder(self, folder):
        self.current = folder
        return True

    def AddSubFolder(self, parent, name):
        folder = FakeFolder(name)
        parent.subfolders.append(folder)
        return folder

    def RefreshFolders(self):
        return True

    def ImportMedia(self, items):
        clips = []
        for it in items:
            if isinstance(it, dict):
                name = it["FilePath"].replace("\\", "/").rsplit("/", 1)[-1]
                clip = FakeClip(name.replace("%03d", f"[{it.get('StartIndex', 1):03d}-{it.get('EndIndex', 1):03d}]"))
            else:
                clip = FakeClip(it.replace("\\", "/").rsplit("/", 1)[-1])
            clips.append(clip)
        self.current.clips.extend(clips)
        return clips

    def CreateEmptyTimeline(self, name):
        if any(t.GetName() == name for t in self.project.timelines):
            return None
        tl = FakeTimeline(name, project=self.project)
        self.project.timelines.append(tl)
        self.project.current_timeline = tl
        return tl

    def CreateTimelineFromClips(self, name, clips):
        tl = self.CreateEmptyTimeline(name)
        if tl is None:
            return None
        for c in clips:
            info = c if isinstance(c, dict) else {"mediaPoolItem": c}
            tl._append(info)
        return tl

    def ImportTimelineFromFile(self, path, options=None):
        name = (options or {}).get("timelineName") or path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        tl = self.CreateEmptyTimeline(name)
        if tl:
            tl.imported_from = (path, options)
        return tl

    def AppendToTimeline(self, infos):
        tl = self.project.current_timeline
        if tl is None:
            return None
        out = []
        for info in infos:
            info = info if isinstance(info, dict) else {"mediaPoolItem": info}
            self.appended.append(info)
            out.append(tl._append(info))
        return out

    def DeleteTimelines(self, timelines):
        for tl in timelines:
            if tl in self.project.timelines:
                self.project.timelines.remove(tl)
                if self.project.current_timeline is tl:
                    self.project.current_timeline = self.project.timelines[0] if self.project.timelines else None
        return True

    def DeleteClips(self, clips):
        for folder in _walk(self.root):
            folder.clips = [c for c in folder.clips if c not in clips]
        self.deleted.extend(clips)
        return True

    def DeleteFolders(self, folders):
        for folder in _walk(self.root):
            folder.subfolders = [f for f in folder.subfolders if f not in folders]
        return True

    def MoveClips(self, clips, target):
        self.DeleteClips(clips)
        self.deleted = [c for c in self.deleted if c not in clips]
        target.clips.extend(clips)
        return True

    def MoveFolders(self, folders, target):
        self.DeleteFolders(folders)
        target.subfolders.extend(folders)
        return True

    def ImportFolderFromFile(self, path, sourceClipsPath=""):
        self.imported_folders.append(path)
        self.current.subfolders.append(FakeFolder(path.rsplit("/", 1)[-1].rsplit(".", 1)[0]))
        return True

    def GetClipMatteList(self, clip):
        return list(self.mattes.get(clip.GetUniqueId(), []))

    def GetTimelineMatteList(self, folder):
        return list(self.timeline_mattes.get(folder.GetUniqueId(), []))

    def DeleteClipMattes(self, clip, paths):
        cur = self.mattes.get(clip.GetUniqueId(), [])
        self.mattes[clip.GetUniqueId()] = [p for p in cur if p not in paths]
        return True

    def RelinkClips(self, clips, folderPath):
        self.relinked.append((clips, folderPath))
        return True

    def UnlinkClips(self, clips):
        self.unlinked.extend(clips)
        return True

    def ExportMetadata(self, fileName, clips=None):
        self.exported_metadata = (fileName, clips)
        return True

    def CreateStereoClip(self, left, right):
        clip = FakeClip(left.GetName() + "_3D")
        self.current.clips.append(clip)
        return clip

    def AutoSyncAudio(self, clips, settings):
        if len(clips) < 2:
            return False
        self.synced = (clips, settings)
        return True

    def GetSelectedClips(self):
        return list(self.selected)

    def SetSelectedClip(self, clip):
        self.selected = [clip]
        return True


def _walk(folder):
    yield folder
    for f in folder.subfolders:
        yield from _walk(f)


# --------------------------------------------------------------------------
# color / fusion objects
# --------------------------------------------------------------------------


class FakeGraph:
    def __init__(self, nodes=2):
        self.nodes = [{"label": f"Node {i}", "lut": "", "cache": 0, "enabled": True, "tools": ["Primaries"]} for i in range(1, nodes + 1)]
        self.applied_drx = None
        self.reset = False

    def GetNumNodes(self):
        return len(self.nodes)

    def _node(self, idx):
        return self.nodes[idx - 1] if 1 <= idx <= len(self.nodes) else None

    def SetLUT(self, idx, path):
        n = self._node(idx)
        if not n or not path:
            return False
        n["lut"] = path
        return True

    def GetLUT(self, idx):
        n = self._node(idx)
        return n["lut"] if n else ""

    def SetNodeCacheMode(self, idx, value):
        n = self._node(idx)
        if not n:
            return False
        n["cache"] = value
        return True

    def GetNodeCacheMode(self, idx):
        n = self._node(idx)
        return n["cache"] if n else None

    def GetNodeLabel(self, idx):
        n = self._node(idx)
        return n["label"] if n else ""

    def GetToolsInNode(self, idx):
        n = self._node(idx)
        return list(n["tools"]) if n else []

    def SetNodeEnabled(self, idx, enabled):
        n = self._node(idx)
        if not n:
            return False
        n["enabled"] = enabled
        return True

    def ApplyGradeFromDRX(self, path, mode):
        self.applied_drx = (path, mode)
        return path.endswith(".drx")

    def ApplyArriCdlLut(self):
        return True

    def ResetAllGrades(self):
        self.reset = True
        return True


class FakeInput:
    """A Fusion Input proxy: supports `inp[frame] = value` keyframing."""

    def __init__(self, tool, name):
        self.tool, self.name = tool, name

    def __setitem__(self, frame, value):
        self.tool.keyframes.setdefault(self.name, {})[frame] = value
        self.tool.inputs[self.name] = value

    def __getitem__(self, frame):
        return self.tool.keyframes.get(self.name, {}).get(frame, self.tool.inputs.get(self.name))

    def GetAttrs(self):
        return {"INPS_Name": self.name, "INPS_ID": self.name, "INPB_Connected": False}


class FakeTool:
    def __init__(self, comp, reg_id, name):
        self.comp, self.reg_id = comp, reg_id
        self.Name, self.ID = name, reg_id
        self.inputs = {"StyledText": "Title", "Size": 0.08} if reg_id == "TextPlus" else {}
        self.keyframes = {}
        self.connections = {}
        self.deleted = False

    def GetAttrs(self):
        return {"TOOLS_Name": self.Name, "TOOLS_RegID": self.reg_id, "TOOLB_PassThrough": False, "TOOLB_Selected": False}

    def SetAttrs(self, attrs):
        if "TOOLS_Name" in attrs:
            self.comp.tools[attrs["TOOLS_Name"]] = self.comp.tools.pop(self.Name)
            self.Name = attrs["TOOLS_Name"]
        return True

    def GetInput(self, name, time=None):
        return self.inputs.get(name)

    def SetInput(self, name, value, time=None):
        if time is not None:
            self.keyframes.setdefault(name, {})[time] = value
        self.inputs[name] = value
        return True

    def GetInputList(self):
        return {i + 1: FakeInput(self, n) for i, n in enumerate(sorted(set(self.inputs) | {"Center", "Font"}))}

    def ConnectInput(self, name, source):
        self.connections[name] = source.Name
        return True

    def Delete(self):
        self.deleted = True
        self.comp.tools.pop(self.Name, None)

    def __getattr__(self, name):
        if name.startswith("_") or name in ("comp", "reg_id", "Name", "ID", "inputs", "keyframes", "connections", "deleted"):
            raise AttributeError(name)
        return FakeInput(self, name)


class FakeComp:
    def __init__(self, name="Composition 1", with_text=False):
        self.name = name
        self.tools = {}
        self.locked = False
        self.saved_to = None
        self.attrs = {"COMPN_RenderStart": 0, "COMPN_RenderEnd": 149, "COMPN_CurrentTime": 0, "COMPS_Name": name}
        self.AddTool("MediaIn")
        self.AddTool("MediaOut")
        if with_text:
            t = self.AddTool("TextPlus")
            t.SetAttrs({"TOOLS_Name": "Template"})

    def GetToolList(self, selectedOnly=False, toolType=None):
        tools = [t for t in self.tools.values() if toolType in (None, "") or t.reg_id == toolType]
        return {i + 1: t for i, t in enumerate(tools)}

    def AddTool(self, reg_id, x=None, y=None):
        n = 1 + sum(1 for t in self.tools.values() if t.reg_id == reg_id)
        tool = FakeTool(self, reg_id, f"{reg_id}{n}")
        self.tools[tool.Name] = tool
        return tool

    def FindTool(self, name):
        return self.tools.get(name)

    def Lock(self):
        self.locked = True

    def Unlock(self):
        self.locked = False

    def StartUndo(self, name):
        return True

    def EndUndo(self, keep=True):
        return True

    def Save(self, path):
        self.saved_to = path
        return True

    def GetAttrs(self):
        return dict(self.attrs)

    def SetAttrs(self, attrs):
        self.attrs.update(attrs)
        return True

    def BezierSpline(self):
        return object()


class FakeGalleryStill:
    def __init__(self, label=""):
        self.label = label


class FakeAlbum:
    def __init__(self, name, kind="still", stills=None):
        self.name, self.kind = name, kind
        self.stills = stills or []
        self.exported = None

    def GetStills(self):
        return list(self.stills)

    def GetLabel(self, still):
        return still.label

    def SetLabel(self, still, label):
        still.label = label
        return True

    def ImportStills(self, paths):
        self.stills.extend(FakeGalleryStill(p.rsplit("/", 1)[-1]) for p in paths)
        return bool(paths)

    def ExportStills(self, stills, folder, prefix, fmt):
        self.exported = (stills, folder, prefix, fmt)
        return True

    def DeleteStills(self, stills):
        self.stills = [s for s in self.stills if s not in stills]
        return True


class FakeGallery:
    def __init__(self):
        self.still_albums = [FakeAlbum("Stills", stills=[FakeGalleryStill("shot 1")])]
        self.pg_albums = [FakeAlbum("PowerGrade 1", "powergrade")]
        self.current = self.still_albums[0]

    def GetAlbumName(self, album):
        return album.name

    def SetAlbumName(self, album, name):
        album.name = name
        return True

    def GetCurrentStillAlbum(self):
        return self.current

    def SetCurrentStillAlbum(self, album):
        self.current = album
        return True

    def GetGalleryStillAlbums(self):
        return list(self.still_albums)

    def GetGalleryPowerGradeAlbums(self):
        return list(self.pg_albums)

    def CreateGalleryStillAlbum(self):
        a = FakeAlbum(f"Album {len(self.still_albums) + 1}")
        self.still_albums.append(a)
        return a

    def CreateGalleryPowerGradeAlbum(self):
        a = FakeAlbum(f"PowerGrade {len(self.pg_albums) + 1}", "powergrade")
        self.pg_albums.append(a)
        return a


class FakeColorGroup:
    def __init__(self, name, project):
        self.name, self.project = name, project
        self.pre, self.post = FakeGraph(1), FakeGraph(1)

    def GetName(self):
        return self.name

    def SetName(self, name):
        self.name = name
        return True

    def GetClipsInTimeline(self, timeline=None):
        tl = timeline or self.project.current_timeline
        return [it for it in tl._all_items() if it.group is self]

    def GetPreClipNodeGraph(self):
        return self.pre

    def GetPostClipNodeGraph(self):
        return self.post


# --------------------------------------------------------------------------
# timeline
# --------------------------------------------------------------------------


class FakeTimelineItem(Markable, Flaggable):
    def __init__(self, name, start, duration, track_type, track_index, mpi=None, timeline=None, source_start=0):
        self._name = name
        self._id = _uid("ti")
        self.start, self.duration = start, duration
        self.track_type, self.track_index = track_type, track_index
        self.mpi, self.timeline = mpi, timeline
        self.source_start = source_start
        self.link_group = None
        self.props = {"ZoomX": 1.0, "ZoomY": 1.0, "Pan": 0.0, "Tilt": 0.0, "Opacity": 100.0, "CompositeMode": 0, "RotationAngle": 0.0}
        self.enabled = True
        self.comps = []
        self.versions = {0: ["Version 1"], 1: []}
        self.current_version = ("Version 1", 0)
        self.cdl = None
        self.takes = []
        self.selected_take = 0
        self.group = None
        self.graphs = {1: FakeGraph()}
        self.color_cache, self.fusion_cache = False, -1
        self.voice = {"isEnabled": False, "amount": 0}
        self.burn_in = None
        self.exported_lut = None
        self.grades_copied_to = []
        self.stabilized = self.reframed = self.magic_mask = False
        self._init_markers()
        self._init_flags()

    # identity / timing
    def GetName(self):
        return self._name

    def SetName(self, name):
        self._name = name
        return True

    def GetUniqueId(self):
        return self._id

    def GetStart(self, subframe=False):
        return self.start

    def GetEnd(self, subframe=False):
        return self.start + self.duration

    def GetDuration(self, subframe=False):
        return self.duration

    def GetLeftOffset(self, subframe=False):
        return self.source_start

    def GetRightOffset(self, subframe=False):
        return 10

    def GetSourceStartFrame(self):
        return self.source_start

    def GetSourceEndFrame(self):
        return self.source_start + self.duration

    def GetSourceStartTime(self):
        return self.source_start / 24.0

    def GetSourceEndTime(self):
        return (self.source_start + self.duration) / 24.0

    def GetMediaPoolItem(self):
        return self.mpi

    def GetTrackTypeAndIndex(self):
        return [self.track_type, self.track_index]

    def GetLinkedItems(self):
        return [it for it in self.timeline._all_items() if it is not self and self.link_group is not None and it.link_group == self.link_group]

    # properties
    def SetProperty(self, key, value=None):
        if isinstance(key, dict):
            self.props.update(key)
        else:
            self.props[key] = value
        return True

    def GetProperty(self, key=None):
        return dict(self.props) if key is None else self.props.get(key)

    def SetClipEnabled(self, enabled):
        self.enabled = bool(enabled)
        return True

    def GetClipEnabled(self):
        return self.enabled

    # fusion
    def GetFusionCompCount(self):
        return len(self.comps)

    def GetFusionCompByIndex(self, idx):
        return self.comps[idx - 1] if 1 <= idx <= len(self.comps) else None

    def GetFusionCompNameList(self):
        return [c.name for c in self.comps]

    def GetFusionCompByName(self, name):
        return next((c for c in self.comps if c.name == name), None)

    def AddFusionComp(self):
        comp = FakeComp(f"Composition {len(self.comps) + 1}")
        self.comps.append(comp)
        return comp

    def ImportFusionComp(self, path):
        comp = FakeComp(path.rsplit("/", 1)[-1].rsplit(".", 1)[0])
        self.comps.append(comp)
        return comp

    def ExportFusionComp(self, path, idx):
        comp = self.GetFusionCompByIndex(idx)
        if not comp:
            return False
        comp.saved_to = path
        return True

    def DeleteFusionCompByName(self, name):
        before = len(self.comps)
        self.comps = [c for c in self.comps if c.name != name]
        return len(self.comps) != before

    def LoadFusionCompByName(self, name):
        return self.GetFusionCompByName(name)

    def RenameFusionCompByName(self, old, new):
        comp = self.GetFusionCompByName(old)
        if not comp:
            return False
        comp.name = new
        return True

    # color
    def AddVersion(self, name, vtype):
        if name in self.versions[vtype]:
            return False
        self.versions[vtype].append(name)
        return True

    def GetCurrentVersion(self):
        return {"versionName": self.current_version[0], "versionType": self.current_version[1]}

    def DeleteVersionByName(self, name, vtype):
        if name not in self.versions[vtype]:
            return False
        self.versions[vtype].remove(name)
        return True

    def LoadVersionByName(self, name, vtype):
        if name not in self.versions[vtype]:
            return False
        self.current_version = (name, vtype)
        return True

    def RenameVersionByName(self, old, new, vtype):
        if old not in self.versions[vtype]:
            return False
        self.versions[vtype][self.versions[vtype].index(old)] = new
        return True

    def GetVersionNameList(self, vtype):
        return list(self.versions[vtype])

    def SetCDL(self, cdl):
        self.cdl = cdl
        return True

    def CopyGrades(self, targets):
        self.grades_copied_to.extend(targets)
        return True

    def GetNodeGraph(self, layer=1):
        return self.graphs.setdefault(layer, FakeGraph())

    def GetColorGroup(self):
        return self.group

    def AssignToColorGroup(self, group):
        self.group = group
        return True

    def RemoveFromColorGroup(self):
        self.group = None
        return True

    def ExportLUT(self, export_type, path):
        self.exported_lut = (export_type, path)
        return True

    def ResetAllNodeColors(self):
        return True

    def LoadBurnInPreset(self, name):
        self.burn_in = name
        return True

    # takes
    def AddTake(self, mpi, start=None, end=None):
        self.takes.append({"mediaPoolItem": mpi, "startFrame": start or 0, "endFrame": end or 100})
        self.selected_take = len(self.takes)
        return True

    def GetSelectedTakeIndex(self):
        return self.selected_take

    def GetTakesCount(self):
        return len(self.takes)

    def GetTakeByIndex(self, idx):
        return dict(self.takes[idx - 1]) if 1 <= idx <= len(self.takes) else None

    def DeleteTakeByIndex(self, idx):
        if not 1 <= idx <= len(self.takes):
            return False
        del self.takes[idx - 1]
        return True

    def SelectTakeByIndex(self, idx):
        if not 1 <= idx <= len(self.takes):
            return False
        self.selected_take = idx
        return True

    def FinalizeTake(self):
        self.takes = []
        return True

    # ai / misc
    def Stabilize(self):
        self.stabilized = True
        return True

    def SmartReframe(self):
        self.reframed = True
        return True

    def CreateMagicMask(self, mode):
        self.magic_mask = mode in ("F", "B", "BI")
        return self.magic_mask

    def RegenerateMagicMask(self):
        return self.magic_mask

    def UpdateSidecar(self):
        return True

    def GetSourceAudioChannelMapping(self):
        return json.dumps({"embedded_audio_channels": 2, "linked_audio": {}, "track_mapping": {}})

    def GetIsColorOutputCacheEnabled(self):
        return self.color_cache

    def GetIsFusionOutputCacheEnabled(self):
        return self.fusion_cache

    def SetColorOutputCache(self, value):
        self.color_cache = value
        return True

    def SetFusionOutputCache(self, value):
        self.fusion_cache = value
        return True

    def GetVoiceIsolationState(self):
        return dict(self.voice)

    def SetVoiceIsolationState(self, state):
        self.voice = dict(state)
        return True

    def GetStereoConvergenceValues(self):
        return {}


class FakeTimeline(Markable):
    START = 108000  # Resolve's classic 01:00:00:00 at 30fps

    def __init__(self, name, fps="30", project=None):
        self._name = name
        self._id = _uid("tl")
        self.project = project
        self.settings = {"timelineFrameRate": fps, "timelineResolutionWidth": "1080", "timelineResolutionHeight": "1920"}
        self.tracks = {"video": [self._track("Video 1")], "audio": [self._track("Audio 1", "stereo")], "subtitle": []}
        self.start_tc = "01:00:00:00"
        self.playhead = "01:00:00:00"
        self.mark = {}
        self.exported = None
        self.imported_into = None
        self.imported_from = None
        self.subtitles = None
        self.scene_cuts = False
        self.graph = FakeGraph(1)
        self.voice = {}
        self.linked_calls = []
        self.dolby = None
        self._init_markers()

    @staticmethod
    def _track(name, subtype=""):
        return {"name": name, "enabled": True, "locked": False, "subtype": subtype, "items": []}

    def _all_items(self):
        return [it for tt in ("video", "audio", "subtitle") for tr in self.tracks[tt] for it in tr["items"]]

    def _append(self, info):
        mpi = info.get("mediaPoolItem")
        track_index = int(info.get("trackIndex", 1))
        media_type = info.get("mediaType")
        kinds = ["video", "audio"] if media_type is None else (["video"] if media_type == 1 else ["audio"])
        created = None
        group = _uid("link") if len(kinds) > 1 else None
        for kind in kinds:
            while len(self.tracks[kind]) < track_index:
                self.tracks[kind].append(self._track(f"{kind.title()} {len(self.tracks[kind]) + 1}"))
            track = self.tracks[kind][track_index - 1]
            s, e = info.get("startFrame", 0), info.get("endFrame")
            frames = int(mpi.GetClipProperty("Frames") or 240) if mpi else 120
            duration = (int(e) - int(s)) if e is not None else frames - int(s)  # endFrame is EXCLUSIVE (live-verified)
            record = info.get("recordFrame")
            start = int(record) if record is not None else max([it.GetEnd() for it in track["items"]] + [self.START])
            item = FakeTimelineItem(mpi.GetName() if mpi else "item", start, duration, kind, track_index, mpi, self, int(s))
            item.link_group = group
            track["items"].append(item)
            created = created or item
        return created

    def GetName(self):
        return self._name

    def SetName(self, name):
        if any(t.GetName() == name for t in self.project.timelines if t is not self):
            return False
        self._name = name
        return True

    def GetUniqueId(self):
        return self._id

    def GetStartFrame(self):
        return self.START

    def GetEndFrame(self):
        return max([it.GetEnd() for it in self._all_items()] + [self.START + 630])

    def SetStartTimecode(self, tc):
        self.start_tc = tc
        return True

    def GetStartTimecode(self):
        return self.start_tc

    def GetSetting(self, key=None):
        return dict(self.settings) if key is None else self.settings.get(key, "")

    def SetSetting(self, key, value):
        self.settings[key] = value
        return True

    # tracks
    def GetTrackCount(self, kind):
        return len(self.tracks.get(kind, []))

    def AddTrack(self, kind, options=None):
        subtype = ""
        index = None
        if isinstance(options, dict):
            subtype = options.get("audioType", "mono" if kind == "audio" else "")
            index = options.get("index")
        elif isinstance(options, str):
            subtype = options
        elif kind == "audio":
            subtype = "mono"
        track = self._track(f"{kind.title()} {len(self.tracks[kind]) + 1}", subtype)
        if index and 1 <= index <= len(self.tracks[kind]):
            self.tracks[kind].insert(index - 1, track)
        else:
            self.tracks[kind].append(track)
        return True

    def DeleteTrack(self, kind, idx):
        if not 1 <= idx <= len(self.tracks[kind]):
            return False
        del self.tracks[kind][idx - 1]
        return True

    def _tr(self, kind, idx):
        tracks = self.tracks.get(kind, [])
        return tracks[idx - 1] if 1 <= idx <= len(tracks) else None

    def GetTrackSubType(self, kind, idx):
        t = self._tr(kind, idx)
        return t["subtype"] if t and kind == "audio" else ""

    def SetTrackEnable(self, kind, idx, enabled):
        t = self._tr(kind, idx)
        if not t:
            return False
        t["enabled"] = enabled
        return True

    def GetIsTrackEnabled(self, kind, idx):
        t = self._tr(kind, idx)
        return bool(t and t["enabled"])

    def SetTrackLock(self, kind, idx, locked):
        t = self._tr(kind, idx)
        if not t:
            return False
        t["locked"] = locked
        return True

    def GetIsTrackLocked(self, kind, idx):
        t = self._tr(kind, idx)
        return bool(t and t["locked"])

    def GetTrackName(self, kind, idx):
        t = self._tr(kind, idx)
        return t["name"] if t else ""

    def SetTrackName(self, kind, idx, name):
        t = self._tr(kind, idx)
        if not t:
            return False
        t["name"] = name
        return True

    def GetItemListInTrack(self, kind, idx):
        t = self._tr(kind, idx)
        return list(t["items"]) if t else []

    def GetSelectedClips(self):
        return self._all_items()[:1]

    def DeleteClips(self, items, ripple=False):
        for tt in self.tracks.values():
            for tr in tt:
                tr["items"] = [it for it in tr["items"] if it not in items]
        self.last_ripple = ripple
        return True

    def SetClipsLinked(self, items, linked):
        self.linked_calls.append((items, linked))
        return True

    # playhead / marks
    def GetCurrentTimecode(self):
        return self.playhead

    def SetCurrentTimecode(self, tc):
        self.playhead = tc
        return True

    def GetCurrentVideoItem(self):
        items = self.tracks["video"][0]["items"]
        return items[0] if items else None

    def GetCurrentClipThumbnailImage(self):
        import base64

        return {"width": 2, "height": 1, "format": "RGB 8 bit", "data": base64.b64encode(bytes([255, 0, 0, 0, 0, 255])).decode()}

    def GetMarkInOut(self):
        return dict(self.mark)

    def SetMarkInOut(self, i, o, kind="all"):
        for k in (["video", "audio"] if kind == "all" else [kind]):
            self.mark[k] = {"in": i, "out": o}
        return True

    def ClearMarkInOut(self, kind="all"):
        for k in (["video", "audio"] if kind == "all" else [kind]):
            self.mark.pop(k, None)
        return True

    # structure
    def DuplicateTimeline(self, name=None):
        name = name or self._name + " copy"
        if any(t.GetName() == name for t in self.project.timelines):
            return None
        tl = FakeTimeline(name, self.settings["timelineFrameRate"], self.project)
        self.project.timelines.append(tl)
        return tl

    def CreateCompoundClip(self, items, info=None):
        if not items:
            return None
        name = (info or {}).get("name", "Compound Clip 1")
        first = items[0]
        item = FakeTimelineItem(name, first.start, sum(i.duration for i in items), first.track_type, first.track_index, None, self)
        self.DeleteClips(items)
        self.tracks[first.track_type][first.track_index - 1]["items"].append(item)
        return item

    def CreateFusionClip(self, items):
        item = self.CreateCompoundClip(items, {"name": "Fusion Clip 1"})
        if item:
            item.AddFusionComp()
        return item

    def ImportIntoTimeline(self, path, options=None):
        self.imported_into = (path, options)
        return path.endswith(".aaf")

    def Export(self, path, export_type, subtype=None):
        self.exported = (path, export_type, subtype)
        return True

    def _insert(self, name, kind):
        item = FakeTimelineItem(name, self.START, 150, "video", 1, None, self)
        if kind in ("fusion_title", "fusion_generator", "fusion_composition"):
            item.comps.append(FakeComp("Composition 1", with_text=(kind == "fusion_title")))
        self.tracks["video"][0]["items"].append(item)
        return item

    def InsertGeneratorIntoTimeline(self, name):
        return self._insert(name, "generator") if name else None

    def InsertFusionGeneratorIntoTimeline(self, name):
        return self._insert(name, "fusion_generator")

    def InsertFusionCompositionIntoTimeline(self):
        return self._insert("Fusion Composition", "fusion_composition")

    def InsertOFXGeneratorIntoTimeline(self, name):
        return self._insert(name, "ofx")

    def InsertTitleIntoTimeline(self, name):
        return self._insert(name, "title")

    def InsertFusionTitleIntoTimeline(self, name):
        return self._insert(name, "fusion_title") if name == "Text+" else None

    def GrabStill(self):
        still = FakeGalleryStill("grab")
        self.project.gallery.current.stills.append(still)
        return still

    def GrabAllStills(self, source):
        stills = [FakeGalleryStill(it.GetName()) for it in self.tracks["video"][0]["items"]]
        self.project.gallery.current.stills.extend(stills)
        return stills

    def CreateSubtitlesFromAudio(self, settings=None):
        self.subtitles = settings or {}
        if not self.tracks["subtitle"]:
            self.tracks["subtitle"].append(self._track("Subtitle 1"))
        return True

    def DetectSceneCuts(self):
        self.scene_cuts = True
        return True

    def ConvertTimelineToStereo(self):
        return True

    def GetNodeGraph(self):
        return self.graph

    def AnalyzeDolbyVision(self, items=None, analysisType=None):
        self.dolby = (items, analysisType)
        return True

    def GetMediaPoolItem(self):
        return FakeClip(self._name, {"Type": "Timeline", "Duration": "", "FPS": "30", "Resolution": "", "Frames": ""})

    def GetVoiceIsolationState(self, track):
        return dict(self.voice.get(track, {"isEnabled": False, "amount": 0}))

    def SetVoiceIsolationState(self, track, state):
        if not 1 <= track <= len(self.tracks["audio"]):
            return False
        self.voice[track] = dict(state)
        return True


# --------------------------------------------------------------------------
# project / project manager / resolve
# --------------------------------------------------------------------------


class FakeProject:
    def __init__(self, name="TutorBee"):
        self._name = name
        self._id = _uid("proj")
        self.gallery = FakeGallery()
        self.timelines = [FakeTimeline("R8-final-art2b", project=self)]
        self.current_timeline = self.timelines[0]
        self.settings = {"timelineFrameRate": "30", "timelineResolutionWidth": "1080", "timelineResolutionHeight": "1920", "nodeStackLayers": "1"}
        spokes, art = FakeClip("spokes.mp4"), FakeClip("art.mov")
        root = FakeFolder("Master", clips=[FakeClip("music.wav")], subfolders=[FakeFolder("R3-auto", clips=[spokes, art])])
        self.pool = FakeMediaPool(root, self)
        # seed the timeline: spokes on V1, art on V2, music on A1
        tl = self.current_timeline
        tl._append({"mediaPoolItem": spokes, "startFrame": 0, "endFrame": 240, "recordFrame": tl.START, "mediaType": 1})
        tl._append({"mediaPoolItem": art, "trackIndex": 2, "startFrame": 0, "endFrame": 60, "recordFrame": tl.START + 30, "mediaType": 1})
        tl._append({"mediaPoolItem": root.clips[0], "startFrame": 0, "endFrame": 240, "recordFrame": tl.START, "mediaType": 2})
        self.jobs = {}
        self._job_seq = 0
        self.render_presets = ["YouTube 1080p", "H.264 Master"]
        self.current_preset = None
        self.render_mode = 1
        self.fmt, self.codec = "mp4", "H264"
        self.render_settings = {}
        self.stopped = False
        self.groups = []
        self.presets = [{"Name": "Default"}, {"Name": "Vertical"}]
        self.exported_still = None
        self.fairlight_preset = None
        self.burn_in = None
        self.speech = []
        self.rendering = False

    def GetName(self):
        return self._name

    def SetName(self, name):
        self._name = name
        return True

    def GetUniqueId(self):
        return self._id

    def GetMediaPool(self):
        return self.pool

    def GetGallery(self):
        return self.gallery

    def GetTimelineCount(self):
        return len(self.timelines)

    def GetTimelineByIndex(self, i):
        return self.timelines[i - 1]

    def GetCurrentTimeline(self):
        return self.current_timeline

    def SetCurrentTimeline(self, tl):
        self.current_timeline = tl
        return True

    def GetSetting(self, key=None):
        return dict(self.settings) if key is None else self.settings.get(key, "")

    def SetSetting(self, key, value):
        self.settings[key] = value
        return True

    def GetPresetList(self):
        return list(self.presets)

    def SetPreset(self, name):
        return any(p["Name"] == name for p in self.presets)

    # render
    def GetRenderFormats(self):
        return {"MP4": "mp4", "QuickTime": "mov"}

    def GetRenderCodecs(self, fmt):
        return {"H.264": "H264"} if fmt == "mp4" else {}

    def GetCurrentRenderFormatAndCodec(self):
        return {"format": self.fmt, "codec": self.codec}

    def SetCurrentRenderFormatAndCodec(self, fmt, codec):
        if not (fmt == "mp4" and codec == "H264"):
            return False
        self.fmt, self.codec = fmt, codec
        return True

    def GetCurrentRenderMode(self):
        return self.render_mode

    def SetCurrentRenderMode(self, mode):
        self.render_mode = mode
        return True

    def GetRenderResolutions(self, fmt=None, codec=None):
        return [{"Width": 1920, "Height": 1080}, {"Width": 1080, "Height": 1920}]

    def SetRenderSettings(self, settings):
        self.render_settings.update(settings)
        return True

    def AddRenderJob(self):
        self._job_seq += 1
        job_id = f"job-{self._job_seq}"
        self.jobs[job_id] = {"JobStatus": "Ready", "CompletionPercentage": 0}
        return job_id

    def StartRendering(self, *args, **kwargs):
        # forms: (), (bool), ([ids]), ([ids], bool), (id1, id2, ...)
        if not args or isinstance(args[0], bool) or args[0] == []:
            ids = list(self.jobs)
        else:
            ids = args[0] if isinstance(args[0], list) else list(args)
        for job_id in ids:
            if job_id in self.jobs:
                self.jobs[job_id] = {"JobStatus": "Complete", "CompletionPercentage": 100}
        return True

    def StopRendering(self):
        self.stopped = True

    def IsRenderingInProgress(self):
        return self.rendering

    def GetRenderJobList(self):
        return [{"JobId": k, **v} for k, v in self.jobs.items()]

    def GetRenderJobStatus(self, job_id):
        return self.jobs.get(job_id)

    def DeleteRenderJob(self, job_id):
        return self.jobs.pop(job_id, None) is not None

    def DeleteAllRenderJobs(self):
        self.jobs.clear()
        return True

    def GetRenderPresetList(self):
        return list(self.render_presets)

    def LoadRenderPreset(self, name):
        if name not in self.render_presets:
            return False
        self.current_preset = name
        return True

    def SaveAsNewRenderPreset(self, name):
        if name in self.render_presets:
            return False
        self.render_presets.append(name)
        return True

    def DeleteRenderPreset(self, name):
        if name not in self.render_presets:
            return False
        self.render_presets.remove(name)
        return True

    def GetQuickExportRenderPresets(self):
        return ["H.264", "YouTube", "TikTok"]

    def RenderWithQuickExport(self, preset, params):
        if preset not in self.GetQuickExportRenderPresets():
            return "Unknown preset"
        return {"JobStatus": "Complete", "TimeTakenToRenderInMs": 1200}

    def RefreshLUTList(self):
        return True

    def InsertAudioToCurrentTrackAtPlayhead(self, path, start, duration):
        return True

    def LoadBurnInPreset(self, name):
        self.burn_in = name
        return True

    def ExportCurrentFrameAsStill(self, path):
        self.exported_still = path
        return True

    def GetColorGroupsList(self):
        return list(self.groups)

    def AddColorGroup(self, name):
        if any(g.name == name for g in self.groups):
            return None
        g = FakeColorGroup(name, self)
        self.groups.append(g)
        return g

    def DeleteColorGroup(self, group):
        if group not in self.groups:
            return False
        self.groups.remove(group)
        return True

    def ApplyFairlightPresetToCurrentTimeline(self, name):
        self.fairlight_preset = name
        return True

    def ResetIntellisearchAnalysis(self):
        return True

    def GenerateSpeech(self, settings, timecode=None):
        clip = FakeClip((settings.get("Filename") or "speech") + ".wav")
        self.pool.current.clips.append(clip)
        self.speech.append((settings, timecode))
        return clip


class FakeProjectManager:
    def __init__(self):
        self.projects = {"TutorBee": FakeProject("TutorBee")}
        self.current = self.projects["TutorBee"]
        self.folders = {"": ["Archive"], "Archive": []}
        self.cwd = ""
        self.db = {"DbType": "Disk", "DbName": "Local Database"}
        self.exports = []
        self.archives = []

    def GetCurrentProject(self):
        return self.current

    def GetProjectListInCurrentFolder(self):
        return list(self.projects) if self.cwd == "" else []

    def GetProjectAttributesInCurrentFolder(self):
        return {n: {"lastModifiedDate": "2026-09-16", "creationDate": "2026-09-01", "notes": "", "liveCollaborationMode": False} for n in self.projects}

    def LoadProject(self, name):
        self.current = self.projects.get(name)
        return self.current

    def CreateProject(self, name, mediaLocationPath=None):
        if name in self.projects:
            return None
        self.projects[name] = FakeProject(name)
        self.current = self.projects[name]
        return self.current

    def DeleteProject(self, name):
        if name not in self.projects or self.projects[name] is self.current:
            return False
        del self.projects[name]
        return True

    def CloseProject(self, project):
        if project is self.current:
            self.current = None
        return True

    def SaveProject(self):
        return True

    def CreateFolder(self, name):
        if name in self.folders.get(self.cwd, []):
            return False
        self.folders.setdefault(self.cwd, []).append(name)
        self.folders.setdefault(name, [])
        return True

    def DeleteFolder(self, name):
        if name not in self.folders.get(self.cwd, []):
            return False
        self.folders[self.cwd].remove(name)
        return True

    def GetFolderListInCurrentFolder(self):
        return list(self.folders.get(self.cwd, []))

    def GotoRootFolder(self):
        self.cwd = ""
        return True

    def GotoParentFolder(self):
        self.cwd = ""
        return True

    def GetCurrentFolder(self):
        return self.cwd

    def OpenFolder(self, name):
        if name not in self.folders.get(self.cwd, []):
            return False
        self.cwd = name
        return True

    def ImportProject(self, path, name=None):
        name = name or path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        return self.CreateProject(name) is not None

    def ExportProject(self, name, path, withStillsAndLUTs=True):
        if name not in self.projects:
            return False
        self.exports.append((name, path, withStillsAndLUTs))
        return True

    def ArchiveProject(self, name, path, isArchiveSrcMedia=True, isArchiveRenderCache=True, isArchiveProxyMedia=False):
        if name not in self.projects:
            return False
        self.archives.append((name, path, isArchiveSrcMedia, isArchiveRenderCache, isArchiveProxyMedia))
        return True

    def RestoreProject(self, path, name=None):
        return self.ImportProject(path, name)

    def GetCurrentDatabase(self):
        return dict(self.db)

    def GetDatabaseList(self):
        return [dict(self.db), {"DbType": "PostgreSQL", "DbName": "studio", "IpAddress": "10.0.0.5"}]

    def SetCurrentDatabase(self, info):
        self.db = dict(info)
        self.current = None
        return True


class FakeFusion:
    def __init__(self):
        self.current_comp = FakeComp("Composition 1", with_text=True)

    def GetCurrentComp(self):
        return self.current_comp


_CONSTANTS = {
    # timeline export
    **{n: i for i, n in enumerate(["EXPORT_AAF", "EXPORT_DRT", "EXPORT_EDL", "EXPORT_FCP_7_XML", "EXPORT_FCPXML_1_8", "EXPORT_FCPXML_1_9", "EXPORT_FCPXML_1_10", "EXPORT_HDR_10_PROFILE_A", "EXPORT_HDR_10_PROFILE_B", "EXPORT_TEXT_CSV", "EXPORT_TEXT_TAB", "EXPORT_DOLBY_VISION_VER_2_9", "EXPORT_DOLBY_VISION_VER_4_0", "EXPORT_DOLBY_VISION_VER_5_1", "EXPORT_OTIO", "EXPORT_ALE", "EXPORT_ALE_CDL"])},
    **{n: 100 + i for i, n in enumerate(["EXPORT_NONE", "EXPORT_AAF_NEW", "EXPORT_AAF_EXISTING", "EXPORT_CDL", "EXPORT_SDL", "EXPORT_MISSING_CLIPS"])},
    "KEYFRAME_MODE_ALL": 0, "KEYFRAME_MODE_COLOR": 1, "KEYFRAME_MODE_SIZING": 2,
    "CACHE_AUTO_ENABLED": -1, "CACHE_DISABLED": 0, "CACHE_ENABLED": 1,
    **{f"MARKER_{c}": i for i, c in enumerate(["BLUE", "CYAN", "GREEN", "YELLOW", "RED", "PINK", "PURPLE", "FUCHSIA", "ROSE", "LAVENDER", "SKY", "MINT", "LEMON", "SAND", "COCOA", "CREAM"])},
    "SUBTITLE_LANGUAGE": "SUBTITLE_LANGUAGE", "SUBTITLE_CAPTION_PRESET": "SUBTITLE_CAPTION_PRESET", "SUBTITLE_CHARS_PER_LINE": "SUBTITLE_CHARS_PER_LINE", "SUBTITLE_LINE_BREAK": "SUBTITLE_LINE_BREAK", "SUBTITLE_GAP": "SUBTITLE_GAP",
    **{f"AUTO_CAPTION_{l}": 200 + i for i, l in enumerate(["AUTO", "DANISH", "DUTCH", "ENGLISH", "FRENCH", "GERMAN", "ITALIAN", "JAPANESE", "KOREAN", "MANDARIN_SIMPLIFIED", "MANDARIN_TRADITIONAL", "NORWEGIAN", "PORTUGUESE", "RUSSIAN", "SPANISH", "SWEDISH"])},
    "AUTO_CAPTION_SUBTITLE_DEFAULT": 300, "AUTO_CAPTION_TELETEXT": 301, "AUTO_CAPTION_NETFLIX": 302, "AUTO_CAPTION_LINE_SINGLE": 310, "AUTO_CAPTION_LINE_DOUBLE": 311,
    "AUDIO_SYNC_MODE": "AUDIO_SYNC_MODE", "AUDIO_SYNC_CHANNEL_NUMBER": "AUDIO_SYNC_CHANNEL_NUMBER", "AUDIO_SYNC_RETAIN_EMBEDDED_AUDIO": "AUDIO_SYNC_RETAIN_EMBEDDED_AUDIO", "AUDIO_SYNC_RETAIN_VIDEO_METADATA": "AUDIO_SYNC_RETAIN_VIDEO_METADATA",
    "AUDIO_SYNC_WAVEFORM": 400, "AUDIO_SYNC_TIMECODE": 401, "AUDIO_SYNC_CHANNEL_AUTOMATIC": -1, "AUDIO_SYNC_CHANNEL_MIX": -2,
    "EXPORT_LUT_17PTCUBE": 500, "EXPORT_LUT_33PTCUBE": 501, "EXPORT_LUT_65PTCUBE": 502, "EXPORT_LUT_PANASONICVLUT": 503,
    "DLB_BLEND_SHOTS": 600,
}


class FakeResolve:
    def __init__(self):
        self.pm = FakeProjectManager()
        self.page = "edit"
        self.storage = FakeMediaStorage(lambda: self.pm.current.pool)
        self._fusion = FakeFusion()
        self.layouts = ["Default", "Editing"]
        self.prefs_presets = ["Default"]
        self.burn_in_presets = ["Dailies"]
        self.keyframe_mode = 0
        self.quit_called = False
        self.imported_render_preset = None
        self.exported = []
        for k, v in _CONSTANTS.items():
            setattr(self, k, v)

    def GetProductName(self):
        return "DaVinci Resolve Studio (fake)"

    def GetVersionString(self):
        return "21.0.4b.5"

    def GetVersion(self):
        return [21, 0, 4, 5, "b"]

    def GetCurrentPage(self):
        return self.page

    def OpenPage(self, page):
        self.page = page
        return True

    def GetProjectManager(self):
        return self.pm

    def GetMediaStorage(self):
        return self.storage

    def Fusion(self):
        return self._fusion

    def Quit(self):
        self.quit_called = True

    def DisableBackgroundTasksForCurrentResolveSession(self):
        return None

    # layout presets
    def GetLayoutPresetList(self):
        return list(self.layouts)

    def LoadLayoutPreset(self, name):
        return name in self.layouts

    def UpdateLayoutPreset(self, name):
        return name in self.layouts

    def ExportLayoutPreset(self, name, path):
        self.exported.append(("layout", name, path))
        return name in self.layouts

    def DeleteLayoutPreset(self, name):
        if name not in self.layouts:
            return False
        self.layouts.remove(name)
        return True

    def SaveLayoutPreset(self, name):
        self.layouts.append(name)
        return True

    def ImportLayoutPreset(self, path, name=None):
        self.layouts.append(name or path.rsplit("/", 1)[-1])
        return True

    # render / burn-in / prefs presets
    def ImportRenderPreset(self, path):
        self.imported_render_preset = path
        return True

    def ExportRenderPreset(self, name, path):
        self.exported.append(("render", name, path))
        return name in self.pm.current.render_presets

    def GetBurnInPresetList(self):
        return list(self.burn_in_presets)

    def DeleteBurnInPreset(self, name):
        if name not in self.burn_in_presets:
            return False
        self.burn_in_presets.remove(name)
        return True

    def ImportBurnInPreset(self, path):
        self.burn_in_presets.append(path.rsplit("/", 1)[-1])
        return True

    def ExportBurnInPreset(self, name, path):
        self.exported.append(("burnin", name, path))
        return name in self.burn_in_presets

    def GetUserPreferencesPresetList(self):
        return list(self.prefs_presets)

    def LoadUserPreferencesPreset(self, name):
        return name in self.prefs_presets

    def SaveUserPreferencesPreset(self, name):
        self.prefs_presets.append(name)
        return True

    def DeleteUserPreferencesPreset(self, name):
        if name not in self.prefs_presets:
            return False
        self.prefs_presets.remove(name)
        return True

    def ImportUserPreferencesPreset(self, path, name=None):
        self.prefs_presets.append(name or path.rsplit("/", 1)[-1])
        return True

    def ExportUserPreferencesPreset(self, name, path):
        self.exported.append(("prefs", name, path))
        return name in self.prefs_presets

    def GetKeyframeMode(self):
        return self.keyframe_mode

    def SetKeyframeMode(self, mode):
        self.keyframe_mode = mode
        return True

    def GetFairlightPresets(self):
        return ["Podcast", "Dialogue Cleanup"]
