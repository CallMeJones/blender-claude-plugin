"""Asynchronous external asset download/cache jobs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import uuid

import bpy

from . import external_assets, render_jobs, viewport_capture


METADATA_FILENAME = "metadata.json"
CONFIG_FILENAME = "worker-config.json"
CHILD_STATUS_FILENAME = "child-status.json"
LOG_FILENAME = "asset-job.log"
SCRIPT_FILENAME = "asset_job_worker.py"
DEFAULT_ASSET_JOB_POLL_INTERVAL_SECONDS = 2
ASSET_JOB_MODE_ENV = "BLENDER_AGENT_BRIDGE_ASSET_JOB_MODE"
ASSET_JOB_SECRET_TOKEN_ENV = "BLENDER_AGENT_BRIDGE_ASSET_JOB_API_TOKEN"
ASSET_JOB_SECRET_PASSWORD_ENV = "BLENDER_AGENT_BRIDGE_ASSET_JOB_MODEL_PASSWORD"

_PROCESSES = {}
_THREADS = {}
_CANCEL_REQUESTS = set()
_IMPORT_QUEUE = []
_IMPORT_ACTIVE = set()
_IMPORT_CANCEL_REQUESTS = set()
_IMPORT_TIMER_REGISTERED = False
_LOCK = threading.Lock()
_METADATA_LOCK = threading.Lock()
_IMPORT_LOCK = threading.Lock()


def _safe_id(value, fallback="asset-job"):
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in str(value or ""))
    safe = safe.strip("._")
    return safe[:80] or fallback


def _job_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _job_root_info(context=None, *, preferred_dir=None, create=False):
    capture_info = viewport_capture.resolve_capture_dir(context, preferred_dir=preferred_dir, create=create)
    root = os.path.join(capture_info["capture_dir"], "asset-jobs")
    if create:
        os.makedirs(root, exist_ok=True)
    return {**capture_info, "asset_job_root": root}


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
        return [{**info, "asset_job_root": os.path.join(capture_dir, "asset-jobs")}]
    return [
        {**info, "asset_job_root": os.path.join(info["capture_dir"], "asset-jobs")}
        for info in viewport_capture.capture_dir_candidates(context=context, preferred_dir=preferred_dir)
    ]


def _metadata_path(job_dir):
    return os.path.join(job_dir, METADATA_FILENAME)


def _config_path(job_dir):
    return os.path.join(job_dir, CONFIG_FILENAME)


def _child_status_path(job_dir):
    return os.path.join(job_dir, CHILD_STATUS_FILENAME)


def _script_path(job_dir):
    return os.path.join(job_dir, SCRIPT_FILENAME)


def _log_path(job_dir):
    return os.path.join(job_dir, LOG_FILENAME)


def _write_json(path, payload):
    temp_path = f"{path}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
    return path


def _read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _log_tail(path, max_bytes=4096):
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - int(max_bytes)))
            data = handle.read()
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _read_metadata(path):
    with _METADATA_LOCK:
        return _read_json(path)


def _write_metadata(path, payload):
    with _METADATA_LOCK:
        return _write_json(path, payload)


def _metadata_for_id(job_id, capture_dir=None, *, context=None, preferred_dir=None):
    job_id = _safe_id(job_id, "")
    if not job_id:
        return None
    for info in _job_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir):
        path = os.path.join(info["asset_job_root"], job_id, METADATA_FILENAME)
        if os.path.isfile(path):
            return _read_metadata(path)
    return None


def _asset_job_uri(job_id):
    return f"blender://asset-jobs/{_safe_id(job_id)}/metadata"


def _worker_config_args(provider, args):
    args = dict(args or {})
    if provider == "sketchfab":
        args.pop("api_token", None)
        args.pop("model_password", None)
    return args


def _child_env(args):
    env = render_jobs._child_env()
    token = str((args or {}).get("api_token") or "").strip()
    password = str((args or {}).get("model_password") or "").strip()
    if token:
        env[ASSET_JOB_SECRET_TOKEN_ENV] = token
    else:
        env.pop(ASSET_JOB_SECRET_TOKEN_ENV, None)
    if password:
        env[ASSET_JOB_SECRET_PASSWORD_ENV] = password
    else:
        env.pop(ASSET_JOB_SECRET_PASSWORD_ENV, None)
    return env


def _package_parent():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _child_script_text(config):
    config_json = json.dumps(config, sort_keys=True)
    return f"""\
from __future__ import annotations

import json
import os
import sys
import time
import traceback
import uuid

CONFIG = json.loads({config_json!r})


def write_json(path, payload):
    temp_path = f"{{path}}.{{os.getpid()}}.{{uuid.uuid4().hex}}.tmp"
    with open(temp_path, "w", encoding="utf-8", newline="\\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, default=str)
    os.replace(temp_path, path)


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def manifest_summary(manifest):
    manifest = manifest if isinstance(manifest, dict) else {{}}
    downloaded = [item for item in manifest.get("downloaded_files") or [] if isinstance(item, dict)]
    extracted = manifest.get("extracted_files") if isinstance(manifest.get("extracted_files"), list) else []
    return {{
        "ok": bool(manifest.get("ok")),
        "provider": str(manifest.get("provider") or ""),
        "asset_id": str(manifest.get("asset_id") or ""),
        "uid": str(manifest.get("uid") or ""),
        "asset_type": str(manifest.get("asset_type") or ""),
        "cache_dir": str(manifest.get("cache_dir") or ""),
        "manifest_path": str(manifest.get("manifest_path") or ""),
        "import_file": str(manifest.get("import_file") or ""),
        "downloaded_file_count": len(downloaded),
        "extracted_file_count": len(extracted),
        "import_status": str(manifest.get("import_status") or ""),
        "message": str(manifest.get("message") or ""),
    }}


def write_status(status, **updates):
    path = CONFIG["child_status_path"]
    try:
        payload = read_json(path) if os.path.isfile(path) else {{}}
    except Exception:
        payload = {{}}
    payload.update(updates)
    payload["status"] = status
    payload["updated_at"] = time.time()
    write_json(path, payload)


def progress_callback(update):
    update = update if isinstance(update, dict) else {{}}
    expected = int(update.get("expected_size") or 0)
    downloaded = int(update.get("bytes_downloaded") or 0)
    progress = round(min(0.99, max(0.0, downloaded / expected)), 4) if expected else 0.0
    write_status(
        "running",
        phase=str(update.get("phase") or "download"),
        current_url=str(update.get("url") or ""),
        current_file=str(update.get("path") or ""),
        partial_path=str(update.get("partial_path") or ""),
        bytes_downloaded=downloaded,
        expected_size_bytes=expected,
        current_file_progress=progress,
        progress=progress,
        attempt=int(update.get("attempt") or 0),
        resumed=bool(update.get("resumed", False)),
        message="External asset download/cache in progress",
    )


try:
    sys.path.insert(0, CONFIG["package_parent"])
    from claude_blender import external_assets

    provider = str(CONFIG.get("provider") or "")
    args = dict(CONFIG.get("args") or {{}})
    write_status("running", message=f"{{provider.replace('_', ' ').title()}} asset download/cache started")
    if provider == "poly_haven":
        manifest = external_assets.download_poly_haven_asset(
            asset_id=str(args.get("asset_id") or ""),
            asset_type=str(args.get("asset_type") or ""),
            resolution=str(args.get("resolution") or "2k"),
            file_format=str(args.get("file_format") or ""),
            map_types=args.get("map_types") if isinstance(args.get("map_types"), list) else None,
            include_dependencies=bool(args.get("include_dependencies", True)),
            cache_dir=str(args.get("cache_dir") or ""),
            timeout=int(args.get("timeout") or 60),
            progress_callback=progress_callback,
        )
    elif provider == "sketchfab":
        manifest = external_assets.download_sketchfab_model(
            uid=str(args.get("uid") or ""),
            api_token=os.environ.get({ASSET_JOB_SECRET_TOKEN_ENV!r}, ""),
            token_env_var=str(args.get("token_env_var") or external_assets.SKETCHFAB_TOKEN_ENV_VAR),
            model_password=os.environ.get({ASSET_JOB_SECRET_PASSWORD_ENV!r}, ""),
            cache_dir=str(args.get("cache_dir") or ""),
            timeout=int(args.get("timeout") or 120),
            progress_callback=progress_callback,
        )
    else:
        manifest = {{"ok": False, "message": f"Unsupported external asset provider: {{provider}}"}}
    status = "completed" if manifest.get("ok") else "failed"
    write_status(
        status,
        ok=bool(manifest.get("ok")),
        completed_at=time.time(),
        progress=1.0 if manifest.get("ok") else 0.0,
        poll_after_seconds=0,
        manifest_path=str(manifest.get("manifest_path") or ""),
        manifest_summary=manifest_summary(manifest),
        message=str(manifest.get("message") or ("External asset cached" if manifest.get("ok") else "External asset job failed")),
    )
except Exception as exc:
    write_status(
        "failed",
        ok=False,
        completed_at=time.time(),
        progress=0.0,
        poll_after_seconds=0,
        message=f"External asset worker failed: {{type(exc).__name__}}: {{exc}}",
        traceback=traceback.format_exc(),
    )
    raise
"""


def _bounded_int(value, default, *, minimum, maximum):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    return max(int(minimum), min(int(maximum), result))


def _redacted_parameters(provider, args):
    provider = str(provider or "").strip().lower()
    args = dict(args or {})
    if provider == "poly_haven":
        return {
            "provider": "poly_haven",
            "asset_id": str(args.get("asset_id") or ""),
            "asset_type": str(args.get("asset_type") or ""),
            "resolution": str(args.get("resolution") or ""),
            "file_format": str(args.get("file_format") or ""),
            "map_types": [str(item) for item in args.get("map_types") or []],
            "include_dependencies": bool(args.get("include_dependencies", True)),
            "cache_dir": str(args.get("cache_dir") or ""),
            "timeout": _bounded_int(args.get("timeout"), 60, minimum=1, maximum=300),
        }
    return {
        "provider": "sketchfab",
        "uid": str(args.get("uid") or ""),
        "api_token_supplied": bool(str(args.get("api_token") or "").strip()),
        "token_env_var": str(args.get("token_env_var") or external_assets.SKETCHFAB_TOKEN_ENV_VAR),
        "model_password_supplied": bool(str(args.get("model_password") or "").strip()),
        "cache_dir": str(args.get("cache_dir") or ""),
        "timeout": _bounded_int(args.get("timeout"), 120, minimum=1, maximum=300),
    }


def _manifest_summary(manifest):
    manifest = manifest if isinstance(manifest, dict) else {}
    downloaded = [item for item in manifest.get("downloaded_files") or [] if isinstance(item, dict)]
    extracted = manifest.get("extracted_files") if isinstance(manifest.get("extracted_files"), list) else []
    return {
        "ok": bool(manifest.get("ok")),
        "provider": str(manifest.get("provider") or ""),
        "asset_id": str(manifest.get("asset_id") or ""),
        "uid": str(manifest.get("uid") or ""),
        "asset_type": str(manifest.get("asset_type") or ""),
        "cache_dir": str(manifest.get("cache_dir") or ""),
        "manifest_path": str(manifest.get("manifest_path") or ""),
        "import_file": str(manifest.get("import_file") or ""),
        "downloaded_file_count": len(downloaded),
        "extracted_file_count": len(extracted),
        "import_status": str(manifest.get("import_status") or ""),
        "message": str(manifest.get("message") or ""),
    }


def _progress_metadata(update):
    update = update if isinstance(update, dict) else {}
    expected = int(update.get("expected_size") or 0)
    downloaded = int(update.get("bytes_downloaded") or 0)
    progress = round(min(0.99, max(0.0, downloaded / expected)), 4) if expected else 0.0
    return {
        "phase": str(update.get("phase") or "download"),
        "current_url": str(update.get("url") or ""),
        "current_file": str(update.get("path") or ""),
        "partial_path": str(update.get("partial_path") or ""),
        "bytes_downloaded": downloaded,
        "expected_size_bytes": expected,
        "current_file_progress": progress,
        "progress": progress,
        "attempt": int(update.get("attempt") or 0),
        "resumed": bool(update.get("resumed", False)),
        "message": "External asset download/cache in progress",
    }


def _is_cancel_requested(job_id):
    with _LOCK:
        return job_id in _CANCEL_REQUESTS


def _update_metadata(metadata_path, **updates):
    with _METADATA_LOCK:
        try:
            metadata = _read_json(metadata_path)
        except Exception:
            metadata = {}
        metadata.update(updates)
        metadata["updated_at"] = time.time()
        _write_json(metadata_path, metadata)
        return metadata


def _run_download_job(job_id, provider, args, metadata_path):
    try:
        _update_metadata(
            metadata_path,
            status="running",
            started_at=time.time(),
            message=f"{provider.replace('_', ' ').title()} asset download/cache started",
        )
        if _is_cancel_requested(job_id):
            _update_metadata(
                metadata_path,
                ok=False,
                status="cancelled",
                completed_at=time.time(),
                progress=0.0,
                poll_after_seconds=0,
                message="External asset job cancelled before download started",
            )
            return
        try:
            def progress_callback(update):
                _update_metadata(metadata_path, **_progress_metadata(update))

            if provider == "poly_haven":
                manifest = external_assets.download_poly_haven_asset(
                    asset_id=str(args.get("asset_id") or ""),
                    asset_type=str(args.get("asset_type") or ""),
                    resolution=str(args.get("resolution") or "2k"),
                    file_format=str(args.get("file_format") or ""),
                    map_types=args.get("map_types") if isinstance(args.get("map_types"), list) else None,
                    include_dependencies=bool(args.get("include_dependencies", True)),
                    cache_dir=str(args.get("cache_dir") or ""),
                    timeout=_bounded_int(args.get("timeout"), 60, minimum=1, maximum=300),
                    progress_callback=progress_callback,
                )
            elif provider == "sketchfab":
                manifest = external_assets.download_sketchfab_model(
                    uid=str(args.get("uid") or ""),
                    api_token=str(args.get("api_token") or ""),
                    token_env_var=str(args.get("token_env_var") or external_assets.SKETCHFAB_TOKEN_ENV_VAR),
                    model_password=str(args.get("model_password") or ""),
                    cache_dir=str(args.get("cache_dir") or ""),
                    timeout=_bounded_int(args.get("timeout"), 120, minimum=1, maximum=300),
                    progress_callback=progress_callback,
                )
            else:
                manifest = {"ok": False, "message": f"Unsupported external asset provider: {provider}"}
        except Exception as exc:
            manifest = {"ok": False, "message": f"External asset job failed: {type(exc).__name__}: {exc}"}

        cancelled = _is_cancel_requested(job_id)
        status = "cancelled" if cancelled else ("completed" if manifest.get("ok") else "failed")
        _update_metadata(
            metadata_path,
            ok=bool(manifest.get("ok")) and not cancelled,
            status=status,
            completed_at=time.time(),
            progress=1.0 if manifest.get("ok") and not cancelled else 0.0,
            poll_after_seconds=0,
            manifest_path=str(manifest.get("manifest_path") or ""),
            manifest_summary=_manifest_summary(manifest),
            message=(
                "External asset job cancelled after download/cache work returned"
                if cancelled
                else str(manifest.get("message") or ("External asset cached" if manifest.get("ok") else "External asset job failed"))
            ),
        )
    finally:
        with _LOCK:
            _THREADS.pop(job_id, None)
            _CANCEL_REQUESTS.discard(job_id)


def _use_in_process_worker():
    return str(os.environ.get(ASSET_JOB_MODE_ENV) or "").strip().lower() in {"thread", "in-process", "in_process", "inline"}


def _start_process_job(job_id, provider, args, metadata):
    job_dir = metadata["job_dir"]
    config_path = metadata["config_path"]
    script_path = metadata["script_path"]
    log_path = metadata["log_path"]
    child_status_path = metadata["child_status_path"]
    config = {
        "job_id": job_id,
        "provider": provider,
        "args": _worker_config_args(provider, args),
        "package_parent": _package_parent(),
        "child_status_path": child_status_path,
    }
    _write_json(config_path, config)
    with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(_child_script_text(config))

    blender_binary = getattr(bpy.app, "binary_path", "") or "blender"
    command = [blender_binary, "--background", "--factory-startup", "--python", script_path]
    log_handle = open(log_path, "w", encoding="utf-8", newline="\n")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        process = subprocess.Popen(
            command,
            cwd=job_dir,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            env=_child_env(args),
        )
    finally:
        log_handle.close()
    with _LOCK:
        _PROCESSES[job_id] = process
    return process


def _terminate_process(process, timeout=5):
    if process is None:
        return None
    if process.poll() is not None:
        return process.poll()
    try:
        process.terminate()
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
    except Exception:
        pass
    return process.poll()


def _import_queue_contains(job_id):
    with _IMPORT_LOCK:
        queued = any(item.get("job_id") == job_id for item in _IMPORT_QUEUE)
        active = job_id in _IMPORT_ACTIVE
        cancel_requested = job_id in _IMPORT_CANCEL_REQUESTS
    return queued, active, cancel_requested


def _import_timer_is_registered():
    try:
        return bool(bpy.app.timers.is_registered(_process_import_queue))
    except Exception:
        return bool(_IMPORT_TIMER_REGISTERED)


def _ensure_import_timer():
    global _IMPORT_TIMER_REGISTERED
    if _import_timer_is_registered():
        _IMPORT_TIMER_REGISTERED = True
        return
    try:
        bpy.app.timers.register(_process_import_queue, first_interval=0.1, persistent=True)
    except TypeError:
        bpy.app.timers.register(_process_import_queue, first_interval=0.1)
    _IMPORT_TIMER_REGISTERED = True


def _stop_import_timer_if_idle():
    global _IMPORT_TIMER_REGISTERED
    with _IMPORT_LOCK:
        idle = not _IMPORT_QUEUE and not _IMPORT_ACTIVE
    if not idle:
        return
    try:
        if _import_timer_is_registered():
            bpy.app.timers.unregister(_process_import_queue)
    except Exception:
        pass
    _IMPORT_TIMER_REGISTERED = False


def _process_import_queue():
    global _IMPORT_TIMER_REGISTERED
    with _IMPORT_LOCK:
        if not _IMPORT_QUEUE:
            _IMPORT_TIMER_REGISTERED = False
            return None
        item = _IMPORT_QUEUE.pop(0)
        job_id = item["job_id"]
        _IMPORT_ACTIVE.add(job_id)
        cancelled = job_id in _IMPORT_CANCEL_REQUESTS
    metadata_path = item["metadata_path"]
    if cancelled:
        _update_metadata(
            metadata_path,
            ok=False,
            status="cancelled",
            completed_at=time.time(),
            progress=0.0,
            poll_after_seconds=0,
            cancel_requested=True,
            message="External asset import job cancelled before it started",
        )
    else:
        _update_metadata(
            metadata_path,
            status="running",
            started_at=time.time(),
            phase="import",
            progress=0.0,
            message="External asset import started on Blender main thread",
        )
        try:
            result = external_assets.import_cached_asset(
                bpy.context,
                manifest_path=item.get("manifest_path", ""),
                target_object_name=item.get("target_object_name", ""),
                label=item.get("label", "") or "Import external asset job result",
            )
        except Exception as exc:
            result = {"ok": False, "message": f"External asset import failed: {type(exc).__name__}: {exc}"}
        _update_metadata(
            metadata_path,
            ok=bool(result.get("ok")),
            status="completed" if result.get("ok") else "failed",
            completed_at=time.time(),
            progress=1.0 if result.get("ok") else 0.0,
            poll_after_seconds=0,
            import_result=result,
            message=result.get("message", "External asset import finished"),
        )
    with _IMPORT_LOCK:
        _IMPORT_ACTIVE.discard(job_id)
        _IMPORT_CANCEL_REQUESTS.discard(job_id)
        keep_running = bool(_IMPORT_QUEUE)
        if not keep_running:
            _IMPORT_TIMER_REGISTERED = False
    return 0.1 if keep_running else None


def start_external_asset_download(
    context,
    *,
    provider,
    job_name="",
    note="",
    capture_dir=None,
    **args,
):
    provider = str(provider or "").strip().lower()
    if provider not in {"poly_haven", "sketchfab"}:
        return {"ok": False, "message": "provider must be poly_haven or sketchfab"}
    if provider == "poly_haven" and not str(args.get("asset_id") or "").strip():
        return {"ok": False, "message": "asset_id is required for Poly Haven jobs"}
    if provider == "sketchfab" and not str(args.get("uid") or "").strip():
        return {"ok": False, "message": "uid is required for Sketchfab jobs"}

    job_id = _job_id()
    info = _job_root_info(context, preferred_dir=capture_dir, create=True)
    job_dir = os.path.join(info["asset_job_root"], job_id)
    os.makedirs(job_dir, exist_ok=True)
    metadata_path = _metadata_path(job_dir)
    config_path = _config_path(job_dir)
    child_status_path = _child_status_path(job_dir)
    script_path = _script_path(job_dir)
    log_path = _log_path(job_dir)
    worker_type = "in_process_thread" if _use_in_process_worker() else "subprocess"
    metadata = {
        "ok": True,
        "available": True,
        "status": "starting",
        "job_id": job_id,
        "job_name": str(job_name or "")[:120],
        "note": str(note or "")[:1000],
        "provider": provider,
        "operation": "download_cache",
        "created_at": time.time(),
        "started_at": 0.0,
        "completed_at": 0.0,
        "updated_at": time.time(),
        "project_id": info.get("project_id", ""),
        "session_id": info.get("session_id", ""),
        "storage_scope": info.get("storage_scope", ""),
        "capture_dir": info.get("capture_dir", ""),
        "base_dir": info.get("base_dir", ""),
        "fallback_reason": info.get("fallback_reason", ""),
        "job_dir": job_dir,
        "config_path": config_path,
        "script_path": script_path,
        "log_path": log_path,
        "child_status_path": child_status_path,
        "metadata_path": metadata_path,
        "metadata_uri": _asset_job_uri(job_id),
        "parameters": _redacted_parameters(provider, args),
        "worker_type": worker_type,
        "pid": 0,
        "returncode": None,
        "manifest_path": "",
        "manifest_summary": {},
        "phase": "queued",
        "current_url": "",
        "current_file": "",
        "partial_path": "",
        "bytes_downloaded": 0,
        "expected_size_bytes": 0,
        "current_file_progress": 0.0,
        "attempt": 0,
        "resumed": False,
        "progress": 0.0,
        "elapsed_seconds": 0,
        "poll_interval_seconds": DEFAULT_ASSET_JOB_POLL_INTERVAL_SECONDS,
        "poll_after_seconds": DEFAULT_ASSET_JOB_POLL_INTERVAL_SECONDS,
        "cancel_requested": False,
        "message": "External asset job prepared",
        "client_guidance": (
            "This job downloads/caches external asset files outside Blender's scene mutation path. "
            "Poll get_external_asset_job_status, then call import_external_asset_job_result after completion."
        ),
    }
    _write_metadata(metadata_path, metadata)

    if worker_type == "in_process_thread":
        thread = threading.Thread(
            target=_run_download_job,
            args=(job_id, provider, dict(args), metadata_path),
            name=f"BlenderAgentBridgeAssetJob-{job_id}",
            daemon=True,
        )
        with _LOCK:
            _THREADS[job_id] = thread
        thread.start()
    else:
        try:
            process = _start_process_job(job_id, provider, dict(args), metadata)
            metadata.update(
                {
                    "status": "running",
                    "started_at": time.time(),
                    "pid": int(process.pid or 0),
                    "message": "External asset download/cache job started in a background Blender process",
                }
            )
            _write_metadata(metadata_path, metadata)
        except Exception as exc:
            metadata.update(
                {
                    "ok": False,
                    "status": "failed",
                    "completed_at": time.time(),
                    "message": f"Failed to start external asset worker: {type(exc).__name__}: {exc}",
                }
            )
            _write_metadata(metadata_path, metadata)
            return {"ok": False, "message": metadata["message"], "job_id": job_id, "asset_job": metadata}
    status = external_asset_job_status(job_id, context=context, preferred_dir=capture_dir)
    return {
        "ok": True,
        "message": "External asset download/cache job started",
        "job_id": job_id,
        "asset_job": status,
    }


def external_asset_job_status(job_id, *, context=None, preferred_dir=None, capture_dir=None):
    metadata = _metadata_for_id(job_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if not metadata:
        return {
            "ok": False,
            "available": False,
            "job_id": str(job_id or ""),
            "metadata_uri": _asset_job_uri(job_id),
            "message": "External asset job was not found for this Blender project/session",
        }
    job_id = metadata.get("job_id", str(job_id or ""))
    metadata_path = metadata.get("metadata_path", "")
    with _LOCK:
        thread = _THREADS.get(job_id)
        process = _PROCESSES.get(job_id)
        cancel_requested = job_id in _CANCEL_REQUESTS
    returncode = None
    if process is not None:
        returncode = process.poll()
        if returncode is not None:
            try:
                process.wait(timeout=0)
            except Exception:
                pass
            with _LOCK:
                _PROCESSES.pop(job_id, None)
    thread_running = bool(thread and thread.is_alive())
    process_running = bool(process and returncode is None)
    child_status_path = metadata.get("child_status_path") or ""
    child_status = {}
    if os.path.isfile(child_status_path):
        try:
            child_status = _read_json(child_status_path)
        except (OSError, json.JSONDecodeError):
            child_status = {}
    now = time.time()
    terminal_statuses = {"completed", "failed", "cancelled"}
    with _METADATA_LOCK:
        try:
            latest = _read_json(metadata_path) if metadata_path else dict(metadata)
        except Exception:
            latest = dict(metadata)
        stored_status = str(latest.get("status") or "unknown")
        child_status_name = str(child_status.get("status") or "")
        if child_status:
            for key in (
                "ok",
                "completed_at",
                "progress",
                "manifest_path",
                "manifest_summary",
                "message",
                "traceback",
                "phase",
                "current_url",
                "current_file",
                "partial_path",
                "bytes_downloaded",
                "expected_size_bytes",
                "current_file_progress",
                "attempt",
                "resumed",
            ):
                if key in child_status:
                    latest[key] = child_status[key]
        if cancel_requested and not thread_running and not process_running:
            status = "cancelled"
            latest["ok"] = False
            latest["message"] = latest.get("message") or "External asset job cancelled"
        elif child_status_name in terminal_statuses:
            status = child_status_name
        elif stored_status in terminal_statuses:
            status = stored_status
        elif thread_running or process_running:
            status = "cancelling" if cancel_requested else "running"
        elif returncode == 0 and stored_status not in terminal_statuses:
            status = "unknown"
            latest["message"] = "External asset worker exited before final status was recorded"
        elif returncode not in {None, 0}:
            status = "cancelled" if cancel_requested else "failed"
            latest["message"] = latest.get("message") or f"External asset worker exited with code {returncode}"
        elif stored_status in {"starting", "running", "cancelling"}:
            if latest.get("pid") and render_jobs._pid_alive(latest.get("pid")):
                status = "cancelling" if cancel_requested else "running"
                latest["message"] = latest.get("message") or "External asset worker still running (recovered across bridge session)"
            else:
                status = "unknown"
                latest["message"] = "External asset job is no longer running and final status was not recorded"
        else:
            status = stored_status

        started_at = float(latest.get("started_at") or 0.0)
        elapsed = max(0.0, now - started_at) if started_at else 0.0
        terminal = status in terminal_statuses
        if terminal and not latest.get("completed_at"):
            latest["completed_at"] = now
        latest.update(
            {
                "status": status,
                "ok": bool(latest.get("ok")) and status == "completed",
                "elapsed_seconds": int(round(elapsed)),
                "cancel_requested": bool(cancel_requested),
                "poll_after_seconds": 0 if terminal else int(latest.get("poll_interval_seconds") or DEFAULT_ASSET_JOB_POLL_INTERVAL_SECONDS),
                "returncode": returncode if returncode is not None else latest.get("returncode"),
                "log_tail": _log_tail(latest.get("log_path") or "", max_bytes=4096),
                "updated_at": now,
            }
        )
        if status == "completed":
            latest["progress"] = 1.0
        if metadata_path:
            _write_json(metadata_path, latest)
        return latest


def cancel_external_asset_job(job_id, *, context=None, preferred_dir=None, capture_dir=None):
    metadata = external_asset_job_status(job_id, context=context, preferred_dir=preferred_dir, capture_dir=capture_dir)
    if not metadata.get("available"):
        return {"ok": False, "message": metadata.get("message", "External asset job was not found"), "asset_job": metadata}
    status = str(metadata.get("status") or "")
    if status in {"completed", "failed", "cancelled"}:
        return {"ok": False, "message": f"External asset job is already {status}", "asset_job": metadata}
    job_id = metadata.get("job_id", str(job_id or ""))
    with _LOCK:
        _CANCEL_REQUESTS.add(job_id)
        process = _PROCESSES.get(job_id)
    if process is not None and process.poll() is None:
        returncode = _terminate_process(process)
        with _LOCK:
            _PROCESSES.pop(job_id, None)
        metadata = _update_metadata(
            metadata.get("metadata_path", ""),
            ok=False,
            status="cancelled",
            completed_at=time.time(),
            cancel_requested=True,
            poll_after_seconds=0,
            returncode=returncode,
            message="External asset worker process cancelled",
        )
        with _LOCK:
            _CANCEL_REQUESTS.discard(job_id)
        return {"ok": True, "message": "External asset job cancelled", "asset_job": metadata}
    metadata = _update_metadata(
        metadata.get("metadata_path", ""),
        status="cancelling",
        cancel_requested=True,
        message="Cancellation requested; any in-flight HTTP read may finish before the job stops",
    )
    return {"ok": True, "message": "External asset job cancellation requested", "asset_job": metadata}


def import_external_asset_job_result(
    context,
    *,
    job_id,
    target_object_name="",
    label="Import external asset job result",
    capture_dir=None,
):
    metadata = external_asset_job_status(job_id, context=context, preferred_dir=capture_dir)
    if not metadata.get("available"):
        return {"ok": False, "message": metadata.get("message", "External asset job was not found"), "asset_job": metadata}
    if metadata.get("status") != "completed" or not metadata.get("manifest_path"):
        return {
            "ok": False,
            "message": "External asset job is not completed with a cached manifest",
            "asset_job": metadata,
        }
    result = external_assets.import_cached_asset(
        context,
        manifest_path=metadata.get("manifest_path", ""),
        target_object_name=target_object_name,
        label=label or "Import external asset job result",
    )
    return {
        "ok": bool(result.get("ok")),
        "message": result.get("message", "External asset job import finished"),
        "asset_job": metadata,
        "import_result": result,
    }


def start_external_asset_import_job(
    context,
    *,
    source_job_id="",
    manifest_path="",
    target_object_name="",
    label="Import external asset job result",
    capture_dir=None,
):
    source_job = {}
    manifest_path = str(manifest_path or "").strip()
    source_job_id = str(source_job_id or "").strip()
    if source_job_id:
        source_job = external_asset_job_status(source_job_id, context=context, preferred_dir=capture_dir)
        if not source_job.get("available"):
            return {"ok": False, "message": source_job.get("message", "External asset job was not found"), "asset_job": source_job}
        if source_job.get("status") != "completed" or not source_job.get("manifest_path"):
            return {
                "ok": False,
                "message": "External asset download/cache job is not completed with a cached manifest",
                "asset_job": source_job,
            }
        manifest_path = str(source_job.get("manifest_path") or "")
    if not manifest_path:
        return {"ok": False, "message": "source_job_id or manifest_path is required"}

    import_job_id = _job_id()
    info = _job_root_info(context, preferred_dir=capture_dir, create=True)
    job_dir = os.path.join(info["asset_job_root"], import_job_id)
    os.makedirs(job_dir, exist_ok=True)
    metadata_path = _metadata_path(job_dir)
    metadata = {
        "ok": True,
        "available": True,
        "status": "queued",
        "job_id": import_job_id,
        "source_asset_job_id": source_job_id,
        "operation": "import_result",
        "created_at": time.time(),
        "started_at": 0.0,
        "completed_at": 0.0,
        "updated_at": time.time(),
        "project_id": info.get("project_id", ""),
        "session_id": info.get("session_id", ""),
        "storage_scope": info.get("storage_scope", ""),
        "capture_dir": info.get("capture_dir", ""),
        "base_dir": info.get("base_dir", ""),
        "fallback_reason": info.get("fallback_reason", ""),
        "job_dir": job_dir,
        "metadata_path": metadata_path,
        "metadata_uri": _asset_job_uri(import_job_id),
        "manifest_path": manifest_path,
        "target_object_name": str(target_object_name or ""),
        "label": str(label or "Import external asset job result"),
        "phase": "queued",
        "progress": 0.0,
        "elapsed_seconds": 0,
        "poll_interval_seconds": DEFAULT_ASSET_JOB_POLL_INTERVAL_SECONDS,
        "poll_after_seconds": DEFAULT_ASSET_JOB_POLL_INTERVAL_SECONDS,
        "cancel_requested": False,
        "import_result": {},
        "message": "External asset import job queued",
        "client_guidance": "Poll get_external_asset_import_job_status until completed, failed, or cancelled.",
    }
    _write_metadata(metadata_path, metadata)
    with _IMPORT_LOCK:
        _IMPORT_QUEUE.append(
            {
                "job_id": import_job_id,
                "metadata_path": metadata_path,
                "manifest_path": manifest_path,
                "target_object_name": str(target_object_name or ""),
                "label": str(label or "Import external asset job result"),
            }
        )
    _ensure_import_timer()
    status = external_asset_import_job_status(import_job_id, context=context, preferred_dir=capture_dir)
    return {
        "ok": True,
        "message": "External asset import job queued",
        "job_id": import_job_id,
        "asset_import_job": status,
        "source_asset_job": source_job,
    }


def external_asset_import_job_status(job_id, *, context=None, preferred_dir=None, capture_dir=None):
    metadata = _metadata_for_id(job_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if not metadata:
        return {
            "ok": False,
            "available": False,
            "job_id": str(job_id or ""),
            "metadata_uri": _asset_job_uri(job_id),
            "message": "External asset import job was not found for this Blender project/session",
        }
    job_id = metadata.get("job_id", str(job_id or ""))
    metadata_path = metadata.get("metadata_path", "")
    queued, active, cancel_requested = _import_queue_contains(job_id)
    status = str(metadata.get("status") or "unknown")
    if status not in {"completed", "failed", "cancelled"}:
        if queued:
            status = "queued"
        elif active:
            status = "running"
        elif status in {"queued", "running"}:
            status = "unknown"
            metadata["message"] = "External asset import job is no longer queued/running and final status was not recorded"
    now = time.time()
    started_at = float(metadata.get("started_at") or 0.0)
    elapsed = max(0.0, now - started_at) if started_at else 0.0
    terminal = status in {"completed", "failed", "cancelled"}
    metadata.update(
        {
            "status": status,
            "ok": bool(metadata.get("ok")) and status == "completed",
            "elapsed_seconds": int(round(elapsed)),
            "cancel_requested": bool(cancel_requested),
            "poll_after_seconds": 0 if terminal else int(metadata.get("poll_interval_seconds") or DEFAULT_ASSET_JOB_POLL_INTERVAL_SECONDS),
            "updated_at": now,
        }
    )
    if metadata_path:
        _write_metadata(metadata_path, metadata)
    return metadata


def cancel_external_asset_import_job(job_id, *, context=None, preferred_dir=None, capture_dir=None):
    metadata = external_asset_import_job_status(job_id, context=context, preferred_dir=preferred_dir, capture_dir=capture_dir)
    if not metadata.get("available"):
        return {"ok": False, "message": metadata.get("message", "External asset import job was not found"), "asset_import_job": metadata}
    status = str(metadata.get("status") or "")
    if status in {"completed", "failed", "cancelled"}:
        return {"ok": False, "message": f"External asset import job is already {status}", "asset_import_job": metadata}
    job_id = metadata.get("job_id", str(job_id or ""))
    queued_cancelled = None
    with _IMPORT_LOCK:
        queued_index = next((index for index, item in enumerate(_IMPORT_QUEUE) if item.get("job_id") == job_id), None)
        if queued_index is not None:
            _IMPORT_QUEUE.pop(queued_index)
            _IMPORT_CANCEL_REQUESTS.discard(job_id)
            metadata = _update_metadata(
                metadata.get("metadata_path", ""),
                ok=False,
                status="cancelled",
                completed_at=time.time(),
                progress=0.0,
                poll_after_seconds=0,
                cancel_requested=True,
                message="External asset import job cancelled before it started",
            )
            queued_cancelled = {"ok": True, "message": "External asset import job cancelled", "asset_import_job": metadata}
        if job_id in _IMPORT_ACTIVE:
            return {
                "ok": False,
                "message": "External asset import is already running on Blender's main thread and cannot be interrupted safely",
                "asset_import_job": metadata,
            }
        if queued_cancelled is None:
            _IMPORT_CANCEL_REQUESTS.add(job_id)
    if queued_cancelled is not None:
        _stop_import_timer_if_idle()
        return queued_cancelled
    metadata = _update_metadata(
        metadata.get("metadata_path", ""),
        status="cancelled",
        completed_at=time.time(),
        poll_after_seconds=0,
        cancel_requested=True,
        message="External asset import job cancelled",
    )
    return {"ok": True, "message": "External asset import job cancelled", "asset_import_job": metadata}


def delete_external_asset_job(job_id, *, context=None, preferred_dir=None, capture_dir=None, dry_run=True):
    metadata = _metadata_for_id(job_id, capture_dir, context=context, preferred_dir=preferred_dir)
    if not metadata:
        return {
            "ok": False,
            "message": "External asset job was not found for this Blender project/session",
            "job_id": str(job_id or ""),
            "dry_run": bool(dry_run),
        }
    job_id = metadata.get("job_id", str(job_id or ""))
    if metadata.get("operation") == "import_result":
        metadata = external_asset_import_job_status(job_id, context=context, preferred_dir=preferred_dir, capture_dir=capture_dir)
    else:
        metadata = external_asset_job_status(job_id, context=context, preferred_dir=preferred_dir, capture_dir=capture_dir)
    queued, active, _cancel_requested = _import_queue_contains(job_id)
    with _LOCK:
        thread = _THREADS.get(job_id)
        process = _PROCESSES.get(job_id)
    running = bool((thread and thread.is_alive()) or (process and process.poll() is None) or queued or active)
    status = str(metadata.get("status") or "")
    if running or status not in {"completed", "failed", "cancelled"}:
        return {
            "ok": False,
            "message": "Only completed, failed, or cancelled external asset jobs can be deleted",
            "asset_job": metadata,
            "dry_run": bool(dry_run),
        }
    job_dir = os.path.abspath(str(metadata.get("job_dir") or ""))
    roots = [
        os.path.abspath(info["asset_job_root"])
        for info in _job_dir_candidates(capture_dir, context=context, preferred_dir=preferred_dir)
    ]
    if not job_dir or not any(job_dir == root or job_dir.startswith(root + os.sep) for root in roots):
        return {
            "ok": False,
            "message": "Refusing to delete external asset job outside known job roots",
            "asset_job": metadata,
            "job_dir": job_dir,
            "dry_run": bool(dry_run),
        }
    size = 0
    for root, _dirs, files in os.walk(job_dir):
        for filename in files:
            try:
                size += os.path.getsize(os.path.join(root, filename))
            except OSError:
                pass
    if not dry_run:
        try:
            shutil.rmtree(job_dir)
        except Exception as exc:
            return {
                "ok": False,
                "message": f"External asset job delete failed: {type(exc).__name__}: {exc}",
                "dry_run": False,
                "job_id": job_id,
                "job_dir": job_dir,
                "bytes": size,
            }
    return {
        "ok": True,
        "message": "External asset job delete dry run complete" if dry_run else "External asset job deleted",
        "dry_run": bool(dry_run),
        "job_id": job_id,
        "operation": metadata.get("operation", ""),
        "status": status,
        "job_dir": job_dir,
        "bytes": size,
        "deleted": not bool(dry_run),
    }


def register():
    pass


def unregister():
    global _IMPORT_TIMER_REGISTERED
    with _LOCK:
        _CANCEL_REQUESTS.update(_THREADS.keys())
        processes = list(_PROCESSES.items())
    for _job_id, process in processes:
        _terminate_process(process, timeout=2)
    with _LOCK:
        _PROCESSES.clear()
    with _IMPORT_LOCK:
        _IMPORT_CANCEL_REQUESTS.update(item.get("job_id") for item in _IMPORT_QUEUE)
        _IMPORT_QUEUE.clear()
        _IMPORT_ACTIVE.clear()
    try:
        if _import_timer_is_registered():
            bpy.app.timers.unregister(_process_import_queue)
    except Exception:
        pass
    _IMPORT_TIMER_REGISTERED = False
