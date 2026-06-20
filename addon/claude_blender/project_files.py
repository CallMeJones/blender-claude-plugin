"""Blend-file save/open/new-project helpers for external tools."""

from __future__ import annotations

import os
import re
import time

import bpy

from . import lab_parity, script_runner


DEFAULT_PROJECT_DIRS = ("assets", "refs", "renders", "exports")
PROJECT_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def _abspath(path):
    raw = str(path or "").strip()
    if not raw:
        return ""
    expanded = os.path.expanduser(bpy.path.abspath(raw))
    return os.path.abspath(expanded)


def _is_blend_path(path):
    return bool(str(path or "").lower().endswith(".blend"))


def _safe_project_name(value):
    name = PROJECT_NAME_RE.sub("_", str(value or "").strip())
    name = name.strip(" ._")
    return name[:80] or "untitled-project"


def _safe_project_subdir(value):
    raw = str(value or "").strip().replace("\\", "/").strip("/")
    if not raw or os.path.isabs(raw) or ":" in raw:
        return ""
    parts = [part.strip() for part in raw.split("/") if part.strip()]
    if not parts or any(part in {".", ".."} for part in parts):
        return ""
    return os.path.join(*parts)


def _current_state():
    filepath = getattr(bpy.data, "filepath", "") or ""
    absolute = os.path.abspath(filepath) if filepath else ""
    return {
        "filepath": filepath,
        "absolute_path": absolute,
        "is_saved": bool(filepath),
        "exists": bool(absolute and os.path.isfile(absolute)),
        "is_dirty": bool(getattr(bpy.data, "is_dirty", False)),
    }


def _ensure_parent_dir(path, *, create_dirs):
    directory = os.path.dirname(path)
    if not directory:
        return {"ok": False, "message": "Target path must include a directory", "directory": directory}
    if os.path.isdir(directory):
        return {"ok": True, "directory": directory}
    if not create_dirs:
        return {"ok": False, "message": f"Target directory does not exist: {directory}", "directory": directory}
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "message": f"Could not create target directory: {type(exc).__name__}: {exc}", "directory": directory}
    return {"ok": True, "directory": directory}


def _checkpoint_before_replace(context, *, create_checkpoint=True, require_checkpoint=True, checkpoint_dir=None):
    if not bool(create_checkpoint):
        return {"ok": False, "requested": False, "message": "Checkpoint disabled", "path": ""}
    checkpoint = script_runner.create_checkpoint(context, checkpoint_dir=checkpoint_dir)
    checkpoint["requested"] = True
    if not checkpoint.get("ok") and bool(require_checkpoint):
        checkpoint["blocking"] = True
    return checkpoint


def _clear_scene_runtime_state(message):
    script_runner.clear_external_script_trust_for_all_scenes(
        status=script_runner.NO_EXTERNAL_TRUST_STATUS,
        audit_action="clear_on_project_file_change",
    )
    state = getattr(getattr(bpy.context, "scene", None), "claude_blender", None)
    if not state:
        return
    state.pending_preview = False
    state.pending_preview_label = ""
    state.pending_preview_summary = ""
    state.pending_preview_warnings = ""
    state.pending_script = False
    state.pending_script_blocked = False
    state.pending_script_text_name = ""
    state.pending_script_intent = ""
    state.pending_script_expected_changes = ""
    state.pending_script_risk = ""
    state.pending_script_status = "No pending script"
    state.pending_script_issues = ""
    state.pending_script_warnings = ""
    script_runner.clear_external_script_approval(state=state)
    state.status = str(message or "Project file operation finished")


def _run_open_mainfile(path, *, load_ui=False):
    try:
        return bpy.ops.wm.open_mainfile(filepath=path, load_ui=bool(load_ui))
    except TypeError:
        return bpy.ops.wm.open_mainfile(filepath=path)


def _run_read_homefile(*, template="default"):
    normalized = str(template or "default").strip().lower().replace("-", "_")
    kwargs = {}
    if normalized == "empty":
        kwargs["use_empty"] = True
    elif normalized in {"factory", "factory_startup", "factory-startup"}:
        kwargs["use_factory_startup"] = True
    try:
        return bpy.ops.wm.read_homefile(**kwargs)
    except TypeError:
        return bpy.ops.wm.read_homefile()


def _save_result_payload(path, *, operation, operator_result, before, copy):
    exists = os.path.isfile(path)
    diagnostics = lab_parity.get_blend_file_diagnostics(bpy.context)
    return {
        "ok": bool(exists),
        "message": f"Blend file {operation} complete" if exists else f"Blend file {operation} did not create a file",
        "operation": operation,
        "path": path,
        "copy": bool(copy),
        "operator_result": sorted(str(item) for item in operator_result),
        "size_bytes": os.path.getsize(path) if exists else 0,
        "before": before,
        "after": _current_state(),
        "diagnostics": diagnostics,
    }


def save_blend_file(context, *, filepath="", copy=False, overwrite=False, create_dirs=True):
    before = _current_state()
    target = _abspath(filepath) if str(filepath or "").strip() else before["absolute_path"]
    requested_path = bool(str(filepath or "").strip())
    copy = bool(copy)
    if not target:
        return {
            "ok": False,
            "message": "A filepath is required because the current blend file has not been saved yet",
            "before": before,
        }
    if not _is_blend_path(target):
        return {"ok": False, "message": "Blend file path must end with .blend", "path": target, "before": before}
    if copy and not requested_path:
        return {"ok": False, "message": "Saving a copy requires an explicit filepath", "path": target, "before": before}
    current = before["absolute_path"]
    same_current = bool(current and os.path.normcase(current) == os.path.normcase(target))
    if copy and same_current:
        return {"ok": False, "message": "Save-copy target must differ from the active blend file", "path": target, "before": before}
    parent = _ensure_parent_dir(target, create_dirs=bool(create_dirs))
    if not parent.get("ok"):
        return {"ok": False, **parent, "path": target, "before": before}
    exists = os.path.isfile(target)
    if exists and not bool(overwrite) and requested_path and not same_current:
        return {
            "ok": False,
            "message": "Target blend file already exists; pass overwrite=true to replace it",
            "path": target,
            "exists": True,
            "before": before,
        }
    try:
        operator_result = bpy.ops.wm.save_as_mainfile(filepath=target, check_existing=False, copy=copy)
    except Exception as exc:
        return {
            "ok": False,
            "message": f"Blend file save failed: {type(exc).__name__}: {exc}",
            "path": target,
            "before": before,
        }
    return _save_result_payload(
        target,
        operation="copy save" if copy else ("save-as" if requested_path and not same_current else "save"),
        operator_result=operator_result,
        before=before,
        copy=copy,
    )


def open_blend_file(
    context,
    *,
    filepath,
    confirm_discard_current=False,
    create_checkpoint=True,
    require_checkpoint=True,
    checkpoint_dir=None,
    load_ui=False,
):
    before = _current_state()
    path = _abspath(filepath)
    if not bool(confirm_discard_current):
        return {
            "ok": False,
            "message": "Opening a blend file replaces the active Blender session; pass confirm_discard_current=true",
            "path": path,
            "before": before,
        }
    if not path:
        return {"ok": False, "message": "A filepath is required", "before": before}
    if not _is_blend_path(path):
        return {"ok": False, "message": "Blend file path must end with .blend", "path": path, "before": before}
    if not os.path.isfile(path):
        return {"ok": False, "message": f"Blend file not found: {path}", "path": path, "before": before}
    checkpoint = _checkpoint_before_replace(
        context,
        create_checkpoint=create_checkpoint,
        require_checkpoint=require_checkpoint,
        checkpoint_dir=checkpoint_dir,
    )
    if checkpoint.get("blocking"):
        return {
            "ok": False,
            "message": checkpoint.get("message", "Checkpoint failed; open was not attempted"),
            "path": path,
            "checkpoint": checkpoint,
            "before": before,
        }
    started_at = time.time()
    try:
        operator_result = _run_open_mainfile(path, load_ui=bool(load_ui))
    except Exception as exc:
        return {
            "ok": False,
            "message": f"Blend file open failed: {type(exc).__name__}: {exc}",
            "path": path,
            "checkpoint": checkpoint,
            "before": before,
        }
    _clear_scene_runtime_state(f"Opened blend file: {path}")
    diagnostics = lab_parity.get_blend_file_diagnostics(bpy.context)
    return {
        "ok": True,
        "message": "Blend file opened",
        "path": path,
        "operator_result": sorted(str(item) for item in operator_result),
        "elapsed_seconds": round(time.time() - started_at, 3),
        "checkpoint": checkpoint,
        "before": before,
        "after": _current_state(),
        "diagnostics": diagnostics,
    }


def create_new_blender_project(
    context,
    *,
    project_dir="",
    project_name="",
    filepath="",
    template="default",
    create_standard_dirs=True,
    standard_dirs=None,
    overwrite=False,
    create_dirs=True,
    confirm_discard_current=False,
    create_checkpoint=True,
    require_checkpoint=True,
    checkpoint_dir=None,
):
    before = _current_state()
    requested_project_name = str(project_name or "").strip()
    safe_name = _safe_project_name(requested_project_name)
    target = _abspath(filepath)
    if target:
        project_root = os.path.dirname(target)
        safe_name = _safe_project_name(project_name or os.path.splitext(os.path.basename(target))[0])
    else:
        root = _abspath(project_dir)
        if not root:
            return {"ok": False, "message": "project_dir or filepath is required", "before": before}
        if not requested_project_name:
            safe_name = _safe_project_name(os.path.basename(os.path.normpath(root)))
            project_root = root
        else:
            project_root = os.path.join(root, safe_name) if os.path.basename(root).lower() != safe_name.lower() else root
        target = os.path.join(project_root, f"{safe_name}.blend")
    if not bool(confirm_discard_current):
        return {
            "ok": False,
            "message": "Creating a new project replaces the active Blender session; pass confirm_discard_current=true",
            "path": target,
            "before": before,
        }
    if not _is_blend_path(target):
        return {"ok": False, "message": "Blend file path must end with .blend", "path": target, "before": before}
    parent = _ensure_parent_dir(target, create_dirs=bool(create_dirs))
    if not parent.get("ok"):
        return {"ok": False, **parent, "path": target, "before": before}
    if os.path.isfile(target) and not bool(overwrite):
        return {
            "ok": False,
            "message": "Project blend file already exists; pass overwrite=true to replace it",
            "path": target,
            "exists": True,
            "before": before,
        }
    checkpoint = _checkpoint_before_replace(
        context,
        create_checkpoint=create_checkpoint,
        require_checkpoint=require_checkpoint,
        checkpoint_dir=checkpoint_dir,
    )
    if checkpoint.get("blocking"):
        return {
            "ok": False,
            "message": checkpoint.get("message", "Checkpoint failed; new project was not created"),
            "path": target,
            "checkpoint": checkpoint,
            "before": before,
        }
    created_dirs = []
    started_at = time.time()
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if bool(create_standard_dirs):
            requested_dirs = standard_dirs if isinstance(standard_dirs, (list, tuple)) else DEFAULT_PROJECT_DIRS
            for item in requested_dirs:
                name = _safe_project_subdir(item)
                if not name:
                    continue
                path = os.path.join(os.path.dirname(target), name)
                os.makedirs(path, exist_ok=True)
                created_dirs.append(path)
        read_result = _run_read_homefile(template=template)
        if safe_name and getattr(bpy.context, "scene", None):
            bpy.context.scene.name = safe_name[:63]
        save_result = bpy.ops.wm.save_as_mainfile(filepath=target, check_existing=False)
    except Exception as exc:
        return {
            "ok": False,
            "message": f"New project creation failed: {type(exc).__name__}: {exc}",
            "path": target,
            "checkpoint": checkpoint,
            "created_dirs": created_dirs,
            "before": before,
        }
    _clear_scene_runtime_state(f"Created new Blender project: {target}")
    diagnostics = lab_parity.get_blend_file_diagnostics(bpy.context)
    return {
        "ok": bool(os.path.isfile(target)),
        "message": "New Blender project created" if os.path.isfile(target) else "New project save did not create a blend file",
        "project_name": safe_name,
        "project_dir": os.path.dirname(target),
        "path": target,
        "template": str(template or "default"),
        "created_dirs": created_dirs,
        "operator_result": {
            "read_homefile": sorted(str(item) for item in read_result),
            "save_as_mainfile": sorted(str(item) for item in save_result),
        },
        "elapsed_seconds": round(time.time() - started_at, 3),
        "checkpoint": checkpoint,
        "before": before,
        "after": _current_state(),
        "diagnostics": diagnostics,
    }


def register():
    pass


def unregister():
    pass
