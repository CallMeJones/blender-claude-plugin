"""Approval-gated generated Python staging and execution."""

from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib
import io
import os
import re
import secrets
import textwrap
import time
import traceback

import bpy
from bpy.app.handlers import persistent

from . import audit_log, script_analysis, transcript

PENDING_SCRIPT_NAME = "Agent Bridge Pending Script"
SCRIPT_LOG_NAME = "Agent Bridge Script Log"
SCRIPT_FAILURE_PROMPT_NAME = "Agent Bridge Script Repair Context"

MAX_SCRIPT_CHARS = 80_000
MAX_STATE_TEXT_CHARS = 1800
EXTERNAL_APPROVAL_TTL_SECONDS = 300
EXTERNAL_TRUST_TTL_SECONDS = 15 * 60
NO_EXTERNAL_TRUST_STATUS = "No external script trust window"
EXTERNAL_TRUST_EXPIRED_STATUS = "External script trust window expired"
EXTERNAL_TRUST_SESSION_STATUS = "External script trust active for this Blender session"
CHECKPOINT_FILENAME_RE = re.compile(r"-(?:agent|claude)-\d{8}-\d{6}\.blend$", re.IGNORECASE)

_runtime_external_trust_expires_at = 0.0
_runtime_external_trust_session = False


def _default_checkpoint_dir():
    return os.path.join(os.path.expanduser("~"), ".claude_blender", "checkpoints")


def _safe_filename(value):
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "untitled").strip("._")
    return value[:80] or "untitled"


def _text_block(name):
    text = bpy.data.texts.get(name)
    if text is None:
        text = bpy.data.texts.new(name)
    return text


def _write_text_block(name, body):
    text = _text_block(name)
    text.clear()
    text.write(body)
    return text


def _read_text_block(name):
    text = bpy.data.texts.get(name)
    return text.as_string() if text else ""


def _short_text(value, max_chars=MAX_STATE_TEXT_CHARS):
    value = str(value or "").strip()
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}... [truncated]"


def _join_lines(values, *, empty="", max_chars=MAX_STATE_TEXT_CHARS):
    lines = [str(value) for value in values or [] if str(value)]
    if not lines:
        return empty
    return _short_text("\n".join(f"- {line}" for line in lines), max_chars=max_chars)


def _scene_state(context=None):
    scene = getattr(context, "scene", None) if context else None
    if scene is None:
        scene = getattr(bpy.context, "scene", None)
    return getattr(scene, "claude_blender", None) if scene else None


def _source_hash(source):
    return hashlib.sha256(str(source or "").encode("utf-8")).hexdigest()


def _token_hash(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def clear_external_script_approval(context=None, *, state=None, status="No external script approval"):
    state = state or _scene_state(context)
    if not state:
        return False
    state.pending_script_external_approval_status = str(status or "No external script approval")
    state.pending_script_external_approval_hash = ""
    state.pending_script_external_approval_text_name = ""
    state.pending_script_external_approval_source_hash = ""
    state.pending_script_external_approval_expires_at = ""
    return True


def _external_approval_expires_at(state):
    try:
        return float(getattr(state, "pending_script_external_approval_expires_at", "") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _external_trust_expires_at(state):
    return float(_runtime_external_trust_expires_at or 0.0)


def _trust_duration_label(seconds):
    seconds = max(0, int(seconds))
    if seconds >= 60:
        minutes, remaining_seconds = divmod(seconds, 60)
        return f"{minutes}m {remaining_seconds:02d}s"
    return f"{seconds}s"


def external_script_trust_snapshot(context=None, *, state=None):
    state = state or _scene_state(context)
    now = time.time()
    expires_at = _external_trust_expires_at(state)
    session_active = bool(state and _runtime_external_trust_session)
    stored_status = getattr(state, "external_script_trust_status", NO_EXTERNAL_TRUST_STATUS) if state else NO_EXTERNAL_TRUST_STATUS
    stored_expires_at = getattr(state, "external_script_trust_expires_at", "") if state else ""
    seconds_remaining = max(0, int(expires_at - now + 0.999)) if expires_at else 0
    stored_expired = stored_status == EXTERNAL_TRUST_EXPIRED_STATUS
    active = bool(session_active or (state and expires_at and seconds_remaining > 0))
    expired = bool(state and ((expires_at and not active) or stored_expired))
    stale_scene_state = bool(stored_expires_at and not expires_at and not session_active)
    if session_active:
        status = EXTERNAL_TRUST_SESSION_STATUS
    elif active:
        status = f"External script trust active: {_trust_duration_label(seconds_remaining)} remaining"
    elif expired:
        status = EXTERNAL_TRUST_EXPIRED_STATUS
    elif str(stored_status).startswith("External script trust active"):
        status = NO_EXTERNAL_TRUST_STATUS
    else:
        status = stored_status or NO_EXTERNAL_TRUST_STATUS
    return {
        "active": active,
        "expired": expired,
        "status": status,
        "expires_at": expires_at if expires_at else 0.0,
        "seconds_remaining": seconds_remaining,
        "can_run_without_token": active,
        "runtime_only": True,
        "session": session_active,
        "stale_scene_state": stale_scene_state,
    }


def clear_external_script_trust(context=None, *, state=None, status=NO_EXTERNAL_TRUST_STATUS):
    global _runtime_external_trust_expires_at, _runtime_external_trust_session
    state = state or _scene_state(context)
    _runtime_external_trust_expires_at = 0.0
    _runtime_external_trust_session = False
    if not state:
        return False
    state.external_script_trust_status = str(status or NO_EXTERNAL_TRUST_STATUS)
    state.external_script_trust_expires_at = ""
    return True


def _coerce_ttl_seconds(value, default):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return int(default)


def external_script_trust_active(context=None, *, state=None):
    return bool(external_script_trust_snapshot(context, state=state)["active"])


def external_script_trust_status(context=None, *, state=None):
    return external_script_trust_snapshot(context, state=state)["status"]


def _audit_external_script_trust(action, *, state=None, ttl_seconds=None, expires_at=None, status=""):
    try:
        audit_log.append_event(
            "external_script_trust",
            source="blender",
            action=str(action),
            ttl_seconds=ttl_seconds,
            expires_at=expires_at,
            active=external_script_trust_active(state=state) if state else False,
            status=status or (external_script_trust_status(state=state) if state else ""),
        )
    except Exception:
        pass


def expire_external_script_trust_if_needed(context=None, *, state=None):
    state = state or _scene_state(context)
    snapshot = external_script_trust_snapshot(state=state)
    expires_at = snapshot["expires_at"]
    if not expires_at or not snapshot["expired"]:
        return False
    clear_external_script_trust(state=state, status=EXTERNAL_TRUST_EXPIRED_STATUS)
    _audit_external_script_trust(
        "expire",
        state=state,
        expires_at=expires_at,
        status=EXTERNAL_TRUST_EXPIRED_STATUS,
    )
    return True


def clear_external_script_trust_for_all_scenes(*, status=NO_EXTERNAL_TRUST_STATUS, audit_action="clear"):
    global _runtime_external_trust_expires_at, _runtime_external_trust_session
    had_runtime_trust = bool(_runtime_external_trust_expires_at or _runtime_external_trust_session)
    _runtime_external_trust_expires_at = 0.0
    _runtime_external_trust_session = False
    cleared = 0
    for scene in getattr(bpy.data, "scenes", []):
        state = getattr(scene, "claude_blender", None)
        if not state:
            continue
        had_scene_status = (
            bool(getattr(state, "external_script_trust_expires_at", ""))
            or getattr(state, "external_script_trust_status", NO_EXTERNAL_TRUST_STATUS) != NO_EXTERNAL_TRUST_STATUS
        )
        if had_scene_status:
            state.external_script_trust_status = str(status or NO_EXTERNAL_TRUST_STATUS)
            state.external_script_trust_expires_at = ""
            cleared += 1
    if had_runtime_trust or cleared:
        _audit_external_script_trust(audit_action, status=status)
    return cleared


def approve_external_script_trust_window(context, *, ttl_seconds=EXTERNAL_TRUST_TTL_SECONDS, session=False):
    global _runtime_external_trust_expires_at, _runtime_external_trust_session
    state = _scene_state(context)
    if not state:
        return {"ok": False, "message": "No Blender scene state is available"}
    session = bool(session)
    if session:
        _runtime_external_trust_expires_at = 0.0
        _runtime_external_trust_session = True
        state.external_script_trust_expires_at = "session"
        state.external_script_trust_status = external_script_trust_status(state=state)
        state.status = state.external_script_trust_status
        _audit_external_script_trust(
            "grant",
            state=state,
            ttl_seconds=None,
            expires_at=None,
            status=state.external_script_trust_status,
        )
        transcript.record_system_message(
            "User approved external script trust for this Blender session. "
            "External clients may run staged scripts without a per-script token until revoke, reload, or bridge restart; "
            "blocked scripts and failing static checks remain refused."
        )
        return {
            "ok": True,
            "message": "External script trust approved for this Blender session",
            "expires_at": 0.0,
            "ttl_seconds": 0,
            "session": True,
        }
    ttl = _coerce_ttl_seconds(ttl_seconds, EXTERNAL_TRUST_TTL_SECONDS)
    expires_at = time.time() + ttl
    _runtime_external_trust_expires_at = expires_at
    _runtime_external_trust_session = False
    state.external_script_trust_expires_at = f"{expires_at:.6f}"
    state.external_script_trust_status = external_script_trust_status(state=state)
    state.status = state.external_script_trust_status
    _audit_external_script_trust(
        "grant",
        state=state,
        ttl_seconds=ttl,
        expires_at=expires_at,
        status=state.external_script_trust_status,
    )
    transcript.record_system_message(
        "User approved a timed external script trust window. "
        "External clients may run staged scripts without a per-script token until it expires; "
        "blocked scripts and failing static checks remain refused."
    )
    return {
        "ok": True,
        "message": "External script trust window approved",
        "expires_at": expires_at,
        "ttl_seconds": ttl,
        "session": False,
    }


def revoke_external_script_trust_window(context):
    state = _scene_state(context)
    if not state:
        return {"ok": False, "message": "No Blender scene state is available"}
    clear_external_script_trust(state=state, status="External script trust window revoked")
    state.status = "External script trust window revoked"
    _audit_external_script_trust("revoke", state=state, status="External script trust window revoked")
    transcript.record_system_message("User revoked the external script trust window.")
    return {"ok": True, "message": "External script trust window revoked"}


def approve_pending_script_for_external_run(context, *, ttl_seconds=EXTERNAL_APPROVAL_TTL_SECONDS):
    state = _scene_state(context)
    if not state or not state.pending_script:
        return {"ok": False, "message": "No pending script to approve for external execution"}
    if state.pending_script_blocked:
        clear_external_script_approval(state=state, status="External approval blocked by static checks")
        return {"ok": False, "message": "Pending script is blocked by static checks"}
    text_name = state.pending_script_text_name or PENDING_SCRIPT_NAME
    source = _read_text_block(text_name)
    if not source:
        clear_external_script_approval(state=state, status="External approval failed: missing script text")
        return {"ok": False, "message": "No pending script text found"}
    analysis = analyze_script(source)
    if not analysis["ok"]:
        state.pending_script_blocked = True
        state.pending_script_status = "Blocked by static checks"
        state.pending_script_issues = _join_lines(analysis.get("issues"))
        state.pending_script_warnings = _join_lines(analysis.get("warnings"))
        state.status = state.pending_script_status
        clear_external_script_approval(state=state, status="External approval blocked by static checks")
        return {"ok": False, "message": "Script blocked by static checks", "analysis": analysis}

    ttl = _coerce_ttl_seconds(ttl_seconds, EXTERNAL_APPROVAL_TTL_SECONDS)
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + ttl
    state.pending_script_external_approval_hash = _token_hash(token)
    state.pending_script_external_approval_text_name = text_name
    state.pending_script_external_approval_source_hash = _source_hash(source)
    state.pending_script_external_approval_expires_at = f"{expires_at:.6f}"
    state.pending_script_external_approval_status = f"External run approved for {ttl} second(s)"
    state.pending_script_status = state.pending_script_external_approval_status
    state.status = state.pending_script_external_approval_status
    transcript.record_system_message(
        "User approved pending script for external execution. "
        "A one-time approval token was issued in Blender UI and is not stored in transcripts."
    )
    return {
        "ok": True,
        "message": "External run approval token issued",
        "approval_token": token,
        "expires_at": expires_at,
        "ttl_seconds": ttl,
        "text_datablock": text_name,
    }


def _external_approval_error(state, message, *, clear=False):
    if state:
        state.pending_script_external_approval_status = message
        state.status = message
        if clear:
            clear_external_script_approval(state=state, status=message)
    return {"ok": False, "message": message}


def _validate_current_pending_script_for_external_run(context, state):
    if state.pending_script_blocked:
        return _external_approval_error(state, "Pending script is blocked by static checks", clear=True)
    text_name = state.pending_script_text_name or PENDING_SCRIPT_NAME
    source = _read_text_block(text_name)
    if not source:
        return _external_approval_error(state, "No pending script text found", clear=True)
    analysis = analyze_script(source)
    if not analysis["ok"]:
        state.pending_script_blocked = True
        state.pending_script_status = "Blocked by static checks"
        state.pending_script_issues = _join_lines(analysis.get("issues"))
        state.pending_script_warnings = _join_lines(analysis.get("warnings"))
        state.status = state.pending_script_status
        clear_external_script_approval(state=state, status="External approval blocked by static checks")
        return {"ok": False, "message": "Script blocked by static checks", "analysis": analysis}
    return {"ok": True, "message": "Pending script accepted", "text_name": text_name, "source": source}


def validate_external_script_approval(context, approval_token):
    state = _scene_state(context)
    if not state or not state.pending_script:
        return _external_approval_error(state, "No pending script to run")
    token = str(approval_token or "").strip()
    if not token:
        expire_external_script_trust_if_needed(state=state)
        if external_script_trust_active(state=state):
            accepted = _validate_current_pending_script_for_external_run(context, state)
            if not accepted.get("ok"):
                return accepted
            return {
                "ok": True,
                "message": "External trusted window accepted",
                "approval_mode": "trusted_window",
            }
        return _external_approval_error(state, "Missing external approval token and no active external trust window")
    accepted = _validate_current_pending_script_for_external_run(context, state)
    if not accepted.get("ok"):
        return accepted
    expected_hash = state.pending_script_external_approval_hash
    if not expected_hash:
        return _external_approval_error(state, "No Blender-side external approval is active")
    if time.time() > _external_approval_expires_at(state):
        return _external_approval_error(state, "External script approval expired", clear=True)
    if not secrets.compare_digest(_token_hash(token), expected_hash):
        return _external_approval_error(state, "External approval token did not match")

    text_name = accepted["text_name"]
    if text_name != state.pending_script_external_approval_text_name:
        return _external_approval_error(state, "External approval is stale for this script", clear=True)
    source = accepted["source"]
    if _source_hash(source) != state.pending_script_external_approval_source_hash:
        return _external_approval_error(state, "External approval is stale because the script changed", clear=True)
    return {"ok": True, "message": "External approval accepted", "approval_mode": "one_time_token"}


def run_externally_approved_script(context, approval_token, *, checkpoint_enabled=True, checkpoint_dir=None):
    approval = validate_external_script_approval(context, approval_token)
    if not approval.get("ok"):
        return approval
    state = _scene_state(context)
    if approval.get("approval_mode") == "one_time_token":
        clear_external_script_approval(state=state, status="External approval consumed")
    result = run_pending_script(
        context,
        checkpoint_enabled=checkpoint_enabled,
        checkpoint_dir=checkpoint_dir,
    )
    if state and result.get("ok") and approval.get("approval_mode") == "one_time_token":
        state.pending_script_external_approval_status = "External approval consumed"
    return result


def analyze_script(source):
    return script_analysis.analyze_script(source)


def _is_checkpoint_path(path):
    return bool(path and CHECKPOINT_FILENAME_RE.search(os.path.basename(path)))


def checkpoint_metadata(context, path, *, ok=None, message=""):
    raw_path = str(path or "").strip()
    path = bpy.path.abspath(raw_path) if raw_path else ""
    exists = bool(path and os.path.exists(path))
    size_bytes = os.path.getsize(path) if exists else 0
    scene = getattr(context, "scene", None) if context else getattr(bpy.context, "scene", None)
    restorable = bool(exists and path.lower().endswith(".blend") and _is_checkpoint_path(path))
    return {
        "ok": bool(exists) if ok is None else bool(ok),
        "path": path,
        "message": str(message or ("Checkpoint available" if exists else "Checkpoint not found")),
        "exists": exists,
        "restorable": restorable,
        "created_by_bridge": _is_checkpoint_path(path),
        "created_by_claude": _is_checkpoint_path(path),
        "size_bytes": int(size_bytes),
        "scene_name": scene.name if scene else "",
        "current_filepath": bpy.data.filepath or "",
    }


def create_checkpoint(context, checkpoint_dir=None):
    directory = bpy.path.abspath(checkpoint_dir or _default_checkpoint_dir())
    os.makedirs(directory, exist_ok=True)
    current_path = bpy.data.filepath
    if current_path:
        base = os.path.splitext(os.path.basename(current_path))[0]
    else:
        base = context.scene.name if context and context.scene else "unsaved"
    timestamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(directory, f"{_safe_filename(base)}-agent-{timestamp}.blend")
    try:
        bpy.ops.wm.save_as_mainfile(filepath=path, check_existing=False, copy=True)
    except Exception as exc:
        return checkpoint_metadata(
            context,
            path,
            ok=False,
            message=f"Checkpoint failed: {type(exc).__name__}: {exc}",
        )
    metadata = checkpoint_metadata(context, path, ok=True, message="Checkpoint saved")
    metadata["created_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    metadata["source_filepath"] = current_path or ""
    return metadata


def restore_checkpoint(context, checkpoint_path=None):
    state = _scene_state(context)
    path = checkpoint_path or (state.last_checkpoint_path if state else "")
    metadata = checkpoint_metadata(context, path)
    if not metadata["path"]:
        message = "No checkpoint path available"
        if state:
            state.last_checkpoint_restored_status = message
            state.status = message
        return {"ok": False, "message": message, "checkpoint": metadata}
    if not metadata["exists"]:
        message = f"Checkpoint not found: {metadata['path']}"
        if state:
            state.last_checkpoint_restored_status = message
            state.status = message
        metadata["message"] = message
        return {"ok": False, "message": message, "checkpoint": metadata}
    if not metadata["restorable"]:
        message = f"Checkpoint is not a .blend file: {metadata['path']}"
        if metadata["exists"] and metadata["path"].lower().endswith(".blend"):
            message = f"Blend file was not created by Agent Bridge checkpointing: {metadata['path']}"
        if state:
            state.last_checkpoint_restored_status = message
            state.status = message
        metadata["ok"] = False
        metadata["message"] = message
        return {"ok": False, "message": message, "checkpoint": metadata}
    try:
        bpy.ops.wm.open_mainfile(filepath=metadata["path"])
    except Exception as exc:
        message = f"Checkpoint restore failed: {type(exc).__name__}: {exc}"
        state = _scene_state()
        if state:
            state.last_checkpoint_restored_status = message
            state.status = message
        metadata["ok"] = False
        metadata["message"] = message
        return {"ok": False, "message": message, "checkpoint": metadata}

    state = _scene_state()
    message = f"Checkpoint restored: {metadata['path']}"
    if state:
        state.last_checkpoint_status = "Checkpoint restored"
        state.last_checkpoint_path = metadata["path"]
        state.last_checkpoint_restored_status = message
        state.last_checkpoint_restored_path = metadata["path"]
        if state.pending_script:
            state.pending_script_status = "Checkpoint restored; review before running again"
        state.status = message
    transcript.record_system_message(message)
    metadata = checkpoint_metadata(bpy.context, metadata["path"], ok=True, message="Checkpoint restored")
    return {"ok": True, "message": "Checkpoint restored", "checkpoint": metadata}


def _metadata_text(*, intent, expected_changes, risk_level, target_objects, analysis):
    lines = [
        "# Agent Bridge Pending Script",
        "",
        f"Intent: {intent or 'No intent provided'}",
        f"Declared risk: {risk_level or 'unspecified'}",
        f"Detected risk: {analysis.get('risk_level', 'unknown')}",
        f"Checkpoint recommended: {'yes' if analysis.get('checkpoint_recommended') else 'no'}",
        f"Targets: {', '.join(target_objects) if target_objects else 'unspecified'}",
        "",
        "Expected changes:",
        expected_changes or "No expected changes provided",
        "",
        "Static analysis:",
        "PASS" if analysis["ok"] else "BLOCKED",
    ]
    for issue in analysis.get("issues", []):
        lines.append(f"- {issue}")
    for warning in analysis.get("warnings", []):
        lines.append(f"- Warning: {warning}")
    for reason in analysis.get("risk_reasons", [])[:12]:
        lines.append(f"- Risk: {reason}")
    return "\n".join(lines)


def stage_script(context, *, code, intent="", expected_changes="", risk_level="medium", target_objects=None):
    target_objects = [str(obj) for obj in (target_objects or []) if str(obj)]
    code = textwrap.dedent(str(code or "")).strip()
    if not code:
        return {
            "ok": False,
            "message": (
                "No script code was provided. Retry draft_script with complete Blender Python "
                "source in the code field; do not ask the user to paste code manually."
            ),
            "missing_code": True,
        }
    analysis = analyze_script(code)
    script_text = _write_text_block(PENDING_SCRIPT_NAME, code)
    metadata = _metadata_text(
        intent=str(intent or ""),
        expected_changes=str(expected_changes or ""),
        risk_level=str(risk_level or "medium"),
        target_objects=target_objects,
        analysis=analysis,
    )
    _write_text_block(f"{PENDING_SCRIPT_NAME} Metadata", metadata)

    state = getattr(context.scene, "claude_blender", None)
    if state:
        clear_external_script_approval(state=state)
        issue_text = _join_lines(analysis.get("issues"))
        warning_text = _join_lines(analysis.get("warnings"))
        if analysis.get("blocked"):
            status = "Blocked by static checks"
        elif analysis.get("warnings"):
            status = f"Pending approval with {len(analysis.get('warnings', []))} warning(s)"
        else:
            status = "Pending approval"
        state.pending_script = True
        state.pending_script_blocked = bool(analysis.get("blocked"))
        state.pending_script_text_name = script_text.name
        state.pending_script_intent = str(intent or "")[:1000]
        state.pending_script_expected_changes = str(expected_changes or "")[:1000]
        state.pending_script_risk = f"{str(risk_level or 'medium')} / detected {analysis.get('risk_level', 'unknown')}"[:80]
        state.pending_script_status = status
        state.pending_script_issues = issue_text
        state.pending_script_warnings = warning_text
        state.last_script_error_summary = ""
        state.status = state.pending_script_status

    transcript.record_system_message(
        "Drafted pending script:\n"
        f"{metadata}\n\n"
        f"Script text datablock: {script_text.name}"
    )
    return {
        "ok": True,
        "message": "Script staged for approval" if analysis["ok"] else "Script staged but blocked by static checks",
        "text_datablock": script_text.name,
        "metadata_datablock": f"{PENDING_SCRIPT_NAME} Metadata",
        "analysis": analysis,
        "requires_user_approval": True,
    }


def reject_pending_script(context):
    state = getattr(context.scene, "claude_blender", None)
    if state:
        clear_external_script_approval(state=state)
        state.pending_script = False
        state.pending_script_blocked = False
        state.pending_script_status = "Pending script rejected"
        state.pending_script_text_name = ""
        state.pending_script_intent = ""
        state.pending_script_expected_changes = ""
        state.pending_script_risk = ""
        state.pending_script_issues = ""
        state.pending_script_warnings = ""
        state.status = "Pending script rejected"
    transcript.record_system_message("Pending script rejected by user.")
    return {"ok": True, "message": "Pending script rejected"}


def pending_script_source(context):
    state = getattr(context.scene, "claude_blender", None)
    text_name = state.pending_script_text_name if state else PENDING_SCRIPT_NAME
    return _read_text_block(text_name or PENDING_SCRIPT_NAME)


def script_log_text():
    return _read_text_block(SCRIPT_LOG_NAME)


def repair_context_text(context):
    source = pending_script_source(context)
    log_text = script_log_text()
    state = _scene_state(context)
    checkpoint = checkpoint_metadata(context, state.last_checkpoint_path if state else "")
    body = (
        "The user approved this Blender Python script, but execution failed. "
        "Prepare a corrected draft only; do not run Python directly.\n\n"
        "Checkpoint status:\n"
        f"- Message: {checkpoint.get('message') or 'No checkpoint recorded'}\n"
        f"- Path: {checkpoint.get('path') or '(none)'}\n"
        f"- Exists: {'yes' if checkpoint.get('exists') else 'no'}\n"
        f"- Restorable: {'yes' if checkpoint.get('restorable') else 'no'}\n\n"
        "Pending script:\n"
        f"{source or '(missing)'}\n\n"
        "Execution log / traceback:\n"
        f"{log_text or '(missing)'}\n"
    )
    _write_text_block(SCRIPT_FAILURE_PROMPT_NAME, body)
    return body


def run_pending_script(context, *, checkpoint_enabled=True, checkpoint_dir=None):
    state = getattr(context.scene, "claude_blender", None)
    text_name = state.pending_script_text_name if state else PENDING_SCRIPT_NAME
    source = _read_text_block(text_name or PENDING_SCRIPT_NAME)
    if not source:
        clear_external_script_approval(state=state, status="No pending script text found")
        return {"ok": False, "message": "No pending script text found"}
    analysis = analyze_script(source)
    if not analysis["ok"]:
        if state:
            state.pending_script_blocked = True
            state.pending_script_status = "Blocked by static checks"
            state.pending_script_issues = _join_lines(analysis.get("issues"))
            state.pending_script_warnings = _join_lines(analysis.get("warnings"))
            state.status = state.pending_script_status
        clear_external_script_approval(state=state, status="External approval blocked by static checks")
        return {"ok": False, "message": "Script blocked by static checks", "analysis": analysis}

    checkpoint = {"ok": False, "message": "Checkpoint disabled", "path": ""}
    if checkpoint_enabled:
        checkpoint = create_checkpoint(context, checkpoint_dir=checkpoint_dir)
        if state:
            state.last_checkpoint_status = checkpoint["message"]
            state.last_checkpoint_path = checkpoint.get("path", "")
            state.last_checkpoint_restored_status = "No checkpoint restored"
            state.last_checkpoint_restored_path = ""
        if not checkpoint["ok"]:
            transcript.record_system_message(checkpoint["message"])
            if state:
                state.status = checkpoint["message"]
                state.pending_script_status = "Checkpoint failed"
            return {
                "ok": False,
                "message": checkpoint["message"],
                "checkpoint": checkpoint,
            }
    elif state:
        state.last_checkpoint_status = "Checkpoint disabled"
        state.last_checkpoint_path = ""

    stdout = io.StringIO()
    namespace = {
        "__name__": "__claude_blender_pending_script__",
        "bpy": bpy,
        "context": context,
        "scene": context.scene,
    }
    try:
        bpy.ops.ed.undo_push(message="Before Agent Bridge approved script")
    except Exception:
        pass

    try:
        compiled = compile(source, text_name or PENDING_SCRIPT_NAME, "exec")
        with contextlib.redirect_stdout(stdout):
            exec(compiled, namespace, namespace)
    except Exception:
        output = stdout.getvalue()
        error = traceback.format_exc()
        log = (
            "Script failed.\n\n"
            f"CHECKPOINT:\n{checkpoint.get('path') or checkpoint.get('message')}\n\n"
            f"STDOUT:\n{output}\n\n"
            f"ERROR:\n{error}"
        )
        _write_text_block(SCRIPT_LOG_NAME, log)
        if state:
            state.pending_script_status = "Script failed"
            state.last_script_error_summary = _short_text(error)
            state.last_script_log_name = SCRIPT_LOG_NAME
            state.status = "Script failed"
        transcript.record_system_message(log)
        return {
            "ok": False,
            "message": "Script failed",
            "error": error,
            "stdout": output,
            "log_datablock": SCRIPT_LOG_NAME,
            "checkpoint": checkpoint,
        }

    output = stdout.getvalue()
    log = (
        "Script executed successfully.\n\n"
        f"CHECKPOINT:\n{checkpoint.get('path') or checkpoint.get('message')}\n\n"
        f"STDOUT:\n{output or '(none)'}"
    )
    _write_text_block(SCRIPT_LOG_NAME, log)
    if state:
        state.pending_script = False
        state.pending_script_blocked = False
        state.pending_script_status = "Script executed"
        state.pending_script_text_name = ""
        state.pending_script_intent = ""
        state.pending_script_expected_changes = ""
        state.pending_script_risk = ""
        state.pending_script_issues = ""
        state.pending_script_warnings = ""
        clear_external_script_approval(state=state)
        state.last_script_error_summary = ""
        state.last_script_log_name = SCRIPT_LOG_NAME
        state.status = "Script executed"
    transcript.record_system_message(log)
    try:
        context.view_layer.update()
    except Exception:
        pass
    return {
        "ok": True,
        "message": "Script executed",
        "stdout": output,
        "log_datablock": SCRIPT_LOG_NAME,
        "checkpoint": checkpoint,
    }


@persistent
def _clear_external_script_trust_on_load(_dummy):
    clear_external_script_trust_for_all_scenes(
        status=NO_EXTERNAL_TRUST_STATUS,
        audit_action="clear_on_load",
    )


def _remove_external_trust_load_handler():
    handlers = bpy.app.handlers.load_post
    for handler in list(handlers):
        if (
            getattr(handler, "__name__", "") == "_clear_external_script_trust_on_load"
            and str(getattr(handler, "__module__", "")).endswith(".script_runner")
        ):
            handlers.remove(handler)


def register():
    clear_external_script_trust_for_all_scenes(
        status=NO_EXTERNAL_TRUST_STATUS,
        audit_action="clear_on_register",
    )
    _remove_external_trust_load_handler()
    bpy.app.handlers.load_post.append(_clear_external_script_trust_on_load)


def unregister():
    _remove_external_trust_load_handler()
    clear_external_script_trust_for_all_scenes(
        status=NO_EXTERNAL_TRUST_STATUS,
        audit_action="clear_on_unregister",
    )
