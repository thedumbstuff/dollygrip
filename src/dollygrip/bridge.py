"""The bridge: one cached, lock-guarded connection to the running Resolve.

The fusionscript handle is a live object into another process; it goes stale
when Resolve restarts and it is not documented as thread-safe. So:

- every request runs under `bridge.lock` (a FastAPI dependency serializes
  access - see server.py), and
- every access goes through `ensure()`, which probes the cached handle and
  transparently reconnects once if Resolve was restarted.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from . import discovery


class ResolveUnavailable(RuntimeError):
    """Resolve is not running / not reachable (surfaces as HTTP 503)."""


class NothingOpen(RuntimeError):
    """No project or timeline is open for the requested operation (HTTP 409)."""


class NotFound(RuntimeError):
    """A named project/clip/timeline/job was not found (HTTP 404)."""


class ResolveBridge:
    def __init__(self, connector: Optional[Callable] = None):
        # `connector` is injectable so tests can hand in a fake Resolve.
        self._connector = connector or discovery.connect_to_resolve
        self._resolve = None
        self.lock = threading.Lock()

    # -- connection -------------------------------------------------------

    def ensure(self):
        """Return a live resolve handle, reconnecting once if it went stale."""
        if self._resolve is not None:
            try:
                self._resolve.GetProductName()
                return self._resolve
            except Exception:
                self._resolve = None  # stale (Resolve restarted) - reconnect
        try:
            self._resolve = self._connector()
        except Exception as e:
            raise ResolveUnavailable(str(e)) from e
        if self._resolve is None:
            raise ResolveUnavailable("scriptapp('Resolve') returned nothing - is Resolve running?")
        return self._resolve

    @property
    def connected(self) -> bool:
        try:
            self.ensure()
            return True
        except ResolveUnavailable:
            return False

    # -- common object graph helpers --------------------------------------

    def project_manager(self):
        pm = self.ensure().GetProjectManager()
        if pm is None:
            raise ResolveUnavailable("GetProjectManager() returned nothing")
        return pm

    def current_project(self):
        project = self.project_manager().GetCurrentProject()
        if project is None:
            raise NothingOpen("No project is open in Resolve")
        return project

    def media_pool(self):
        return self.current_project().GetMediaPool()

    def current_timeline(self):
        timeline = self.current_project().GetCurrentTimeline()
        if timeline is None:
            raise NothingOpen("No timeline is open in the current project")
        return timeline

    def timeline_by_name(self, name: str):
        project = self.current_project()
        for i in range(1, int(project.GetTimelineCount()) + 1):
            tl = project.GetTimelineByIndex(i)
            if tl and tl.GetName() == name:
                return tl
        raise NotFound(f"Timeline {name!r} not found in project {project.GetName()!r}")

    def clip_by_name(self, name: str):
        """Find a media pool clip by name in the CURRENT bin (folder)."""
        folder = self.media_pool().GetCurrentFolder()
        for clip in folder.GetClipList() or []:
            if clip.GetName() == name:
                return clip
        raise NotFound(
            f"Clip {name!r} not found in the current bin {folder.GetName()!r}. "
            "Set the bin first (POST /api/v1/mediapool/folders) or import the file."
        )
