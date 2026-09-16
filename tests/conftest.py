"""A minimal in-memory fake of the Resolve scripting object graph, shaped
exactly like the subset DollyGrip touches, so the API is testable without
Resolve installed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dollygrip.bridge import ResolveBridge
from dollygrip.server import Settings, create_app


class FakeClip:
    def __init__(self, name, props=None):
        self._name = name
        self._props = props or {"Duration": "00:00:10:00", "FPS": "24", "Resolution": "1080x1920", "Type": "Video"}

    def GetName(self):
        return self._name

    def GetClipProperty(self, key=None):
        return self._props if key is None else self._props.get(key)


class FakeFolder:
    def __init__(self, name, clips=None, subfolders=None):
        self._name = name
        self.clips = clips or []
        self.subfolders = subfolders or []

    def GetName(self):
        return self._name

    def GetClipList(self):
        return self.clips

    def GetSubFolderList(self):
        return self.subfolders


class FakeTimeline:
    def __init__(self, name, fps="30"):
        self._name = name
        self.settings = {"timelineFrameRate": fps}
        self.tracks = {"video": 1, "audio": 1}

    def GetName(self):
        return self._name

    def GetStartFrame(self):
        return 108000  # Resolve's classic 01:00:00:00 start

    def GetEndFrame(self):
        return 108630

    def GetSetting(self, key):
        return self.settings.get(key, "")

    def SetSetting(self, key, value):
        self.settings[key] = value
        return True

    def GetTrackCount(self, kind):
        return self.tracks.get(kind, 0)

    def AddTrack(self, kind, subtype=None):
        self.tracks[kind] = self.tracks.get(kind, 0) + 1
        return True


class FakeMediaPool:
    def __init__(self, root, project):
        self.root = root
        self.current = root
        self.project = project
        self.appended = []

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

    def ImportMedia(self, paths):
        clips = [FakeClip(p.replace("\\", "/").rsplit("/", 1)[-1]) for p in paths]
        self.current.clips.extend(clips)
        return clips

    def CreateEmptyTimeline(self, name):
        if any(t.GetName() == name for t in self.project.timelines):
            return None
        tl = FakeTimeline(name)
        self.project.timelines.append(tl)
        self.project.current_timeline = tl
        return tl

    def AppendToTimeline(self, infos):
        self.appended.extend(infos)
        return [object()] * len(infos)


class FakeProject:
    def __init__(self, name="TutorBee"):
        self._name = name
        self.timelines = [FakeTimeline("R8-final-art2b")]
        self.current_timeline = self.timelines[0]
        self.settings = {"timelineFrameRate": "30", "timelineResolutionWidth": "1080", "timelineResolutionHeight": "1920"}
        root = FakeFolder("Master", subfolders=[FakeFolder("R3-auto", clips=[FakeClip("spokes.mp4"), FakeClip("art.mov")])])
        self.pool = FakeMediaPool(root, self)
        self.jobs = {}
        self._job_seq = 0

    def GetName(self):
        return self._name

    def GetMediaPool(self):
        return self.pool

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
        return self.settings if key is None else self.settings.get(key, "")

    def SetSetting(self, key, value):
        self.settings[key] = value
        return True

    def GetRenderFormats(self):
        return {"MP4": "mp4", "QuickTime": "mov"}

    def GetRenderCodecs(self, fmt):
        return {"H.264": "H264"} if fmt == "mp4" else {}

    def SetCurrentRenderFormatAndCodec(self, fmt, codec):
        return fmt == "mp4" and codec == "H264"

    def SetRenderSettings(self, settings):
        self.render_settings = settings
        return True

    def AddRenderJob(self):
        self._job_seq += 1
        job_id = f"job-{self._job_seq}"
        self.jobs[job_id] = {"JobStatus": "Ready", "CompletionPercentage": 0}
        return job_id

    def StartRendering(self, job_id):
        self.jobs[job_id]["JobStatus"] = "Complete"
        self.jobs[job_id]["CompletionPercentage"] = 100
        return True

    def IsRenderingInProgress(self):
        return False

    def GetRenderJobList(self):
        return [{"JobId": k, **v} for k, v in self.jobs.items()]

    def GetRenderJobStatus(self, job_id):
        return self.jobs.get(job_id)

    def DeleteRenderJob(self, job_id):
        return self.jobs.pop(job_id, None) is not None


class FakeProjectManager:
    def __init__(self):
        self.projects = {"TutorBee": FakeProject("TutorBee")}
        self.current = self.projects["TutorBee"]

    def GetCurrentProject(self):
        return self.current

    def GetProjectListInCurrentFolder(self):
        return list(self.projects)

    def LoadProject(self, name):
        self.current = self.projects.get(name)
        return self.current

    def SaveProject(self):
        return True


class FakeResolve:
    def __init__(self):
        self.pm = FakeProjectManager()
        self.page = "edit"

    def GetProductName(self):
        return "DaVinci Resolve Studio (fake)"

    def GetVersionString(self):
        return "0.0.0"

    def GetCurrentPage(self):
        return self.page

    def OpenPage(self, page):
        self.page = page
        return True

    def GetProjectManager(self):
        return self.pm


@pytest.fixture
def fake_resolve():
    return FakeResolve()


def make_client(fake, **settings_kwargs):
    bridge = ResolveBridge(connector=lambda: fake)
    app = create_app(Settings(**settings_kwargs), bridge=bridge)
    return TestClient(app)


@pytest.fixture
def client(fake_resolve):
    return make_client(fake_resolve)
