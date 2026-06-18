"""Asynchronous Blender render jobs and MCP resource helpers."""

from __future__ import annotations

import base64
import glob
import json
import os
import re
import subprocess
import time
import uuid

import bpy

from . import viewport_capture


LATEST_RENDER_JOB_METADATA_URI = "blender://render-jobs/latest/metadata"
METADATA_FILENAME = "metadata.json"
CHILD_STATUS_FILENAME = "child-status.json"
LOG_FILENAME = "render.log"
SCRIPT_FILENAME = "render_job.py"
BLEND_COPY_FILENAME = "render_job.blend"
FRAME_PREFIX = "frame_"
MAX_FRAME_RESOURCE_BYTES = 20 * 1024 * 1024
MAX_VIDEO_RESOURCE_BYTES = 25 * 1024 * 1024

_PROCESSES = {}


def _safe_id(value, fallback="render-job"):
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in str(value or ""))
    safe = safe.strip("._")
    return safe[:80] or fallback


def _job_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _metadata_uri(job_id):
    return f"blender://render-jobs/{_safe_id(job_id)}/metadata"


def _frame_resource_uri(job_id, frame_number):
    return f"blender://render-jobs/{_safe_id(job_id)}/frames/{int(frame_number)}"


def _log_resource_uri(job_id):
    return f"blender://render-jobs/{_safe_id(job_id)}/log"


def _video_resource_uri(job_id):
    return f"blender://render-jobs/{_safe_id(job_id)}/video"


def _job_root_info(context=None, *, preferred_dir=None, create=False):
    capture_info = viewport_capture.resolve_capture_dir(context, preferred_dir=preferred_dir, create=create)
    root = os.path.join(capture_info["capture_dir"], "render-jobs")
    if create:
        os.makedirs(root, exist_ok=True)
    return {**capture_info, "render_job_root": root}


def _job_dir_candidates(capture_dir=None, *, context=None, preferred_dir=None):
    if capture_dir:
        info = {
            "capture_dir": capture_dir,
            "storage_scope": "explicit",
            "project_id": viewport_capture.project_id(context),
            "session_id": viewport_capture.capture_session_id(),
            "base_dir": capture_dir,
            "fallback_reason": "",
        }
        return [{**info, "render_job_root": os.path.join(capture_dir, "render-jobs")}]
    return [
        {**info, "render_job_root": os.path.join(info["capture_dir"], "render-jobs")}
        for info in viewport_capture.capture_dir_candidates(context=context, preferred_dir=preferred_dir)
    ]


def _metadata_path(job_dir):
    return os.path.join(job_dir, METADATA_FILENAME)


def _child_status_path(job_dir):
    return os.path.join(job_dir, CHILD_STATUS_FILENAME)


def _write_json(path, payload):
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    os.replace(temp_path, path)
    return path


def _read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _metadata_candidates(capture_dir=None, *, context=None, preferred_dir=None):
    candidates = []
    for info in _job_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        root = info["render_job_root"]
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            metadata_path = os.path.join(root, name, METADATA_FILENAME)
            if os.path.isfile(metadata_path):
                candidates.append(metadata_path)
    return candidates


def _metadata_for_id(job_id, capture_dir=None, *, context=None, preferred_dir=None):
    job_id = _safe_id(job_id, "")
    if not job_id:
        return None
    for info in _job_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        metadata_path = os.path.join(info["render_job_root"], job_id, METADATA_FILENAME)
        if os.path.isfile(metadata_path):
            return _read_json(metadata_path)
    return None


def _frame_path(frames_dir, frame_number):
    return os.path.join(frames_dir, f"{FRAME_PREFIX}{int(frame_number):04d}.png")


def _frame_number_from_path(path):
    match = re.search(rf"{re.escape(FRAME_PREFIX)}(\d+)\.png$", os.path.basename(path), re.IGNORECASE)
    return int(match.group(1)) if match else None


def _frame_files(metadata):
    frames_dir = metadata.get("frames_dir") or ""
    if not os.path.isdir(frames_dir):
        return []
    paths = []
    for path in glob.glob(os.path.join(frames_dir, f"{FRAME_PREFIX}*.png")):
        frame_number = _frame_number_from_path(path)
        if frame_number is not None:
            paths.append((frame_number, path))
    return sorted(paths)


def _log_tail(path, max_bytes=8192):
    if not os.path.isfile(path):
        return ""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            if size > max_bytes:
                handle.seek(-max_bytes, os.SEEK_END)
            data = handle.read()
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _bounded_int(value, default, *, minimum, maximum):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    return max(int(minimum), min(int(maximum), result))


def _normalize_output_kind(value):
    normalized = str(value or "frames").strip().lower().replace("-", "_")
    if normalized in {"mp4", "mpeg4", "movie"}:
        return "video"
    if normalized not in {"frames", "video"}:
        return "frames"
    return normalized


def _copy_current_blend(blend_path):
    os.makedirs(os.path.dirname(blend_path), exist_ok=True)
    result = bpy.ops.wm.save_as_mainfile(filepath=blend_path, copy=True)
    return {str(item) for item in result}


def _child_script_text(config):
    config_text = json.dumps(config, indent=2, sort_keys=True)
    return f"""import json
import os
import traceback

import bpy

CONFIG = {config_text}


def write_status(status, **extra):
    payload = {{
        "ok": status == "completed",
        "status": status,
        "updated_at": __import__("time").time(),
    }}
    payload.update(extra)
    path = CONFIG["child_status_path"]
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8", newline="\\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    os.replace(temp, path)


def set_samples(scene, samples):
    samples = int(samples)
    if hasattr(scene, "eevee"):
        try:
            scene.eevee.taa_render_samples = samples
        except Exception:
            pass
    if hasattr(scene, "cycles"):
        try:
            scene.cycles.samples = samples
        except Exception:
            pass


try:
    scene = bpy.context.scene
    camera_name = CONFIG.get("camera_name") or ""
    if camera_name:
        camera = bpy.data.objects.get(camera_name)
        if camera is None or getattr(camera, "type", "") != "CAMERA":
            raise RuntimeError("Camera not found: " + camera_name)
        scene.camera = camera

    scene.frame_start = int(CONFIG["frame_start"])
    scene.frame_end = int(CONFIG["frame_end"])
    scene.render.resolution_x = int(CONFIG["resolution_x"])
    scene.render.resolution_y = int(CONFIG["resolution_y"])
    scene.render.resolution_percentage = int(CONFIG["resolution_percentage"])
    scene.render.fps = int(CONFIG["fps"])
    scene.render.use_file_extension = True
    set_samples(scene, int(CONFIG["samples"]))

    output_kind = CONFIG.get("output_kind", "frames")
    if output_kind == "video":
        scene.render.image_settings.file_format = "FFMPEG"
        scene.render.filepath = CONFIG["video_path"]
        try:
            scene.render.ffmpeg.format = "MPEG4"
            scene.render.ffmpeg.codec = "H264"
            scene.render.ffmpeg.constant_rate_factor = CONFIG.get("quality", "HIGH")
        except Exception:
            pass
    else:
        os.makedirs(CONFIG["frames_dir"], exist_ok=True)
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = os.path.join(CONFIG["frames_dir"], "{FRAME_PREFIX}")

    write_status("running", message="Render started")
    bpy.ops.render.render(animation=True)
    write_status("completed", message="Render completed")
except Exception as exc:
    write_status("failed", message=f"{{type(exc).__name__}}: {{exc}}", traceback=traceback.format_exc())
    raise
"""


def start_render_job(
    context,
    *,
    frame_start=None,
    frame_end=None,
    resolution_x=1920,
    resolution_y=1080,
    resolution_percentage=100,
    samples=64,
    fps=None,
    camera_name="",
    output_kind="frames",
    job_name="",
    note="",
    capture_dir=None,
):
    scene = context.scene
    start = _bounded_int(frame_start, scene.frame_start, minimum=-100000, maximum=100000)
    end = _bounded_int(frame_end, scene.frame_end, minimum=-100000, maximum=100000)
    if end < start:
        start, end = end, start
    total_frames = end - start + 1
    if total_frames > 20000:
        return {"ok": False, "message": "Render job frame range is too large; limit is 20000 frames"}

    output_kind = _normalize_output_kind(output_kind)
    render_job_id = _job_id()
    info = _job_root_info(context, preferred_dir=capture_dir, create=True)
    job_dir = os.path.join(info["render_job_root"], render_job_id)
    frames_dir = os.path.join(job_dir, "frames")
    os.makedirs(job_dir, exist_ok=True)
    if output_kind == "frames":
        os.makedirs(frames_dir, exist_ok=True)

    blend_path = os.path.join(job_dir, BLEND_COPY_FILENAME)
    script_path = os.path.join(job_dir, SCRIPT_FILENAME)
    log_path = os.path.join(job_dir, LOG_FILENAME)
    video_path = os.path.join(job_dir, "render.mp4")
    child_status_path = _child_status_path(job_dir)
    blender_binary = getattr(bpy.app, "binary_path", "") or "blender"
    fps_value = _bounded_int(fps, getattr(scene.render, "fps", 24) or 24, minimum=1, maximum=240)

    metadata = {
        "ok": True,
        "available": True,
        "status": "starting",
        "job_id": render_job_id,
        "job_name": str(job_name or "")[:120],
        "note": str(note or "")[:1000],
        "created_at": time.time(),
        "started_at": 0.0,
        "completed_at": 0.0,
        "project_id": info.get("project_id", ""),
        "session_id": info.get("session_id", ""),
        "storage_scope": info.get("storage_scope", ""),
        "capture_dir": info.get("capture_dir", ""),
        "base_dir": info.get("base_dir", ""),
        "fallback_reason": info.get("fallback_reason", ""),
        "job_dir": job_dir,
        "frames_dir": frames_dir,
        "blend_path": blend_path,
        "script_path": script_path,
        "log_path": log_path,
        "video_path": video_path if output_kind == "video" else "",
        "metadata_path": _metadata_path(job_dir),
        "child_status_path": child_status_path,
        "metadata_uri": _metadata_uri(render_job_id),
        "latest_metadata_uri": LATEST_RENDER_JOB_METADATA_URI,
        "log_resource_uri": _log_resource_uri(render_job_id),
        "video_resource_uri": _video_resource_uri(render_job_id) if output_kind == "video" else "",
        "output_kind": output_kind,
        "frame_start": start,
        "frame_end": end,
        "total_frames": total_frames,
        "fps": fps_value,
        "resolution_x": _bounded_int(resolution_x, 1920, minimum=16, maximum=8192),
        "resolution_y": _bounded_int(resolution_y, 1080, minimum=16, maximum=8192),
        "resolution_percentage": _bounded_int(resolution_percentage, 100, minimum=1, maximum=100),
        "samples": _bounded_int(samples, 64, minimum=1, maximum=4096),
        "camera_name": str(camera_name or "")[:120],
        "pid": 0,
        "returncode": None,
        "frame_count": 0,
        "progress": 0.0,
        "newest_frame": None,
        "newest_frame_resource_uri": "",
        "message": "Render job prepared",
    }
    _write_json(metadata["metadata_path"], metadata)

    try:
        copy_result = _copy_current_blend(blend_path)
        metadata["blend_copy_result"] = sorted(copy_result)
        config = {
            "frame_start": start,
            "frame_end": end,
            "resolution_x": metadata["resolution_x"],
            "resolution_y": metadata["resolution_y"],
            "resolution_percentage": metadata["resolution_percentage"],
            "samples": metadata["samples"],
            "fps": fps_value,
            "camera_name": metadata["camera_name"],
            "output_kind": output_kind,
            "frames_dir": frames_dir,
            "video_path": video_path,
            "child_status_path": child_status_path,
            "quality": "HIGH",
        }
        with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_child_script_text(config))
        command = [blender_binary, "--background", blend_path, "--python", script_path]
        log_handle = open(log_path, "w", encoding="utf-8", newline="\n")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            command,
            cwd=job_dir,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        log_handle.close()
        _PROCESSES[render_job_id] = process
        metadata.update(
            {
                "status": "running",
                "started_at": time.time(),
                "pid": int(process.pid or 0),
                "message": "Render job started in a background Blender process",
            }
        )
        _write_json(metadata["metadata_path"], metadata)
    except Exception as exc:
        metadata.update(
            {
                "ok": False,
                "status": "failed",
                "completed_at": time.time(),
                "message": f"Failed to start render job: {type(exc).__name__}: {exc}",
            }
        )
        _write_json(metadata["metadata_path"], metadata)
        return {"ok": False, "message": metadata["message"], "render_job": metadata}

    return {"ok": True, "message": metadata["message"], "render_job": render_job_status(render_job_id, context=context, preferred_dir=capture_dir)}


def render_job_status(job_id, *, context=None, preferred_dir=None, capture_dir=None):
    metadata = _metadata_for_id(job_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if not metadata:
        return {
            "ok": False,
            "available": False,
            "job_id": str(job_id or ""),
            "metadata_uri": _metadata_uri(job_id),
            "message": "Render job was not found for this Blender project/session",
        }

    job_id = metadata.get("job_id", str(job_id or ""))
    process = _PROCESSES.get(job_id)
    returncode = None
    if process is not None:
        returncode = process.poll()
        metadata["returncode"] = returncode

    child_status_path = metadata.get("child_status_path") or ""
    child_status = {}
    if os.path.isfile(child_status_path):
        try:
            child_status = _read_json(child_status_path)
        except (OSError, json.JSONDecodeError):
            child_status = {}

    frame_files = _frame_files(metadata)
    frame_count = len(frame_files)
    newest = frame_files[-1] if frame_files else None
    total = int(metadata.get("total_frames", 0) or 0)
    status = str(metadata.get("status") or "unknown")
    message = str(metadata.get("message") or "")
    process_running = process is not None and returncode is None

    if child_status:
        status = str(child_status.get("status") or status)
        message = str(child_status.get("message") or message)
    if process_running:
        status = "running"
    elif returncode == 0 and status not in {"completed", "cancelled"}:
        status = "completed"
        message = "Render completed"
    elif returncode not in {None, 0} and status != "cancelled":
        status = "failed"
        message = message or f"Render process exited with code {returncode}"
    elif process is None and status == "running":
        status = "unknown"
        message = "Render process is not tracked by this Blender bridge session"
    if metadata.get("output_kind") == "frames" and total and frame_count >= total and status == "unknown":
        status = "completed"
        message = "All expected frame files are present"

    if status in {"completed", "failed", "cancelled"} and not metadata.get("completed_at"):
        metadata["completed_at"] = time.time()
    metadata.update(
        {
            "status": status,
            "message": message,
            "frame_count": frame_count,
            "progress": round((frame_count / total), 4) if total and metadata.get("output_kind") == "frames" else (1.0 if status == "completed" else 0.0),
            "newest_frame": newest[0] if newest else None,
            "newest_frame_path": newest[1] if newest else "",
            "newest_frame_resource_uri": _frame_resource_uri(job_id, newest[0]) if newest else "",
            "returncode": returncode if returncode is not None else metadata.get("returncode"),
            "updated_at": time.time(),
            "log_tail": _log_tail(metadata.get("log_path") or "", max_bytes=4096),
        }
    )
    if metadata.get("output_kind") == "video":
        video_path = metadata.get("video_path") or ""
        metadata["video_available"] = bool(video_path and os.path.isfile(video_path))
        metadata["video_size_bytes"] = os.path.getsize(video_path) if metadata["video_available"] else 0
    _write_json(metadata["metadata_path"], metadata)
    return metadata


def latest_render_job_metadata(capture_dir=None, *, context=None, preferred_dir=None):
    newest = []
    for metadata_path in _metadata_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        try:
            metadata = _read_json(metadata_path)
        except (OSError, json.JSONDecodeError):
            continue
        newest.append((metadata.get("created_at", 0.0), os.path.getmtime(metadata_path), metadata))
    if newest:
        metadata = max(newest, key=lambda item: (item[0], item[1]))[2]
        return render_job_status(metadata.get("job_id"), context=context, preferred_dir=preferred_dir, capture_dir=capture_dir)
    info = _job_root_info(context, preferred_dir=preferred_dir)
    return {
        "ok": False,
        "available": False,
        "project_id": info.get("project_id", ""),
        "session_id": info.get("session_id", ""),
        "storage_scope": info.get("storage_scope", ""),
        "metadata_uri": LATEST_RENDER_JOB_METADATA_URI,
        "note": "No render job is available yet",
    }


def cancel_render_job(job_id, *, context=None, preferred_dir=None, capture_dir=None):
    metadata = render_job_status(job_id, context=context, preferred_dir=preferred_dir, capture_dir=capture_dir)
    if not metadata.get("available", True) and not metadata.get("ok"):
        return metadata
    job_id = metadata.get("job_id", str(job_id or ""))
    process = _PROCESSES.get(job_id)
    if process is None:
        return {"ok": False, "message": "Render job process is not tracked by this Blender bridge session", "render_job": metadata}
    if process.poll() is not None:
        return {"ok": True, "message": "Render job is already stopped", "render_job": metadata}
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    metadata.update({"status": "cancelled", "completed_at": time.time(), "message": "Render job cancelled"})
    _write_json(metadata["metadata_path"], metadata)
    return {"ok": True, "message": "Render job cancelled", "render_job": metadata}


def render_job_frame_resource(job_id, frame_number, capture_dir=None, *, context=None, preferred_dir=None):
    metadata = _metadata_for_id(job_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if not metadata:
        return None
    path = _frame_path(metadata.get("frames_dir") or "", frame_number)
    if not os.path.isfile(path) or os.path.getsize(path) > MAX_FRAME_RESOURCE_BYTES:
        return None
    with open(path, "rb") as handle:
        data = base64.b64encode(handle.read()).decode("ascii")
    return {
        "mimeType": "image/png",
        "blob": data,
        "path": path,
        "jobId": metadata.get("job_id", ""),
        "frame": int(frame_number),
        "resourceUri": _frame_resource_uri(metadata.get("job_id", ""), frame_number),
        "metadataUri": metadata.get("metadata_uri", ""),
        "sizeBytes": os.path.getsize(path),
    }


def render_job_log_resource(job_id, capture_dir=None, *, context=None, preferred_dir=None):
    metadata = _metadata_for_id(job_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if not metadata:
        return None
    path = metadata.get("log_path") or ""
    if not os.path.isfile(path):
        return None
    return {
        "mimeType": "text/plain",
        "text": _log_tail(path, max_bytes=65536),
        "path": path,
        "jobId": metadata.get("job_id", ""),
        "metadataUri": metadata.get("metadata_uri", ""),
    }


def render_job_video_resource(job_id, capture_dir=None, *, context=None, preferred_dir=None):
    metadata = _metadata_for_id(job_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if not metadata:
        return None
    path = metadata.get("video_path") or ""
    if not os.path.isfile(path):
        return None
    size = os.path.getsize(path)
    if size > MAX_VIDEO_RESOURCE_BYTES:
        return {
            "mimeType": "application/json",
            "text": json.dumps(
                {
                    "ok": False,
                    "available": True,
                    "too_large": True,
                    "path": path,
                    "size_bytes": size,
                    "message": "Video is too large to return as a base64 MCP resource; use the local path.",
                },
                indent=2,
                sort_keys=True,
            ),
        }
    with open(path, "rb") as handle:
        data = base64.b64encode(handle.read()).decode("ascii")
    return {
        "mimeType": "video/mp4",
        "blob": data,
        "path": path,
        "jobId": metadata.get("job_id", ""),
        "resourceUri": _video_resource_uri(metadata.get("job_id", "")),
        "metadataUri": metadata.get("metadata_uri", ""),
        "sizeBytes": size,
    }


def parse_render_job_resource_uri(uri):
    uri = str(uri or "")
    prefix = "blender://render-jobs/"
    if not uri.startswith(prefix):
        return "", "", ""
    tail = uri[len(prefix) :]
    if tail == "latest/metadata":
        return "latest", "metadata", ""
    parts = tail.split("/")
    if len(parts) == 2 and parts[1] == "metadata":
        return _safe_id(parts[0], ""), "metadata", ""
    if len(parts) == 2 and parts[1] == "log":
        return _safe_id(parts[0], ""), "log", ""
    if len(parts) == 2 and parts[1] == "video":
        return _safe_id(parts[0], ""), "video", ""
    if len(parts) == 3 and parts[1] == "frames":
        return _safe_id(parts[0], ""), "frame", parts[2]
    return "", "", ""


def register():
    pass


def unregister():
    for process in list(_PROCESSES.values()):
        if process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass
    _PROCESSES.clear()
