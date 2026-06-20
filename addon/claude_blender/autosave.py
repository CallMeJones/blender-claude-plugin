"""Project-bound in-place autosave for Blender Agent Bridge."""

from __future__ import annotations

import os
import time

import bpy
from bpy.app.handlers import persistent

from . import preferences


DEFAULT_AUTOSAVE_INTERVAL_SECONDS = 300

_last_autosave_at = 0.0
_last_result = {}

_previous_timer_callback = globals().get("_timer_callback")
if _previous_timer_callback is not None:
    try:
        if bpy.app.timers.is_registered(_previous_timer_callback):
            bpy.app.timers.unregister(_previous_timer_callback)
    except Exception:
        pass


def _prefs(context=None):
    context = context or bpy.context
    return preferences.get_preferences(context)


def _enabled(context=None):
    prefs = _prefs(context)
    return True if prefs is None else bool(getattr(prefs, "autosave_enabled", True))


def _interval_seconds(context=None):
    prefs = _prefs(context)
    value = (
        getattr(prefs, "autosave_interval_seconds", DEFAULT_AUTOSAVE_INTERVAL_SECONDS)
        if prefs
        else DEFAULT_AUTOSAVE_INTERVAL_SECONDS
    )
    try:
        return max(30, int(value))
    except (TypeError, ValueError):
        return DEFAULT_AUTOSAVE_INTERVAL_SECONDS


def _current_blend_path():
    filepath = getattr(bpy.data, "filepath", "") or ""
    return os.path.abspath(filepath) if filepath else ""


def _binding_status(filepath=None):
    filepath = filepath or _current_blend_path()
    directory = os.path.dirname(filepath) if filepath else ""
    bound = bool(filepath)
    writable = bool(directory and os.path.isdir(directory) and os.access(directory, os.W_OK))
    exists = bool(filepath and os.path.isfile(filepath))
    return {
        "active_blend_bound": bound,
        "filepath": filepath,
        "project_dir": directory,
        "project_dir_writable": writable,
        "active_file_exists": exists,
        "requires_user_path": not bound,
        "human_in_loop_message": "" if bound else "Autosave is disabled until the user saves or opens a .blend file path.",
    }


def _pending_preview_state(context=None):
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    state = getattr(scene, "claude_blender", None)
    pending = bool(getattr(state, "pending_preview", False)) if state else False
    return {
        "pending_preview": pending,
        "pending_preview_label": str(getattr(state, "pending_preview_label", "") or "") if state else "",
    }


def autosave_status(context=None):
    filepath = _current_blend_path()
    binding = _binding_status(filepath)
    preview = _pending_preview_state(context)
    return {
        "ok": True,
        "enabled": _enabled(context),
        "mode": "in_place",
        "interval_seconds": _interval_seconds(context),
        "active_blend_bound": binding["active_blend_bound"],
        "active_filepath": binding["filepath"],
        "project_dir": binding["project_dir"],
        "last_result": dict(_last_result),
        "requires_user_path": binding["requires_user_path"],
        "human_in_loop_message": binding["human_in_loop_message"],
        "pending_preview": preview["pending_preview"],
        "pending_preview_label": preview["pending_preview_label"],
        "policy": "Autosave saves the current open .blend in place after Blender is bound to a human-chosen path.",
    }


def autosave_current_blend_file(
    context=None,
    *,
    force=False,
    reason="manual",
    respect_enabled=False,
):
    global _last_autosave_at, _last_result

    context = context or bpy.context
    now = time.time()
    filepath = _current_blend_path()
    binding = _binding_status(filepath)
    if not binding["active_blend_bound"]:
        result = {
            "ok": False,
            "skipped": True,
            "code": "user_path_required",
            "message": binding["human_in_loop_message"],
            "human_in_loop_required": True,
            "requires_user_path": True,
            "reason": str(reason or "manual"),
            "binding": binding,
        }
        _last_result = result
        return result
    if not binding["project_dir_writable"]:
        result = {
            "ok": False,
            "skipped": True,
            "code": "project_dir_not_writable",
            "message": f"Autosave target directory is not writable: {binding['project_dir']}",
            "reason": str(reason or "manual"),
            "binding": binding,
        }
        _last_result = result
        return result
    if respect_enabled and not _enabled(context):
        return {
            "ok": True,
            "skipped": True,
            "message": "Autosave is disabled",
            "reason": str(reason or "timer"),
            "binding": binding,
        }
    preview = _pending_preview_state(context)
    if not force and preview["pending_preview"]:
        result = {
            "ok": True,
            "skipped": True,
            "code": "pending_preview",
            "message": "Autosave skipped while live preview changes are pending",
            "reason": str(reason or "timer"),
            "binding": binding,
            **preview,
        }
        _last_result = result
        return result
    interval = _interval_seconds(context)
    if not force and _last_autosave_at and now - _last_autosave_at < interval:
        return {
            "ok": True,
            "skipped": True,
            "message": "Autosave interval has not elapsed",
            "seconds_until_next": int(round(interval - (now - _last_autosave_at))),
            "reason": str(reason or "timer"),
            "binding": binding,
        }
    if not force and not bool(getattr(bpy.data, "is_dirty", False)):
        return {
            "ok": True,
            "skipped": True,
            "message": "Current blend file has no unsaved changes",
            "reason": str(reason or "timer"),
            "binding": binding,
        }

    try:
        operator_result = bpy.ops.wm.save_as_mainfile(filepath=filepath, check_existing=False)
    except Exception as exc:
        result = {
            "ok": False,
            "message": f"Autosave failed: {type(exc).__name__}: {exc}",
            "path": filepath,
            "reason": str(reason or "manual"),
            "binding": binding,
        }
        _last_result = result
        return result

    _last_autosave_at = now
    exists = os.path.isfile(filepath)
    result = {
        "ok": bool(exists),
        "message": "Current blend file autosaved" if exists else "Autosave did not create the active blend file",
        "path": filepath,
        "mode": "in_place",
        "reason": str(reason or "manual"),
        "operator_result": sorted(str(item) for item in operator_result),
        "size_bytes": os.path.getsize(filepath) if exists else 0,
        "active_filepath": _current_blend_path(),
        "active_file_unchanged": os.path.normcase(_current_blend_path()) == os.path.normcase(filepath),
        "binding": _binding_status(filepath),
    }
    _last_result = result
    return result


def _timer_callback():
    global _last_result
    try:
        autosave_current_blend_file(bpy.context, force=False, reason="timer", respect_enabled=True)
    except Exception as exc:
        _last_result = {"ok": False, "message": f"Autosave timer failed: {type(exc).__name__}: {exc}", "reason": "timer"}
    return float(_interval_seconds(bpy.context))


def _timer_is_registered():
    try:
        return bool(bpy.app.timers.is_registered(_timer_callback))
    except Exception:
        return False


def _register_timer():
    try:
        bpy.app.timers.register(_timer_callback, first_interval=float(_interval_seconds(bpy.context)), persistent=True)
    except TypeError:
        bpy.app.timers.register(_timer_callback, first_interval=float(_interval_seconds(bpy.context)))


def _ensure_timer():
    if _timer_is_registered():
        return
    try:
        _register_timer()
    except Exception:
        pass


@persistent
def _ensure_timer_after_load(_dummy):
    _ensure_timer()


def _remove_timer_load_handler():
    handlers = bpy.app.handlers.load_post
    for handler in list(handlers):
        if (
            getattr(handler, "__name__", "") == "_ensure_timer_after_load"
            and str(getattr(handler, "__module__", "")).endswith(".autosave")
        ):
            handlers.remove(handler)


def register():
    _remove_timer_load_handler()
    bpy.app.handlers.load_post.append(_ensure_timer_after_load)
    _ensure_timer()


def unregister():
    _remove_timer_load_handler()
    try:
        if _timer_is_registered():
            bpy.app.timers.unregister(_timer_callback)
    except Exception:
        pass
