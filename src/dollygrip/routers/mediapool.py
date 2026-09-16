from __future__ import annotations

from fastapi import APIRouter, Depends

from ..bridge import NotFound, ResolveBridge
from ..deps import resolve_session
from ..schemas import ImportMedia, SetFolder

router = APIRouter(prefix="/mediapool", tags=["mediapool"])

_MAX_DEPTH = 6


def _tree(folder, depth: int = 0):
    node = {"name": folder.GetName(), "clip_count": len(folder.GetClipList() or [])}
    if depth < _MAX_DEPTH:
        node["folders"] = [_tree(f, depth + 1) for f in folder.GetSubFolderList() or []]
    return node


@router.get("/folders")
def folder_tree(bridge: ResolveBridge = Depends(resolve_session)):
    mp = bridge.media_pool()
    return {
        "root": _tree(mp.GetRootFolder()),
        "current": mp.GetCurrentFolder().GetName(),
    }


@router.post("/folders")
def set_current_folder(body: SetFolder, bridge: ResolveBridge = Depends(resolve_session)):
    """Walk (and optionally create) a bin path from the root, set it current."""
    mp = bridge.media_pool()
    folder = mp.GetRootFolder()
    for part in [p for p in body.path.replace("\\", "/").split("/") if p]:
        nxt = next((f for f in folder.GetSubFolderList() or [] if f.GetName() == part), None)
        if nxt is None:
            if not body.create:
                raise NotFound(f"Bin {part!r} not found under {folder.GetName()!r}")
            nxt = mp.AddSubFolder(folder, part)
            if not nxt:
                raise NotFound(f"Could not create bin {part!r} under {folder.GetName()!r}")
        folder = nxt
    mp.SetCurrentFolder(folder)
    return {"ok": True, "current": folder.GetName()}


@router.get("/clips")
def list_clips(bridge: ResolveBridge = Depends(resolve_session)):
    folder = bridge.media_pool().GetCurrentFolder()
    clips = []
    for clip in folder.GetClipList() or []:
        props = clip.GetClipProperty() or {}
        clips.append(
            {
                "name": clip.GetName(),
                "duration": props.get("Duration"),
                "fps": props.get("FPS"),
                "resolution": props.get("Resolution"),
                "type": props.get("Type"),
            }
        )
    return {"bin": folder.GetName(), "clips": clips}


@router.post("/import")
def import_media(body: ImportMedia, bridge: ResolveBridge = Depends(resolve_session)):
    """Import files into the CURRENT bin. Paths are as seen by the Resolve machine."""
    items = bridge.media_pool().ImportMedia(body.paths) or []
    return {"imported": [c.GetName() for c in items], "requested": len(body.paths)}
