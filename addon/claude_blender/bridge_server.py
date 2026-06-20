"""Local localhost JSON bridge for external MCP/agent access."""

from __future__ import annotations

import hmac
import json
import os
import queue
import threading
import time
import urllib.parse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bpy
from bpy.app.handlers import persistent

from . import (
    audit_log,
    agent_tools,
    bridge_protocol,
    build_info,
    context_bundle,
    inspection_render,
    lab_parity,
    playblast_capture,
    preferences,
    render_jobs,
    script_runner,
    tool_dispatcher,
    transcript,
    viewport_capture,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
REQUEST_TIMEOUT_GRACE_SECONDS = 10
STATUS_PROBE_TIMEOUT_SECONDS = 2
# Cap inbound request bodies so a local client cannot exhaust memory.
MAX_REQUEST_BODY_BYTES = 8 * 1024 * 1024
# Per-connection socket timeout so a stalled/partial request cannot pin a worker thread.
REQUEST_READ_TIMEOUT_SECONDS = 30
# Hostnames accepted in the Host/Origin headers; anything else is a cross-origin or
# DNS-rebinding attempt against the localhost bridge and is refused.
ALLOWED_HOST_NAMES = frozenset({"127.0.0.1", "localhost", "::1"})


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)


REQUEST_TIMEOUT_SECONDS = max(10, _env_int("BLENDER_AGENT_BRIDGE_REQUEST_TIMEOUT", "90"))
AUDIT_SUMMARY_EVENT_LIMIT = 40
AUDIT_LATEST_EVENT_LIMIT = 20


class _RequestTooLarge(Exception):
    """Raised when an inbound request body exceeds MAX_REQUEST_BODY_BYTES."""

_server = None
_thread = None
_requests = queue.Queue()
_timer_registered = False
_lock = threading.Lock()
_operation_lock = threading.Lock()
_active_operation = {}
_last_operation = {}


def _json_bytes(payload):
    return json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")


def _public_context():
    return context_bundle.public_bundle(context_bundle.build_context_bundle(bpy.context))


def _compact_tool_catalog():
    contracts = bridge_protocol.list_tool_contracts()
    tools = []
    for name, contract in sorted((contracts.get("tools") or {}).items()):
        normalized = bridge_protocol.normalized_tool_contract(name, contract)
        annotations = bridge_protocol.mcp_annotations_for_tool(name)
        tools.append(
            {
                "name": name,
                "risk_level": str(annotations.get("riskLevel", "") or ""),
                "permissions": list(annotations.get("permissions", []) or []),
                "mutates_scene": bool(annotations.get("mutatesScene", False)),
                "requires_approval": bool(annotations.get("requiresApproval", False)),
                "requires_live_preview": bool(annotations.get("requiresLivePreview", False)),
                "human_in_loop_required": bool(annotations.get("humanInLoopRequired", False)),
                "requires_user_path": bool(annotations.get("requiresUserPath", False)),
                "title": normalized.get("title") or name.replace("_", " ").title(),
            }
        )
    return {
        "ok": True,
        "schema_version": contracts.get("schema_version"),
        "bridge_version": contracts.get("bridge_version"),
        "count": len(tools),
        "tools": tools,
        "full_contracts_resource": "blender://tools/contracts",
        "note": "Compact catalog for resource discovery. Use MCP tool search/schema helpers for normal tool routing.",
    }


def _audit_summary():
    events = audit_log.read_recent(AUDIT_SUMMARY_EVENT_LIMIT)
    event_counts = Counter(str(event.get("event") or "unknown") for event in events)
    tool_counts = Counter(str(event.get("tool_name") or "") for event in events if event.get("tool_name"))
    error_count = sum(1 for event in events if event.get("ok") is False or event.get("code"))
    latest = []
    for event in events[-8:]:
        latest.append(
            {
                "timestamp": event.get("timestamp"),
                "event": event.get("event"),
                "tool_name": event.get("tool_name"),
                "ok": event.get("ok"),
                "code": event.get("code"),
            }
        )
    return {
        "ok": True,
        "event_count": len(events),
        "events_by_type": dict(sorted(event_counts.items())),
        "tool_calls_by_name": dict(sorted(tool_counts.items())),
        "error_count": error_count,
        "latest_events": latest,
        "latest_full_resource": "blender://audit/latest",
        "latest_full_event_limit": AUDIT_LATEST_EVENT_LIMIT,
    }


def _operation_recovery_guidance(name):
    try:
        contract = bridge_protocol.normalized_tool_contract(str(name or ""))
    except Exception:
        contract = {}
    recovery = contract.get("timeout_recovery") if isinstance(contract.get("timeout_recovery"), dict) else {}
    recommended_tool = str(recovery.get("recommended_tool") or "")
    if not recommended_tool and any(term in str(name or "") for term in ("render", "playblast", "thumbnail")):
        recommended_tool = "start_render_job"
    return {
        "recoverable": bool(recovery.get("recoverable", True)),
        "poll_after_seconds": int(recovery.get("poll_after_seconds") or 5),
        "status_tool": str(recovery.get("status_tool") or "blender_bridge_status"),
        "resource_tool": str(recovery.get("resource_tool") or "get_visual_evidence_resources"),
        "recommended_tool": recommended_tool,
        "message": str(
            recovery.get("message")
            or "Wait briefly, call blender_bridge_status, then inspect latest resources or audit logs before rerunning."
        ),
    }


def _operation_snapshot(operation):
    if not isinstance(operation, dict) or not operation:
        return {}
    started_monotonic = float(operation.get("started_monotonic", 0.0) or 0.0)
    completed_monotonic = float(operation.get("completed_monotonic", 0.0) or 0.0)
    elapsed_until = completed_monotonic if completed_monotonic else time.monotonic()
    elapsed = max(0.0, elapsed_until - started_monotonic) if started_monotonic else 0.0
    timeout_seconds = int(operation.get("timeout_seconds", 0) or 0)
    snapshot = {
        "tool": str(operation.get("tool") or ""),
        "started_at": float(operation.get("started_at", 0.0) or 0.0),
        "elapsed_seconds": int(round(elapsed)),
        "timeout_seconds": timeout_seconds,
        "request_may_still_be_running": bool(operation.get("request_may_still_be_running", True)),
        "result_may_be_lost_after_client_timeout": True,
        "duration_hint": str(operation.get("duration_hint") or ""),
        "recovery": dict(operation.get("recovery") or {}),
    }
    if operation.get("completed_at"):
        snapshot["completed_at"] = float(operation.get("completed_at", 0.0) or 0.0)
        snapshot["ok"] = bool(operation.get("ok", False))
        snapshot["message"] = str(operation.get("message") or "")
        snapshot["request_may_still_be_running"] = False
    if timeout_seconds:
        snapshot["timeout_exceeded"] = elapsed >= float(timeout_seconds)
    return snapshot


def _active_operation_status():
    with _operation_lock:
        return _operation_snapshot(dict(_active_operation))


def _last_operation_status():
    with _operation_lock:
        return _operation_snapshot(dict(_last_operation))


def _begin_active_operation(name, args, timeout_seconds):
    global _active_operation
    try:
        contract = bridge_protocol.normalized_tool_contract(str(name or ""))
    except Exception:
        contract = {}
    operation = {
        "tool": str(name or ""),
        "started_at": time.time(),
        "started_monotonic": time.monotonic(),
        "timeout_seconds": int(timeout_seconds or 0),
        "request_may_still_be_running": True,
        "duration_hint": str(contract.get("duration_hint") or ""),
        "recovery": _operation_recovery_guidance(name),
        "arguments": audit_log.summarize_arguments(args),
    }
    with _operation_lock:
        _active_operation = operation
    return operation


def _finish_active_operation(name, *, ok=False, message=""):
    global _active_operation, _last_operation
    with _operation_lock:
        operation = dict(_active_operation)
        if operation.get("tool") != str(name or ""):
            return
        operation["completed_at"] = time.time()
        operation["completed_monotonic"] = time.monotonic()
        operation["ok"] = bool(ok)
        operation["message"] = str(message or "")
        _last_operation = operation
        _active_operation = {}


def _busy_scene_status(message=""):
    active = _active_operation_status()
    last = _last_operation_status()
    recovery = active.get("recovery") or _operation_recovery_guidance(active.get("tool", ""))
    diagnostics = build_info.diagnostics_dict(bridge_url=bridge_url())
    tool = str(active.get("tool") or "")
    return {
        "ok": True,
        "bridge_url": bridge_url(),
        "bridge_version": bridge_protocol.BRIDGE_VERSION,
        "addon_id": diagnostics["addon_id"],
        "addon_name": diagnostics["addon_name"],
        "addon_version": diagnostics["addon_version"],
        "addon_path": diagnostics["addon_path"],
        "addon_source_hash": diagnostics["addon_source_hash"],
        "addon_loaded_source_hash": diagnostics["addon_loaded_source_hash"],
        "addon_runtime_source_stale": diagnostics["addon_runtime_source_stale"],
        "addon_runtime_source_status": diagnostics["addon_runtime_source_status"],
        "addon_runtime_source_message": diagnostics["addon_runtime_source_message"],
        "expected_addon_source_hash": diagnostics["expected_addon_source_hash"],
        "addon_source_hash_match": diagnostics["addon_source_hash_match"],
        "addon_source_hash_status": diagnostics["addon_source_hash_status"],
        "addon_source_hash_message": diagnostics["addon_source_hash_message"],
        "mcp_server_version": diagnostics["mcp_server_version"],
        "mcp_server_path": diagnostics["mcp_server_path"],
        "mcp_config_version": diagnostics["mcp_config_version"],
        "build_diagnostics": build_info.diagnostics_summary(),
        "bridge_busy": True,
        "recoverable": True,
        "active_tool_name": tool,
        "active_operation": active,
        "last_operation": last,
        "poll_after_seconds": int(recovery.get("poll_after_seconds") or 5),
        "recovery_hint": str(recovery.get("message") or ""),
        "message": message
        or (
            f"Blender is busy running '{tool}' on the main thread. "
            "The bridge is reachable and should recover when the operation completes."
            if tool
            else "Blender main thread did not answer the status probe. The bridge is reachable and may recover after the active Blender operation completes."
        ),
        "mcp_client_refresh_hint": (
            "Restart or refresh the MCP client if newly added Blender tools are missing from its callable tool list."
        ),
    }


def _scene_status():
    bundle = context_bundle.build_context_bundle(bpy.context)
    state = getattr(bpy.context.scene, "claude_blender", None)
    trust = script_runner.external_script_trust_snapshot(bpy.context, state=state) if state else {}
    url = bridge_url() or (getattr(state, "bridge_url", "") if state else "")
    active = _active_operation_status()
    last = _last_operation_status()
    diagnostics = build_info.diagnostics_dict(
        bridge_url=url,
        blender_version=".".join(str(part) for part in bpy.app.version),
    )
    return {
        "ok": True,
        "bridge_url": url,
        "bridge_version": bridge_protocol.BRIDGE_VERSION,
        "blender_version": ".".join(str(part) for part in bpy.app.version),
        "addon_id": diagnostics["addon_id"],
        "addon_name": diagnostics["addon_name"],
        "addon_version": diagnostics["addon_version"],
        "addon_path": diagnostics["addon_path"],
        "addon_source_hash": diagnostics["addon_source_hash"],
        "addon_loaded_source_hash": diagnostics["addon_loaded_source_hash"],
        "addon_runtime_source_stale": diagnostics["addon_runtime_source_stale"],
        "addon_runtime_source_status": diagnostics["addon_runtime_source_status"],
        "addon_runtime_source_message": diagnostics["addon_runtime_source_message"],
        "expected_addon_source_hash": diagnostics["expected_addon_source_hash"],
        "addon_source_hash_match": diagnostics["addon_source_hash_match"],
        "addon_source_hash_status": diagnostics["addon_source_hash_status"],
        "addon_source_hash_message": diagnostics["addon_source_hash_message"],
        "mcp_server_version": diagnostics["mcp_server_version"],
        "mcp_server_path": diagnostics["mcp_server_path"],
        "mcp_config_version": diagnostics["mcp_config_version"],
        "build_diagnostics": build_info.diagnostics_summary(),
        "scene": bpy.context.scene.name,
        "bridge_busy": bool(active),
        "recoverable": bool(active),
        "active_tool_name": str(active.get("tool") or ""),
        "active_operation": active,
        "last_operation": last,
        "poll_after_seconds": int((active.get("recovery") or {}).get("poll_after_seconds") or 0),
        "recovery_hint": str((active.get("recovery") or {}).get("message") or ""),
        "context_summary": context_bundle.summarize_for_status(bundle),
        "ui_status": getattr(state, "status", "") if state else "",
        "pending_preview": bool(getattr(state, "pending_preview", False)) if state else False,
        "pending_script": bool(getattr(state, "pending_script", False)) if state else False,
        "external_script_trust": bool(trust.get("active", False)),
        "external_script_trust_status": str(trust.get("status", "")),
        "external_script_trust_expires_at": float(trust.get("expires_at", 0.0) or 0.0),
        "external_script_trust_seconds_remaining": int(trust.get("seconds_remaining", 0) or 0),
        "external_script_trust_can_run_without_token": bool(trust.get("can_run_without_token", False)),
        "external_script_trust_session": bool(trust.get("session", False)),
        "external_script_trust_stale_scene_state": bool(trust.get("stale_scene_state", False)),
        "mcp_client_refresh_hint": (
            "Restart or refresh the MCP client if newly added Blender tools are missing from its callable tool list."
        ),
    }


def _tool_definitions():
    contracts = bridge_protocol.TOOL_CONTRACTS
    result = []
    seen = set()
    for tool in agent_tools.blender_tool_definitions():
        name = tool["name"]
        contract = bridge_protocol.normalized_tool_contract(name, contracts.get(name, {}))
        seen.add(name)
        result.append(
            {
                "name": name,
                "title": contract.get("title") or name.replace("_", " ").title(),
                "description": tool.get("description", contract.get("description", "")),
                "inputSchema": tool.get("input_schema") or tool.get("inputSchema") or {"type": "object"},
                "outputSchema": contract.get("output_schema") or bridge_protocol.DEFAULT_OUTPUT_SCHEMA,
                "annotations": bridge_protocol.mcp_annotations_for_tool(name),
            }
        )
    for name, raw_contract in contracts.items():
        if name in seen or not raw_contract.get("external_only"):
            continue
        contract = bridge_protocol.normalized_tool_contract(name, raw_contract)
        result.append(
            {
                "name": name,
                "title": contract.get("title") or name.replace("_", " ").title(),
                "description": contract.get("description", ""),
                "inputSchema": contract.get("input_schema") or {"type": "object"},
                "outputSchema": contract.get("output_schema") or bridge_protocol.DEFAULT_OUTPUT_SCHEMA,
                "annotations": bridge_protocol.mcp_annotations_for_tool(name),
            }
        )
    return result


def _resources():
    return [
        {
            "uri": "blender://scene/status",
            "name": "scene-status",
            "title": "Current Blender Scene Status",
            "description": "Compact status for the open Blender scene and bridge",
            "mimeType": "application/json",
        },
        {
            "uri": "blender://scene/context",
            "name": "scene-context",
            "title": "Current Blender Scene Context",
            "description": "Public context bundle for the active Blender scene",
            "mimeType": "application/json",
        },
        {
            "uri": "blender://tools/catalog",
            "name": "tool-catalog",
            "title": "Compact Blender Tool Catalog",
            "description": "Compact tool names, risk, and permission metadata for resource discovery",
            "mimeType": "application/json",
        },
        {
            "uri": "blender://transcript/latest",
            "name": "latest-transcript",
            "title": "Blender Agent Bridge Transcript",
            "description": "Local transcript Text datablock contents",
            "mimeType": "text/plain",
        },
        {
            "uri": "blender://audit/summary",
            "name": "audit-summary",
            "title": "Blender Agent Bridge Audit Summary",
            "description": "Compact summary of recent local audit events for bridge and MCP tool calls",
            "mimeType": "application/json",
        },
        {
            "uri": viewport_capture.LATEST_CAPTURE_RESOURCE_URI,
            "name": "latest-capture",
            "title": "Latest Viewport Capture",
            "description": "Latest viewport screenshot PNG captured by the Blender add-on",
            "mimeType": "image/png",
        },
        {
            "uri": viewport_capture.LATEST_CAPTURE_METADATA_URI,
            "name": "latest-capture-metadata",
            "title": "Latest Viewport Capture Metadata",
            "description": "Metadata and local path for the latest viewport screenshot",
            "mimeType": "application/json",
        },
        {
            "uri": playblast_capture.LATEST_PLAYBLAST_METADATA_URI,
            "name": "latest-playblast-metadata",
            "title": "Latest Animation Playblast Metadata",
            "description": "Metadata and frame resource URIs for the latest sampled animation playblast",
            "mimeType": "application/json",
        },
        {
            "uri": inspection_render.LATEST_INSPECTION_RENDER_METADATA_URI,
            "name": "latest-inspection-render-metadata",
            "title": "Latest Object Inspection Render Metadata",
            "description": "Metadata and image resource URIs for the latest diagnostic object renders",
            "mimeType": "application/json",
        },
        {
            "uri": lab_parity.LATEST_RENDER_THUMBNAIL_URI,
            "name": "latest-render-thumbnail",
            "title": "Latest Render Thumbnail",
            "description": "Latest scene thumbnail PNG rendered by the Blender bridge",
            "mimeType": "image/png",
        },
        {
            "uri": lab_parity.LATEST_RENDER_THUMBNAIL_METADATA_URI,
            "name": "latest-render-thumbnail-metadata",
            "title": "Latest Render Thumbnail Metadata",
            "description": "Metadata and local path for the latest rendered thumbnail",
            "mimeType": "application/json",
        },
        {
            "uri": render_jobs.LATEST_RENDER_JOB_METADATA_URI,
            "name": "latest-render-job-metadata",
            "title": "Latest Async Render Job Metadata",
            "description": "Status, progress, output paths, and resource URIs for the latest async render job",
            "mimeType": "application/json",
        },
    ]


def _capture_cache_dir():
    try:
        prefs = preferences.get_preferences(bpy.context)
        return getattr(prefs, "capture_cache_dir", None)
    except Exception:
        return None


def _read_resource(uri):
    if uri == "blender://scene/status":
        return {"mimeType": "application/json", "text": json.dumps(_scene_status(), indent=2, sort_keys=True)}
    if uri == "blender://scene/context":
        return {"mimeType": "application/json", "text": json.dumps(_public_context(), indent=2, sort_keys=True, default=str)}
    if uri == "blender://tools/catalog":
        return {
            "mimeType": "application/json",
            "text": json.dumps(_compact_tool_catalog(), indent=2, sort_keys=True),
        }
    if uri == "blender://tools/contracts":
        return {
            "mimeType": "application/json",
            "text": json.dumps(bridge_protocol.list_tool_contracts(), indent=2, sort_keys=True),
        }
    if uri == "blender://transcript/latest":
        return {"mimeType": "text/plain", "text": transcript.transcript_text()}
    if uri == "blender://audit/latest":
        return {
            "mimeType": "application/json",
            "text": json.dumps(
                {
                    "ok": True,
                    "events": audit_log.read_recent(AUDIT_LATEST_EVENT_LIMIT),
                    "event_limit": AUDIT_LATEST_EVENT_LIMIT,
                    "summary_resource": "blender://audit/summary",
                },
                indent=2,
                sort_keys=True,
            ),
        }
    if uri == "blender://audit/summary":
        return {
            "mimeType": "application/json",
            "text": json.dumps(_audit_summary(), indent=2, sort_keys=True),
        }
    if uri == viewport_capture.LATEST_CAPTURE_RESOURCE_URI:
        return viewport_capture.latest_capture_resource(context=bpy.context, preferred_dir=_capture_cache_dir())
    if uri == viewport_capture.LATEST_CAPTURE_METADATA_URI:
        return {
            "mimeType": "application/json",
            "text": json.dumps(
                viewport_capture.latest_capture_metadata(context=bpy.context, preferred_dir=_capture_cache_dir()),
                indent=2,
                sort_keys=True,
            ),
        }
    capture_id, wants_metadata = viewport_capture.parse_capture_resource_uri(uri)
    if capture_id and capture_id != "latest":
        if wants_metadata:
            metadata = viewport_capture.capture_metadata(
                capture_id,
                context=bpy.context,
                preferred_dir=_capture_cache_dir(),
            )
            if not metadata.get("available"):
                return None
            return {
                "mimeType": "application/json",
                "text": json.dumps(metadata, indent=2, sort_keys=True),
            }
        return viewport_capture.capture_resource(
            capture_id,
            context=bpy.context,
            preferred_dir=_capture_cache_dir(),
        )
    playblast_id, playblast_kind, playblast_frame = playblast_capture.parse_playblast_resource_uri(uri)
    if playblast_id:
        if playblast_id == "latest" and playblast_kind == "metadata":
            return {
                "mimeType": "application/json",
                "text": json.dumps(
                    playblast_capture.latest_playblast_metadata(context=bpy.context, preferred_dir=_capture_cache_dir()),
                    indent=2,
                    sort_keys=True,
                ),
            }
        if playblast_kind == "metadata":
            metadata = playblast_capture.playblast_metadata(
                playblast_id,
                context=bpy.context,
                preferred_dir=_capture_cache_dir(),
            )
            if not metadata.get("available"):
                return None
            return {
                "mimeType": "application/json",
                "text": json.dumps(metadata, indent=2, sort_keys=True),
            }
        if playblast_kind == "frame":
            return playblast_capture.playblast_frame_resource(
                playblast_id,
                playblast_frame,
                context=bpy.context,
                preferred_dir=_capture_cache_dir(),
            )
    render_id, render_kind, image_id = inspection_render.parse_inspection_render_resource_uri(uri)
    if render_id:
        if render_id == "latest" and render_kind == "metadata":
            return {
                "mimeType": "application/json",
                "text": json.dumps(
                    inspection_render.latest_inspection_render_metadata(
                        context=bpy.context,
                        preferred_dir=_capture_cache_dir(),
                    ),
                    indent=2,
                    sort_keys=True,
                ),
            }
        if render_kind == "metadata":
            metadata = inspection_render.inspection_render_metadata(
                render_id,
                context=bpy.context,
                preferred_dir=_capture_cache_dir(),
            )
            if not metadata.get("available"):
                return None
            return {
                "mimeType": "application/json",
                "text": json.dumps(metadata, indent=2, sort_keys=True),
            }
        if render_kind == "image":
            return inspection_render.inspection_render_image_resource(
                render_id,
                image_id,
                context=bpy.context,
                preferred_dir=_capture_cache_dir(),
            )
    thumbnail_id, thumbnail_kind = lab_parity.parse_render_thumbnail_resource_uri(uri)
    if thumbnail_id:
        if thumbnail_id == "latest" and thumbnail_kind == "metadata":
            return {
                "mimeType": "application/json",
                "text": json.dumps(
                    lab_parity.latest_render_thumbnail_metadata(
                        context=bpy.context,
                        preferred_dir=_capture_cache_dir(),
                    ),
                    indent=2,
                    sort_keys=True,
                ),
            }
        if thumbnail_kind == "metadata":
            metadata = lab_parity.render_thumbnail_metadata(
                thumbnail_id,
                context=bpy.context,
                preferred_dir=_capture_cache_dir(),
            )
            if not metadata.get("available"):
                return None
            return {
                "mimeType": "application/json",
                "text": json.dumps(metadata, indent=2, sort_keys=True),
            }
        if thumbnail_kind == "image":
            return lab_parity.render_thumbnail_resource(
                thumbnail_id,
                context=bpy.context,
                preferred_dir=_capture_cache_dir(),
            )
    job_id, job_kind, job_token = render_jobs.parse_render_job_resource_uri(uri)
    if job_id:
        if job_id == "latest" and job_kind == "metadata":
            return {
                "mimeType": "application/json",
                "text": json.dumps(
                    render_jobs.latest_render_job_metadata(
                        context=bpy.context,
                        preferred_dir=_capture_cache_dir(),
                    ),
                    indent=2,
                    sort_keys=True,
                ),
            }
        if job_kind == "metadata":
            metadata = render_jobs.render_job_status(
                job_id,
                context=bpy.context,
                preferred_dir=_capture_cache_dir(),
            )
            if not metadata.get("available"):
                return None
            return {
                "mimeType": "application/json",
                "text": json.dumps(metadata, indent=2, sort_keys=True),
            }
        if job_kind == "frame":
            return render_jobs.render_job_frame_resource(
                job_id,
                job_token,
                context=bpy.context,
                preferred_dir=_capture_cache_dir(),
            )
        if job_kind == "log":
            return render_jobs.render_job_log_resource(
                job_id,
                context=bpy.context,
                preferred_dir=_capture_cache_dir(),
            )
        if job_kind == "video":
            return render_jobs.render_job_video_resource(
                job_id,
                context=bpy.context,
                preferred_dir=_capture_cache_dir(),
            )
    return None


def _execute_tool(payload):
    name = str(payload.get("name") or "")
    args = payload.get("arguments")
    if args is None:
        args = payload.get("input")
    if not isinstance(args, dict):
        args = {}
    # Defense-in-depth: enforce the tool contract on the raw HTTP path too, not just
    # on the MCP path, so malformed arguments are rejected before dispatch.
    input_schema = bridge_protocol.normalized_tool_contract(name).get("input_schema")
    if isinstance(input_schema, dict):
        schema_errors = bridge_protocol.validate_arguments(args, input_schema)
        if schema_errors:
            return {
                "ok": False,
                "result": {
                    "ok": False,
                    "message": "Invalid arguments for tool '%s': %s"
                    % (name, "; ".join(schema_errors[:8])),
                    "schema_errors": schema_errors[:32],
                },
            }
    ok = False
    result = {}
    _begin_active_operation(name, args, _tool_timeout_seconds(name))
    try:
        result_text = tool_dispatcher.execute_tool(bpy.context, name, args)
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            result = {"ok": True, "text": result_text}
        ok = bool(result.get("ok", True))
        try:
            contract = bridge_protocol.normalized_tool_contract(name)
            audit_log.append_event(
                "bridge_tool_call",
                source="bridge",
                tool_name=name,
                ok=ok,
                risk_level=contract.get("risk_level", ""),
                mutates_scene=bool(contract.get("mutates_scene", False)),
                requires_approval=bool(contract.get("requires_approval", False)),
                arguments=audit_log.summarize_arguments(args),
            )
        except Exception:
            pass
        return {"ok": ok, "result": result}
    finally:
        message = result.get("message", "") if isinstance(result, dict) else ""
        _finish_active_operation(name, ok=ok, message=message)


def _tool_timeout_seconds(name):
    try:
        contract = bridge_protocol.normalized_tool_contract(str(name or ""))
        timeout = int(contract.get("timeout_seconds") or REQUEST_TIMEOUT_SECONDS)
    except Exception:
        timeout = REQUEST_TIMEOUT_SECONDS
    return max(REQUEST_TIMEOUT_SECONDS, timeout + REQUEST_TIMEOUT_GRACE_SECONDS)


def _timeout_payload(name, timeout):
    name = str(name or "")
    render_like = any(term in name for term in ("render", "playblast", "thumbnail"))
    active = _active_operation_status()
    last = _last_operation_status()
    recovery = _operation_recovery_guidance(name)
    return {
        "ok": False,
        "result": {
            "ok": False,
            "code": "bridge_main_thread_timeout",
            "message": (
                f"Blender did not finish tool '{name or '(unknown)'}' within {int(timeout)}s. "
                "The operation may still be running on Blender's main thread; wait for Blender to become responsive, "
                "then call blender_bridge_status or get_visual_evidence_resources. For long renders/playblasts, "
                "use start_render_job and poll get_render_job_status instead of blocking preview/render tools."
            ),
            "tool": name,
            "timeout_seconds": int(timeout),
            "request_may_still_be_running": True,
            "result_may_be_lost_after_client_timeout": True,
            "recoverable": True,
            "poll_after_seconds": int(recovery.get("poll_after_seconds") or 5),
            "status_tool": str(recovery.get("status_tool") or "blender_bridge_status"),
            "resource_tool": str(recovery.get("resource_tool") or "get_visual_evidence_resources"),
            "recommended_tool": str(recovery.get("recommended_tool") or ("start_render_job" if render_like else "")),
            "recovery_hint": str(recovery.get("message") or ""),
            "active_operation": active,
            "last_operation": last,
        },
    }


def _call_on_main(fn, timeout=REQUEST_TIMEOUT_SECONDS):
    event = threading.Event()
    request = {"fn": fn, "event": event, "result": None, "error": None}
    _requests.put(request)
    if not event.wait(timeout=float(timeout)):
        raise TimeoutError("Timed out waiting for Blender main thread")
    if request["error"] is not None:
        raise request["error"]
    return request["result"]


def _process_requests():
    global _timer_registered
    while True:
        try:
            request = _requests.get_nowait()
        except queue.Empty:
            break
        try:
            request["result"] = request["fn"]()
        except Exception as exc:
            request["error"] = exc
        finally:
            request["event"].set()
    if is_running() or not _requests.empty():
        return 0.05
    _timer_registered = False
    return None


def _process_timer_is_registered():
    is_registered = getattr(bpy.app.timers, "is_registered", None)
    if not is_registered:
        return bool(_timer_registered)
    try:
        return bool(is_registered(_process_requests))
    except Exception:
        return bool(_timer_registered)


def _register_process_timer():
    try:
        bpy.app.timers.register(_process_requests, first_interval=0.05, persistent=True)
    except TypeError:
        bpy.app.timers.register(_process_requests, first_interval=0.05)


def _ensure_timer():
    global _timer_registered
    if _process_timer_is_registered():
        _timer_registered = True
        return
    _register_process_timer()
    _timer_registered = True


@persistent
def _ensure_timer_after_load(_dummy):
    global _timer_registered
    if is_running() or not _requests.empty():
        if not _process_timer_is_registered():
            _timer_registered = False
        _ensure_timer()


def _remove_timer_load_handler():
    handlers = bpy.app.handlers.load_post
    for handler in list(handlers):
        if (
            getattr(handler, "__name__", "") == "_ensure_timer_after_load"
            and str(getattr(handler, "__module__", "")).endswith(".bridge_server")
        ):
            handlers.remove(handler)


class _BridgeHandler(BaseHTTPRequestHandler):
    server_version = "BlenderAgentBridge/0.2"
    timeout = REQUEST_READ_TIMEOUT_SECONDS

    def log_message(self, fmt, *args):
        return

    def _host_origin_allowed(self):
        host = self.headers.get("Host", "") or ""
        if host:
            host_value = host.strip()
            if host_value.startswith("[") and "]" in host_value:
                hostname = host_value[1:host_value.find("]")]
            else:
                hostname = host_value.rsplit(":", 1)[0]
            hostname = hostname.strip().lower()
            if hostname and hostname not in ALLOWED_HOST_NAMES:
                return False
        origin = self.headers.get("Origin")
        if origin:
            origin_host = (urllib.parse.urlparse(origin).hostname or "").lower()
            if origin_host not in ALLOWED_HOST_NAMES:
                return False
        return True

    def _send(self, status, payload):
        data = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, status, message):
        self._send(status, {"ok": False, "message": message})

    def _authorized(self):
        token = getattr(self.server, "auth_token", "") or ""
        if not token:
            return True
        header = self.headers.get("Authorization", "")
        return hmac.compare_digest(header, f"Bearer {token}")

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            raise _RequestTooLarge("Invalid Content-Length header")
        if length <= 0:
            return {}
        if length > MAX_REQUEST_BODY_BYTES:
            raise _RequestTooLarge(
                f"Request body of {length} bytes exceeds the {MAX_REQUEST_BODY_BYTES}-byte limit"
            )
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def do_GET(self):
        if not self._host_origin_allowed():
            self._send_error(403, "Forbidden host or origin")
            return
        if not self._authorized():
            self._send_error(401, "Unauthorized")
            return
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path == "/health":
                if _active_operation_status():
                    self._send(200, _busy_scene_status())
                else:
                    try:
                        self._send(200, _call_on_main(_scene_status, timeout=STATUS_PROBE_TIMEOUT_SECONDS))
                    except TimeoutError:
                        self._send(
                            200,
                            _busy_scene_status(
                                "Blender main thread did not answer the status probe quickly. "
                                "A render, playblast, script, or manual Blender operation may still be running."
                            ),
                        )
            elif parsed.path == "/tools":
                self._send(200, {"ok": True, "tools": _tool_definitions()})
            elif parsed.path == "/contracts":
                self._send(200, {"ok": True, **bridge_protocol.list_tool_contracts()})
            elif parsed.path == "/resources":
                self._send(200, {"ok": True, "resources": _resources()})
            elif parsed.path == "/resource":
                uri = (query.get("uri") or [""])[0]
                resource = _call_on_main(lambda: _read_resource(uri))
                if resource is None:
                    self._send_error(404, f"Unknown resource: {uri}")
                else:
                    self._send(200, {"ok": True, "uri": uri, **resource})
            else:
                self._send_error(404, f"Unknown endpoint: {parsed.path}")
        except Exception as exc:
            self._send_error(500, f"{type(exc).__name__}: {exc}")

    def do_POST(self):
        if not self._host_origin_allowed():
            self._send_error(403, "Forbidden host or origin")
            return
        if not self._authorized():
            self._send_error(401, "Unauthorized")
            return
        parsed = urllib.parse.urlparse(self.path)
        payload = {}
        try:
            payload = self._read_json()
            if parsed.path == "/tool":
                tool_name = str(payload.get("name") or "") if isinstance(payload, dict) else ""
                timeout = _tool_timeout_seconds(tool_name)
                self._send(200, _call_on_main(lambda: _execute_tool(payload), timeout=timeout))
            else:
                self._send_error(404, f"Unknown endpoint: {parsed.path}")
        except TimeoutError:
            tool_name = str(payload.get("name") or "") if isinstance(payload, dict) else ""
            try:
                audit_log.append_event(
                    "bridge_tool_timeout",
                    source="bridge",
                    tool_name=tool_name,
                    timeout_seconds=_tool_timeout_seconds(tool_name),
                    active_operation=_active_operation_status(),
                    recovery=_operation_recovery_guidance(tool_name),
                )
            except Exception:
                pass
            self._send(504, _timeout_payload(tool_name, _tool_timeout_seconds(tool_name)))
        except _RequestTooLarge as exc:
            self._send_error(413, str(exc))
        except json.JSONDecodeError as exc:
            self._send_error(400, f"Invalid JSON: {exc}")
        except Exception as exc:
            self._send_error(500, f"{type(exc).__name__}: {exc}")


def is_running():
    return _server is not None


def bridge_url():
    if not _server:
        return ""
    host, port = _server.server_address
    return f"http://{host}:{port}"


def start_bridge(*, host=DEFAULT_HOST, port=DEFAULT_PORT, auth_token=""):
    global _server, _thread
    with _lock:
        if _server is not None:
            return {"ok": True, "message": "Bridge already running", "url": bridge_url()}
        if host != DEFAULT_HOST:
            return {"ok": False, "message": "Bridge only supports localhost binding"}
        _ensure_timer()
        server = ThreadingHTTPServer((DEFAULT_HOST, int(port)), _BridgeHandler)
        server.auth_token = str(auth_token or "")
        thread = threading.Thread(target=server.serve_forever, name="BlenderAgentBridge", daemon=True)
        thread.start()
        _server = server
        _thread = thread
    url = bridge_url()
    script_runner.clear_external_script_trust_for_all_scenes(
        status=script_runner.NO_EXTERNAL_TRUST_STATUS,
        audit_action="clear_on_bridge_start",
    )
    _set_scene_bridge_state(running=True, url=url, status=f"Bridge running at {url}")
    return {"ok": True, "message": f"Bridge running at {url}", "url": url}


def stop_bridge():
    global _server, _thread
    with _lock:
        server = _server
        thread = _thread
        _server = None
        _thread = None
    if server:
        server.shutdown()
        server.server_close()
    if thread and thread.is_alive():
        thread.join(timeout=2)
    _set_scene_bridge_state(running=False, url="", status="Bridge stopped")
    return {"ok": True, "message": "Bridge stopped"}


def status():
    return {
        "ok": True,
        "running": is_running(),
        "url": bridge_url(),
        "bridge_version": bridge_protocol.BRIDGE_VERSION,
        "addon_version": build_info.ADDON_VERSION,
        "mcp_server_version": build_info.MCP_SERVER_VERSION,
        "mcp_config_version": build_info.MCP_CONFIG_VERSION,
    }


def _set_scene_bridge_state(*, running, url, status):
    scene = getattr(bpy.context, "scene", None)
    state = getattr(scene, "claude_blender", None) if scene else None
    if state:
        state.bridge_running = bool(running)
        state.bridge_url = str(url or "")
        state.bridge_status = str(status or "")
        state.status = state.bridge_status


def register():
    _remove_timer_load_handler()
    bpy.app.handlers.load_post.append(_ensure_timer_after_load)


def unregister():
    _remove_timer_load_handler()
    stop_bridge()
