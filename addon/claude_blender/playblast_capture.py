"""Animation playblast frame capture and MCP resource helpers."""

from __future__ import annotations

import base64
import json
import os
import time
import uuid

import bpy

from . import live_preview, viewport_capture


LATEST_PLAYBLAST_METADATA_URI = "blender://playblasts/latest/metadata"
DEFAULT_MAX_FRAMES = 12
MAX_PLAYBLAST_FRAMES = 48
DEFAULT_PLAYBLAST_QUALITY = "preview"
DEFAULT_PLAYBLAST_MAX_WIDTH = 640
DEFAULT_PLAYBLAST_MAX_HEIGHT = 360
PLAYBLAST_QUALITY_PRESETS = {
    "low": (DEFAULT_PLAYBLAST_MAX_WIDTH, DEFAULT_PLAYBLAST_MAX_HEIGHT),
    "preview": (DEFAULT_PLAYBLAST_MAX_WIDTH, DEFAULT_PLAYBLAST_MAX_HEIGHT),
    "standard": (960, 540),
    "medium": (960, 540),
    "high": (1280, 720),
    "hd": (1280, 720),
    "source": (0, 0),
    "original": (0, 0),
    "full": (0, 0),
}
METADATA_FILENAME = "metadata.json"


def _playblast_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _safe_id(value):
    value = str(value or "").strip()
    if not value or "/" in value or "\\" in value:
        return ""
    return value


def _metadata_uri(playblast_id):
    return f"blender://playblasts/{playblast_id}/metadata"


def _frame_resource_uri(playblast_id, frame_number):
    return f"blender://playblasts/{playblast_id}/frames/{int(frame_number)}"


def _playblast_root_info(context=None, *, preferred_dir=None, create=False):
    capture_info = viewport_capture.resolve_capture_dir(context, preferred_dir=preferred_dir, create=create)
    root = os.path.join(capture_info["capture_dir"], "playblasts")
    if create:
        os.makedirs(root, exist_ok=True)
    return {**capture_info, "playblast_root": root}


def _playblast_dir_candidates(capture_dir=None, *, context=None, preferred_dir=None):
    if capture_dir:
        info = {
            "capture_dir": capture_dir,
            "storage_scope": "explicit",
            "project_id": viewport_capture.project_id(context),
            "session_id": viewport_capture.capture_session_id(),
            "base_dir": capture_dir,
            "fallback_reason": "",
        }
        return [{**info, "playblast_root": os.path.join(capture_dir, "playblasts")}]
    candidates = []
    for info in viewport_capture.capture_dir_candidates(context=context, preferred_dir=preferred_dir):
        candidates.append({**info, "playblast_root": os.path.join(info["capture_dir"], "playblasts")})
    return candidates


def _metadata_path(playblast_dir):
    return os.path.join(playblast_dir, METADATA_FILENAME)


def _write_metadata(metadata):
    path = metadata.get("metadata_path") or _metadata_path(metadata["playblast_dir"])
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(metadata, handle, indent=2, sort_keys=True)
    return path


def _read_metadata(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _metadata_candidates(capture_dir=None, *, context=None, preferred_dir=None):
    candidates = []
    for info in _playblast_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        root = info["playblast_root"]
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            metadata_path = os.path.join(root, name, METADATA_FILENAME)
            if os.path.isfile(metadata_path):
                candidates.append((metadata_path, info))
    return candidates


def _metadata_for_id(playblast_id, capture_dir=None, *, context=None, preferred_dir=None):
    playblast_id = _safe_id(playblast_id)
    if not playblast_id:
        return None
    for info in _playblast_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        metadata_path = os.path.join(info["playblast_root"], playblast_id, METADATA_FILENAME)
        if os.path.isfile(metadata_path):
            return _read_metadata(metadata_path)
    return None


def latest_playblast_metadata(capture_dir=None, *, context=None, preferred_dir=None):
    newest = []
    for metadata_path, _info in _metadata_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        try:
            metadata = _read_metadata(metadata_path)
        except (OSError, json.JSONDecodeError):
            continue
        newest.append((metadata.get("created_at", 0.0), os.path.getmtime(metadata_path), metadata))
    if newest:
        return max(newest, key=lambda item: (item[0], item[1]))[2]
    info = _playblast_root_info(context, preferred_dir=preferred_dir)
    return {
        "ok": False,
        "available": False,
        "project_id": info.get("project_id", ""),
        "session_id": info.get("session_id", ""),
        "storage_scope": info.get("storage_scope", ""),
        "metadata_uri": LATEST_PLAYBLAST_METADATA_URI,
        "note": "No animation playblast capture is available yet",
    }


def playblast_metadata(playblast_id, capture_dir=None, *, context=None, preferred_dir=None):
    metadata = _metadata_for_id(playblast_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if metadata:
        return metadata
    info = _playblast_root_info(context, preferred_dir=preferred_dir)
    return {
        "ok": False,
        "available": False,
        "playblast_id": str(playblast_id or ""),
        "project_id": info.get("project_id", ""),
        "session_id": info.get("session_id", ""),
        "storage_scope": info.get("storage_scope", ""),
        "metadata_uri": _metadata_uri(playblast_id),
        "note": "Animation playblast capture was not found for this Blender project/session",
    }


def playblast_frame_resource(playblast_id, frame_number, capture_dir=None, *, context=None, preferred_dir=None):
    metadata = _metadata_for_id(playblast_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if not metadata:
        return None
    try:
        frame_token = str(int(frame_number))
    except (TypeError, ValueError):
        return None
    for frame in metadata.get("frames") or []:
        if str(frame.get("frame")) != frame_token:
            continue
        path = frame.get("path") or ""
        if not frame.get("available") or not os.path.isfile(path):
            return None
        with open(path, "rb") as handle:
            data = base64.b64encode(handle.read()).decode("ascii")
        return {
            "mimeType": "image/png",
            "blob": data,
            "path": path,
            "playblastId": metadata.get("playblast_id", ""),
            "frame": int(frame.get("frame", 0) or 0),
            "resourceUri": frame.get("resource_uri", ""),
            "metadataUri": metadata.get("metadata_uri", ""),
            "sizeBytes": int(frame.get("size_bytes", 0) or 0),
            "width": int(frame.get("width", 0) or 0),
            "height": int(frame.get("height", 0) or 0),
        }
    return None


def parse_playblast_resource_uri(uri):
    uri = str(uri or "")
    prefix = "blender://playblasts/"
    if not uri.startswith(prefix):
        return "", "", ""
    tail = uri[len(prefix) :]
    if tail == "latest/metadata":
        return "latest", "metadata", ""
    parts = tail.split("/")
    if len(parts) == 2 and parts[1] == "metadata":
        return _safe_id(parts[0]), "metadata", ""
    if len(parts) == 3 and parts[1] == "frames":
        return _safe_id(parts[0]), "frame", parts[2]
    return "", "", ""


def _sample_frames(frame_start, frame_end, max_frames):
    start = int(frame_start)
    end = int(frame_end)
    if end < start:
        start, end = end, start
    max_frames = max(1, min(MAX_PLAYBLAST_FRAMES, int(max_frames or DEFAULT_MAX_FRAMES)))
    total = end - start + 1
    if total <= max_frames:
        return list(range(start, end + 1))
    if max_frames == 1:
        return [start]
    sampled = []
    span = end - start
    for index in range(max_frames):
        sampled.append(int(round(start + (span * index / (max_frames - 1)))))
    return sorted(set(sampled))


def _duration_label(seconds):
    try:
        seconds = int(round(float(seconds)))
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0:
        return "unknown"
    if seconds < 90:
        return f"about {seconds}s"
    minutes = int(round(seconds / 60.0))
    return f"about {minutes} min"


def _estimated_capture_seconds(frame_count):
    try:
        count = max(1, int(frame_count))
    except (TypeError, ValueError):
        count = DEFAULT_MAX_FRAMES
    return max(2, int(round(count * 1.25)))


def _poll_interval_seconds(estimated_seconds):
    try:
        estimated = int(round(float(estimated_seconds)))
    except (TypeError, ValueError):
        estimated = 0
    if estimated <= 10:
        return 2
    if estimated <= 60:
        return 5
    return 10


def _playblast_quality_limits(quality, max_width=None, max_height=None):
    normalized = str(quality or DEFAULT_PLAYBLAST_QUALITY).strip().lower() or DEFAULT_PLAYBLAST_QUALITY
    preset = PLAYBLAST_QUALITY_PRESETS.get(
        normalized,
        PLAYBLAST_QUALITY_PRESETS[DEFAULT_PLAYBLAST_QUALITY],
    )
    try:
        width = int(max_width) if max_width is not None else int(preset[0])
    except (TypeError, ValueError):
        width = int(preset[0])
    try:
        height = int(max_height) if max_height is not None else int(preset[1])
    except (TypeError, ValueError):
        height = int(preset[1])
    width = max(0, min(4096, width))
    height = max(0, min(4096, height))
    if not width and not height and normalized not in {"source", "original", "full"}:
        normalized = DEFAULT_PLAYBLAST_QUALITY
        width, height = PLAYBLAST_QUALITY_PRESETS[normalized]
    return normalized, width, height


def _flush_frame_capture_view(context):
    live_preview.redraw(context)
    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        pass


def capture_animation_playblast(
    context,
    *,
    frame_start=None,
    frame_end=None,
    max_frames=DEFAULT_MAX_FRAMES,
    max_bytes=viewport_capture.DEFAULT_MAX_BYTES,
    quality=DEFAULT_PLAYBLAST_QUALITY,
    max_width=None,
    max_height=None,
    brief="",
    capture_dir=None,
):
    scene = context.scene
    start = int(frame_start if frame_start is not None else scene.frame_start)
    end = int(frame_end if frame_end is not None else scene.frame_end)
    sampled_frames = _sample_frames(start, end, max_frames)
    estimated_seconds = _estimated_capture_seconds(len(sampled_frames))
    poll_interval = _poll_interval_seconds(estimated_seconds)
    quality, resolved_max_width, resolved_max_height = _playblast_quality_limits(quality, max_width=max_width, max_height=max_height)
    quality_note = (
        f"Frames are capped to {resolved_max_width or 'source'}x{resolved_max_height or 'source'} by default-quality policy."
        if resolved_max_width or resolved_max_height
        else "Frames keep source viewport dimensions because source/original quality was requested."
    )
    if not viewport_capture.has_ui_context(context):
        return {
            "ok": False,
            "requested": True,
            "available": False,
            "frame_start": start,
            "frame_end": end,
            "sampled_frames": sampled_frames,
            "estimated_seconds": estimated_seconds,
            "estimated_duration": _duration_label(estimated_seconds),
            "poll_after_seconds": poll_interval,
            "timeout_safe": False,
            "quality": quality,
            "max_width": resolved_max_width,
            "max_height": resolved_max_height,
            "client_guidance": (
                "Synchronous sampled viewport playblast capture can block the bridge while frames are captured. "
                f"{quality_note} "
                "If an MCP client times out, wait, call blender_bridge_status, then inspect latest playblast metadata."
            ),
            "note": "Animation playblast capture requires an interactive Blender window",
        }

    capture_info = _playblast_root_info(context, preferred_dir=capture_dir, create=True)
    playblast_id = _playblast_id()
    playblast_dir = os.path.join(capture_info["playblast_root"], playblast_id)
    os.makedirs(playblast_dir, exist_ok=True)
    current_frame = int(scene.frame_current)
    frames = []
    method = ""
    try:
        for frame_number in sampled_frames:
            filepath = os.path.join(playblast_dir, f"frame-{int(frame_number):04d}.png")
            try:
                scene.frame_set(frame_number)
                _flush_frame_capture_view(context)
                method = viewport_capture.capture_viewport_to_file(context, filepath)
                frame_metadata, _attachments = viewport_capture.prepare_image_attachment(
                    filepath,
                    max_bytes=max_bytes,
                    capture_method=method,
                    capture_info=capture_info,
                    max_width=resolved_max_width,
                    max_height=resolved_max_height,
                )
            except Exception as exc:
                frame_metadata = {
                    "available": False,
                    "path": filepath,
                    "size_bytes": 0,
                    "width": 0,
                    "height": 0,
                    "note": f"Animation playblast frame capture failed: {type(exc).__name__}: {exc}",
                }
            frames.append(
                {
                    "frame": int(frame_number),
                    "captured_scene_frame": int(scene.frame_current),
                    "available": bool(frame_metadata.get("available")),
                    "path": frame_metadata.get("path", filepath),
                    "resource_uri": _frame_resource_uri(playblast_id, frame_number),
                    "size_bytes": int(frame_metadata.get("size_bytes", 0) or 0),
                    "width": int(frame_metadata.get("width", 0) or 0),
                    "height": int(frame_metadata.get("height", 0) or 0),
                    "original_width": int(frame_metadata.get("original_width", 0) or 0),
                    "original_height": int(frame_metadata.get("original_height", 0) or 0),
                    "resized": bool(frame_metadata.get("resized")),
                    "dimension_limited": bool(frame_metadata.get("dimension_limited")),
                    "note": frame_metadata.get("note", ""),
                }
            )
    finally:
        scene.frame_set(current_frame)

    available_frames = [frame for frame in frames if frame.get("available")]
    metadata = {
        "ok": bool(available_frames),
        "requested": True,
        "available": bool(available_frames),
        "playblast_id": playblast_id,
        "project_id": capture_info.get("project_id", ""),
        "session_id": capture_info.get("session_id", ""),
        "storage_scope": capture_info.get("storage_scope", ""),
        "capture_dir": capture_info.get("capture_dir", ""),
        "base_dir": capture_info.get("base_dir", ""),
        "fallback_reason": capture_info.get("fallback_reason", ""),
        "playblast_dir": playblast_dir,
        "metadata_uri": _metadata_uri(playblast_id),
        "latest_metadata_uri": LATEST_PLAYBLAST_METADATA_URI,
        "created_at": time.time(),
        "scene": scene.name,
        "fps": int(getattr(scene.render, "fps", 24) or 24),
        "frame_start": start,
        "frame_end": end,
        "current_frame_restored": current_frame,
        "sampled_frames": sampled_frames,
        "frame_count": len(available_frames),
        "requested_frame_count": len(sampled_frames),
        "estimated_seconds": estimated_seconds,
        "estimated_duration": _duration_label(estimated_seconds),
        "poll_after_seconds": poll_interval,
        "timeout_safe": False,
        "quality": quality,
        "max_width": resolved_max_width,
        "max_height": resolved_max_height,
        "capture_method": method,
        "brief": str(brief or "")[:1000],
        "resource_type": "png_frame_sequence",
        "frames": frames,
        "client_guidance": (
            "This sampled playblast ran synchronously on Blender's main thread. "
            f"Rough expected duration was {_duration_label(estimated_seconds)} for {len(sampled_frames)} sampled frame(s). "
            f"{quality_note} "
            "If an MCP client times out during capture, wait, call blender_bridge_status, then inspect latest playblast metadata before recapturing."
        ),
        "review_hints": [
            "Compare sampled frames against the requested animation brief.",
            "Check staging, silhouettes, arcs, timing spacing, contact points, and camera framing.",
            "Use exact frame resources when a single pose or contact point needs inspection.",
        ],
        "note": "Animation playblast frames are available as MCP image resources" if available_frames else "No playblast frames were captured",
    }
    metadata["metadata_path"] = _metadata_path(playblast_dir)
    _write_metadata(metadata)
    return metadata


def register():
    pass


def unregister():
    pass
