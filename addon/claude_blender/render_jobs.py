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
ASSEMBLY_LOG_FILENAME = "assembly.log"
ASSEMBLY_SCRIPT_FILENAME = "assemble_video.py"
BLEND_COPY_FILENAME = "render_job.blend"
FRAME_PREFIX = "frame_"
MAX_FRAME_RESOURCE_BYTES = 20 * 1024 * 1024
MAX_VIDEO_RESOURCE_BYTES = 25 * 1024 * 1024
DEFAULT_RENDER_POLL_INTERVAL_SECONDS = 5
DEFAULT_FINAL_RENDER_WIDTH = 1920
DEFAULT_FINAL_RENDER_HEIGHT = 1080
DEFAULT_FINAL_RENDER_SAMPLES = 64
DEFAULT_PLAYBLAST_RENDER_WIDTH = 640
DEFAULT_PLAYBLAST_RENDER_HEIGHT = 360
DEFAULT_PLAYBLAST_RENDER_SAMPLES = 8
PREVIEW_INTENT_TERMS = {
    "playblast",
    "preview",
    "review",
    "draft",
    "quick",
    "rough",
    "blocking",
    "motion check",
    "timing check",
}

_PROCESSES = {}


def _child_env():
    """Environment for background Blender child processes with bridge secrets removed."""
    env = dict(os.environ)
    for key in ("BLENDER_BRIDGE_TOKEN", "BLENDER_BRIDGE_URL"):
        env.pop(key, None)
    return env


def _pid_alive(pid):
    """Best-effort cross-platform check that a process id is still running."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return False
            try:
                exit_code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


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
    if minutes < 90:
        return f"about {minutes} min"
    hours = minutes / 60.0
    return f"about {hours:.1f} hr"


def _rough_estimated_seconds(total_frames, resolution_x, resolution_y, resolution_percentage, samples):
    """Very rough render estimate for user messaging, corrected by live frame rate later."""

    try:
        frame_count = max(1, int(total_frames))
        width = max(16, int(resolution_x))
        height = max(16, int(resolution_y))
        pct = max(1, min(100, int(resolution_percentage))) / 100.0
        sample_count = max(1, int(samples))
    except (TypeError, ValueError):
        return 0
    megapixels = (width * height * pct * pct) / 1_000_000.0
    per_frame = max(0.25, 0.35 * max(0.1, megapixels) * (sample_count / 64.0))
    return max(1, int(round(frame_count * per_frame)))


def _poll_interval_seconds(total_frames, estimated_seconds):
    try:
        frame_count = int(total_frames)
        estimated = float(estimated_seconds or 0)
    except (TypeError, ValueError):
        return DEFAULT_RENDER_POLL_INTERVAL_SECONDS
    if frame_count <= 4 or estimated < 20:
        return 1
    if estimated < 180:
        return 3
    if estimated < 900:
        return 5
    return 10


def _quality_profile(quality, output_kind, job_name, note):
    requested = str(quality or "auto").strip().lower() or "auto"
    intent_text = " ".join(
        [
            str(output_kind or ""),
            str(job_name or ""),
            str(note or ""),
        ]
    ).lower()
    preview_intent = any(term in intent_text for term in PREVIEW_INTENT_TERMS)
    profile = {
        "quality": requested,
        "profile": "final",
        "resolution_x": DEFAULT_FINAL_RENDER_WIDTH,
        "resolution_y": DEFAULT_FINAL_RENDER_HEIGHT,
        "samples": DEFAULT_FINAL_RENDER_SAMPLES,
        "ffmpeg_quality": "HIGH",
        "preview_default_applied": False,
    }
    if requested in {"low", "preview", "draft", "quick"} or (requested == "auto" and preview_intent):
        profile.update(
            {
                "profile": "preview",
                "resolution_x": DEFAULT_PLAYBLAST_RENDER_WIDTH,
                "resolution_y": DEFAULT_PLAYBLAST_RENDER_HEIGHT,
                "samples": DEFAULT_PLAYBLAST_RENDER_SAMPLES,
                "ffmpeg_quality": "MEDIUM",
                "preview_default_applied": True,
            }
        )
    elif requested in {"standard", "medium"}:
        profile.update(
            {
                "profile": "standard",
                "resolution_x": 960,
                "resolution_y": 540,
                "samples": 16,
                "ffmpeg_quality": "MEDIUM",
            }
        )
    elif requested in {"high", "hd"}:
        profile.update(
            {
                "profile": "hd",
                "resolution_x": 1280,
                "resolution_y": 720,
                "samples": 32,
                "ffmpeg_quality": "HIGH",
            }
        )
    elif requested in {"final", "full", "production", "1080p"}:
        profile["quality"] = requested
    elif requested != "auto":
        profile["quality"] = "auto"
    return profile


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


def set_movie_output(scene):
    settings = scene.render.image_settings
    if hasattr(settings, "media_type"):
        settings.media_type = "VIDEO"
    else:
        settings.file_format = "FFMPEG"


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
        set_movie_output(scene)
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


def _assembly_script_text(config):
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


def sequence_collection(editor):
    strips = getattr(editor, "strips", None)
    if strips is not None:
        return strips
    return getattr(editor, "sequences", None)


def add_image_sequence(scene, frame_paths):
    editor = scene.sequence_editor_create()
    strips = sequence_collection(editor)
    if strips is None or not hasattr(strips, "new_image"):
        raise RuntimeError("Blender sequence editor image API is unavailable")
    first_path = frame_paths[0]
    strip = strips.new_image(
        name="render_job_frames",
        filepath=first_path,
        channel=1,
        frame_start=1,
    )
    directory = os.path.dirname(first_path)
    for path in frame_paths[1:]:
        if os.path.dirname(path) != directory:
            raise RuntimeError("All frame paths must be in the same directory")
        strip.elements.append(os.path.basename(path))
    try:
        strip.frame_final_duration = len(frame_paths)
    except Exception:
        pass
    return strip


def set_movie_output(scene):
    settings = scene.render.image_settings
    if hasattr(settings, "media_type"):
        settings.media_type = "VIDEO"
    else:
        settings.file_format = "FFMPEG"


try:
    frame_paths = list(CONFIG["frame_paths"])
    if not frame_paths:
        raise RuntimeError("No frame paths were provided")
    for path in frame_paths:
        if not os.path.isfile(path):
            raise RuntimeError("Frame file missing: " + path)

    output_path = CONFIG["output_path"]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    scene = bpy.context.scene
    add_image_sequence(scene, frame_paths)

    scene.frame_start = 1
    scene.frame_end = len(frame_paths)
    scene.render.fps = int(CONFIG["fps"])
    scene.render.resolution_x = int(CONFIG["resolution_x"])
    scene.render.resolution_y = int(CONFIG["resolution_y"])
    scene.render.resolution_percentage = 100
    scene.render.use_file_extension = True
    set_movie_output(scene)
    scene.render.filepath = output_path
    try:
        scene.render.ffmpeg.format = "MPEG4"
        scene.render.ffmpeg.codec = "H264"
        scene.render.ffmpeg.constant_rate_factor = CONFIG.get("quality", "HIGH")
    except Exception:
        pass

    write_status("running", message="Video assembly started", render_phase="video_assembly")
    bpy.ops.render.render(animation=True)
    final_path = output_path if os.path.isfile(output_path) else output_path + ".mp4"
    write_status(
        "completed",
        message="Video assembly completed",
        render_phase="video_assembly",
        video_path=final_path,
        video_size_bytes=os.path.getsize(final_path) if os.path.isfile(final_path) else 0,
    )
except Exception as exc:
    write_status(
        "failed",
        message=f"{{type(exc).__name__}}: {{exc}}",
        render_phase="video_assembly",
        traceback=traceback.format_exc(),
    )
    raise
"""


def start_render_job(
    context,
    *,
    frame_start=None,
    frame_end=None,
    resolution_x=None,
    resolution_y=None,
    resolution_percentage=100,
    samples=None,
    fps=None,
    camera_name="",
    output_kind="frames",
    quality="auto",
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

    quality_profile = _quality_profile(quality, output_kind, job_name, note)
    resolution_x_value = _bounded_int(resolution_x, quality_profile["resolution_x"], minimum=16, maximum=8192)
    resolution_y_value = _bounded_int(resolution_y, quality_profile["resolution_y"], minimum=16, maximum=8192)
    resolution_percentage_value = _bounded_int(resolution_percentage, 100, minimum=1, maximum=100)
    samples_value = _bounded_int(samples, quality_profile["samples"], minimum=1, maximum=4096)
    estimated_seconds = _rough_estimated_seconds(
        total_frames,
        resolution_x_value,
        resolution_y_value,
        resolution_percentage_value,
        samples_value,
    )
    poll_interval = _poll_interval_seconds(total_frames, estimated_seconds)

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
        "assembly_script_path": "",
        "assembly_log_path": "",
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
        "resolution_x": resolution_x_value,
        "resolution_y": resolution_y_value,
        "resolution_percentage": resolution_percentage_value,
        "samples": samples_value,
        "quality": quality_profile["quality"],
        "quality_profile": quality_profile["profile"],
        "preview_default_applied": bool(quality_profile["preview_default_applied"]),
        "ffmpeg_quality": quality_profile["ffmpeg_quality"],
        "estimated_seconds": estimated_seconds,
        "estimated_duration": _duration_label(estimated_seconds),
        "estimated_seconds_remaining": estimated_seconds,
        "estimated_time_remaining": _duration_label(estimated_seconds),
        "elapsed_seconds": 0,
        "frames_per_second": 0.0,
        "poll_interval_seconds": poll_interval,
        "poll_after_seconds": poll_interval,
        "timeout_safe": True,
        "client_guidance": (
            "This render runs in a background Blender process. Poll get_render_job_status "
            f"about every {poll_interval}s, then assemble/validate video output when needed. "
            "Playblast/preview/review jobs default to low resolution unless quality or resolution is specified."
        ),
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
            "quality": metadata["ffmpeg_quality"],
        }
        with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_child_script_text(config))
        command = [blender_binary, "--background", "--factory-startup", blend_path, "--python", script_path]
        log_handle = open(log_path, "w", encoding="utf-8", newline="\n")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            command,
            cwd=job_dir,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            env=_child_env(),
        )
        log_handle.close()
        _PROCESSES[render_job_id] = process
        metadata.update(
            {
                "status": "running",
                "started_at": time.time(),
                "pid": int(process.pid or 0),
                "message": (
                    "Render job started in a background Blender process; rough estimate "
                    f"{_duration_label(estimated_seconds)}"
                ),
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
        if returncode is not None:
            # Reap the finished child and stop tracking it so it does not become a
            # zombie and _PROCESSES does not grow without bound across a session.
            try:
                process.wait(timeout=0)
            except Exception:
                pass
            _PROCESSES.pop(job_id, None)

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
        for key in ("render_phase", "video_path", "video_size_bytes"):
            if key in child_status:
                metadata[key] = child_status[key]
    if process_running:
        status = "running"
    elif returncode == 0 and status not in {"completed", "failed", "cancelled"}:
        status = "completed"
        message = "Render completed"
    elif returncode not in {None, 0} and status != "cancelled":
        status = "failed"
        message = message or f"Render process exited with code {returncode}"
    elif process is None and status == "running":
        # Process not tracked in this session (e.g. Blender was restarted). Use the
        # persisted pid to distinguish "still running" from "finished but unrecorded".
        if _pid_alive(metadata.get("pid")):
            status = "running"
            message = message or "Render process still running (recovered across bridge session)"
        else:
            status = "unknown"
            message = "Render process is no longer running and final status was not recorded"
    if metadata.get("output_kind") == "frames" and total and frame_count >= total and status == "unknown":
        status = "completed"
        message = "All expected frame files are present"

    if status in {"completed", "failed", "cancelled"} and not metadata.get("completed_at"):
        metadata["completed_at"] = time.time()
    now = time.time()
    started_at = float(metadata.get("started_at") or 0.0)
    elapsed = max(0.0, now - started_at) if started_at else 0.0
    frames_per_second = round(frame_count / elapsed, 4) if frame_count and elapsed > 0.0 else 0.0
    estimated_remaining = 0
    if status in {"completed", "failed", "cancelled"}:
        estimated_remaining = 0
    elif total and metadata.get("output_kind") == "frames" and frame_count and frames_per_second > 0.0:
        estimated_remaining = int(round(max(0, total - frame_count) / frames_per_second))
    elif metadata.get("estimated_seconds") and elapsed:
        estimated_remaining = int(round(max(0.0, float(metadata.get("estimated_seconds") or 0.0) - elapsed)))
    poll_interval = _poll_interval_seconds(total, metadata.get("estimated_seconds") or estimated_remaining)

    metadata.update(
        {
            "status": status,
            "message": message,
            "frame_count": frame_count,
            "progress": round((frame_count / total), 4) if total and metadata.get("output_kind") == "frames" else (1.0 if status == "completed" else 0.0),
            "elapsed_seconds": int(round(elapsed)),
            "frames_per_second": frames_per_second,
            "estimated_seconds_remaining": estimated_remaining,
            "estimated_time_remaining": _duration_label(estimated_remaining),
            "poll_interval_seconds": poll_interval,
            "poll_after_seconds": poll_interval if status == "running" else 0,
            "newest_frame": newest[0] if newest else None,
            "newest_frame_path": newest[1] if newest else "",
            "newest_frame_resource_uri": _frame_resource_uri(job_id, newest[0]) if newest else "",
            "returncode": returncode if returncode is not None else metadata.get("returncode"),
            "updated_at": now,
            "log_tail": _log_tail(metadata.get("log_path") or "", max_bytes=4096),
        }
    )
    if metadata.get("output_kind") == "video":
        video_path = metadata.get("video_path") or ""
        metadata["video_available"] = bool(video_path and os.path.isfile(video_path))
        metadata["video_size_bytes"] = os.path.getsize(video_path) if metadata["video_available"] else 0
    else:
        video_path = metadata.get("video_path") or ""
        metadata["video_available"] = bool(video_path and os.path.isfile(video_path))
        metadata["video_size_bytes"] = os.path.getsize(video_path) if metadata["video_available"] else int(metadata.get("video_size_bytes") or 0)
    if status == "unknown" and metadata.get("output_kind") == "video" and metadata.get("video_available"):
        # Recover a finished video job whose final status was lost (e.g. restart):
        # the assembled MP4 is present, so treat it as completed.
        status = "completed"
        message = "Assembled video output is present"
        metadata["status"] = status
        metadata["message"] = message
        if not metadata.get("completed_at"):
            metadata["completed_at"] = time.time()
    assembly_log_path = metadata.get("assembly_log_path") or ""
    if assembly_log_path:
        metadata["assembly_log_tail"] = _log_tail(assembly_log_path, max_bytes=4096)
    _write_json(metadata["metadata_path"], metadata)
    return metadata


def _default_video_output_path(metadata, output_path=""):
    job_dir = metadata.get("job_dir") or os.path.dirname(metadata.get("metadata_path") or "")
    requested = str(output_path or "").strip()
    if requested:
        path = os.path.expanduser(requested)
        if not os.path.isabs(path):
            path = os.path.join(job_dir, path)
    else:
        path = os.path.join(job_dir, "render.mp4")
    if os.path.splitext(path)[1].lower() != ".mp4":
        path = f"{path}.mp4"
    return os.path.abspath(path)


def _validation_for_metadata(metadata, *, require_video=True, min_video_size_bytes=1):
    frame_files = _frame_files(metadata)
    total = int(metadata.get("total_frames", 0) or 0)
    frame_count = len(frame_files)
    video_path = metadata.get("video_path") or ""
    video_available = bool(video_path and os.path.isfile(video_path))
    video_size = os.path.getsize(video_path) if video_available else 0
    min_video_size = _bounded_int(min_video_size_bytes, 1, minimum=0, maximum=1024 * 1024 * 1024)
    checks = {
        "frame_count": frame_count,
        "total_frames": total,
        "frame_sequence_complete": bool(frame_count and (not total or frame_count >= total)),
        "newest_frame": frame_files[-1][0] if frame_files else None,
        "newest_frame_path": frame_files[-1][1] if frame_files else "",
        "video_required": bool(require_video),
        "video_available": video_available,
        "video_path": video_path,
        "video_size_bytes": video_size,
        "video_min_size_bytes": min_video_size,
        "video_size_ok": bool(video_available and video_size >= min_video_size),
    }
    warnings = []
    if not checks["frame_sequence_complete"]:
        warnings.append("Frame sequence is incomplete")
    if require_video and not video_available:
        warnings.append("MP4 video output is missing")
    if require_video and video_available and video_size < min_video_size:
        warnings.append("MP4 video output is smaller than expected")
    return {
        "ok": checks["frame_sequence_complete"] and (not require_video or checks["video_size_ok"]),
        "available": True,
        "job_id": metadata.get("job_id", ""),
        "status": metadata.get("status", ""),
        "checks": checks,
        "warnings": warnings,
        "metadata_uri": metadata.get("metadata_uri", ""),
        "log_resource_uri": metadata.get("log_resource_uri", ""),
        "video_resource_uri": metadata.get("video_resource_uri", "") if video_available else "",
        "message": "Render output validated" if not warnings else "; ".join(warnings),
    }


def validate_render_job_output(job_id, *, context=None, preferred_dir=None, capture_dir=None, require_video=True, min_video_size_bytes=1):
    metadata = render_job_status(job_id, context=context, preferred_dir=preferred_dir, capture_dir=capture_dir)
    if not metadata.get("available", True) and not metadata.get("ok"):
        return metadata
    return _validation_for_metadata(
        metadata,
        require_video=bool(require_video),
        min_video_size_bytes=min_video_size_bytes,
    )


def assemble_render_job_video(
    job_id,
    *,
    context=None,
    preferred_dir=None,
    capture_dir=None,
    fps=None,
    output_path="",
    quality="HIGH",
    overwrite=True,
    allow_partial=False,
):
    metadata = render_job_status(job_id, context=context, preferred_dir=preferred_dir, capture_dir=capture_dir)
    if not metadata.get("available", True) and not metadata.get("ok"):
        return metadata

    job_id = metadata.get("job_id", str(job_id or ""))
    process = _PROCESSES.get(job_id)
    if process is not None and process.poll() is None:
        return {
            "ok": False,
            "message": "Render job is still running; wait for completion before assembling MP4 output",
            "render_job": metadata,
        }

    frame_files = _frame_files(metadata)
    frame_count = len(frame_files)
    total = int(metadata.get("total_frames", 0) or 0)
    if not frame_files:
        return {"ok": False, "message": "Render job has no PNG frames to assemble", "render_job": metadata}
    if total and frame_count < total and not allow_partial:
        return {
            "ok": False,
            "message": f"Render job frame sequence is incomplete ({frame_count}/{total}); pass allow_partial to assemble anyway",
            "render_job": metadata,
        }

    output_path = _default_video_output_path(metadata, output_path)
    if os.path.isfile(output_path) and not overwrite:
        metadata["video_path"] = output_path
        metadata["video_resource_uri"] = _video_resource_uri(job_id)
        _write_json(metadata["metadata_path"], metadata)
        validation = _validation_for_metadata(metadata, require_video=True)
        return {
            "ok": validation["ok"],
            "message": "Existing MP4 output reused" if validation["ok"] else validation["message"],
            "render_job": render_job_status(job_id, context=context, preferred_dir=preferred_dir, capture_dir=capture_dir),
            "validation": validation,
        }

    job_dir = metadata.get("job_dir") or os.path.dirname(metadata.get("metadata_path") or output_path)
    script_path = os.path.join(job_dir, ASSEMBLY_SCRIPT_FILENAME)
    log_path = os.path.join(job_dir, ASSEMBLY_LOG_FILENAME)
    blender_binary = getattr(bpy.app, "binary_path", "") or "blender"
    fps_value = _bounded_int(fps, int(metadata.get("fps", 24) or 24), minimum=1, maximum=240)
    quality_value = str(quality or "HIGH").upper()
    if quality_value not in {"NONE", "LOWEST", "LOW", "MEDIUM", "HIGH", "PERC_LOSSLESS", "LOSSLESS"}:
        quality_value = "HIGH"
    config = {
        "frame_paths": [path for _frame, path in frame_files],
        "fps": fps_value,
        "output_path": output_path,
        "resolution_x": int(metadata.get("resolution_x", 1920) or 1920),
        "resolution_y": int(metadata.get("resolution_y", 1080) or 1080),
        "quality": quality_value,
        "child_status_path": metadata.get("child_status_path") or _child_status_path(job_dir),
    }
    try:
        with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_assembly_script_text(config))
        command = [blender_binary, "--background", "--factory-startup", "--python", script_path]
        log_handle = open(log_path, "w", encoding="utf-8", newline="\n")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            command,
            cwd=job_dir,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            env=_child_env(),
        )
        log_handle.close()
        _PROCESSES[job_id] = process
        metadata.update(
            {
                "status": "running",
                "render_phase": "video_assembly",
                "message": "Video assembly started in a background Blender process",
                "assembly_started_at": time.time(),
                "completed_at": 0.0,
                "assembly_script_path": script_path,
                "assembly_log_path": log_path,
                "video_path": output_path,
                "video_resource_uri": _video_resource_uri(job_id),
                "video_available": False,
                "video_size_bytes": 0,
                "pid": int(process.pid or 0),
                "returncode": None,
            }
        )
        _write_json(metadata["metadata_path"], metadata)
    except Exception as exc:
        metadata.update(
            {
                "ok": False,
                "status": "failed",
                "render_phase": "video_assembly",
                "completed_at": time.time(),
                "message": f"Failed to start video assembly: {type(exc).__name__}: {exc}",
            }
        )
        _write_json(metadata["metadata_path"], metadata)
        return {"ok": False, "message": metadata["message"], "render_job": metadata}

    return {
        "ok": True,
        "message": metadata["message"],
        "render_job": render_job_status(job_id, context=context, preferred_dir=preferred_dir, capture_dir=capture_dir),
    }


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
