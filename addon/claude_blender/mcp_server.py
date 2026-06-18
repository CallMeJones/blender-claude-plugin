"""Stdio MCP server that forwards tool/resource calls to Blender's localhost bridge."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

try:
    from . import audit_log, anthropic_client, bridge_protocol, build_info
except ImportError:  # Allows direct execution as addon/claude_blender/mcp_server.py.
    package_parent = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if package_parent not in sys.path:
        sys.path.insert(0, package_parent)
    try:
        from claude_blender import audit_log, anthropic_client, bridge_protocol, build_info
    except ImportError:
        import audit_log
        import build_info
        import bridge_protocol

        anthropic_client = None


PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = (PROTOCOL_VERSION,)
SERVER_NAME = "claude-blender"
SERVER_VERSION = build_info.MCP_SERVER_VERSION
DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 100
FULL_TOOL_LIST_ENV = "BLENDER_MCP_FULL_TOOL_LIST"
COMPACT_DIRECT_TOOL_NAMES = (
    "list_scene_objects",
    "plan_animation_workflow",
    "run_animation_workflow",
    "run_animation_task",
    "start_render_job",
    "get_render_job_status",
    "cancel_render_job",
)
CATALOG_TOOL_NAME = "blender_tool_catalog"
WRAPPER_TOOL_NAMES = {
    "blender_bridge_status",
    CATALOG_TOOL_NAME,
    "search_blender_tools",
    "get_blender_tool_schema",
    "invoke_blender_tool",
}

ANIMATION_ROUTE_TERMS = {
    "animate",
    "animation",
    "bounce",
    "jump",
    "keyframe",
    "keyframes",
    "pose",
    "timing",
    "arc",
    "arcs",
    "settle",
    "squash",
    "stretch",
    "playblast",
    "f-curve",
    "fcurve",
    "block",
    "blocking",
    "anticipation",
    "contact",
    "spacing",
}
ANIMATION_ROUTE_TOOLS = {
    "run_animation_task",
    "plan_animation_workflow",
    "run_animation_workflow",
    "create_animation_brief",
    "create_timing_chart",
    "get_animation_scene_context",
    "analyze_animation_principles",
    "compare_animation_to_brief",
    "review_playblast_against_brief",
    "review_inspection_renders_against_brief",
    "repair_animation_from_findings",
    "run_animation_repair_loop",
    "capture_animation_playblast",
    "set_rig_pose_hold",
}
GENERIC_SELECTED_OBJECT_TOOLS = {
    "set_selected_location_delta",
    "set_selected_transform",
    "select_objects",
}
SCRIPT_EXPLICIT_TERMS = {
    "script",
    "python",
    "custom code",
    "custom python",
    "draft_script",
    "helper tools cannot express",
    "helpers cannot express",
    "approved script",
}

TOOL_CATEGORY_LABELS = {
    "inspect": "Scene Inspection",
    "transform": "Selection And Transform",
    "creation": "Object Creation",
    "materials": "Materials And Shading",
    "animation": "Animation",
    "camera_render": "Camera, Light, And Render",
    "geometry": "Geometry And Modifiers",
    "rigging": "Rigging And Constraints",
    "simulation": "Simulation",
    "organization": "Collections And Organization",
    "preview": "Preview Control",
    "script": "Approval-Gated Python",
    "scene": "Scene Settings",
    "navigation": "Workspace And View Navigation",
    "other": "Other",
}

GENERIC_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "message": {"type": "string"},
    },
    "additionalProperties": True,
}

STATUS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "bridge_url": {"type": "string"},
        "message": {"type": "string"},
        "bridge_version": {"type": "string"},
        "blender_version": {"type": "string"},
        "addon_id": {"type": "string"},
        "addon_name": {"type": "string"},
        "addon_version": {"type": "string"},
        "addon_path": {"type": "string"},
        "mcp_server_version": {"type": "string"},
        "mcp_server_path": {"type": "string"},
        "mcp_config_version": {"type": "string"},
        "build_diagnostics": {"type": "string"},
        "scene": {"type": "string"},
        "external_script_trust": {"type": "boolean"},
        "external_script_trust_status": {"type": "string"},
        "external_script_trust_expires_at": {"type": "number"},
        "external_script_trust_seconds_remaining": {"type": "integer"},
        "external_script_trust_can_run_without_token": {"type": "boolean"},
        "external_script_trust_session": {"type": "boolean"},
        "external_script_trust_stale_scene_state": {"type": "boolean"},
        "mcp_client_refresh_hint": {"type": "string"},
    },
    "required": ["ok"],
    "additionalProperties": True,
}

RESOURCE_TEMPLATES = [
    {
        "uriTemplate": "blender://scene/{resource}",
        "name": "scene-resource",
        "title": "Blender Scene Resource",
        "description": "Scene resources such as status or context exposed by the running Blender bridge.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://tools/{resource}",
        "name": "tool-resource",
        "title": "Blender Tool Resource",
        "description": "Tool metadata resources such as the normalized contract registry.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://transcript/{resource}",
        "name": "transcript-resource",
        "title": "Blender Transcript Resource",
        "description": "Transcript resources from the Blender add-on.",
        "mimeType": "text/plain",
    },
    {
        "uriTemplate": "blender://audit/{resource}",
        "name": "audit-resource",
        "title": "Blender Audit Resource",
        "description": "Recent local audit events for MCP and bridge tool calls.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://captures/{capture_id}",
        "name": "capture-resource",
        "title": "Blender Capture Resource",
        "description": "Exact viewport screenshot PNG resources captured by the running Blender bridge.",
        "mimeType": "image/png",
    },
    {
        "uriTemplate": "blender://captures/{capture_id}/metadata",
        "name": "capture-metadata-resource",
        "title": "Blender Capture Metadata Resource",
        "description": "Exact viewport screenshot metadata for a capture from the running Blender bridge.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://playblasts/{playblast_id}/metadata",
        "name": "playblast-metadata-resource",
        "title": "Blender Playblast Metadata Resource",
        "description": "Animation playblast metadata with sampled frame resource URIs.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://playblasts/{playblast_id}/frames/{frame}",
        "name": "playblast-frame-resource",
        "title": "Blender Playblast Frame Resource",
        "description": "Sampled animation playblast frame PNG resources captured by the running Blender bridge.",
        "mimeType": "image/png",
    },
    {
        "uriTemplate": "blender://inspection-renders/{render_id}/metadata",
        "name": "inspection-render-metadata-resource",
        "title": "Blender Inspection Render Metadata Resource",
        "description": "Diagnostic object render metadata with close-up image resource URIs.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://inspection-renders/{render_id}/images/{image_id}",
        "name": "inspection-render-image-resource",
        "title": "Blender Inspection Render Image Resource",
        "description": "Diagnostic close-up object render PNG resources captured by the running Blender bridge.",
        "mimeType": "image/png",
    },
    {
        "uriTemplate": "blender://render-thumbnails/{thumbnail_id}",
        "name": "render-thumbnail-resource",
        "title": "Blender Render Thumbnail Resource",
        "description": "Scene thumbnail PNG resources rendered by the running Blender bridge.",
        "mimeType": "image/png",
    },
    {
        "uriTemplate": "blender://render-thumbnails/{thumbnail_id}/metadata",
        "name": "render-thumbnail-metadata-resource",
        "title": "Blender Render Thumbnail Metadata Resource",
        "description": "Scene thumbnail metadata for a rendered still from the running Blender bridge.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://render-jobs/{job_id}/metadata",
        "name": "render-job-metadata-resource",
        "title": "Blender Render Job Metadata Resource",
        "description": "Async render job status, output paths, progress, and resource URIs.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "blender://render-jobs/{job_id}/frames/{frame}",
        "name": "render-job-frame-resource",
        "title": "Blender Render Job Frame Resource",
        "description": "Exact PNG frame output from an async render job.",
        "mimeType": "image/png",
    },
    {
        "uriTemplate": "blender://render-jobs/{job_id}/log",
        "name": "render-job-log-resource",
        "title": "Blender Render Job Log Resource",
        "description": "Background Blender render process log for an async render job.",
        "mimeType": "text/plain",
    },
    {
        "uriTemplate": "blender://render-jobs/{job_id}/video",
        "name": "render-job-video-resource",
        "title": "Blender Render Job Video Resource",
        "description": "MP4 output from an async video render job when small enough to return through MCP.",
        "mimeType": "video/mp4",
    },
]

PROMPTS = {
    "inspect_scene": {
        "name": "inspect_scene",
        "title": "Inspect Blender Scene",
        "description": "Ask an MCP client to inspect the active Blender scene before making changes.",
        "arguments": [
            {
                "name": "goal",
                "description": "Optional user goal or question to focus the inspection.",
                "required": False,
            }
        ],
        "template": (
            "Inspect the current Blender scene using read-only tools first. "
            "Summarize the relevant objects, materials, animation, camera, lights, and render context. "
            "User goal: {goal}"
        ),
    },
    "safe_scene_change": {
        "name": "safe_scene_change",
        "title": "Plan Safe Blender Change",
        "description": "Plan a scene change using reversible helper tools before approval-gated Python.",
        "arguments": [
            {
                "name": "goal",
                "description": "The scene change the user wants.",
                "required": True,
            }
        ],
        "template": (
            "Make this Blender change safely: {goal}\n\n"
            "Use read-only inspection first if needed. Prefer typed reversible helper tools for common edits. "
            "Only call draft_script when helper tools cannot express the change."
        ),
    },
    "advanced_animation_workflow": {
        "name": "advanced_animation_workflow",
        "title": "Run Advanced Animation Workflow",
        "description": "Guide an MCP client through the Milestone 7 animation brief, helper, evaluation, and repair workflow before scripts.",
        "arguments": [
            {
                "name": "goal",
                "description": "The animation generation, review, or repair goal.",
                "required": True,
            }
        ],
        "template": (
            "Handle this Blender animation task through the Milestone 7 workflow: {goal}\n\n"
            "For simple prompt-in/task-out use, call run_animation_task. For manual control, call "
            "plan_animation_workflow first. For common helper-backed generation, call "
            "run_animation_workflow to execute the plan, review the result, and leave changes as a preview. "
            "For manual control, follow next_tool_calls in order for brief, scene routing, timing, "
            "helper generation, validation, playblast review, and repair. "
            "When rendered visual evidence is needed for object details, use capture_object_inspection_renders. "
            "Use draft_script only when the workflow's script_fallback_policy says helpers cannot express the edit."
        ),
    },
    "draft_approved_script": {
        "name": "draft_approved_script",
        "title": "Draft Approval-Gated Blender Python",
        "description": "Draft Blender Python for explicit user approval inside Blender.",
        "arguments": [
            {
                "name": "goal",
                "description": "The scripted Blender task.",
                "required": True,
            }
        ],
        "template": (
            "Draft Blender Python for this task without running it: {goal}\n\n"
            "Search Blender docs before unfamiliar APIs. Call draft_script with complete code, intent, "
            "expected_changes, risk_level, and target_objects. Do not claim the script has executed."
        ),
    },
}


def _json_dumps(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=False)


def _stderr(message):
    print(message, file=sys.stderr, flush=True)


def _decode_cursor(cursor):
    if cursor in (None, ""):
        return 0
    try:
        return max(0, int(str(cursor)))
    except ValueError:
        return 0


def _page_items(items, params, result_key):
    params = params or {}
    start = _decode_cursor(params.get("cursor"))
    try:
        requested_limit = int(params.get("limit") or DEFAULT_PAGE_SIZE)
    except (TypeError, ValueError):
        requested_limit = DEFAULT_PAGE_SIZE
    limit = max(1, min(MAX_PAGE_SIZE, requested_limit))
    end = min(len(items), start + limit)
    result = {result_key: items[start:end]}
    if end < len(items):
        result["nextCursor"] = str(end)
    return result


def _schema_types(schema):
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return set(str(item) for item in schema_type)
    if isinstance(schema_type, str):
        return {schema_type}
    return set()


def _matches_json_type(value, schema_type):
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return True


def _integer_schema_value(schema, key):
    value = schema.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _validate_schema(value, schema, path="$"):
    """Validate the JSON Schema subset used by this project without dependencies."""

    if not isinstance(schema, dict):
        return []
    errors = []
    schema_types = _schema_types(schema)
    if schema_types and not any(_matches_json_type(value, item) for item in schema_types):
        errors.append(f"{path}: expected {', '.join(sorted(schema_types))}")
        return errors
    if "enum" in schema and value not in schema.get("enum", []):
        errors.append(f"{path}: expected one of {schema.get('enum')}")
        return errors
    if isinstance(value, dict):
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: required property is missing")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key}: additional property is not allowed")
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(_validate_schema(value[key], child_schema, f"{path}.{key}"))
    if isinstance(value, list):
        min_items = _integer_schema_value(schema, "minItems")
        max_items = _integer_schema_value(schema, "maxItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} item(s)")
        if max_items is not None and len(value) > max_items:
            errors.append(f"{path}: expected at most {max_items} item(s)")
        if isinstance(schema.get("items"), dict):
            item_schema = schema["items"]
            for index, item in enumerate(value):
                errors.extend(_validate_schema(item, item_schema, f"{path}[{index}]"))
    if isinstance(value, str):
        min_length = _integer_schema_value(schema, "minLength")
        max_length = _integer_schema_value(schema, "maxLength")
        if min_length is not None and len(value) < min_length:
            errors.append(f"{path}: expected at least {min_length} character(s)")
        if max_length is not None and len(value) > max_length:
            errors.append(f"{path}: expected at most {max_length} character(s)")
    return errors


def _normalize_tool_definition(tool):
    result = dict(tool or {})
    result.setdefault("inputSchema", result.pop("input_schema", {"type": "object"}))
    result.setdefault("outputSchema", GENERIC_OUTPUT_SCHEMA)
    result.setdefault("annotations", {})
    return result


def _contract_tool_definition(name, contract):
    normalized = bridge_protocol.normalized_tool_contract(name, contract)
    return {
        "name": name,
        "title": normalized.get("title") or name.replace("_", " ").title(),
        "description": normalized.get("description", ""),
        "inputSchema": normalized.get("input_schema") or {"type": "object", "properties": {}, "additionalProperties": True},
        "outputSchema": normalized.get("output_schema") or GENERIC_OUTPUT_SCHEMA,
        "annotations": bridge_protocol.mcp_annotations_for_tool(name),
    }


def _read_only_annotations(permissions=None):
    return {
        "mutatesScene": False,
        "hasSideEffects": False,
        "requiresApproval": False,
        "requiresLivePreview": False,
        "riskLevel": "read",
        "permissions": list(permissions or ["tools:read"]),
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


def _compact_tool_definitions():
    return [
        {
            "name": CATALOG_TOOL_NAME,
            "title": "Blender Tool Catalog",
            "description": (
                "Search, inspect, and invoke tools from the full Blender MCP catalog through one compact entry point."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["search", "schema", "invoke", "categories"],
                        "description": "Catalog action. Defaults to search.",
                    },
                    "query": {"type": "string", "description": "Search text such as material, camera, script, or preview"},
                    "limit": {"type": "integer", "description": "Maximum matching tools to return"},
                    "name": {"type": "string", "description": "Tool name for schema or invoke actions"},
                    "arguments": {"type": "object", "description": "Target tool arguments for invoke", "additionalProperties": True},
                    "category": {"type": "string", "description": "Filter by catalog category"},
                    "permission": {"type": "string", "description": "Filter by a required permission such as scene:mutate"},
                    "mutates_scene": {"type": "boolean", "description": "Filter by whether tools can mutate the scene"},
                    "requires_approval": {"type": "boolean", "description": "Filter by approval requirement"},
                    "requires_live_preview": {"type": "boolean", "description": "Filter by live-preview requirement"},
                    "risk_level": {"type": "string", "description": "Filter by risk level such as read, preview, or approval"},
                    "include_schemas": {"type": "boolean", "description": "Include input/output schemas in search results"},
                },
                "additionalProperties": False,
            },
            "outputSchema": GENERIC_OUTPUT_SCHEMA,
            "annotations": {
                "mutatesScene": True,
                "hasSideEffects": True,
                "requiresApproval": False,
                "requiresLivePreview": False,
                "riskLevel": "dynamic",
                "permissions": ["tools:read", "scene:read", "scene:mutate", "script:stage"],
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        },
        {
            "name": "search_blender_tools",
            "title": "Search Blender Tools",
            "description": "Search the full Blender MCP tool catalog by name, description, risk, and permissions.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text such as material, camera, script, or preview"},
                    "limit": {"type": "integer", "description": "Maximum matching tools to return"},
                    "category": {"type": "string", "description": "Filter by catalog category"},
                    "permission": {"type": "string", "description": "Filter by a required permission such as scene:mutate"},
                    "mutates_scene": {"type": "boolean", "description": "Filter by whether tools can mutate the scene"},
                    "requires_approval": {"type": "boolean", "description": "Filter by approval requirement"},
                    "requires_live_preview": {"type": "boolean", "description": "Filter by live-preview requirement"},
                    "risk_level": {"type": "string", "description": "Filter by risk level such as read, preview, or approval"},
                    "include_schemas": {"type": "boolean", "description": "Include input/output schemas in search results"},
                },
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                    "tools": {"type": "array"},
                    "count": {"type": "integer"},
                },
                "required": ["ok", "tools"],
                "additionalProperties": True,
            },
            "annotations": _read_only_annotations(),
        },
        {
            "name": "get_blender_tool_schema",
            "title": "Get Blender Tool Schema",
            "description": "Return the input schema, output schema, and safety annotations for one Blender tool.",
            "inputSchema": {
                "type": "object",
                "properties": {"name": {"type": "string", "minLength": 1}},
                "required": ["name"],
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                    "tool": {"type": "object"},
                },
                "required": ["ok"],
                "additionalProperties": True,
            },
            "annotations": _read_only_annotations(),
        },
        {
            "name": "invoke_blender_tool",
            "title": "Invoke Blender Tool",
            "description": (
                "Invoke a tool from the full Blender MCP catalog after looking up its schema. "
                "The target tool schema is validated before forwarding to Blender."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "arguments": {"type": "object", "additionalProperties": True},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            "outputSchema": GENERIC_OUTPUT_SCHEMA,
            "annotations": {
                "mutatesScene": True,
                "hasSideEffects": True,
                "requiresApproval": False,
                "requiresLivePreview": False,
                "riskLevel": "dynamic",
                "permissions": ["scene:read", "scene:mutate", "script:stage"],
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        },
    ]


def _static_tool_definitions():
    tools = []
    seen = set()
    if anthropic_client is not None:
        try:
            for tool in anthropic_client.blender_tool_definitions():
                name = str(tool.get("name") or "")
                if not name:
                    continue
                contract = bridge_protocol.normalized_tool_contract(
                    name,
                    bridge_protocol.TOOL_CONTRACTS.get(name, {}),
                )
                tools.append(
                    {
                        "name": name,
                        "title": contract.get("title") or name.replace("_", " ").title(),
                        "description": tool.get("description", contract.get("description", "")),
                        "inputSchema": tool.get("input_schema") or tool.get("inputSchema") or {"type": "object"},
                        "outputSchema": contract.get("output_schema") or GENERIC_OUTPUT_SCHEMA,
                        "annotations": bridge_protocol.mcp_annotations_for_tool(name),
                    }
                )
                seen.add(name)
        except Exception as exc:
            _stderr(f"static tools warning: {exc}")
    for name, contract in bridge_protocol.TOOL_CONTRACTS.items():
        if name not in seen:
            tools.append(_contract_tool_definition(name, contract))
            seen.add(name)
    return tools


def _merge_tool_definitions(primary, fallback):
    merged = []
    seen = set()
    for tool in list(primary or []) + list(fallback or []):
        name = str((tool or {}).get("name") or "")
        if not name or name in seen:
            continue
        merged.append(_normalize_tool_definition(tool))
        seen.add(name)
    return merged


def _truthy_env(name):
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _tool_search_text(tool):
    annotations = tool.get("annotations") or {}
    schema = tool.get("inputSchema") or {}
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    category = _tool_category(tool)
    parts = [
        tool.get("name", ""),
        tool.get("title", ""),
        tool.get("description", ""),
        category,
        TOOL_CATEGORY_LABELS.get(category, ""),
        annotations.get("riskLevel", ""),
        " ".join(str(item) for item in annotations.get("permissions", []) or []),
        " ".join(str(item) for item in properties),
    ]
    return " ".join(str(part).lower() for part in parts if part)


def _contains_any_phrase(text, phrases):
    normalized = str(text or "").lower()
    for phrase in phrases:
        phrase_text = str(phrase or "").strip().lower()
        if not phrase_text:
            continue
        pattern = re.escape(phrase_text).replace(r"\ ", r"\s+")
        if re.search(rf"(?<![a-z0-9_]){pattern}(?![a-z0-9_])", normalized):
            return True
    return False


def _tool_category(tool):
    name = str((tool or {}).get("name") or "").lower()
    if name in {"draft_script", "run_approved_script"}:
        return "script"
    if name in {"commit_preview", "revert_preview"}:
        return "preview"
    if name in {"get_workspace_layout", "jump_to_workspace", "focus_object_in_viewport"}:
        return "navigation"
    if name in {"start_render_job", "get_render_job_status", "cancel_render_job"}:
        return "camera_render"
    if name.startswith("get_") or name.startswith("list_") or name in {
        "inspect_scene",
        "search_blender_docs",
        "capture_viewport",
        "capture_animation_playblast",
        "capture_object_inspection_renders",
        "review_inspection_renders_against_brief",
    }:
        return "inspect"
    if name == "analyze_center_of_mass":
        return "animation"
    if "material" in name or "shader" in name or name == "set_world_background":
        return "materials"
    if "camera" in name or "render" in name or name in {"add_light", "set_active_camera"}:
        return "camera_render"
    if "animate" in name or "animation" in name or "frame" in name:
        return "animation"
    if "geometry" in name or "modifier" in name or "bevel" in name or "subsurf" in name or "shape_key" in name:
        return "geometry"
    if "rigging" in name or "armature" in name or "constraint" in name or name == "set_rig_pose_hold":
        return "rigging"
    if "simulation" in name or "particle" in name:
        return "simulation"
    if "collection" in name:
        return "organization"
    if name.startswith("create_") or name.startswith("add_") or name.startswith("apply_"):
        return "creation"
    if "transform" in name or "selected" in name or name == "select_objects":
        return "transform"
    if name.startswith("set_"):
        return "scene"
    return "other"


def _tool_summary(tool, *, include_schema=True):
    annotations = dict(tool.get("annotations") or {})
    category = _tool_category(tool)
    summary = {
        "name": tool.get("name", ""),
        "title": tool.get("title", ""),
        "description": tool.get("description", ""),
        "category": category,
        "category_label": TOOL_CATEGORY_LABELS.get(category, TOOL_CATEGORY_LABELS["other"]),
        "risk_level": annotations.get("riskLevel", ""),
        "permissions": list(annotations.get("permissions", []) or []),
        "mutates_scene": bool(annotations.get("mutatesScene", False)),
        "has_side_effects": bool(annotations.get("hasSideEffects", False)),
        "requires_approval": bool(annotations.get("requiresApproval", False)),
        "requires_live_preview": bool(annotations.get("requiresLivePreview", False)),
    }
    if include_schema:
        summary["input_schema"] = tool.get("inputSchema") or {}
        summary["output_schema"] = tool.get("outputSchema") or GENERIC_OUTPUT_SCHEMA
        summary["annotations"] = annotations
    return summary


def _bounded_limit(value, default=12, maximum=50):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    return max(1, min(int(maximum), result))


def _tool_result(content_text, structured, *, is_error=False):
    if not isinstance(structured, dict):
        structured = {"ok": not is_error, "text": str(content_text)}
    structured.setdefault("ok", not is_error)
    return {
        "content": [{"type": "text", "text": str(content_text)}],
        "structuredContent": structured,
        "isError": bool(is_error),
    }


def _catalog_filters(arguments):
    return {
        "query": str(arguments.get("query") or "").strip(),
        "category": str(arguments.get("category") or "").strip().lower(),
        "permission": str(arguments.get("permission") or "").strip().lower(),
        "risk_level": str(arguments.get("risk_level") or "").strip().lower(),
        "mutates_scene": arguments.get("mutates_scene") if isinstance(arguments.get("mutates_scene"), bool) else None,
        "requires_approval": (
            arguments.get("requires_approval") if isinstance(arguments.get("requires_approval"), bool) else None
        ),
        "requires_live_preview": (
            arguments.get("requires_live_preview") if isinstance(arguments.get("requires_live_preview"), bool) else None
        ),
    }


def _tool_matches_filters(tool, filters):
    annotations = tool.get("annotations") or {}
    category = _tool_category(tool)
    if filters["category"] and category != filters["category"]:
        return False
    if filters["permission"]:
        permissions = [str(item).lower() for item in annotations.get("permissions", []) or []]
        if filters["permission"] not in permissions:
            return False
    if filters["risk_level"] and str(annotations.get("riskLevel") or "").lower() != filters["risk_level"]:
        return False
    if filters["mutates_scene"] is not None and bool(annotations.get("mutatesScene", False)) is not filters["mutates_scene"]:
        return False
    if filters["requires_approval"] is not None and bool(annotations.get("requiresApproval", False)) is not filters["requires_approval"]:
        return False
    if (
        filters["requires_live_preview"] is not None
        and bool(annotations.get("requiresLivePreview", False)) is not filters["requires_live_preview"]
    ):
        return False
    return True


def _score_tool_match(tool, query):
    normalized_query = str(query or "").strip().lower()
    if not normalized_query:
        return 0
    terms = [term for term in normalized_query.split() if term]
    text = _tool_search_text(tool)
    name = str(tool.get("name") or "").lower()
    title = str(tool.get("title") or "").lower()
    category = _tool_category(tool)
    animation_query = _contains_any_phrase(normalized_query, ANIMATION_ROUTE_TERMS)
    explicit_script_query = _contains_any_phrase(normalized_query, SCRIPT_EXPLICIT_TERMS)
    matched_terms = [term for term in terms if term in text]
    if not matched_terms:
        if animation_query and (name in ANIMATION_ROUTE_TOOLS or category == "animation"):
            score = 25
        else:
            return None
    else:
        score = sum(text.count(term) for term in terms)
        score += len(matched_terms) * 5
        if len(matched_terms) == len(terms):
            score += 15
    if name == normalized_query:
        score += 1000
    elif name.startswith(normalized_query):
        score += 200
    if title == normalized_query:
        score += 500
    elif title.startswith(normalized_query):
        score += 100
    if animation_query:
        if name == "run_animation_task":
            score += 1200
        elif name == "plan_animation_workflow":
            score += 1000
        elif name == "run_animation_workflow":
            score += 950
        elif name in ANIMATION_ROUTE_TOOLS:
            score += 500
        elif category == "animation":
            score += 250
        if name in GENERIC_SELECTED_OBJECT_TOOLS:
            score -= 250
        if name == "draft_script" and not explicit_script_query:
            score -= 1000
    elif name == "draft_script" and not explicit_script_query:
        score -= 100
    return score


def _catalog_facets(tools):
    categories = {}
    risk_levels = {}
    permissions = {}
    for tool in tools:
        annotations = tool.get("annotations") or {}
        category = _tool_category(tool)
        categories[category] = categories.get(category, 0) + 1
        risk = str(annotations.get("riskLevel") or "unknown")
        risk_levels[risk] = risk_levels.get(risk, 0) + 1
        for permission in annotations.get("permissions", []) or []:
            key = str(permission)
            permissions[key] = permissions.get(key, 0) + 1
    return {
        "categories": [
            {
                "name": name,
                "label": TOOL_CATEGORY_LABELS.get(name, TOOL_CATEGORY_LABELS["other"]),
                "count": count,
            }
            for name, count in sorted(categories.items())
        ],
        "risk_levels": [{"name": name, "count": count} for name, count in sorted(risk_levels.items())],
        "permissions": [{"name": name, "count": count} for name, count in sorted(permissions.items())],
    }


def _tool_error(message, *, code="tool_error", data=None):
    structured = {"ok": False, "code": str(code), "message": str(message)}
    if data is not None:
        structured["data"] = data
    return _tool_result(json.dumps(structured, indent=2, sort_keys=True), structured, is_error=True)


def _audit_tool_call(name, arguments, result, *, tool=None):
    try:
        structured = result.get("structuredContent") if isinstance(result, dict) else {}
        annotations = (tool or {}).get("annotations") or {}
        audit_log.append_event(
            "mcp_tool_call",
            source="mcp",
            tool_name=str(name or ""),
            ok=bool(structured.get("ok", False)) if isinstance(structured, dict) else False,
            is_error=bool(result.get("isError", True)) if isinstance(result, dict) else True,
            code=structured.get("code", "") if isinstance(structured, dict) else "",
            risk_level=annotations.get("riskLevel", ""),
            mutates_scene=bool(annotations.get("mutatesScene", False)),
            requires_approval=bool(annotations.get("requiresApproval", False)),
            arguments=audit_log.summarize_arguments(arguments),
        )
    except Exception as exc:
        _stderr(f"audit warning: {exc}")


class BridgeClient:
    def __init__(self, base_url, token="", timeout=30):
        self.base_url = str(base_url or DEFAULT_BRIDGE_URL).rstrip("/")
        self.token = str(token or "")
        self.timeout = float(timeout)

    def _headers(self):
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get(self, path, params=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Bridge HTTP {exc.code}: {detail}") from exc
        except OSError as exc:
            raise RuntimeError(f"Bridge unavailable at {self.base_url}: {exc}") from exc

    def post(self, path, payload):
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=max(self.timeout, 65.0)) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Bridge HTTP {exc.code}: {detail}") from exc
        except OSError as exc:
            raise RuntimeError(f"Bridge unavailable at {self.base_url}: {exc}") from exc


class BlenderMCPServer:
    def __init__(self, bridge):
        self.bridge = bridge
        self._tool_cache = None
        self._full_tool_cache = None
        self._log_level = "info"
        self._full_tool_list = _truthy_env(FULL_TOOL_LIST_ENV)

    def initialize(self, params):
        requested = (params or {}).get("protocolVersion") or PROTOCOL_VERSION
        protocol = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        return {
            "protocolVersion": protocol,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False},
                "prompts": {"listChanged": False},
                "logging": {},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "title": "Blender Agent Bridge",
                "version": SERVER_VERSION,
            },
            "instructions": (
                "Connects MCP-capable AI clients to the running Blender scene through the Blender Agent Bridge localhost service. "
                "Start the bridge inside Blender before using scene tools. By default, this server exposes a compact "
                "tool surface; use search_blender_tools, get_blender_tool_schema, and invoke_blender_tool for the full "
                "Blender helper catalog. Mutating tools affect the live scene and may leave preview changes pending."
            ),
        }

    def _bridge_status_tool(self):
        return {
            "name": "blender_bridge_status",
            "title": "Blender Bridge Status",
            "description": "Check whether the MCP server can reach the running Blender localhost bridge.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "outputSchema": STATUS_OUTPUT_SCHEMA,
            "annotations": {
                "mutatesScene": False,
                "riskLevel": "read",
                "permissions": ["bridge:status"],
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def _load_full_tools(self):
        bridge_tools = []
        try:
            response = self.bridge.get("/tools")
            bridge_tools = response.get("tools") or []
        except Exception as exc:
            _stderr(f"tools/list bridge warning: {exc}")
        tools = _merge_tool_definitions(bridge_tools, _static_tool_definitions())
        self._full_tool_cache = tools
        return tools

    def _full_tool_definition(self, name):
        tools = self._full_tool_cache or self._load_full_tools()
        for tool in tools:
            if tool.get("name") == name:
                return tool
        tools = self._load_full_tools()
        for tool in tools:
            if tool.get("name") == name:
                return tool
        return None

    def _load_tools(self):
        if self._full_tool_list:
            compact = {tool["name"]: tool for tool in _compact_tool_definitions()}
            tools = [self._bridge_status_tool(), _normalize_tool_definition(compact[CATALOG_TOOL_NAME])]
            tools.extend(self._load_full_tools())
        else:
            tools = [self._bridge_status_tool()]
            compact = {tool["name"]: tool for tool in _compact_tool_definitions()}
            for name in COMPACT_DIRECT_TOOL_NAMES:
                tool = self._full_tool_definition(name)
                if tool:
                    compact[name] = tool
            for name in (
                CATALOG_TOOL_NAME,
                "search_blender_tools",
                "get_blender_tool_schema",
                "invoke_blender_tool",
                *COMPACT_DIRECT_TOOL_NAMES,
            ):
                if name in compact:
                    tools.append(_normalize_tool_definition(compact[name]))
        self._tool_cache = tools
        return tools

    def _tool_definition(self, name):
        tools = self._tool_cache or self._load_tools()
        for tool in tools:
            if tool.get("name") == name:
                return tool
        tools = self._load_tools()
        for tool in tools:
            if tool.get("name") == name:
                return tool
        return None

    def tools_list(self, params=None):
        return _page_items(self._load_tools(), params, "tools")

    def tools_call(self, params):
        params = params or {}
        name = params.get("name")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(name, str) or not name:
            result = _tool_error("Missing tool name", code="invalid_request")
            _audit_tool_call(name, arguments, result)
            return result
        if not isinstance(arguments, dict):
            result = _tool_error("Tool arguments must be a JSON object", code="invalid_arguments")
            _audit_tool_call(name, arguments, result)
            return result
        tool = self._tool_definition(name)
        if tool is None:
            result = _tool_error(f"Unknown tool: {name}", code="unknown_tool")
            _audit_tool_call(name, arguments, result)
            return result
        validation_errors = _validate_schema(arguments, tool.get("inputSchema") or {"type": "object"})
        if validation_errors:
            result = _tool_error(
                "Tool arguments failed schema validation",
                code="invalid_arguments",
                data={"errors": validation_errors},
            )
            _audit_tool_call(name, arguments, result, tool=tool)
            return result
        if name == "blender_bridge_status":
            status = self._bridge_status()
            result = _tool_result(
                json.dumps(status, indent=2, sort_keys=True),
                status,
                is_error=not bool(status.get("ok")),
            )
            _audit_tool_call(name, arguments, result, tool=tool)
            return result
        if name == "search_blender_tools":
            result = self._search_blender_tools(arguments)
            _audit_tool_call(name, arguments, result, tool=tool)
            return result
        if name == CATALOG_TOOL_NAME:
            result = self._blender_tool_catalog(arguments)
            _audit_tool_call(name, arguments, result, tool=tool)
            return result
        if name == "get_blender_tool_schema":
            result = self._get_blender_tool_schema(arguments)
            _audit_tool_call(name, arguments, result, tool=tool)
            return result
        if name == "invoke_blender_tool":
            result = self._invoke_blender_tool(arguments)
            _audit_tool_call(name, arguments, result, tool=tool)
            return result
        try:
            response = self.bridge.post("/tool", {"name": name, "arguments": arguments})
        except Exception as exc:
            result = _tool_error(str(exc), code="bridge_unavailable")
            _audit_tool_call(name, arguments, result, tool=tool)
            return result
        result = response.get("result", response)
        ok = bool(response.get("ok", True)) and bool(result.get("ok", True) if isinstance(result, dict) else True)
        text = json.dumps(result, indent=2, sort_keys=True, default=str)
        tool_result = _tool_result(text, result if isinstance(result, dict) else {"text": text}, is_error=not ok)
        _audit_tool_call(name, arguments, tool_result, tool=tool)
        return tool_result

    def _search_catalog(self, arguments):
        limit = _bounded_limit(arguments.get("limit"), default=12, maximum=50)
        include_schemas = bool(arguments.get("include_schemas", False))
        filters = _catalog_filters(arguments)
        matches = []
        for tool in self._load_full_tools():
            if not _tool_matches_filters(tool, filters):
                continue
            score = _score_tool_match(tool, filters["query"])
            if score is None:
                continue
            matches.append((score, str(tool.get("name") or ""), tool))
        matches.sort(key=lambda item: (-item[0], item[1]))
        tools = [_tool_summary(tool, include_schema=include_schemas) for _, _, tool in matches[:limit]]
        structured = {
            "ok": True,
            "query": filters["query"],
            "count": len(tools),
            "total": len(matches),
            "tools": tools,
            "filters": {
                key: value
                for key, value in filters.items()
                if value not in ("", None)
            },
        }
        return _tool_result(json.dumps(structured, indent=2, sort_keys=True), structured)

    def _search_blender_tools(self, arguments):
        compatible_arguments = dict(arguments)
        compatible_arguments.setdefault("include_schemas", True)
        return self._search_catalog(compatible_arguments)

    def _catalog_categories(self, arguments):
        filters = _catalog_filters(arguments)
        tools = [
            tool
            for tool in self._load_full_tools()
            if _tool_matches_filters(tool, filters) and _score_tool_match(tool, filters["query"]) is not None
        ]
        structured = {"ok": True, "total": len(tools), "facets": _catalog_facets(tools)}
        return _tool_result(json.dumps(structured, indent=2, sort_keys=True), structured)

    def _blender_tool_catalog(self, arguments):
        action = str(arguments.get("action") or "search").strip().lower()
        if action == "search":
            return self._search_catalog(arguments)
        if action == "categories":
            return self._catalog_categories(arguments)
        if action == "schema":
            return self._get_blender_tool_schema({"name": arguments.get("name")})
        if action == "invoke":
            return self._invoke_blender_tool(
                {
                    "name": arguments.get("name"),
                    "arguments": arguments.get("arguments") or {},
                }
            )
        return _tool_error(f"Unknown catalog action: {action}", code="invalid_arguments")

    def _get_blender_tool_schema(self, arguments):
        name = str(arguments.get("name") or "").strip()
        tool = self._full_tool_definition(name)
        if tool is None:
            return _tool_error(f"Unknown Blender tool: {name}", code="unknown_tool")
        structured = {"ok": True, "tool": _normalize_tool_definition(tool)}
        return _tool_result(json.dumps(structured, indent=2, sort_keys=True), structured)

    def _invoke_blender_tool(self, arguments):
        target_name = str(arguments.get("name") or "").strip()
        if target_name in WRAPPER_TOOL_NAMES:
            return _tool_error(f"Cannot invoke MCP wrapper tool through invoke_blender_tool: {target_name}", code="invalid_target")
        target_args = arguments.get("arguments") or {}
        if not isinstance(target_args, dict):
            return _tool_error("Target tool arguments must be a JSON object", code="invalid_arguments")
        target_tool = self._full_tool_definition(target_name)
        if target_tool is None:
            return _tool_error(f"Unknown Blender tool: {target_name}", code="unknown_tool")
        validation_errors = _validate_schema(target_args, target_tool.get("inputSchema") or {"type": "object"})
        if validation_errors:
            return _tool_error(
                "Target tool arguments failed schema validation",
                code="invalid_arguments",
                data={"target": target_name, "errors": validation_errors},
            )
        try:
            response = self.bridge.post("/tool", {"name": target_name, "arguments": target_args})
        except Exception as exc:
            return _tool_error(str(exc), code="bridge_unavailable")
        result = response.get("result", response)
        ok = bool(response.get("ok", True)) and bool(result.get("ok", True) if isinstance(result, dict) else True)
        if isinstance(result, dict):
            result.setdefault("invoked_tool", target_name)
            structured = result
        else:
            structured = {"ok": ok, "text": str(result), "invoked_tool": target_name}
        text = json.dumps(structured, indent=2, sort_keys=True, default=str)
        return _tool_result(text, structured, is_error=not ok)

    def _bridge_status(self):
        try:
            return self.bridge.get("/health")
        except Exception as exc:
            diagnostics = build_info.diagnostics_dict(bridge_url=self.bridge.base_url)
            return {"ok": False, "message": str(exc), **diagnostics}

    def resources_list(self, params=None):
        resources = [
            {
                "uri": "blender://bridge/status",
                "name": "bridge-status",
                "title": "Blender Bridge Connection Status",
                "description": "MCP server connection status for the Blender bridge",
                "mimeType": "application/json",
            }
        ]
        try:
            response = self.bridge.get("/resources")
            resources.extend(response.get("resources") or [])
        except Exception as exc:
            _stderr(f"resources/list bridge warning: {exc}")
        return _page_items(resources, params, "resources")

    def resources_read(self, params):
        uri = (params or {}).get("uri")
        if uri == "blender://bridge/status":
            status = self._bridge_status()
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(status, indent=2, sort_keys=True),
                    }
                ]
            }
        response = self.bridge.get("/resource", {"uri": uri})
        content = {
            "uri": uri,
            "mimeType": response.get("mimeType", "text/plain"),
        }
        if "blob" in response:
            content["blob"] = response.get("blob", "")
        else:
            content["text"] = response.get("text", "")
        return {
            "contents": [content]
        }

    def resource_templates_list(self, params=None):
        return _page_items(RESOURCE_TEMPLATES, params, "resourceTemplates")

    def prompts_list(self, params=None):
        prompts = [
            {
                "name": prompt["name"],
                "title": prompt.get("title", prompt["name"]),
                "description": prompt.get("description", ""),
                "arguments": prompt.get("arguments", []),
            }
            for prompt in PROMPTS.values()
        ]
        return _page_items(prompts, params, "prompts")

    def prompts_get(self, params):
        params = params or {}
        name = params.get("name")
        prompt = PROMPTS.get(name)
        if prompt is None:
            raise KeyError(f"Prompt not found: {name}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        required = [item["name"] for item in prompt.get("arguments", []) if item.get("required")]
        missing = [key for key in required if not str(arguments.get(key) or "").strip()]
        if missing:
            raise ValueError(f"Missing required prompt arguments: {', '.join(missing)}")
        values = {item["name"]: str(arguments.get(item["name"]) or "") for item in prompt.get("arguments", [])}
        return {
            "description": prompt.get("description", ""),
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": prompt["template"].format(**values),
                    },
                }
            ],
        }

    def handle_request(self, message):
        method = message.get("method")
        params = message.get("params") or {}
        if method == "initialize":
            return self.initialize(params)
        if method == "ping":
            return {}
        if method == "logging/setLevel":
            self._log_level = str(params.get("level") or "info")
            return {}
        if method == "tools/list":
            return self.tools_list(params)
        if method == "tools/call":
            return self.tools_call(params)
        if method == "resources/list":
            return self.resources_list(params)
        if method == "resources/read":
            return self.resources_read(params)
        if method == "resources/templates/list":
            return self.resource_templates_list(params)
        if method == "prompts/list":
            return self.prompts_list(params)
        if method == "prompts/get":
            return self.prompts_get(params)
        raise KeyError(f"Method not found: {method}")


def _response(request_id, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result if result is not None else {}
    return payload


def _error(code, message, data=None):
    payload = {"code": int(code), "message": str(message)}
    if data is not None:
        payload["data"] = data
    return payload


def serve(server, input_stream=None, output_stream=None):
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    for raw_line in input_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            output_stream.write(_json_dumps(_response(None, error=_error(-32700, f"Parse error: {exc}"))) + "\n")
            output_stream.flush()
            continue
        if isinstance(message, list):
            responses = [_handle_one(server, item) for item in message]
            responses = [item for item in responses if item is not None]
            if responses:
                output_stream.write(_json_dumps(responses) + "\n")
                output_stream.flush()
            continue
        response = _handle_one(server, message)
        if response is not None:
            output_stream.write(_json_dumps(response) + "\n")
            output_stream.flush()


def _handle_one(server, message):
    if not isinstance(message, dict):
        return _response(None, error=_error(-32600, "Invalid Request"))
    request_id = message.get("id")
    method = message.get("method")
    if method in {"notifications/initialized", "notifications/cancelled", "$/cancelRequest"}:
        return None
    if request_id is None:
        return None
    try:
        result = server.handle_request(message)
        return _response(request_id, result=result)
    except KeyError as exc:
        return _response(request_id, error=_error(-32601, str(exc)))
    except Exception as exc:
        return _response(request_id, error=_error(-32603, f"{type(exc).__name__}: {exc}"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="MCP server for Blender Agent Bridge")
    parser.add_argument("--bridge-url", default=os.environ.get("BLENDER_BRIDGE_URL", DEFAULT_BRIDGE_URL))
    parser.add_argument("--token", default=os.environ.get("BLENDER_BRIDGE_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("BLENDER_BRIDGE_TIMEOUT", "30")))
    args = parser.parse_args(argv)
    serve(BlenderMCPServer(BridgeClient(args.bridge_url, token=args.token, timeout=args.timeout)))


if __name__ == "__main__":
    main()
