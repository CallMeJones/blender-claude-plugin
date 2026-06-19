"""Diagnostic object render capture and MCP resource helpers."""

from __future__ import annotations

import base64
import json
import math
import os
import time
import uuid

import bpy
import mathutils

from . import viewport_capture


LATEST_INSPECTION_RENDER_METADATA_URI = "blender://inspection-renders/latest/metadata"
METADATA_FILENAME = "metadata.json"
DEFAULT_VIEWS = ("front_below", "side")
VIEW_OFFSETS = {
    "front_below": (1.2, -0.8, -0.8),
    "underside": (0.0, -0.4, -1.2),
    "side": (1.4, 0.0, -0.2),
    "front": (0.0, -1.4, 0.1),
    "rear": (0.0, 1.4, 0.1),
    "top": (0.0, -0.2, 1.4),
}


def _safe_id(value, fallback="item"):
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in str(value or ""))
    safe = safe.strip("._")
    return safe[:80] or fallback


def _render_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _metadata_uri(render_id):
    return f"blender://inspection-renders/{render_id}/metadata"


def _image_resource_uri(render_id, image_id):
    return f"blender://inspection-renders/{render_id}/images/{_safe_id(image_id)}"


def _render_root_info(context=None, *, preferred_dir=None, create=False):
    capture_info = viewport_capture.resolve_capture_dir(context, preferred_dir=preferred_dir, create=create)
    root = os.path.join(capture_info["capture_dir"], "inspection-renders")
    if create:
        os.makedirs(root, exist_ok=True)
    return {**capture_info, "inspection_render_root": root}


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
        return [{**info, "inspection_render_root": os.path.join(capture_dir, "inspection-renders")}]
    return [
        {**info, "inspection_render_root": os.path.join(info["capture_dir"], "inspection-renders")}
        for info in viewport_capture.capture_dir_candidates(context=context, preferred_dir=preferred_dir)
    ]


def _metadata_path(render_dir):
    return os.path.join(render_dir, METADATA_FILENAME)


def _write_metadata(metadata):
    path = metadata.get("metadata_path") or _metadata_path(metadata["render_dir"])
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(metadata, handle, indent=2, sort_keys=True)
    return path


def _read_metadata(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _metadata_candidates(capture_dir=None, *, context=None, preferred_dir=None):
    candidates = []
    for info in _render_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        root = info["inspection_render_root"]
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            metadata_path = os.path.join(root, name, METADATA_FILENAME)
            if os.path.isfile(metadata_path):
                candidates.append((metadata_path, info))
    return candidates


def _metadata_for_id(render_id, capture_dir=None, *, context=None, preferred_dir=None):
    render_id = _safe_id(render_id, "")
    if not render_id:
        return None
    for info in _render_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        metadata_path = os.path.join(info["inspection_render_root"], render_id, METADATA_FILENAME)
        if os.path.isfile(metadata_path):
            return _read_metadata(metadata_path)
    return None


def latest_inspection_render_metadata(capture_dir=None, *, context=None, preferred_dir=None):
    newest = []
    for metadata_path, _info in _metadata_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
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
        "metadata_uri": LATEST_INSPECTION_RENDER_METADATA_URI,
        "note": "No inspection render capture is available yet",
    }


def inspection_render_metadata(render_id, capture_dir=None, *, context=None, preferred_dir=None):
    metadata = _metadata_for_id(render_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if metadata:
        return metadata
    info = _render_root_info(context, preferred_dir=preferred_dir)
    return {
        "ok": False,
        "available": False,
        "render_id": str(render_id or ""),
        "project_id": info.get("project_id", ""),
        "session_id": info.get("session_id", ""),
        "storage_scope": info.get("storage_scope", ""),
        "metadata_uri": _metadata_uri(render_id),
        "note": "Inspection render capture was not found for this Blender project/session",
    }


def inspection_render_image_resource(render_id, image_id, capture_dir=None, *, context=None, preferred_dir=None):
    metadata = _metadata_for_id(render_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if not metadata:
        return None
    image_id = _safe_id(image_id, "")
    if not image_id:
        return None
    for image in metadata.get("images") or []:
        if str(image.get("image_id") or "") != image_id:
            continue
        path = image.get("path") or ""
        if not image.get("available") or not os.path.isfile(path):
            return None
        with open(path, "rb") as handle:
            data = base64.b64encode(handle.read()).decode("ascii")
        return {
            "mimeType": "image/png",
            "blob": data,
            "path": path,
            "renderId": metadata.get("render_id", ""),
            "imageId": image_id,
            "objectName": image.get("object", ""),
            "view": image.get("view", ""),
            "resourceUri": image.get("resource_uri", ""),
            "metadataUri": metadata.get("metadata_uri", ""),
            "sizeBytes": int(image.get("size_bytes", 0) or 0),
            "width": int(image.get("width", 0) or 0),
            "height": int(image.get("height", 0) or 0),
        }
    return None


def parse_inspection_render_resource_uri(uri):
    uri = str(uri or "")
    prefix = "blender://inspection-renders/"
    if not uri.startswith(prefix):
        return "", "", ""
    tail = uri[len(prefix) :]
    if tail == "latest/metadata":
        return "latest", "metadata", ""
    parts = tail.split("/")
    if len(parts) == 2 and parts[1] == "metadata":
        return _safe_id(parts[0], ""), "metadata", ""
    if len(parts) == 3 and parts[1] == "images":
        return _safe_id(parts[0], ""), "image", _safe_id(parts[2], "")
    return "", "", ""


def _iter_target_objects(obj):
    yield obj
    for child in obj.children_recursive:
        yield child


def _object_bounds(obj):
    corners = []
    for item in _iter_target_objects(obj):
        if getattr(item, "type", "") in {"MESH", "CURVE", "FONT", "SURFACE", "META"} and getattr(item, "bound_box", None):
            corners.extend(item.matrix_world @ mathutils.Vector(corner) for corner in item.bound_box)
    if not corners:
        center = obj.matrix_world.translation.copy()
        return center, 1.0
    min_v = mathutils.Vector((min(point.x for point in corners), min(point.y for point in corners), min(point.z for point in corners)))
    max_v = mathutils.Vector((max(point.x for point in corners), max(point.y for point in corners), max(point.z for point in corners)))
    center = (min_v + max_v) * 0.5
    radius = max((point - center).length for point in corners)
    return center, max(0.25, float(radius))


def _look_at(camera, target):
    direction = target - camera.location
    if direction.length <= 0.0001:
        direction = mathutils.Vector((0.0, 0.0, -1.0))
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


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


def _view_list(views):
    if isinstance(views, str):
        requested = [views]
    elif isinstance(views, (list, tuple)):
        requested = [str(item) for item in views if str(item).strip()]
    else:
        requested = []
    normalized = []
    for item in requested or list(DEFAULT_VIEWS):
        key = item.strip().lower().replace("-", "_").replace(" ", "_")
        if key in {"under", "below", "bottom"}:
            key = "underside"
        if key in {"front_under", "front_below_3_4", "front_below_three_quarter"}:
            key = "front_below"
        if key not in VIEW_OFFSETS:
            continue
        if key not in normalized:
            normalized.append(key)
    return normalized or list(DEFAULT_VIEWS)


def capture_object_inspection_renders(
    context,
    *,
    object_names=None,
    views=None,
    frame=None,
    resolution_x=800,
    resolution_y=600,
    lens=50.0,
    distance_factor=3.0,
    camera_name="Agent Bridge Inspection Camera",
    note="",
    capture_dir=None,
):
    scene = context.scene
    names = [str(name) for name in (object_names or []) if str(name).strip()]
    if not names:
        active = getattr(context, "active_object", None)
        if active:
            names = [active.name]
    if not names:
        return {"ok": False, "message": "No object names were provided for inspection renders"}

    requested_views = _view_list(views)
    render_id = _render_id()
    capture_info = _render_root_info(context, preferred_dir=capture_dir, create=True)
    render_dir = os.path.join(capture_info["inspection_render_root"], render_id)
    os.makedirs(render_dir, exist_ok=True)
    target_frame = int(frame if frame is not None else scene.frame_current)

    original = {
        "frame": int(scene.frame_current),
        "camera": scene.camera,
        "resolution_x": int(scene.render.resolution_x),
        "resolution_y": int(scene.render.resolution_y),
        "resolution_percentage": int(scene.render.resolution_percentage),
        "filepath": str(scene.render.filepath),
        "file_format": str(scene.render.image_settings.file_format),
    }
    camera_data = bpy.data.cameras.new(f"{_safe_id(camera_name, 'Agent_Bridge_Inspection_Camera')}_Data")
    camera_data.lens = float(lens)
    camera = bpy.data.objects.new(_safe_id(camera_name, "Agent_Bridge_Inspection_Camera"), camera_data)
    scene.collection.objects.link(camera)

    images = []
    missing = []
    try:
        scene.frame_set(target_frame)
        scene.render.resolution_x = max(64, min(4096, int(resolution_x)))
        scene.render.resolution_y = max(64, min(4096, int(resolution_y)))
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.camera = camera
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj is None:
                missing.append(name)
                continue
            center, radius = _object_bounds(obj)
            distance = max(1.0, radius * float(distance_factor))
            for view in requested_views:
                offset = mathutils.Vector(VIEW_OFFSETS[view])
                if offset.length <= 0.0:
                    offset = mathutils.Vector((0.0, -1.0, 0.25))
                camera.location = center + offset.normalized() * distance
                _look_at(camera, center)
                image_id = _safe_id(f"{obj.name}-{view}")
                path = os.path.join(render_dir, f"{image_id}.png")
                item = {
                    "image_id": image_id,
                    "object": obj.name,
                    "view": view,
                    "path": path,
                    "resource_uri": _image_resource_uri(render_id, image_id),
                    "camera_location": [round(float(value), 6) for value in camera.location],
                    "target_location": [round(float(value), 6) for value in center],
                    "available": False,
                    "size_bytes": 0,
                    "width": 0,
                    "height": 0,
                    "note": "",
                }
                try:
                    scene.render.filepath = path
                    bpy.ops.render.render(write_still=True)
                    if os.path.isfile(path):
                        width, height = _image_size(path)
                        item.update(
                            {
                                "available": True,
                                "size_bytes": os.path.getsize(path),
                                "width": width,
                                "height": height,
                            }
                        )
                except Exception as exc:
                    item["note"] = f"Inspection render failed: {type(exc).__name__}: {exc}"
                images.append(item)
    finally:
        scene.render.resolution_x = original["resolution_x"]
        scene.render.resolution_y = original["resolution_y"]
        scene.render.resolution_percentage = original["resolution_percentage"]
        scene.render.filepath = original["filepath"]
        scene.render.image_settings.file_format = original["file_format"]
        scene.camera = original["camera"]
        scene.frame_set(original["frame"])
        if camera.name in bpy.data.objects:
            bpy.data.objects.remove(camera, do_unlink=True)
        if camera_data.name in bpy.data.cameras:
            bpy.data.cameras.remove(camera_data)

    available_images = [image for image in images if image.get("available")]
    metadata = {
        "ok": bool(available_images),
        "requested": True,
        "available": bool(available_images),
        "render_id": render_id,
        "project_id": capture_info.get("project_id", ""),
        "session_id": capture_info.get("session_id", ""),
        "storage_scope": capture_info.get("storage_scope", ""),
        "capture_dir": capture_info.get("capture_dir", ""),
        "base_dir": capture_info.get("base_dir", ""),
        "fallback_reason": capture_info.get("fallback_reason", ""),
        "render_dir": render_dir,
        "metadata_uri": _metadata_uri(render_id),
        "latest_metadata_uri": LATEST_INSPECTION_RENDER_METADATA_URI,
        "created_at": time.time(),
        "scene": scene.name,
        "frame": target_frame,
        "object_names": names,
        "missing_object_names": missing,
        "views": requested_views,
        "image_count": len(available_images),
        "requested_image_count": len(images),
        "resource_type": "png_inspection_renders",
        "note": str(note or "")[:1000],
        "images": images,
    }
    metadata["metadata_path"] = _metadata_path(render_dir)
    _write_metadata(metadata)
    return {
        "ok": bool(available_images),
        "message": "Captured object inspection render(s)" if available_images else "No inspection renders were captured",
        "inspection_render": metadata,
        "missing_object_names": missing,
    }


def register():
    pass


def unregister():
    pass
