"""Official Blender Lab parity helpers for diagnostics, navigation, and render evidence."""

from __future__ import annotations

import base64
import glob
import json
import os
import time
import uuid

import bpy

from . import autosave, inspection_render, playblast_capture, render_jobs, script_runner, viewport_capture


LATEST_RENDER_THUMBNAIL_URI = "blender://render-thumbnails/latest"
LATEST_RENDER_THUMBNAIL_METADATA_URI = "blender://render-thumbnails/latest/metadata"
MAX_BLOCKING_THUMBNAIL_PIXELS = 1280 * 720
METADATA_FILENAME = "metadata.json"
THUMBNAIL_FILENAME = "thumbnail.png"


DATA_COLLECTION_NAMES = (
    "actions",
    "armatures",
    "cameras",
    "collections",
    "curves",
    "fonts",
    "grease_pencils",
    "images",
    "lattices",
    "libraries",
    "lights",
    "materials",
    "meshes",
    "movieclips",
    "node_groups",
    "objects",
    "scenes",
    "sounds",
    "texts",
    "textures",
    "volumes",
    "worlds",
    "workspaces",
)


def _thumbnail_sample_count(scene):
    engine = str(getattr(scene.render, "engine", "") or "")
    if engine == "CYCLES":
        return int(getattr(getattr(scene, "cycles", None), "samples", 64) or 64)
    return int(getattr(getattr(scene, "eevee", None), "taa_render_samples", 64) or 64)

EXTERNAL_FILE_COLLECTION_NAMES = (
    "images",
    "movieclips",
    "sounds",
    "fonts",
    "volumes",
)


def _safe_id(value, fallback="item"):
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in str(value or ""))
    safe = safe.strip("._")
    return safe[:80] or fallback


def _thumbnail_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _resource_uri(thumbnail_id):
    return f"blender://render-thumbnails/{_safe_id(thumbnail_id)}"


def _metadata_uri(thumbnail_id):
    return f"blender://render-thumbnails/{_safe_id(thumbnail_id)}/metadata"


def _render_root_info(context=None, *, preferred_dir=None, create=False):
    capture_info = viewport_capture.resolve_capture_dir(context, preferred_dir=preferred_dir, create=create)
    root = os.path.join(capture_info["capture_dir"], "render-thumbnails")
    if create:
        os.makedirs(root, exist_ok=True)
    return {**capture_info, "render_thumbnail_root": root}


def _render_dir_candidates(capture_dir=None, *, context=None, preferred_dir=None):
    if capture_dir:
        info = {
            "capture_dir": capture_dir,
            "storage_scope": "explicit",
            "project_id": viewport_capture.project_id(context),
            "session_id": viewport_capture.capture_session_id(),
            "base_dir": capture_dir,
            "fallback_reason": "",
        }
        return [{**info, "render_thumbnail_root": os.path.join(capture_dir, "render-thumbnails")}]
    return [
        {**info, "render_thumbnail_root": os.path.join(info["capture_dir"], "render-thumbnails")}
        for info in viewport_capture.capture_dir_candidates(context=context, preferred_dir=preferred_dir)
    ]


def _metadata_path(render_dir):
    return os.path.join(render_dir, METADATA_FILENAME)


def _read_metadata(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_metadata(metadata):
    path = metadata.get("metadata_path") or _metadata_path(metadata["render_dir"])
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(metadata, handle, indent=2, sort_keys=True)
    return path


def _compact_path_info(path):
    path = str(path or "")
    exists = bool(path and os.path.isfile(path))
    return {
        "path": path,
        "exists": exists,
        "size_bytes": os.path.getsize(path) if exists else 0,
    }


def _visual_resource_entry(kind, metadata):
    metadata = dict(metadata or {})
    available = bool(metadata.get("available"))
    resource_uris = []
    metadata_uri = metadata.get("metadata_uri") or ""
    resource_uri = metadata.get("resource_uri") or metadata.get("exact_resource_uri") or ""
    if resource_uri:
        resource_uris.append(resource_uri)
    if metadata.get("exact_resource_uri") and metadata.get("exact_resource_uri") not in resource_uris:
        resource_uris.append(metadata["exact_resource_uri"])
    if kind == "playblast":
        for frame in metadata.get("frames") or []:
            if frame.get("resource_uri"):
                resource_uris.append(frame["resource_uri"])
    elif kind == "inspection_render":
        for image in metadata.get("images") or []:
            if image.get("resource_uri"):
                resource_uris.append(image["resource_uri"])
    elif kind == "render_job":
        for key in ("newest_frame_resource_uri", "log_resource_uri", "video_resource_uri"):
            value = metadata.get(key) or ""
            if value:
                resource_uris.append(value)
    return {
        "kind": kind,
        "available": available,
        "id": (
            metadata.get("capture_id")
            or metadata.get("playblast_id")
            or metadata.get("render_id")
            or metadata.get("thumbnail_id")
            or metadata.get("job_id")
            or ""
        ),
        "metadata_uri": metadata_uri,
        "latest_metadata_uri": metadata.get("latest_metadata_uri") or metadata_uri,
        "resource_uris": resource_uris[:80],
        "path": metadata.get("path") or metadata.get("newest_frame_path") or metadata.get("video_path") or "",
        "path_info": _compact_path_info(metadata.get("path") or metadata.get("newest_frame_path") or metadata.get("video_path") or ""),
        "status": metadata.get("status") or "",
        "note": metadata.get("note") or metadata.get("message") or "",
        "created_at": float(metadata.get("created_at") or 0.0),
        "storage_scope": metadata.get("storage_scope") or "",
        "project_id": metadata.get("project_id") or "",
        "session_id": metadata.get("session_id") or "",
        "summary": {
            "frame_count": int(metadata.get("frame_count") or len(metadata.get("frames") or []) or 0),
            "image_count": int(metadata.get("image_count") or len(metadata.get("images") or []) or 0),
            "size_bytes": int(metadata.get("size_bytes") or metadata.get("video_size_bytes") or 0),
            "width": int(metadata.get("width") or 0),
            "height": int(metadata.get("height") or 0),
        },
    }


def get_visual_evidence_resources(context, *, include_unavailable=True, capture_dir=None):
    """Return a compact inventory of latest visual/render evidence resources."""

    entries = [
        _visual_resource_entry(
            "viewport_capture",
            viewport_capture.latest_capture_metadata(context=context, preferred_dir=capture_dir),
        ),
        _visual_resource_entry(
            "playblast",
            playblast_capture.latest_playblast_metadata(context=context, preferred_dir=capture_dir),
        ),
        _visual_resource_entry(
            "inspection_render",
            inspection_render.latest_inspection_render_metadata(context=context, preferred_dir=capture_dir),
        ),
        _visual_resource_entry(
            "render_thumbnail",
            latest_render_thumbnail_metadata(context=context, preferred_dir=capture_dir),
        ),
        _visual_resource_entry(
            "render_job",
            render_jobs.latest_render_job_metadata(context=context, preferred_dir=capture_dir),
        ),
    ]
    if not include_unavailable:
        entries = [entry for entry in entries if entry["available"]]
    latest_available = [entry for entry in entries if entry["available"]]
    latest_available.sort(key=lambda entry: entry.get("created_at", 0.0), reverse=True)
    return {
        "ok": True,
        "message": "Visual evidence resources collected",
        "available_count": len(latest_available),
        "resource_count": len(entries),
        "latest_available": latest_available[0] if latest_available else None,
        "resources": entries,
        "resource_templates": [
            "blender://captures/latest",
            "blender://captures/latest/metadata",
            "blender://playblasts/latest/metadata",
            "blender://inspection-renders/latest/metadata",
            "blender://render-thumbnails/latest",
            "blender://render-thumbnails/latest/metadata",
            "blender://render-jobs/latest/metadata",
        ],
    }


def _metadata_candidates(capture_dir=None, *, context=None, preferred_dir=None):
    candidates = []
    for info in _render_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        root = info["render_thumbnail_root"]
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            metadata_path = os.path.join(root, name, METADATA_FILENAME)
            if os.path.isfile(metadata_path):
                candidates.append(metadata_path)
    return candidates


def _metadata_for_id(thumbnail_id, capture_dir=None, *, context=None, preferred_dir=None):
    thumbnail_id = _safe_id(thumbnail_id, "")
    if not thumbnail_id:
        return None
    for info in _render_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        metadata_path = os.path.join(info["render_thumbnail_root"], thumbnail_id, METADATA_FILENAME)
        if os.path.isfile(metadata_path):
            return _read_metadata(metadata_path)
    return None


def latest_render_thumbnail_metadata(capture_dir=None, *, context=None, preferred_dir=None):
    newest = []
    for metadata_path in _metadata_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        try:
            metadata = _read_metadata(metadata_path)
        except (OSError, json.JSONDecodeError):
            continue
        newest.append((metadata.get("created_at", 0.0), os.path.getmtime(metadata_path), metadata))
    if newest:
        return max(newest, key=lambda item: (item[0], item[1]))[2]
    info = _render_root_info(context, preferred_dir=preferred_dir)
    return {
        "ok": False,
        "available": False,
        "project_id": info.get("project_id", ""),
        "session_id": info.get("session_id", ""),
        "storage_scope": info.get("storage_scope", ""),
        "resource_uri": LATEST_RENDER_THUMBNAIL_URI,
        "metadata_uri": LATEST_RENDER_THUMBNAIL_METADATA_URI,
        "note": "No render thumbnail is available yet",
    }


def render_thumbnail_metadata(thumbnail_id, capture_dir=None, *, context=None, preferred_dir=None):
    metadata = _metadata_for_id(thumbnail_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if metadata:
        return metadata
    info = _render_root_info(context, preferred_dir=preferred_dir)
    return {
        "ok": False,
        "available": False,
        "thumbnail_id": str(thumbnail_id or ""),
        "project_id": info.get("project_id", ""),
        "session_id": info.get("session_id", ""),
        "storage_scope": info.get("storage_scope", ""),
        "resource_uri": _resource_uri(thumbnail_id),
        "metadata_uri": _metadata_uri(thumbnail_id),
        "note": "Render thumbnail was not found for this Blender project/session",
    }


def render_thumbnail_resource(thumbnail_id, capture_dir=None, *, context=None, preferred_dir=None):
    if str(thumbnail_id or "") == "latest":
        metadata = latest_render_thumbnail_metadata(capture_dir, context=context, preferred_dir=preferred_dir)
    else:
        metadata = render_thumbnail_metadata(thumbnail_id, capture_dir, context=context, preferred_dir=preferred_dir)
    path = metadata.get("path") or ""
    if not metadata.get("available") or not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        data = base64.b64encode(handle.read()).decode("ascii")
    return {
        "mimeType": "image/png",
        "blob": data,
        "path": path,
        "thumbnailId": metadata.get("thumbnail_id", ""),
        "resourceUri": metadata.get("resource_uri", ""),
        "metadataUri": metadata.get("metadata_uri", ""),
        "sizeBytes": int(metadata.get("size_bytes", 0) or 0),
        "width": int(metadata.get("width", 0) or 0),
        "height": int(metadata.get("height", 0) or 0),
    }


def parse_render_thumbnail_resource_uri(uri):
    uri = str(uri or "")
    prefix = "blender://render-thumbnails/"
    if not uri.startswith(prefix):
        return "", ""
    tail = uri[len(prefix) :]
    if tail == "latest":
        return "latest", "image"
    if tail == "latest/metadata":
        return "latest", "metadata"
    parts = tail.split("/")
    if len(parts) == 1:
        return _safe_id(parts[0], ""), "image"
    if len(parts) == 2 and parts[1] == "metadata":
        return _safe_id(parts[0], ""), "metadata"
    return "", ""


def _image_size(path):
    image = None
    try:
        image = bpy.data.images.load(path, check_existing=False)
        return int(image.size[0]), int(image.size[1])
    except Exception:
        return 0, 0
    finally:
        if image is not None:
            try:
                bpy.data.images.remove(image)
            except Exception:
                pass


def _abspath(path):
    if not str(path or "").strip():
        return ""
    try:
        return os.path.abspath(bpy.path.abspath(str(path)))
    except Exception:
        return os.path.abspath(os.path.expanduser(str(path)))


def _is_packed(data_block):
    packed = getattr(data_block, "packed_file", None)
    if packed:
        return True
    packed_files = getattr(data_block, "packed_files", None)
    try:
        return bool(packed_files)
    except Exception:
        return False


def _file_path_for_block(data_block):
    for attr in ("filepath", "filepath_raw"):
        value = getattr(data_block, attr, "")
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _data_collection(name):
    collection = getattr(bpy.data, name, None)
    if collection is None:
        return []
    try:
        return list(collection)
    except Exception:
        return []


def _summarize_data_blocks():
    summaries = []
    for name in DATA_COLLECTION_NAMES:
        items = _data_collection(name)
        if not items:
            summaries.append(
                {
                    "collection": name,
                    "count": 0,
                    "local": 0,
                    "linked": 0,
                    "fake_user": 0,
                    "zero_user": 0,
                }
            )
            continue
        linked = 0
        fake_user = 0
        zero_user = 0
        for item in items:
            if getattr(item, "library", None):
                linked += 1
            if bool(getattr(item, "use_fake_user", False)):
                fake_user += 1
            try:
                if int(getattr(item, "users", 0) or 0) == 0:
                    zero_user += 1
            except Exception:
                pass
        summaries.append(
            {
                "collection": name,
                "count": len(items),
                "local": len(items) - linked,
                "linked": linked,
                "fake_user": fake_user,
                "zero_user": zero_user,
            }
        )
    return summaries


def _library_user_counts():
    counts = {}
    for name in DATA_COLLECTION_NAMES:
        if name == "libraries":
            continue
        for item in _data_collection(name):
            library = getattr(item, "library", None)
            if not library:
                continue
            key = library.name
            counts[key] = counts.get(key, 0) + 1
    return counts


def _linked_libraries(max_items):
    counts = _library_user_counts()
    libraries = []
    for library in _data_collection("libraries")[:max_items]:
        raw_path = str(getattr(library, "filepath", "") or "")
        absolute_path = _abspath(raw_path)
        libraries.append(
            {
                "name": getattr(library, "name", ""),
                "filepath": raw_path,
                "absolute_path": absolute_path,
                "exists": bool(absolute_path and os.path.exists(absolute_path)),
                "user_datablock_count": int(counts.get(getattr(library, "name", ""), 0)),
            }
        )
    return libraries


def _external_files(max_items):
    files = []
    missing = []
    seen = set()
    for collection_name in EXTERNAL_FILE_COLLECTION_NAMES:
        for item in _data_collection(collection_name):
            raw_path = _file_path_for_block(item)
            if not raw_path:
                continue
            absolute_path = _abspath(raw_path)
            packed = _is_packed(item)
            exists = bool(packed or (absolute_path and os.path.exists(absolute_path)))
            key = (collection_name, getattr(item, "name", ""), absolute_path)
            if key in seen:
                continue
            seen.add(key)
            entry = {
                "collection": collection_name,
                "name": getattr(item, "name", ""),
                "filepath": raw_path,
                "absolute_path": absolute_path,
                "exists": exists,
                "packed": packed,
                "library": getattr(getattr(item, "library", None), "name", ""),
            }
            files.append(entry)
            if not exists:
                missing.append(entry)
            if len(files) >= max_items and len(missing) >= max_items:
                break
    return files[:max_items], missing[:max_items]


def _backup_files(filepath, max_items):
    if not filepath:
        return []
    backups = []
    for path in sorted(glob.glob(f"{filepath}[0-9]*"))[:max_items]:
        backups.append(
            {
                "path": path,
                "exists": os.path.isfile(path),
                "size_bytes": os.path.getsize(path) if os.path.isfile(path) else 0,
                "modified_at": os.path.getmtime(path) if os.path.isfile(path) else 0.0,
            }
        )
    return backups


def _script_checkpoint_diagnostics(context):
    state = getattr(getattr(context, "scene", None), "claude_blender", None)
    last_path = getattr(state, "last_checkpoint_path", "") if state else ""
    restored_path = getattr(state, "last_checkpoint_restored_path", "") if state else ""
    return {
        "last_checkpoint_status": getattr(state, "last_checkpoint_status", "") if state else "",
        "last_checkpoint": script_runner.checkpoint_metadata(context, last_path),
        "last_restored_status": getattr(state, "last_checkpoint_restored_status", "") if state else "",
        "last_restored": script_runner.checkpoint_metadata(context, restored_path),
        "path_policy": "Only report checkpoint paths that this metadata marks exists=true and restorable=true.",
    }


def get_blend_file_diagnostics(context, *, max_items=50):
    max_items = max(1, min(200, int(max_items or 50)))
    filepath = getattr(bpy.data, "filepath", "") or ""
    absolute_filepath = os.path.abspath(filepath) if filepath else ""
    directory = os.path.dirname(absolute_filepath) if absolute_filepath else ""
    is_dirty = bool(getattr(bpy.data, "is_dirty", False))
    suggested_project_dir = directory or os.path.join(os.path.expanduser("~"), "Documents", "Blender")
    path_bound = bool(filepath)
    external_files, missing = _external_files(max_items)
    libraries = _linked_libraries(max_items)
    unsaved = not path_bound
    diagnostics = {
        "ok": True,
        "message": "Blend file diagnostics collected",
        "file": {
            "filepath": filepath,
            "absolute_path": absolute_filepath,
            "binding_state": "bound" if path_bound else "unbound",
            "bound_project_dir": directory,
            "is_saved": not unsaved,
            "is_dirty": is_dirty,
            "needs_save": bool(unsaved or is_dirty),
            "can_save_current": bool(filepath and directory and os.path.isdir(directory) and os.access(directory, os.W_OK)),
            "exists": bool(absolute_filepath and os.path.isfile(absolute_filepath)),
            "directory": directory,
            "directory_exists": bool(directory and os.path.isdir(directory)),
            "directory_writable": bool(directory and os.path.isdir(directory) and os.access(directory, os.W_OK)),
            "suggested_project_dir": suggested_project_dir,
            "suggested_project_dir_is_hint_only": True,
            "requires_user_confirmed_path": not path_bound,
            "path_policy": (
                "Use the active .blend path for bound-file edits. Ask the user for a path before save-as, save-copy, open, or new-project operations."
            ),
            "backup_files": _backup_files(absolute_filepath, max_items),
        },
        "script_checkpoints": _script_checkpoint_diagnostics(context),
        "autosave": autosave.autosave_status(context),
        "linked_libraries": libraries,
        "linked_library_count": len(libraries),
        "missing_linked_libraries": [item for item in libraries if not item.get("exists")],
        "external_files": external_files,
        "external_file_count": len(external_files),
        "missing_external_files": missing,
        "missing_external_file_count": len(missing),
        "data_block_summary": _summarize_data_blocks(),
        "notes": [],
    }
    if unsaved:
        diagnostics["notes"].append("Current blend file has not been saved yet")
    if missing:
        diagnostics["notes"].append("One or more external file paths are missing on disk")
    if diagnostics["missing_linked_libraries"]:
        diagnostics["notes"].append("One or more linked library files are missing on disk")
    return diagnostics


def get_workspace_layout(context, *, max_workspaces=20, max_areas=80):
    max_workspaces = max(1, min(100, int(max_workspaces or 20)))
    max_areas = max(1, min(300, int(max_areas or 80)))
    window = getattr(context, "window", None)
    screen = getattr(context, "screen", None)
    ui_available = bool(window) and not bool(getattr(bpy.app, "background", False))
    areas = []
    for screen_item in list(getattr(bpy.data, "screens", [])):
        for area in list(getattr(screen_item, "areas", [])):
            active_space = getattr(area, "spaces", None)
            active_space_type = ""
            if active_space and getattr(active_space, "active", None):
                active_space_type = getattr(active_space.active, "type", "")
            areas.append(
                {
                    "screen": getattr(screen_item, "name", ""),
                    "type": getattr(area, "type", ""),
                    "x": int(getattr(area, "x", 0) or 0),
                    "y": int(getattr(area, "y", 0) or 0),
                    "width": int(getattr(area, "width", 0) or 0),
                    "height": int(getattr(area, "height", 0) or 0),
                    "active_space_type": active_space_type,
                }
            )
            if len(areas) >= max_areas:
                break
        if len(areas) >= max_areas:
            break
    windows = []
    window_manager = getattr(context, "window_manager", None)
    for item in list(getattr(window_manager, "windows", []) or []):
        windows.append(
            {
                "workspace": getattr(getattr(item, "workspace", None), "name", ""),
                "screen": getattr(getattr(item, "screen", None), "name", ""),
            }
        )
    return {
        "ok": True,
        "message": "Workspace layout collected",
        "ui_available": ui_available,
        "current_workspace": getattr(getattr(window, "workspace", None), "name", "") if window else "",
        "current_screen": getattr(screen, "name", "") if screen else "",
        "workspaces": [workspace.name for workspace in list(getattr(bpy.data, "workspaces", []))[:max_workspaces]],
        "windows": windows,
        "window_count": len(windows),
        "areas": areas,
        "area_count": len(areas),
    }


def jump_to_workspace(context, *, workspace_name):
    workspace_name = str(workspace_name or "").strip()
    if not workspace_name:
        return {"ok": False, "message": "workspace_name is required"}
    window = getattr(context, "window", None)
    if not window or bool(getattr(bpy.app, "background", False)):
        return {
            "ok": False,
            "message": "Workspace switching requires an interactive Blender window",
            "ui_available": False,
        }
    workspace = bpy.data.workspaces.get(workspace_name)
    if workspace is None:
        return {
            "ok": False,
            "message": f"Workspace not found: {workspace_name}",
            "available_workspaces": [item.name for item in bpy.data.workspaces],
        }
    window.workspace = workspace
    return {
        "ok": True,
        "message": f"Switched to workspace: {workspace.name}",
        "workspace": workspace.name,
        "ui_available": True,
    }


def _first_view3d_area(context):
    if bool(getattr(bpy.app, "background", False)):
        return None, None, None
    window = getattr(context, "window", None)
    screen = getattr(context, "screen", None) or getattr(window, "screen", None)
    if not window or not screen:
        return None, None, None
    for area in screen.areas:
        if area.type != "VIEW_3D":
            continue
        region = next((item for item in area.regions if item.type == "WINDOW"), None)
        if region:
            return window, area, region
    return window, None, None


def _region_3d_for_area(area):
    space = getattr(getattr(area, "spaces", None), "active", None)
    region_3d = getattr(space, "region_3d", None)
    return space, region_3d


def _vec(values, length=3):
    try:
        return [round(float(values[index]), 5) for index in range(length)]
    except Exception:
        return []


def _viewport_area_state(area):
    space, region_3d = _region_3d_for_area(area)
    if not space:
        return {}
    state = {
        "area_type": getattr(area, "type", ""),
        "space_type": getattr(space, "type", ""),
        "shading_type": getattr(getattr(space, "shading", None), "type", ""),
        "overlay_visible": bool(getattr(getattr(space, "overlay", None), "show_overlays", False)),
        "lens": round(float(getattr(space, "lens", 0.0) or 0.0), 5),
        "clip_start": round(float(getattr(space, "clip_start", 0.0) or 0.0), 5),
        "clip_end": round(float(getattr(space, "clip_end", 0.0) or 0.0), 5),
    }
    if region_3d:
        state.update(
            {
                "view_perspective": getattr(region_3d, "view_perspective", ""),
                "view_location": _vec(getattr(region_3d, "view_location", []), 3),
                "view_distance": round(float(getattr(region_3d, "view_distance", 0.0) or 0.0), 5),
                "view_rotation_quaternion": _vec(getattr(region_3d, "view_rotation", []), 4),
                "is_perspective": bool(getattr(region_3d, "is_perspective", False)),
            }
        )
    return state


def set_viewport_view(context, *, view="front", frame_object_name="", use_orthographic=True):
    view = str(view or "front").strip().lower()
    frame_object_name = str(frame_object_name or "").strip()
    axis_map = {
        "front": "FRONT",
        "back": "BACK",
        "left": "LEFT",
        "right": "RIGHT",
        "top": "TOP",
        "bottom": "BOTTOM",
    }
    if view not in set(axis_map) | {"camera", "user"}:
        return {
            "ok": False,
            "message": "view must be one of front, back, left, right, top, bottom, camera, or user",
            "view": view,
        }
    window, area, region = _first_view3d_area(context)
    if not window or not area or not region:
        return {
            "ok": False,
            "message": "Viewport navigation requires an interactive Blender VIEW_3D area",
            "ui_available": False,
            "view": view,
        }
    obj = bpy.data.objects.get(frame_object_name) if frame_object_name else None
    if frame_object_name and obj is None:
        return {"ok": False, "message": f"Object not found: {frame_object_name}", "view": view}
    before = _viewport_area_state(area)
    try:
        selected = [obj] if obj else list(context.selected_objects)
        active = obj or context.active_object
        with context.temp_override(window=window, area=area, region=region, active_object=active, selected_objects=selected):
            if view == "camera":
                bpy.ops.view3d.view_camera()
            elif view != "user":
                bpy.ops.view3d.view_axis(type=axis_map[view], align_active=False)
                if use_orthographic:
                    space, region_3d = _region_3d_for_area(area)
                    if region_3d:
                        region_3d.view_perspective = "ORTHO"
            if obj:
                bpy.ops.view3d.view_selected(use_all_regions=False)
    except Exception as exc:
        return {
            "ok": False,
            "message": f"Viewport navigation failed: {type(exc).__name__}: {exc}",
            "ui_available": True,
            "view": view,
            "before": before,
        }
    return {
        "ok": True,
        "message": f"Viewport set to {view}",
        "ui_available": True,
        "view": view,
        "framed_object": getattr(obj, "name", ""),
        "before": before,
        "after": _viewport_area_state(area),
    }


def focus_object_in_viewport(context, *, object_name, select=True):
    object_name = str(object_name or "").strip()
    if not object_name:
        return {"ok": False, "message": "object_name is required"}
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        return {"ok": False, "message": f"Object not found: {object_name}", "object": object_name}
    window, area, region = _first_view3d_area(context)
    if not window or not area or not region:
        return {
            "ok": False,
            "message": "Viewport focus requires an interactive Blender VIEW_3D area",
            "ui_available": False,
            "object": obj.name,
        }
    if select:
        for candidate in context.scene.objects:
            candidate.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
    try:
        with context.temp_override(window=window, area=area, region=region, active_object=obj, selected_objects=[obj]):
            bpy.ops.view3d.view_selected(use_all_regions=False)
    except Exception as exc:
        return {
            "ok": False,
            "message": f"Viewport focus failed: {type(exc).__name__}: {exc}",
            "ui_available": True,
            "object": obj.name,
            "selected": bool(obj.select_get()),
        }
    return {
        "ok": True,
        "message": f"Focused viewport on object: {obj.name}",
        "ui_available": True,
        "object": obj.name,
        "selected": bool(obj.select_get()),
    }


def render_scene_thumbnail(
    context,
    *,
    filepath="",
    frame=None,
    resolution_x=512,
    resolution_y=512,
    camera_name="",
    note="",
    capture_dir=None,
    allow_blocking_render=False,
):
    scene = context.scene
    camera = bpy.data.objects.get(str(camera_name or "")) if str(camera_name or "").strip() else scene.camera
    if camera is None or getattr(camera, "type", "") != "CAMERA":
        return {
            "ok": False,
            "message": "A scene camera or camera_name is required to render a thumbnail",
            "thumbnail": {
                "ok": False,
                "available": False,
                "resource_uri": LATEST_RENDER_THUMBNAIL_URI,
                "metadata_uri": LATEST_RENDER_THUMBNAIL_METADATA_URI,
            },
        }

    target_frame = int(frame if frame is not None else scene.frame_current)
    bounded_resolution_x = max(32, min(4096, int(resolution_x)))
    bounded_resolution_y = max(32, min(4096, int(resolution_y)))
    pixel_count = bounded_resolution_x * bounded_resolution_y
    estimated_seconds = render_jobs._rough_estimated_seconds(
        1,
        bounded_resolution_x,
        bounded_resolution_y,
        100,
        _thumbnail_sample_count(scene),
    )
    estimated_duration = render_jobs._duration_label(estimated_seconds)
    if pixel_count > MAX_BLOCKING_THUMBNAIL_PIXELS and not bool(allow_blocking_render):
        return {
            "ok": False,
            "message": (
                "Large still renders are guarded because synchronous render_scene_thumbnail can block the bridge. "
                "Use start_render_job for timeout-safe render previews, or pass allow_blocking_render=true for an intentional one-off still. "
                f"Rough synchronous estimate: {estimated_duration}."
            ),
            "code": "render_job_recommended",
            "recommended_tool": "start_render_job",
            "suggested_arguments": {
                "frame_start": target_frame,
                "frame_end": target_frame,
                "resolution_x": bounded_resolution_x,
                "resolution_y": bounded_resolution_y,
                "resolution_percentage": 100,
                "output_kind": "frames",
                "camera_name": camera.name,
                "job_name": "thumbnail render preview",
                "note": str(note or "Render preview requested through render_scene_thumbnail")[:1000],
            },
            "pixel_count": pixel_count,
            "max_blocking_pixels": MAX_BLOCKING_THUMBNAIL_PIXELS,
            "estimated_seconds": estimated_seconds,
            "estimated_duration": estimated_duration,
            "poll_after_seconds": render_jobs.DEFAULT_RENDER_POLL_INTERVAL_SECONDS,
            "timeout_safe": False,
        }

    thumbnail_id = _thumbnail_id()
    capture_info = _render_root_info(context, preferred_dir=capture_dir, create=True)
    render_dir = os.path.join(capture_info["render_thumbnail_root"], thumbnail_id)
    os.makedirs(render_dir, exist_ok=True)
    path = str(filepath or "").strip()
    if path:
        path = _abspath(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
    else:
        path = os.path.join(render_dir, THUMBNAIL_FILENAME)

    original = {
        "frame": int(scene.frame_current),
        "camera": scene.camera,
        "resolution_x": int(scene.render.resolution_x),
        "resolution_y": int(scene.render.resolution_y),
        "resolution_percentage": int(scene.render.resolution_percentage),
        "filepath": str(scene.render.filepath),
        "file_format": str(scene.render.image_settings.file_format),
    }
    metadata = {
        "ok": False,
        "requested": True,
        "available": False,
        "thumbnail_id": thumbnail_id,
        "project_id": capture_info.get("project_id", ""),
        "session_id": capture_info.get("session_id", ""),
        "storage_scope": capture_info.get("storage_scope", ""),
        "capture_dir": capture_info.get("capture_dir", ""),
        "base_dir": capture_info.get("base_dir", ""),
        "fallback_reason": capture_info.get("fallback_reason", ""),
        "render_dir": render_dir,
        "path": path,
        "resource_uri": _resource_uri(thumbnail_id),
        "metadata_uri": _metadata_uri(thumbnail_id),
        "latest_resource_uri": LATEST_RENDER_THUMBNAIL_URI,
        "latest_metadata_uri": LATEST_RENDER_THUMBNAIL_METADATA_URI,
        "created_at": time.time(),
        "scene": scene.name,
        "frame": target_frame,
        "camera": camera.name,
        "resource_type": "png_render_thumbnail",
        "size_bytes": 0,
        "width": 0,
        "height": 0,
        "estimated_seconds": estimated_seconds,
        "estimated_duration": estimated_duration,
        "poll_after_seconds": render_jobs.DEFAULT_RENDER_POLL_INTERVAL_SECONDS,
        "timeout_safe": False,
        "client_guidance": (
            "This thumbnail render runs synchronously on Blender's main thread. "
            f"Rough expected duration is {estimated_duration}. "
            "For high-resolution or long renders, use start_render_job and poll get_render_job_status."
        ),
        "note": str(note or "")[:1000],
    }
    try:
        scene.frame_set(target_frame)
        scene.camera = camera
        scene.render.resolution_x = bounded_resolution_x
        scene.render.resolution_y = bounded_resolution_y
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        if os.path.isfile(path):
            width, height = _image_size(path)
            metadata.update(
                {
                    "ok": True,
                    "available": True,
                    "size_bytes": os.path.getsize(path),
                    "width": width,
                    "height": height,
                }
            )
    except Exception as exc:
        metadata["note"] = f"Thumbnail render failed: {type(exc).__name__}: {exc}"
    finally:
        scene.render.resolution_x = original["resolution_x"]
        scene.render.resolution_y = original["resolution_y"]
        scene.render.resolution_percentage = original["resolution_percentage"]
        scene.render.filepath = original["filepath"]
        scene.render.image_settings.file_format = original["file_format"]
        scene.camera = original["camera"]
        scene.frame_set(original["frame"])

    metadata["metadata_path"] = _metadata_path(render_dir)
    _write_metadata(metadata)
    return {
        "ok": bool(metadata.get("available")),
        "message": "Rendered scene thumbnail" if metadata.get("available") else "Scene thumbnail render failed",
        "thumbnail": metadata,
    }


def register():
    pass


def unregister():
    pass
