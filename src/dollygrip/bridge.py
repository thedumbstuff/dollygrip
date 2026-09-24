"""The bridge: one cached, lock-guarded connection to the running Resolve.

The fusionscript handle is a live object into another process; it goes stale
when Resolve restarts and it is not documented as thread-safe. So:

- every request runs under `bridge.lock` (a FastAPI dependency serializes
  access - see server.py), and
- every access goes through `ensure()`, which probes the cached handle and
  transparently reconnects once if Resolve was restarted.

It also owns the object-addressing helpers: HTTP clients cannot hold Resolve
object handles, so timeline items are addressed by their `GetUniqueId()`,
media pool clips by unique id OR name, timelines by name, bins by path.
"""

from __future__ import annotations

import threading
from typing import Callable, Iterator, Optional, Tuple

from . import discovery

TRACK_TYPES = ("video", "audio", "subtitle")


class ResolveUnavailable(RuntimeError):
    """Resolve is not running / not reachable (surfaces as HTTP 503)."""


class NothingOpen(RuntimeError):
    """No project or timeline is open for the requested operation (HTTP 409)."""


class NotFound(RuntimeError):
    """A named project/clip/timeline/job was not found (HTTP 404)."""


class Rejected(RuntimeError):
    """Resolve accepted the call but returned a failure (HTTP 422)."""


class ResolveBridge:
    def __init__(self, connector: Optional[Callable] = None):
        # `connector` is injectable so tests can hand in a fake Resolve.
        self._connector = connector or discovery.connect_to_resolve
        self._resolve = None
        # Re-entrant: the render "wait" endpoint re-acquires between polls.
        self.lock = threading.RLock()

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

    def const(self, name: str):
        """A `resolve.SOME_CONSTANT` enum value (EXPORT_AAF, MARKER_BLUE, ...)."""
        value = getattr(self.ensure(), name, None)
        if value is None:
            raise NotFound(f"This Resolve build has no constant {name!r}")
        return value

    # -- common object graph helpers --------------------------------------

    def project_manager(self):
        pm = self.ensure().GetProjectManager()
        if pm is None:
            raise ResolveUnavailable("GetProjectManager() returned nothing")
        return pm

    def media_storage(self):
        ms = self.ensure().GetMediaStorage()
        if ms is None:
            raise ResolveUnavailable("GetMediaStorage() returned nothing")
        return ms

    def fusion(self):
        fu = self.ensure().Fusion()
        if fu is None:
            raise ResolveUnavailable("Fusion() returned nothing")
        return fu

    def current_project(self):
        project = self.project_manager().GetCurrentProject()
        if project is None:
            raise NothingOpen("No project is open in Resolve")
        return project

    def media_pool(self):
        return self.current_project().GetMediaPool()

    def gallery(self):
        gallery = self.current_project().GetGallery()
        if gallery is None:
            raise NothingOpen("The project has no gallery (is a project open?)")
        return gallery

    def current_timeline(self):
        timeline = self.current_project().GetCurrentTimeline()
        if timeline is None:
            raise NothingOpen("No timeline is open in the current project")
        return timeline

    def timelines(self) -> Iterator:
        project = self.current_project()
        for i in range(1, int(project.GetTimelineCount() or 0) + 1):
            tl = project.GetTimelineByIndex(i)
            if tl:
                yield tl

    def timeline_by_name(self, name: str):
        """Timeline by name (or unique id); 'current' is the open one."""
        if name == "current":
            return self.current_timeline()
        for tl in self.timelines():
            if tl.GetName() == name or _safe(tl.GetUniqueId) == name:
                return tl
        raise NotFound(f"Timeline {name!r} not found in project {self.current_project().GetName()!r}")

    # -- media pool ------------------------------------------------------

    def walk_folders(self, folder=None, depth: int = 0, max_depth: int = 12) -> Iterator:
        """Depth-first walk of the bin tree from `folder` (default root)."""
        folder = folder or self.media_pool().GetRootFolder()
        yield folder
        if depth < max_depth:
            for sub in folder.GetSubFolderList() or []:
                yield from self.walk_folders(sub, depth + 1, max_depth)

    def folder_by_path(self, path: str, create: bool = False):
        """Walk (optionally creating) a bin path like 'Reels/R8-assets' from root."""
        mp = self.media_pool()
        folder = mp.GetRootFolder()
        for part in [p for p in path.replace("\\", "/").split("/") if p]:
            nxt = next((f for f in folder.GetSubFolderList() or [] if f.GetName() == part), None)
            if nxt is None:
                if not create:
                    raise NotFound(f"Bin {part!r} not found under {folder.GetName()!r}")
                nxt = mp.AddSubFolder(folder, part)
                if not nxt:
                    raise Rejected(f"Could not create bin {part!r} under {folder.GetName()!r}")
            folder = nxt
        return folder

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

    def clip(self, ref: str):
        """Resolve a clip reference: name in the current bin, else unique id or
        name anywhere in the media pool (first match, depth-first)."""
        current = self.media_pool().GetCurrentFolder()
        for c in current.GetClipList() or []:
            if c.GetName() == ref:
                return c
        for folder in self.walk_folders():
            for c in folder.GetClipList() or []:
                if _safe(c.GetUniqueId) == ref or _safe(c.GetMediaId) == ref or c.GetName() == ref:
                    return c
        raise NotFound(f"Clip {ref!r} not found anywhere in the media pool (tried name, unique id, media id)")

    def clips(self, refs) -> list:
        return [self.clip(r) for r in refs]

    # -- timeline items --------------------------------------------------

    def iter_items(
        self, tl=None, track_type: Optional[str] = None, track_index: Optional[int] = None
    ) -> Iterator[Tuple[str, int, object]]:
        """Yield (track_type, track_index, item) across the timeline's tracks."""
        tl = tl or self.current_timeline()
        for tt in ([track_type] if track_type else TRACK_TYPES):
            count = int(tl.GetTrackCount(tt) or 0)
            for idx in range(1, count + 1):
                if track_index is not None and idx != track_index:
                    continue
                for item in tl.GetItemListInTrack(tt, idx) or []:
                    yield tt, idx, item

    def item(self, ref: str, tl=None):
        """Timeline item by unique id; 'current' = the item under the playhead."""
        tl = tl or self.current_timeline()
        if ref == "current":
            item = tl.GetCurrentVideoItem()
            if item is None:
                raise NotFound("No video item under the playhead")
            return item
        for _, _, item in self.iter_items(tl):
            if _safe(item.GetUniqueId) == ref:
                return item
        raise NotFound(
            f"Timeline item {ref!r} not found on timeline {tl.GetName()!r} "
            "(ids come from GET /timelines/current/items)"
        )

    def items(self, refs, tl=None) -> list:
        tl = tl or self.current_timeline()
        return [self.item(r, tl) for r in refs]

    def located_item(self, ref: str, tl=None):
        """(track_type, track_index, item) for an item id."""
        tl = tl or self.current_timeline()
        for tt, idx, item in self.iter_items(tl):
            if _safe(item.GetUniqueId) == ref:
                return tt, idx, item
        raise NotFound(f"Timeline item {ref!r} not found on timeline {tl.GetName()!r}")

    # -- fusion ----------------------------------------------------------

    def fusion_comp(self, item, comp: Optional[str] = None):
        """A Fusion composition on a timeline item, by name or 1-based index
        (default: the first)."""
        count = int(item.GetFusionCompCount() or 0)
        if count == 0:
            raise NotFound("This timeline item has no Fusion composition (POST .../fusion/comps to add one)")
        if comp is None or comp == "1":
            found = item.GetFusionCompByIndex(1)
        elif comp.isdigit():
            found = item.GetFusionCompByIndex(int(comp)) if 1 <= int(comp) <= count else None
        else:
            found = item.GetFusionCompByName(comp)
        if not found:
            raise NotFound(f"Fusion composition {comp!r} not found (have {item.GetFusionCompNameList()})")
        return found

    # -- color -----------------------------------------------------------

    def color_group(self, name: str):
        for g in self.current_project().GetColorGroupsList() or []:
            if g.GetName() == name:
                return g
        raise NotFound(f"Color group {name!r} not found")

    def gallery_album(self, ref: str, kind: str = "still"):
        """Gallery album by name or 1-based index; 'current' = the active album."""
        gallery = self.gallery()
        if ref == "current":
            album = gallery.GetCurrentStillAlbum()
            if album is None:
                raise NotFound("No current gallery album")
            return album
        albums = (
            gallery.GetGalleryPowerGradeAlbums() if kind == "powergrade" else gallery.GetGalleryStillAlbums()
        ) or []
        if ref.isdigit() and 1 <= int(ref) <= len(albums):
            return albums[int(ref) - 1]
        for album in albums:
            if gallery.GetAlbumName(album) == ref:
                return album
        raise NotFound(f"Gallery {kind} album {ref!r} not found")


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def require(ok, message: str):
    """Turn Resolve's bare False into a 422 with a reason."""
    if not ok:
        raise Rejected(message)
    return ok
