"""Viewport screenshot capture and API image attachment helpers."""

from __future__ import annotations

import base64
import hashlib
import math
import os
import time
import uuid

import bpy


DEFAULT_MAX_BYTES = 5 * 1024 * 1024
PREVIEW_IMAGE_NAME = "Agent Bridge Viewport Preview"
LATEST_CAPTURE_RESOURCE_URI = "blender://captures/latest"
LATEST_CAPTURE_METADATA_URI = "blender://captures/latest/metadata"
MIN_RESIZED_DIMENSION = 64
MAX_RESIZE_ATTEMPTS = 8

_capture_session_id = ""


def default_capture_dir():
    return os.path.join(os.path.expanduser("~"), ".claude_blender", "captures")


def capture_session_id():
    global _capture_session_id
    if not _capture_session_id:
        _capture_session_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    return _capture_session_id


def _safe_path_part(value, fallback="untitled"):
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in str(value or ""))
    safe = safe.strip("._")
    return safe[:80] or fallback


def project_id(context=None):
    filepath = getattr(bpy.data, "filepath", "") or ""
    if filepath:
        normalized = os.path.abspath(filepath)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
        name = _safe_path_part(os.path.splitext(os.path.basename(filepath))[0], "blend")
        return f"{name}-{digest}"
    scene = getattr(getattr(context, "scene", None), "name", "") or "unsaved"
    return f"unsaved-{_safe_path_part(scene, 'scene')}-{os.getpid()}"


def project_capture_root(context=None):
    filepath = getattr(bpy.data, "filepath", "") or ""
    if not filepath:
        return ""
    folder = os.path.dirname(os.path.abspath(filepath))
    if not folder:
        return ""
    return os.path.join(folder, ".claude_blender", "captures")


def _normalized_path(value):
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(value or ""))))


def _is_default_or_empty_capture_dir(value):
    if not str(value or "").strip():
        return True
    return _normalized_path(value) == _normalized_path(default_capture_dir())


def _can_prepare_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except OSError:
        return False


def _global_capture_dir_info(context=None, *, create=False):
    session_id = capture_session_id()
    project = project_id(context)
    base_dir = default_capture_dir()
    capture_dir = os.path.join(base_dir, project, session_id)
    if create:
        os.makedirs(capture_dir, exist_ok=True)
    return {
        "capture_dir": capture_dir,
        "storage_scope": "global",
        "project_id": project,
        "session_id": session_id,
        "base_dir": base_dir,
        "fallback_reason": "unsaved_or_unwritable_project",
    }


def resolve_capture_dir(context=None, *, preferred_dir=None, create=False):
    """Resolve the project/session-scoped capture directory.

    The default capture preference behaves as automatic storage: saved .blend
    projects use a project-local hidden folder, while unsaved or unwritable
    projects fall back to the global user cache. A custom preference remains
    a custom base directory and still gets project/session subfolders.
    """

    session_id = capture_session_id()
    project = project_id(context)
    if _is_default_or_empty_capture_dir(preferred_dir):
        project_root = project_capture_root(context)
        if project_root:
            project_dir = os.path.join(project_root, session_id)
            if not create or _can_prepare_dir(project_dir):
                return {
                    "capture_dir": project_dir,
                    "storage_scope": "project",
                    "project_id": project,
                    "session_id": session_id,
                    "base_dir": project_root,
                    "fallback_reason": "",
                }
        return _global_capture_dir_info(context, create=create)

    base_dir = os.path.abspath(os.path.expanduser(str(preferred_dir)))
    capture_dir = os.path.join(base_dir, project, session_id)
    if create:
        os.makedirs(capture_dir, exist_ok=True)
    return {
        "capture_dir": capture_dir,
        "storage_scope": "custom",
        "project_id": project,
        "session_id": session_id,
        "base_dir": base_dir,
        "fallback_reason": "",
    }


def _capture_id_from_path(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    if stem.endswith("-resized"):
        stem = stem[: -len("-resized")]
    if stem.startswith("viewport-"):
        return stem[len("viewport-") :]
    return stem


def _resource_uri(capture_id):
    return f"blender://captures/{capture_id}"


def _metadata_uri(capture_id):
    return f"blender://captures/{capture_id}/metadata"


def _capture_filepath(capture_dir):
    os.makedirs(capture_dir, exist_ok=True)
    capture_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    return os.path.join(capture_dir, f"viewport-{capture_id}.png")


def _resolve_capture_dir_arg(capture_dir=None, context=None, preferred_dir=None, create=False):
    if capture_dir:
        return {
            "capture_dir": capture_dir,
            "storage_scope": "explicit",
            "project_id": project_id(context),
            "session_id": capture_session_id(),
            "base_dir": capture_dir,
            "fallback_reason": "",
        }
    return resolve_capture_dir(context, preferred_dir=preferred_dir, create=create)


def _capture_dir_candidates(capture_dir=None, *, context=None, preferred_dir=None):
    primary = _resolve_capture_dir_arg(capture_dir, context, preferred_dir)
    candidates = [primary]
    if capture_dir or not _is_default_or_empty_capture_dir(preferred_dir):
        return candidates

    fallback = _global_capture_dir_info(context)
    if _normalized_path(fallback["capture_dir"]) != _normalized_path(primary["capture_dir"]):
        candidates.append(fallback)
    return candidates


def capture_dir_candidates(capture_dir=None, *, context=None, preferred_dir=None):
    return _capture_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir)


def _capture_file_candidates(capture_dir):
    if not os.path.isdir(capture_dir):
        return []
    candidates = []
    for name in os.listdir(capture_dir):
        if not name.startswith("viewport-") or not name.lower().endswith(".png"):
            continue
        path = os.path.join(capture_dir, name)
        if os.path.isfile(path):
            candidates.append(path)
    return candidates


def _latest_capture_entry(capture_dir=None, *, context=None, preferred_dir=None):
    candidates = _capture_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir)
    newest = []
    for resolved in candidates:
        paths = _capture_file_candidates(resolved["capture_dir"])
        newest.extend((path, resolved) for path in paths)
    if newest:
        return max(newest, key=lambda item: (os.path.getmtime(item[0]), item[0]))
    return "", candidates[0]


def latest_capture_path(capture_dir=None, *, context=None, preferred_dir=None):
    path, _resolved = _latest_capture_entry(capture_dir, context=context, preferred_dir=preferred_dir)
    return path


def _capture_entry_for_id(capture_id, capture_dir=None, *, context=None, preferred_dir=None):
    capture_id = str(capture_id or "").strip()
    if not capture_id or "/" in capture_id or "\\" in capture_id:
        return "", _resolve_capture_dir_arg(capture_dir, context, preferred_dir)
    for resolved in _capture_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        capture_dir = resolved["capture_dir"]
        if not os.path.isdir(capture_dir):
            continue
        matches = []
        for suffix in (".png", "-resized.png"):
            path = os.path.join(capture_dir, f"viewport-{capture_id}{suffix}")
            if os.path.isfile(path):
                matches.append(path)
        if matches:
            return max(matches, key=lambda path: (os.path.getmtime(path), path)), resolved
    return "", _resolve_capture_dir_arg(capture_dir, context, preferred_dir)


def _metadata_for_path(path, *, resolved):
    capture_id = _capture_id_from_path(path)
    resource_uri = _resource_uri(capture_id)
    metadata_uri = _metadata_uri(capture_id)
    size_bytes = os.path.getsize(path)
    width = 0
    height = 0
    image = None
    try:
        image = bpy.data.images.load(path, check_existing=False)
        width, height = _image_size_tuple(image)
    except Exception:
        width = 0
        height = 0
    finally:
        if image is not None:
            try:
                bpy.data.images.remove(image)
            except Exception:
                pass
    return {
        "ok": True,
        "available": True,
        "capture_id": capture_id,
        "project_id": resolved.get("project_id", ""),
        "session_id": resolved.get("session_id", ""),
        "storage_scope": resolved.get("storage_scope", ""),
        "capture_dir": resolved.get("capture_dir", ""),
        "base_dir": resolved.get("base_dir", ""),
        "fallback_reason": resolved.get("fallback_reason", ""),
        "resource_uri": resource_uri,
        "metadata_uri": metadata_uri,
        "latest_resource_uri": LATEST_CAPTURE_RESOURCE_URI,
        "latest_metadata_uri": LATEST_CAPTURE_METADATA_URI,
        "media_type": "image/png",
        "path": path,
        "size_bytes": size_bytes,
        "width": width,
        "height": height,
        "scene": bpy.context.scene.name if getattr(bpy.context, "scene", None) else "",
        "frame": int(getattr(getattr(bpy.context, "scene", None), "frame_current", 0) or 0),
        "note": "Viewport capture is available as an MCP image resource",
    }


def capture_metadata(capture_id, capture_dir=None, *, context=None, preferred_dir=None):
    path, resolved = _capture_entry_for_id(capture_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if not path:
        return {
            "ok": False,
            "available": False,
            "capture_id": str(capture_id or ""),
            "project_id": resolved.get("project_id", ""),
            "session_id": resolved.get("session_id", ""),
            "storage_scope": resolved.get("storage_scope", ""),
            "resource_uri": _resource_uri(capture_id),
            "metadata_uri": _metadata_uri(capture_id),
            "latest_resource_uri": LATEST_CAPTURE_RESOURCE_URI,
            "latest_metadata_uri": LATEST_CAPTURE_METADATA_URI,
            "note": "Viewport capture was not found for this Blender project/session",
        }
    return _metadata_for_path(path, resolved=resolved)


def latest_capture_metadata(capture_dir=None, *, context=None, preferred_dir=None):
    path, resolved = _latest_capture_entry(capture_dir, context=context, preferred_dir=preferred_dir)
    if not path:
        return {
            "ok": False,
            "available": False,
            "project_id": resolved.get("project_id", ""),
            "session_id": resolved.get("session_id", ""),
            "storage_scope": resolved.get("storage_scope", ""),
            "resource_uri": LATEST_CAPTURE_RESOURCE_URI,
            "metadata_uri": LATEST_CAPTURE_METADATA_URI,
            "note": "No viewport capture is available yet",
        }
    metadata = _metadata_for_path(path, resolved=resolved)
    metadata["resource_uri"] = LATEST_CAPTURE_RESOURCE_URI
    metadata["metadata_uri"] = LATEST_CAPTURE_METADATA_URI
    metadata["exact_resource_uri"] = _resource_uri(metadata["capture_id"])
    metadata["exact_metadata_uri"] = _metadata_uri(metadata["capture_id"])
    metadata["note"] = "Latest viewport capture is available as an MCP image resource"
    return metadata


def capture_resource(capture_id, capture_dir=None, *, context=None, preferred_dir=None):
    metadata = capture_metadata(capture_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if not metadata.get("available"):
        return None
    with open(metadata["path"], "rb") as handle:
        data = base64.b64encode(handle.read()).decode("ascii")
    return {
        "mimeType": "image/png",
        "blob": data,
        "path": metadata["path"],
        "captureId": metadata["capture_id"],
        "projectId": metadata["project_id"],
        "sessionId": metadata["session_id"],
        "resourceUri": metadata["resource_uri"],
        "metadataUri": metadata["metadata_uri"],
        "sizeBytes": metadata["size_bytes"],
        "width": metadata["width"],
        "height": metadata["height"],
    }


def latest_capture_resource(capture_dir=None, *, context=None, preferred_dir=None):
    metadata = latest_capture_metadata(capture_dir, context=context, preferred_dir=preferred_dir)
    if not metadata.get("available"):
        return None
    with open(metadata["path"], "rb") as handle:
        data = base64.b64encode(handle.read()).decode("ascii")
    return {
        "mimeType": "image/png",
        "blob": data,
        "path": metadata["path"],
        "captureId": metadata.get("capture_id", ""),
        "projectId": metadata.get("project_id", ""),
        "sessionId": metadata.get("session_id", ""),
        "resourceUri": metadata.get("resource_uri", LATEST_CAPTURE_RESOURCE_URI),
        "metadataUri": metadata.get("metadata_uri", LATEST_CAPTURE_METADATA_URI),
        "exactResourceUri": metadata.get("exact_resource_uri", ""),
        "exactMetadataUri": metadata.get("exact_metadata_uri", ""),
        "sizeBytes": metadata["size_bytes"],
        "width": metadata["width"],
        "height": metadata["height"],
    }


def parse_capture_resource_uri(uri):
    uri = str(uri or "")
    prefix = "blender://captures/"
    if not uri.startswith(prefix):
        return "", False
    tail = uri[len(prefix) :]
    if tail in {"latest", "latest/metadata"}:
        return "latest", tail.endswith("/metadata")
    metadata = tail.endswith("/metadata")
    capture_id = tail[: -len("/metadata")] if metadata else tail
    if not capture_id or "/" in capture_id or "\\" in capture_id:
        return "", metadata
    return capture_id, metadata


def _has_ui_context(context):
    if bool(getattr(bpy.app, "background", False)):
        return False
    return bool(getattr(context, "window", None) and getattr(context, "screen", None))


def has_ui_context(context):
    return _has_ui_context(context)


def _capture_with_operator(context, filepath):
    area = getattr(context, "area", None)
    if area and area.type == "VIEW_3D":
        bpy.ops.screen.screenshot_area(filepath=filepath)
        return "screen.screenshot_area"
    bpy.ops.screen.screenshot(filepath=filepath)
    return "screen.screenshot"


def capture_viewport_to_file(context, filepath):
    return _capture_with_operator(context, filepath)


def load_preview_image(filepath):
    """Load the screenshot into a stable Blender Image datablock."""

    existing = bpy.data.images.get(PREVIEW_IMAGE_NAME)
    if existing:
        bpy.data.images.remove(existing)
    image = bpy.data.images.load(filepath, check_existing=False)
    image.name = PREVIEW_IMAGE_NAME
    return image


def _resized_filepath(filepath):
    root, ext = os.path.splitext(filepath)
    return f"{root}-resized{ext or '.png'}"


def _image_size_tuple(image):
    try:
        return int(image.size[0]), int(image.size[1])
    except Exception:
        return 0, 0


def _resize_png_to_fit(filepath, max_bytes):
    """Downscale and re-save a PNG with Blender's image API until it fits."""

    max_bytes = int(max_bytes or DEFAULT_MAX_BYTES)
    original_size = os.path.getsize(filepath)
    if original_size <= max_bytes:
        return filepath, {
            "resized": False,
            "original_size_bytes": original_size,
            "size_bytes": original_size,
        }

    image = bpy.data.images.load(filepath, check_existing=False)
    try:
        width, height = _image_size_tuple(image)
        if width <= 0 or height <= 0:
            return None, {
                "resized": False,
                "original_size_bytes": original_size,
                "size_bytes": original_size,
                "resize_error": "Could not read screenshot dimensions",
            }
        output_path = _resized_filepath(filepath)
        current_size = original_size
        resized_info = {
            "resized": True,
            "original_path": filepath,
            "original_size_bytes": original_size,
            "original_width": width,
            "original_height": height,
        }
        for _attempt in range(MAX_RESIZE_ATTEMPTS):
            scale = math.sqrt(max(1, max_bytes) / max(1, current_size)) * 0.9
            scale = min(0.85, max(0.1, scale))
            next_width = max(MIN_RESIZED_DIMENSION, int(width * scale))
            next_height = max(MIN_RESIZED_DIMENSION, int(height * scale))
            if next_width == width and next_height == height:
                next_width = max(MIN_RESIZED_DIMENSION, width - 1)
                next_height = max(MIN_RESIZED_DIMENSION, height - 1)
            if (next_width, next_height) == (width, height):
                break
            image.scale(next_width, next_height)
            image.filepath_raw = output_path
            image.file_format = "PNG"
            image.save()
            current_size = os.path.getsize(output_path)
            width, height = next_width, next_height
            resized_info.update(
                {
                    "path": output_path,
                    "size_bytes": current_size,
                    "width": width,
                    "height": height,
                    "resize_scale": round(width / max(1, int(resized_info["original_width"])), 5),
                }
            )
            if current_size <= max_bytes:
                return output_path, resized_info
        resized_info["resize_error"] = f"Resized screenshot still exceeds {max_bytes} bytes"
        return None, resized_info
    finally:
        try:
            bpy.data.images.remove(image)
        except Exception:
            pass


def prepare_image_attachment(filepath, *, max_bytes=DEFAULT_MAX_BYTES, capture_method="file", capture_info=None):
    """Prepare a captured PNG as bounded visual evidence for external clients."""

    max_bytes = int(max_bytes or DEFAULT_MAX_BYTES)
    capture_info = dict(capture_info or {})
    if not os.path.exists(filepath):
        return {
            "requested": True,
            "available": False,
            "note": "Viewport screenshot operator completed but did not create a file",
        }, {}

    size_bytes = os.path.getsize(filepath)
    if size_bytes <= 0:
        return {
            "requested": True,
            "available": False,
            "note": "Viewport screenshot file was empty",
            "path": filepath,
        }, {}

    try:
        prepared_path, resize_info = _resize_png_to_fit(filepath, max_bytes)
    except Exception as exc:
        return {
            "requested": True,
            "available": False,
            "note": f"Viewport screenshot could not be prepared: {type(exc).__name__}: {exc}",
            "path": filepath,
            "size_bytes": size_bytes,
        }, {}
    if not prepared_path:
        return {
            "requested": True,
            "available": False,
            "note": resize_info.get("resize_error") or f"Viewport screenshot was larger than the {max_bytes} byte limit",
            "path": filepath,
            **resize_info,
        }, {}

    final_size = os.path.getsize(prepared_path)
    with open(prepared_path, "rb") as handle:
        data = base64.b64encode(handle.read()).decode("ascii")
    try:
        preview_image = load_preview_image(prepared_path)
        preview_image_name = preview_image.name
        width, height = _image_size_tuple(preview_image)
    except Exception:
        preview_image_name = ""
        width = int(resize_info.get("width") or 0)
        height = int(resize_info.get("height") or 0)

    note = "Viewport screenshot prepared for the external client request"
    if resize_info.get("resized"):
        note = "Viewport screenshot resized and prepared for the external client request"
    capture_id = _capture_id_from_path(prepared_path)
    resource_uri = _resource_uri(capture_id)
    metadata_uri = _metadata_uri(capture_id)
    metadata = {
        "requested": True,
        "available": True,
        "capture_id": capture_id,
        "project_id": capture_info.get("project_id", ""),
        "session_id": capture_info.get("session_id", ""),
        "storage_scope": capture_info.get("storage_scope", ""),
        "capture_dir": capture_info.get("capture_dir", ""),
        "base_dir": capture_info.get("base_dir", ""),
        "fallback_reason": capture_info.get("fallback_reason", ""),
        "media_type": "image/png",
        "capture_method": capture_method,
        "path": prepared_path,
        "resource_uri": resource_uri,
        "metadata_uri": metadata_uri,
        "latest_resource_uri": LATEST_CAPTURE_RESOURCE_URI,
        "latest_metadata_uri": LATEST_CAPTURE_METADATA_URI,
        "preview_image": preview_image_name,
        "size_bytes": final_size,
        "width": width,
        "height": height,
        "note": note,
        **resize_info,
    }
    attachments = {
        "viewport_image": {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": data,
            },
        }
    }
    return metadata, attachments


def capture_viewport(context, *, capture_dir=None, max_bytes=DEFAULT_MAX_BYTES):
    """Capture the current Blender UI/viewport as a PNG attachment.

    This intentionally fails soft in background mode or when Blender's UI
    context cannot provide a screenshot operator.
    """

    if not _has_ui_context(context):
        return {
            "requested": True,
            "available": False,
            "note": "Viewport screenshot requires an interactive Blender window",
        }, {}

    resolved = resolve_capture_dir(context, preferred_dir=capture_dir, create=True)
    filepath = _capture_filepath(resolved["capture_dir"])
    try:
        method = _capture_with_operator(context, filepath)
    except Exception as exc:
        return {
            "requested": True,
            "available": False,
            "note": f"Viewport screenshot failed: {type(exc).__name__}: {exc}",
        }, {}

    return prepare_image_attachment(filepath, max_bytes=max_bytes, capture_method=method, capture_info=resolved)


def register():
    pass


def unregister():
    pass
