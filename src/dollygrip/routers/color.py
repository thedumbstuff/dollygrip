"""Color page: versions, CDL, LUT export, node graphs (clip / timeline /
group pre+post), DRX grade apply, color groups, gallery albums & stills,
keyframe mode, frame export."""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, Query

from ..bridge import NotFound, ResolveBridge, require
from ..deps import resolve_session
from ..schemas import (
    AddVersion,
    AlbumCreate,
    AlbumRename,
    ApplyDRX,
    CDL,
    ColorGroupName,
    CopyGrades,
    ExportFrame,
    ExportLUT,
    ExportStills,
    ItemIds,
    KeyframeMode,
    NodeCache,
    NodeEnabled,
    NodeLUT,
    RenameVersion,
    StillIndices,
    StillLabel,
    StillPaths,
    VersionType,
)
from ..serialize import item_summary, safe

router = APIRouter(prefix="/color", tags=["color"])

_VERSION = {"local": 0, "remote": 1}
_CACHE = {"auto": -1, "off": 0, "on": 1}
_CACHE_NAMES = {-1: "auto", 0: "off", 1: "on"}
_DRX_MODE = {"no_keyframes": 0, "source_timecode_aligned": 1, "start_frames_aligned": 2}
_KEYFRAME = {"all": 0, "color": 1, "sizing": 2}
_KEYFRAME_NAMES = {0: "all", 1: "color", 2: "sizing"}


# -- versions -----------------------------------------------------------------------


@router.get("/items/{item_id}/versions")
def list_versions(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    return {
        "current": item.GetCurrentVersion(),
        "local": item.GetVersionNameList(0) or [],
        "remote": item.GetVersionNameList(1) or [],
    }


@router.post("/items/{item_id}/versions")
def add_version(item_id: str, body: AddVersion, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    require(item.AddVersion(body.name, _VERSION[body.type]), f"Could not add {body.type} version {body.name!r} (name taken?)")
    return {"ok": True, "current": item.GetCurrentVersion()}


@router.post("/items/{item_id}/versions/{name}/load")
def load_version(item_id: str, name: str, type: VersionType = Query(default="local"), bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    require(item.LoadVersionByName(name, _VERSION[type]), f"{type} version {name!r} not found")
    return {"ok": True, "current": item.GetCurrentVersion()}


@router.patch("/items/{item_id}/versions/{name}")
def rename_version(item_id: str, name: str, body: RenameVersion, bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    require(item.RenameVersionByName(name, body.new_name, _VERSION[body.type]), f"{body.type} version {name!r} not found")
    return {"ok": True}


@router.delete("/items/{item_id}/versions/{name}")
def delete_version(item_id: str, name: str, type: VersionType = Query(default="local"), bridge: ResolveBridge = Depends(resolve_session)):
    item = bridge.item(item_id)
    require(item.DeleteVersionByName(name, _VERSION[type]), f"{type} version {name!r} not found")
    return {"ok": True}


# -- grades ----------------------------------------------------------------------------


@router.put("/items/{item_id}/cdl")
def set_cdl(item_id: str, body: CDL, bridge: ResolveBridge = Depends(resolve_session)):
    """ASC CDL on one node (slope/offset/power as 'r g b', saturation scalar)."""
    item = bridge.item(item_id)
    cdl = {"NodeIndex": str(body.node_index), "Slope": body.slope, "Offset": body.offset, "Power": body.power, "Saturation": body.saturation}
    require(item.SetCDL(cdl), "Resolve refused the CDL (node index in range?)")
    return {"ok": True, "cdl": cdl}


@router.post("/items/{item_id}/copy-grades")
def copy_grades(item_id: str, body: CopyGrades, bridge: ResolveBridge = Depends(resolve_session)):
    """Copy this clip's current node-stack layer grade onto other clips."""
    tl = bridge.current_timeline()
    item = bridge.item(item_id, tl)
    targets = bridge.items(body.target_item_ids, tl)
    require(item.CopyGrades(targets), "Resolve refused to copy grades")
    return {"ok": True, "copied_to": len(targets)}


@router.post("/items/{item_id}/lut/export")
def export_lut(item_id: str, body: ExportLUT, bridge: ResolveBridge = Depends(resolve_session)):
    """Bake the clip's grade to a .cube (17/33/65) or Panasonic .vlt."""
    item = bridge.item(item_id)
    const = {"17": "EXPORT_LUT_17PTCUBE", "33": "EXPORT_LUT_33PTCUBE", "65": "EXPORT_LUT_65PTCUBE", "panasonic_vlut": "EXPORT_LUT_PANASONICVLUT"}[body.size]
    require(item.ExportLUT(bridge.const(const), body.path), f"Resolve refused to export the LUT to {body.path!r}")
    return {"ok": True, "path": body.path}


@router.post("/items/{item_id}/reset-node-colors")
def reset_node_colors(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.item(item_id).ResetAllNodeColors())}


# -- node graphs (clip, timeline, group pre/post) --------------------------------------------


def _graph_summary(graph) -> dict:
    n = int(safe(graph.GetNumNodes, default=0) or 0)
    nodes = []
    for i in range(1, n + 1):
        nodes.append(
            {
                "index": i,
                "label": safe(graph.GetNodeLabel, i),
                "lut": safe(graph.GetLUT, i),
                "cache_mode": _CACHE_NAMES.get(safe(graph.GetNodeCacheMode, i)),
                "tools": safe(graph.GetToolsInNode, i, default=[]),
            }
        )
    return {"num_nodes": n, "nodes": nodes}


def mount_graph(prefix: str, resolver: Callable, scope: str) -> None:
    """Identical node-graph routes for each graph owner."""
    from .markers import _with_path_params

    def _get(bridge: ResolveBridge = Depends(resolve_session), **p):
        return _graph_summary(resolver(bridge, **p))

    def _lut(node: int, body: NodeLUT, bridge: ResolveBridge = Depends(resolve_session), **p):
        g = resolver(bridge, **p)
        require(g.SetLUT(node, body.path), f"Resolve refused LUT {body.path!r} on node {node} (in the LUT list? node exists?)")
        return {"ok": True, "node": node, "lut": g.GetLUT(node)}

    def _cache(node: int, body: NodeCache, bridge: ResolveBridge = Depends(resolve_session), **p):
        g = resolver(bridge, **p)
        require(g.SetNodeCacheMode(node, _CACHE[body.mode]), f"No node {node}")
        return {"ok": True, "node": node, "cache_mode": body.mode}

    def _enabled(node: int, body: NodeEnabled, bridge: ResolveBridge = Depends(resolve_session), **p):
        g = resolver(bridge, **p)
        require(g.SetNodeEnabled(node, body.enabled), f"No node {node}")
        return {"ok": True, "node": node, "enabled": body.enabled}

    def _drx(body: ApplyDRX, bridge: ResolveBridge = Depends(resolve_session), **p):
        g = resolver(bridge, **p)
        require(g.ApplyGradeFromDRX(body.path, _DRX_MODE[body.mode]), f"Resolve refused to apply {body.path!r}")
        return {"ok": True}

    def _arri(bridge: ResolveBridge = Depends(resolve_session), **p):
        return {"ok": bool(resolver(bridge, **p).ApplyArriCdlLut())}

    def _reset(bridge: ResolveBridge = Depends(resolve_session), **p):
        return {"ok": bool(resolver(bridge, **p).ResetAllGrades())}

    for fn, method, path, name in (
        (_get, "GET", "", f"get_graph_{scope}"),
        (_lut, "PUT", "/nodes/{node}/lut", f"set_node_lut_{scope}"),
        (_cache, "PUT", "/nodes/{node}/cache", f"set_node_cache_{scope}"),
        (_enabled, "PUT", "/nodes/{node}/enabled", f"set_node_enabled_{scope}"),
        (_drx, "POST", "/drx", f"apply_drx_{scope}"),
        (_arri, "POST", "/arri-cdl-lut", f"apply_arri_cdl_lut_{scope}"),
        (_reset, "POST", "/reset", f"reset_grades_{scope}"),
    ):
        router.add_api_route(prefix + path, _with_path_params(fn, prefix), methods=[method], name=name, summary=name.replace("_", " "))


def _clip_graph(bridge: ResolveBridge, item_id: str, layer: int = 1):
    item = bridge.item(item_id)
    graph = item.GetNodeGraph(layer) if layer != 1 else item.GetNodeGraph()
    if graph is None:
        raise NotFound(f"No node graph at layer {layer}")
    return graph


mount_graph("/items/{item_id}/graph", _clip_graph, "clip")
mount_graph("/timeline/graph", lambda bridge: bridge.current_timeline().GetNodeGraph(), "timeline")
mount_graph("/groups/{name}/pre-graph", lambda bridge, name: bridge.color_group(name).GetPreClipNodeGraph(), "group_pre")
mount_graph("/groups/{name}/post-graph", lambda bridge, name: bridge.color_group(name).GetPostClipNodeGraph(), "group_post")


@router.get("/items/{item_id}/graph/layers/{layer}")
def get_graph_layer(item_id: str, layer: int, bridge: ResolveBridge = Depends(resolve_session)):
    """Node graph of a specific node-stack layer (1 <= layer <= nodeStackLayers)."""
    return _graph_summary(_clip_graph(bridge, item_id, layer))


# -- color groups -------------------------------------------------------------------------------


@router.get("/groups")
def list_color_groups(bridge: ResolveBridge = Depends(resolve_session)):
    return {"groups": [g.GetName() for g in bridge.current_project().GetColorGroupsList() or []]}


@router.post("/groups")
def add_color_group(body: ColorGroupName, bridge: ResolveBridge = Depends(resolve_session)):
    group = bridge.current_project().AddColorGroup(body.name)
    if not group:
        raise NotFound(f"Could not create color group {body.name!r} (name taken?)")
    return {"ok": True, "name": group.GetName()}


@router.patch("/groups/{name}")
def rename_color_group(name: str, body: ColorGroupName, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.color_group(name).SetName(body.name), f"Could not rename group {name!r}")
    return {"ok": True, "name": body.name}


@router.delete("/groups/{name}")
def delete_color_group(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    group = bridge.color_group(name)
    return {"ok": bool(bridge.current_project().DeleteColorGroup(group))}


@router.get("/groups/{name}/clips")
def color_group_clips(name: str, bridge: ResolveBridge = Depends(resolve_session)):
    tl = bridge.current_timeline()
    start = int(tl.GetStartFrame())
    items = bridge.color_group(name).GetClipsInTimeline(tl) or []
    return {"items": [item_summary(*(safe(i.GetTrackTypeAndIndex, default=[None, None]) or [None, None]), i, start) for i in items]}


@router.post("/groups/{name}/clips")
def assign_to_color_group(name: str, body: ItemIds, bridge: ResolveBridge = Depends(resolve_session)):
    group = bridge.color_group(name)
    tl = bridge.current_timeline()
    results = {i: bool(bridge.item(i, tl).AssignToColorGroup(group)) for i in body.item_ids}
    return {"results": results}


@router.delete("/items/{item_id}/group")
def remove_from_color_group(item_id: str, bridge: ResolveBridge = Depends(resolve_session)):
    return {"ok": bool(bridge.item(item_id).RemoveFromColorGroup())}


# -- gallery ----------------------------------------------------------------------------------------


def _album_summary(gallery, album, kind: str, index: int) -> dict:
    return {"index": index, "name": gallery.GetAlbumName(album), "kind": kind, "still_count": len(album.GetStills() or [])}


@router.get("/gallery/albums")
def list_albums(bridge: ResolveBridge = Depends(resolve_session)):
    gallery = bridge.gallery()
    current = gallery.GetCurrentStillAlbum()
    stills = [_album_summary(gallery, a, "still", i) for i, a in enumerate(gallery.GetGalleryStillAlbums() or [], start=1)]
    pgs = [_album_summary(gallery, a, "powergrade", i) for i, a in enumerate(gallery.GetGalleryPowerGradeAlbums() or [], start=1)]
    return {"current": gallery.GetAlbumName(current) if current else None, "still_albums": stills, "powergrade_albums": pgs}


@router.post("/gallery/albums")
def create_album(body: AlbumCreate, bridge: ResolveBridge = Depends(resolve_session)):
    gallery = bridge.gallery()
    album = gallery.CreateGalleryPowerGradeAlbum() if body.kind == "powergrade" else gallery.CreateGalleryStillAlbum()
    if not album:
        raise NotFound("Resolve could not create the album")
    if body.name:
        gallery.SetAlbumName(album, body.name)
    return {"ok": True, "name": gallery.GetAlbumName(album), "kind": body.kind}


@router.patch("/gallery/albums/{ref}")
def rename_album(ref: str, body: AlbumRename, kind: str = Query(default="still"), bridge: ResolveBridge = Depends(resolve_session)):
    gallery = bridge.gallery()
    album = bridge.gallery_album(ref, kind)
    require(gallery.SetAlbumName(album, body.name), "Resolve refused the album name")
    return {"ok": True, "name": body.name}


@router.post("/gallery/albums/{ref}/current")
def set_current_album(ref: str, kind: str = Query(default="still"), bridge: ResolveBridge = Depends(resolve_session)):
    gallery = bridge.gallery()
    album = bridge.gallery_album(ref, kind)
    require(gallery.SetCurrentStillAlbum(album), "Resolve refused to switch album")
    return {"ok": True, "current": gallery.GetAlbumName(album)}


@router.get("/gallery/albums/{ref}/stills")
def list_stills(ref: str, kind: str = Query(default="still"), bridge: ResolveBridge = Depends(resolve_session)):
    album = bridge.gallery_album(ref, kind)
    return {"stills": [{"index": i, "label": album.GetLabel(s)} for i, s in enumerate(album.GetStills() or [], start=1)]}


@router.post("/gallery/albums/{ref}/stills/import")
def import_stills(ref: str, body: StillPaths, kind: str = Query(default="still"), bridge: ResolveBridge = Depends(resolve_session)):
    album = bridge.gallery_album(ref, kind)
    require(album.ImportStills(list(body.paths)), "Resolve imported none of the stills")
    return {"ok": True, "still_count": len(album.GetStills() or [])}


@router.post("/gallery/albums/{ref}/stills/export")
def export_stills(ref: str, body: ExportStills, kind: str = Query(default="still"), bridge: ResolveBridge = Depends(resolve_session)):
    """Export stills as images or .drx grade files (format 'drx' = the grade itself)."""
    album = bridge.gallery_album(ref, kind)
    stills = album.GetStills() or []
    chosen = _pick(stills, body.indices)
    require(album.ExportStills(chosen, body.folder, body.prefix, body.format), "Resolve refused to export the stills")
    return {"ok": True, "exported": len(chosen), "folder": body.folder}


@router.post("/gallery/albums/{ref}/stills/delete")
def delete_stills(ref: str, body: StillIndices, kind: str = Query(default="still"), bridge: ResolveBridge = Depends(resolve_session)):
    album = bridge.gallery_album(ref, kind)
    chosen = _pick(album.GetStills() or [], body.indices)
    require(album.DeleteStills(chosen), "Resolve refused to delete the stills")
    return {"ok": True, "still_count": len(album.GetStills() or [])}


@router.patch("/gallery/albums/{ref}/stills/{index}")
def label_still(ref: str, index: int, body: StillLabel, kind: str = Query(default="still"), bridge: ResolveBridge = Depends(resolve_session)):
    album = bridge.gallery_album(ref, kind)
    still = _pick(album.GetStills() or [], [index])[0]
    require(album.SetLabel(still, body.label), "Resolve refused the label")
    return {"ok": True, "index": index, "label": album.GetLabel(still)}


def _pick(stills: list, indices):
    if not indices:
        return list(stills)
    out = []
    for i in indices:
        if not 1 <= i <= len(stills):
            raise NotFound(f"No still {i} (album has {len(stills)})")
        out.append(stills[i - 1])
    return out


# -- misc ------------------------------------------------------------------------------------------


@router.post("/export-frame")
def export_current_frame(body: ExportFrame, bridge: ResolveBridge = Depends(resolve_session)):
    """Export the frame under the playhead as an image (path extension picks the format)."""
    require(bridge.current_project().ExportCurrentFrameAsStill(body.path), f"Resolve refused to export a still to {body.path!r}")
    return {"ok": True, "path": body.path}


@router.get("/keyframe-mode")
def keyframe_mode(bridge: ResolveBridge = Depends(resolve_session)):
    return {"mode": _KEYFRAME_NAMES.get(bridge.ensure().GetKeyframeMode())}


@router.put("/keyframe-mode")
def set_keyframe_mode(body: KeyframeMode, bridge: ResolveBridge = Depends(resolve_session)):
    require(bridge.ensure().SetKeyframeMode(_KEYFRAME[body.mode]), "Resolve refused the keyframe mode")
    return {"mode": body.mode}
