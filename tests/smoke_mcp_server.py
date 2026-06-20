"""Smoke test for the stdio MCP server using a fake Blender bridge."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MCP_SERVER = os.path.join(ROOT, "addon", "claude_blender", "mcp_server.py")
sys.path.insert(0, os.path.join(ROOT, "addon", "claude_blender"))

import bridge_protocol  # noqa: E402
import build_info  # noqa: E402
import mcp_server  # noqa: E402


class FakeBridgeHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send_status(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send(self, payload):
        self._send_status(200, payload)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            diagnostics = build_info.diagnostics_dict()
            self._send(
                {
                    "ok": True,
                    "scene": "Fake Scene",
                    "bridge_version": bridge_protocol.BRIDGE_VERSION,
                    "addon_version": build_info.ADDON_VERSION,
                    "addon_source_hash": diagnostics["addon_source_hash"],
                    "addon_loaded_source_hash": diagnostics["addon_loaded_source_hash"],
                    "addon_runtime_source_stale": diagnostics["addon_runtime_source_stale"],
                    "addon_runtime_source_status": diagnostics["addon_runtime_source_status"],
                    "addon_runtime_source_message": diagnostics["addon_runtime_source_message"],
                    "expected_addon_source_hash": diagnostics["expected_addon_source_hash"],
                    "addon_source_hash_match": diagnostics["addon_source_hash_match"],
                    "addon_source_hash_status": diagnostics["addon_source_hash_status"],
                    "addon_source_hash_message": diagnostics["addon_source_hash_message"],
                    "mcp_server_version": build_info.MCP_SERVER_VERSION,
                    "mcp_config_version": build_info.MCP_CONFIG_VERSION,
                    "build_diagnostics": build_info.diagnostics_summary(),
                }
            )
        elif parsed.path == "/tools":
            self._send(
                {
                    "ok": True,
                    "tools": [
                        {
                            "name": "list_scene_objects",
                            "title": "List Scene Objects",
                            "description": "List objects",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"max_objects": {"type": "integer"}},
                                "additionalProperties": False,
                            },
                            "annotations": {"mutatesScene": False},
                        },
                        {
                            "name": "set_selected_location_delta",
                            "title": "Set Selected Location Delta",
                            "description": "Move selected objects",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "delta": {
                                        "type": "array",
                                        "items": {"type": "number"},
                                        "minItems": 3,
                                        "maxItems": 3,
                                    }
                                },
                                "required": ["delta"],
                                "additionalProperties": False,
                            },
                            "annotations": bridge_protocol.mcp_annotations_for_tool("set_selected_location_delta"),
                        },
                        {
                            "name": "draft_script",
                            "title": "Draft Script",
                            "description": "Stage script for approval",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "intent": {"type": "string"},
                                    "expected_changes": {"type": "string"},
                                    "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
                                    "code": {"type": "string"},
                                },
                                "required": ["intent", "expected_changes", "risk_level", "code"],
                                "additionalProperties": False,
                            },
                            "annotations": bridge_protocol.mcp_annotations_for_tool("draft_script"),
                        },
                        {
                            "name": "run_approved_script",
                            "title": "Run Approved Script",
                            "description": "Run a user-approved pending script with a Blender-issued token",
                            "inputSchema": bridge_protocol.normalized_tool_contract("run_approved_script")["input_schema"],
                            "annotations": bridge_protocol.mcp_annotations_for_tool("run_approved_script"),
                        }
                    ],
                }
            )
        elif parsed.path == "/resources":
            self._send(
                {
                    "ok": True,
                    "resources": [
                        {
                            "uri": "blender://scene/status",
                            "name": "scene-status",
                            "title": "Scene Status",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "blender://tools/catalog",
                            "name": "tool-catalog",
                            "title": "Compact Blender Tool Catalog",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "blender://audit/summary",
                            "name": "audit-summary",
                            "title": "Blender Agent Bridge Audit Summary",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "blender://captures/latest",
                            "name": "latest-capture",
                            "title": "Latest Viewport Capture",
                            "mimeType": "image/png",
                        },
                        {
                            "uri": "blender://captures/latest/metadata",
                            "name": "latest-capture-metadata",
                            "title": "Latest Viewport Capture Metadata",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "blender://playblasts/latest/metadata",
                            "name": "latest-playblast-metadata",
                            "title": "Latest Animation Playblast Metadata",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "blender://inspection-renders/latest/metadata",
                            "name": "latest-inspection-render-metadata",
                            "title": "Latest Object Inspection Render Metadata",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "blender://render-thumbnails/latest",
                            "name": "latest-render-thumbnail",
                            "title": "Latest Render Thumbnail",
                            "mimeType": "image/png",
                        },
                        {
                            "uri": "blender://render-thumbnails/latest/metadata",
                            "name": "latest-render-thumbnail-metadata",
                            "title": "Latest Render Thumbnail Metadata",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "blender://render-jobs/latest/metadata",
                            "name": "latest-render-job-metadata",
                            "title": "Latest Async Render Job Metadata",
                            "mimeType": "application/json",
                        },
                    ],
                }
            )
        elif parsed.path == "/resource":
            uri = urllib.parse.parse_qs(parsed.query).get("uri", [""])[0]
            if uri == "blender://tools/catalog":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://tools/catalog",
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "ok": True,
                                "count": 2,
                                "tools": [
                                    {
                                        "name": "list_scene_objects",
                                        "risk_level": "read",
                                        "permissions": ["scene:read"],
                                    },
                                    {
                                        "name": "draft_script",
                                        "risk_level": "approval",
                                        "permissions": ["script:stage"],
                                        "requires_approval": True,
                                    },
                                ],
                                "full_contracts_resource": "blender://tools/contracts",
                            }
                        ),
                    }
                )
            elif uri == "blender://audit/summary":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://audit/summary",
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "ok": True,
                                "event_count": 1,
                                "events_by_type": {"mcp_tool_call": 1},
                                "tool_calls_by_name": {"list_scene_objects": 1},
                                "error_count": 0,
                                "latest_events": [
                                    {
                                        "timestamp": "2026-06-20T00:00:00+00:00",
                                        "event": "mcp_tool_call",
                                        "tool_name": "list_scene_objects",
                                        "ok": True,
                                    }
                                ],
                                "latest_full_resource": "blender://audit/latest",
                            }
                        ),
                    }
                )
            elif uri == "blender://audit/latest":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://audit/latest",
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "ok": True,
                                "event_limit": 20,
                                "summary_resource": "blender://audit/summary",
                                "events": [
                                    {
                                        "timestamp": "2026-06-20T00:00:00+00:00",
                                        "event": "mcp_tool_call",
                                        "tool_name": "list_scene_objects",
                                        "ok": True,
                                    }
                                ],
                            }
                        ),
                    }
                )
            elif uri == "blender://captures/latest":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://captures/latest",
                        "mimeType": "image/png",
                        "blob": "iVBORw0KGgo=",
                    }
                )
            elif uri == "blender://captures/latest/metadata":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://captures/latest/metadata",
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "ok": True,
                                "available": True,
                                "capture_id": "test-capture",
                                "resource_uri": "blender://captures/latest",
                                "metadata_uri": "blender://captures/latest/metadata",
                                "exact_resource_uri": "blender://captures/test-capture",
                                "exact_metadata_uri": "blender://captures/test-capture/metadata",
                            }
                        ),
                    }
                )
            elif uri == "blender://captures/test-capture":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://captures/test-capture",
                        "mimeType": "image/png",
                        "blob": "iVBORw0KGgo=",
                    }
                )
            elif uri == "blender://captures/test-capture/metadata":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://captures/test-capture/metadata",
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "ok": True,
                                "available": True,
                                "capture_id": "test-capture",
                                "resource_uri": "blender://captures/test-capture",
                                "metadata_uri": "blender://captures/test-capture/metadata",
                            }
                        ),
                    }
                )
            elif uri == "blender://playblasts/latest/metadata":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://playblasts/latest/metadata",
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "ok": True,
                                "available": True,
                                "playblast_id": "test-playblast",
                                "metadata_uri": "blender://playblasts/test-playblast/metadata",
                                "latest_metadata_uri": "blender://playblasts/latest/metadata",
                                "frames": [
                                    {
                                        "frame": 1,
                                        "available": True,
                                        "resource_uri": "blender://playblasts/test-playblast/frames/1",
                                    }
                                ],
                            }
                        ),
                    }
                )
            elif uri == "blender://playblasts/test-playblast/metadata":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://playblasts/test-playblast/metadata",
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "ok": True,
                                "available": True,
                                "playblast_id": "test-playblast",
                                "metadata_uri": "blender://playblasts/test-playblast/metadata",
                            }
                        ),
                    }
                )
            elif uri == "blender://playblasts/test-playblast/frames/1":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://playblasts/test-playblast/frames/1",
                        "mimeType": "image/png",
                        "blob": "iVBORw0KGgo=",
                    }
                )
            elif uri == "blender://inspection-renders/latest/metadata":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://inspection-renders/latest/metadata",
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "ok": True,
                                "available": True,
                                "render_id": "test-render",
                                "metadata_uri": "blender://inspection-renders/test-render/metadata",
                                "latest_metadata_uri": "blender://inspection-renders/latest/metadata",
                                "images": [
                                    {
                                        "image_id": "cube-front_below",
                                        "available": True,
                                        "resource_uri": (
                                            "blender://inspection-renders/test-render/images/cube-front_below"
                                        ),
                                    }
                                ],
                            }
                        ),
                    }
                )
            elif uri == "blender://inspection-renders/test-render/metadata":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://inspection-renders/test-render/metadata",
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "ok": True,
                                "available": True,
                                "render_id": "test-render",
                                "metadata_uri": "blender://inspection-renders/test-render/metadata",
                            }
                        ),
                    }
                )
            elif uri == "blender://inspection-renders/test-render/images/cube-front_below":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://inspection-renders/test-render/images/cube-front_below",
                        "mimeType": "image/png",
                        "blob": "iVBORw0KGgo=",
                    }
                )
            elif uri == "blender://render-thumbnails/latest":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://render-thumbnails/latest",
                        "mimeType": "image/png",
                        "blob": "iVBORw0KGgo=",
                    }
                )
            elif uri == "blender://render-thumbnails/latest/metadata":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://render-thumbnails/latest/metadata",
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "ok": True,
                                "available": True,
                                "thumbnail_id": "test-thumbnail",
                                "resource_uri": "blender://render-thumbnails/test-thumbnail",
                                "metadata_uri": "blender://render-thumbnails/test-thumbnail/metadata",
                                "latest_resource_uri": "blender://render-thumbnails/latest",
                                "latest_metadata_uri": "blender://render-thumbnails/latest/metadata",
                            }
                        ),
                    }
                )
            elif uri == "blender://render-thumbnails/test-thumbnail":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://render-thumbnails/test-thumbnail",
                        "mimeType": "image/png",
                        "blob": "iVBORw0KGgo=",
                    }
                )
            elif uri == "blender://render-thumbnails/test-thumbnail/metadata":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://render-thumbnails/test-thumbnail/metadata",
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "ok": True,
                                "available": True,
                                "thumbnail_id": "test-thumbnail",
                                "resource_uri": "blender://render-thumbnails/test-thumbnail",
                                "metadata_uri": "blender://render-thumbnails/test-thumbnail/metadata",
                            }
                        ),
                    }
                )
            elif uri == "blender://render-jobs/latest/metadata":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://render-jobs/latest/metadata",
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "ok": True,
                                "available": True,
                                "job_id": "test-render-job",
                                "status": "completed",
                                "metadata_uri": "blender://render-jobs/test-render-job/metadata",
                                "latest_metadata_uri": "blender://render-jobs/latest/metadata",
                                "log_resource_uri": "blender://render-jobs/test-render-job/log",
                                "newest_frame_resource_uri": "blender://render-jobs/test-render-job/frames/1",
                                "frame_count": 1,
                                "total_frames": 1,
                            }
                        ),
                    }
                )
            elif uri == "blender://render-jobs/test-render-job/metadata":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://render-jobs/test-render-job/metadata",
                        "mimeType": "application/json",
                        "text": json.dumps(
                            {
                                "ok": True,
                                "available": True,
                                "job_id": "test-render-job",
                                "status": "completed",
                                "metadata_uri": "blender://render-jobs/test-render-job/metadata",
                            }
                        ),
                    }
                )
            elif uri == "blender://render-jobs/test-render-job/frames/1":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://render-jobs/test-render-job/frames/1",
                        "mimeType": "image/png",
                        "blob": "iVBORw0KGgo=",
                    }
                )
            elif uri == "blender://render-jobs/test-render-job/log":
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://render-jobs/test-render-job/log",
                        "mimeType": "text/plain",
                        "text": "render log",
                    }
                )
            else:
                self._send(
                    {
                        "ok": True,
                        "uri": "blender://scene/status",
                        "mimeType": "application/json",
                        "text": '{"ok": true, "scene": "Fake Scene"}',
                    }
                )
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if self.path == "/tool":
            arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
            if payload.get("name") == "start_render_job" and arguments.get("job_name") == "force_timeout_504":
                self._send_status(
                    504,
                    {
                        "ok": False,
                        "result": {
                            "ok": False,
                            "code": "bridge_main_thread_timeout",
                            "message": "Synthetic bridge timeout",
                            "tool": "start_render_job",
                            "timeout_seconds": 45,
                            "request_may_still_be_running": True,
                            "recoverable": True,
                            "poll_after_seconds": 5,
                            "status_tool": "blender_bridge_status",
                            "resource_tool": "get_visual_evidence_resources",
                        },
                    },
                )
                return
            if payload.get("name") == "save_blend_file" and not arguments:
                self._send(
                    {
                        "ok": True,
                        "result": {
                            "ok": False,
                            "code": "user_path_required",
                            "message": (
                                "This operation needs a human-confirmed path. Ask the user for the .blend path "
                                "or project folder, then retry with user_confirmed_path=true."
                            ),
                            "human_in_loop_required": True,
                            "requires_user_confirmed_path": True,
                            "before": {
                                "filepath": "",
                                "absolute_path": "",
                                "is_saved": False,
                                "is_dirty": False,
                            },
                        },
                    }
                )
                return
            self._send(
                {
                    "ok": True,
                    "result": {
                        "ok": True,
                        "tool": payload.get("name"),
                        "objects": [{"name": "Cube", "type": "MESH"}],
                    },
                }
            )
        else:
            self.send_error(404)


def _send(proc, payload):
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    assert line, "MCP server closed stdout"
    return json.loads(line)


def _assert_compact_tools_visible(proc):
    listed = _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {tool["name"] for tool in listed["result"]["tools"]}
    expected_names = set(mcp_server.WRAPPER_TOOL_NAMES) | set(mcp_server.COMPACT_DIRECT_TOOL_NAMES)
    assert names == expected_names, listed
    assert "draft_script" not in names, listed
    assert "run_approved_script" not in names, listed
    status_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "blender_bridge_status")
    status_properties = status_tool["outputSchema"]["properties"]
    assert "external_script_trust_seconds_remaining" in status_properties, status_tool
    assert "external_script_trust_session" in status_properties, status_tool
    assert "mcp_client_refresh_hint" in status_properties, status_tool
    assert "addon_version" in status_properties, status_tool
    assert "mcp_server_version" in status_properties, status_tool
    assert "mcp_config_version" in status_properties, status_tool
    assert "mcp_external_asset_auth" in status_properties, status_tool
    assert "build_diagnostics" in status_properties, status_tool
    assert "addon_source_hash" in status_properties, status_tool
    assert "addon_loaded_source_hash" in status_properties, status_tool
    assert "addon_runtime_source_stale" in status_properties, status_tool
    assert "addon_runtime_source_status" in status_properties, status_tool
    assert "addon_runtime_source_message" in status_properties, status_tool
    assert "mcp_server_source_hash" in status_properties, status_tool
    assert "addon_mcp_source_hash_match" in status_properties, status_tool
    assert "source_hash_status" in status_properties, status_tool
    assert "bridge_busy" in status_properties, status_tool
    assert "active_operation" in status_properties, status_tool
    assert "poll_after_seconds" in status_properties, status_tool
    scene_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "list_scene_objects")
    assert scene_tool["outputSchema"]["type"] == "object", scene_tool
    catalog_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "blender_tool_catalog")
    assert catalog_tool["annotations"]["riskLevel"] == "dynamic", catalog_tool
    assert "invoke" in catalog_tool["inputSchema"]["properties"]["action"]["enum"], catalog_tool
    search_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "search_blender_tools")
    assert search_tool["annotations"]["readOnlyHint"] is True, search_tool
    task_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "run_animation_task")
    assert set(task_tool["inputSchema"]["properties"]) == {"prompt"}, task_tool
    assert task_tool["inputSchema"]["required"] == ["prompt"], task_tool
    render_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "start_render_job")
    assert "output_kind" in render_tool["inputSchema"]["properties"], render_tool
    assert "quality" in render_tool["inputSchema"]["properties"], render_tool
    assert render_tool["annotations"]["riskLevel"] == "read", render_tool
    assert render_tool["annotations"]["returnsBackgroundJob"] is True, render_tool
    assert render_tool["annotations"]["timeoutSeconds"] == 30, render_tool
    assert render_tool["annotations"]["durationHint"], render_tool
    assert render_tool["annotations"]["timeoutRecovery"]["status_tool"] == "blender_bridge_status", render_tool
    task_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "run_animation_task")
    assert task_tool["annotations"]["longRunningHint"] is True, task_tool
    assert task_tool["annotations"]["timeoutRecovery"]["resource_tool"] == "get_visual_evidence_resources", task_tool
    asset_download_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "start_external_asset_download")
    assert "Default client path" in asset_download_tool["description"], asset_download_tool
    assert asset_download_tool["annotations"]["returnsBackgroundJob"] is True, asset_download_tool
    assert asset_download_tool["annotations"]["timeoutRecovery"]["resource_tool"] == "get_external_asset_job_status", asset_download_tool
    asset_import_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "start_external_asset_import_job")
    assert "Default client path" in asset_import_tool["description"], asset_import_tool
    assert asset_import_tool["annotations"]["returnsBackgroundJob"] is True, asset_import_tool
    assert asset_import_tool["annotations"]["timeoutRecovery"]["resource_tool"] == "get_external_asset_import_job_status", asset_import_tool
    assert "import_poly_haven_asset" not in names, listed
    assert "import_sketchfab_model" not in names, listed
    bake_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "stage_persistent_simulation_bake")
    assert bake_tool["annotations"]["requiresApproval"] is True, bake_tool
    assert bake_tool["annotations"]["requiresExplicitOneTimeApproval"] is True, bake_tool
    assert bake_tool["annotations"]["trustWindowAutoRunAllowed"] is False, bake_tool
    assert "one-time" in bake_tool["annotations"]["approvalPolicy"], bake_tool
    assert "get_blend_file_diagnostics" in bake_tool["annotations"]["recoveryHint"], bake_tool
    assert "requires_explicit_one_time_approval" in bake_tool["outputSchema"]["properties"], bake_tool
    assemble_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "assemble_render_job_video")
    assert assemble_tool["inputSchema"]["required"] == ["job_id"], assemble_tool
    validate_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "validate_render_job_output")
    assert validate_tool["annotations"]["readOnlyHint"] is True, validate_tool
    invoke_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "invoke_blender_tool")
    assert invoke_tool["annotations"]["readOnlyHint"] is False, invoke_tool
    assert "run_approved_script" in bridge_protocol.list_tool_contracts()["tools"]
    return listed


def _assert_full_tools_visible(proc):
    listed = _send(proc, {"jsonrpc": "2.0", "id": 91, "method": "tools/list"})
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert {
        "blender_bridge_status",
        "blender_tool_catalog",
        "list_scene_objects",
        "save_blend_file",
        "open_blend_file",
        "create_new_blender_project",
        "autosave_current_blend_file",
        "draft_script",
        "run_approved_script",
    }.issubset(names), listed
    draft_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "draft_script")
    assert draft_tool["annotations"]["mutatesScene"] is True, draft_tool
    assert draft_tool["annotations"]["hasSideEffects"] is True, draft_tool
    assert draft_tool["annotations"]["readOnlyHint"] is False, draft_tool
    run_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "run_approved_script")
    assert run_tool["annotations"]["requiresApproval"] is True, run_tool
    assert run_tool["annotations"]["hasSideEffects"] is True, run_tool
    assert run_tool["annotations"]["readOnlyHint"] is False, run_tool
    open_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "open_blend_file")
    assert open_tool["annotations"]["destructiveHint"] is True, open_tool
    assert open_tool["annotations"]["humanInLoopRequired"] is True, open_tool
    assert open_tool["annotations"]["requiresUserPath"] is True, open_tool
    assert "user_confirmed_path" in open_tool["inputSchema"]["required"], open_tool
    autosave_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "autosave_current_blend_file")
    assert autosave_tool["annotations"]["requiresUserPath"] is False, autosave_tool
    assert autosave_tool["annotations"]["pathPolicy"], autosave_tool
    assert open_tool["annotations"]["timeoutRecovery"]["status_tool"] == "blender_bridge_status", open_tool
    return listed


def _assert_legacy_status_hashes_are_unknown():
    class LegacyBridge:
        base_url = "http://127.0.0.1:8765"

    status = mcp_server.BlenderMCPServer(LegacyBridge())._augment_bridge_status({"ok": True})
    assert status["mcp_server_source_hash"] == build_info.source_tree_hash(), status
    assert status["addon_runtime_source_status"] == "unknown", status
    assert status["addon_runtime_source_stale"] is False, status
    assert status["addon_mcp_source_hash_match"] is None, status
    assert status["source_hash_status"] == "unknown", status


def _start_mcp(bridge_url, audit_path, *, timeout="30", extra_env=None):
    env = dict(os.environ)
    env["CLAUDE_BLENDER_AUDIT_LOG"] = audit_path
    if extra_env:
        env.update(extra_env)
    return subprocess.Popen(
        ["python", MCP_SERVER, "--bridge-url", bridge_url, "--timeout", str(timeout)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )


def _initialize(proc):
    initialized = _send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "1999-01-01",
                "capabilities": {},
                "clientInfo": {"name": "smoke", "version": "1"},
            },
        },
    )
    assert initialized["result"]["protocolVersion"] == "2025-06-18", initialized
    assert initialized["result"]["capabilities"]["tools"] == {"listChanged": False}, initialized
    assert initialized["result"]["capabilities"]["prompts"] == {"listChanged": False}, initialized
    assert "start_external_asset_download" in initialized["result"]["instructions"], initialized
    assert "start_external_asset_import_job" in initialized["result"]["instructions"], initialized
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()
    return initialized


def _assert_animation_search_routes_first(response, *, query):
    tools = response["result"]["structuredContent"]["tools"]
    names = [tool["name"] for tool in tools]
    assert names[:3] == ["run_animation_task", "plan_animation_workflow", "run_animation_workflow"], (query, names)
    for generic_name in ("set_selected_location_delta", "set_selected_transform", "select_objects"):
        if generic_name in names:
            assert names.index(generic_name) > names.index("run_animation_workflow"), (query, names)
    if "draft_script" in names:
        assert names.index("draft_script") > names.index("run_animation_workflow"), (query, names)


def _assert_external_asset_search_routes_first(response, *, query):
    tools = response["result"]["structuredContent"]["tools"]
    names = [tool["name"] for tool in tools]
    assert names[0] == "start_external_asset_download", (query, names)
    assert "start_external_asset_import_job" in names[:4], (query, names)
    assert "get_external_asset_job_status" in names[:5], (query, names)
    assert "get_external_asset_import_job_status" in names[:6], (query, names)
    for direct_name in (
        "download_poly_haven_asset",
        "import_poly_haven_asset",
        "download_sketchfab_model",
        "import_sketchfab_model",
        "import_external_asset_job_result",
    ):
        if direct_name in names:
            assert names.index(direct_name) > names.index("start_external_asset_import_job"), (query, names)


def _assert_material_texture_search_avoids_asset_route(response, *, query):
    tools = response["result"]["structuredContent"]["tools"]
    names = [tool["name"] for tool in tools]
    categories = [tool["category"] for tool in tools]
    assert names[0] != "start_external_asset_download", (query, names)
    assert all(category != "external_assets" for category in categories[:6]), (query, names, categories)


def main():
    _assert_legacy_status_hashes_are_unknown()
    assert not mcp_server._contains_any_phrase(
        "Create an architectural arch from cubes",
        mcp_server.ANIMATION_ROUTE_TERMS,
    )
    assert mcp_server._contains_any_phrase(
        "Make the selected cube bounce twice",
        mcp_server.ANIMATION_ROUTE_TERMS,
    )
    assert mcp_server._is_external_asset_route_query("import texture from Poly Haven")
    assert mcp_server._is_external_asset_route_query("download model from asset library")
    assert not mcp_server._is_external_asset_route_query("create a wood texture material on the selected cube")
    assert not mcp_server._is_external_asset_route_query("assign a procedural texture material to the selected cube")

    offline_audit_fd, offline_audit_path = tempfile.mkstemp(
        prefix="claude-blender-mcp-offline-audit-",
        suffix=".jsonl",
    )
    os.close(offline_audit_fd)
    os.remove(offline_audit_path)
    offline_proc = _start_mcp("http://127.0.0.1:1", offline_audit_path, timeout="1")
    try:
        _initialize(offline_proc)
        offline_listed = _assert_compact_tools_visible(offline_proc)
        offline_names = {tool["name"] for tool in offline_listed["result"]["tools"]}
        assert "invoke_blender_tool" in offline_names, offline_listed
        offline_status = _send(
            offline_proc,
            {
                "jsonrpc": "2.0",
                "id": 88,
                "method": "tools/call",
                "params": {"name": "blender_bridge_status", "arguments": {}},
            },
        )
        offline_status_content = offline_status["result"]["structuredContent"]
        assert offline_status_content["ok"] is False, offline_status
        assert offline_status_content["bridge_url"] == "http://127.0.0.1:1", offline_status
        assert offline_status_content["addon_version"] == build_info.ADDON_VERSION, offline_status
        assert offline_status_content["mcp_config_version"] == build_info.MCP_CONFIG_VERSION, offline_status
        assert offline_status_content["addon_source_hash"] == build_info.source_tree_hash(), offline_status
        assert offline_status_content["mcp_server_source_hash"] == build_info.source_tree_hash(), offline_status
        assert offline_status_content["addon_mcp_source_hash_match"] is True, offline_status
        offline_search = _send(
            offline_proc,
            {
                "jsonrpc": "2.0",
                "id": 89,
                "method": "tools/call",
                "params": {"name": "search_blender_tools", "arguments": {"query": "approved script", "limit": 5}},
            },
        )
        offline_found = {tool["name"] for tool in offline_search["result"]["structuredContent"]["tools"]}
        assert {"draft_script", "run_approved_script"}.issubset(offline_found), offline_search
        offline_simulation_search = _send(
            offline_proc,
            {
                "jsonrpc": "2.0",
                "id": 93,
                "method": "tools/call",
                "params": {"name": "search_blender_tools", "arguments": {"query": "inspect simulation cache bake", "limit": 8}},
            },
        )
        offline_simulation_found = {tool["name"] for tool in offline_simulation_search["result"]["structuredContent"]["tools"]}
        assert "inspect_simulation_bake" in offline_simulation_found, offline_simulation_search
        assert "get_simulation_details" in offline_simulation_found, offline_simulation_search
        assert "stage_persistent_simulation_bake" in offline_simulation_found, offline_simulation_search
        offline_catalog_search = _send(
            offline_proc,
            {
                "jsonrpc": "2.0",
                "id": 94,
                "method": "tools/call",
                "params": {
                    "name": "blender_tool_catalog",
                    "arguments": {"action": "search", "query": "approved script", "limit": 5},
                },
            },
        )
        offline_catalog_found = {
            tool["name"] for tool in offline_catalog_search["result"]["structuredContent"]["tools"]
        }
        assert {"draft_script", "run_approved_script"}.issubset(offline_catalog_found), offline_catalog_search
        for query in (
            "Make the selected cube bounce twice and get smaller each bounce.",
            "Block a jump animation with anticipation, contact, apex, settle.",
            "Review this animation for spacing and contact sliding.",
        ):
            offline_animation_search = _send(
                offline_proc,
                {
                    "jsonrpc": "2.0",
                    "id": 96,
                    "method": "tools/call",
                    "params": {
                        "name": "search_blender_tools",
                        "arguments": {"query": query, "limit": 8},
                    },
                },
            )
            _assert_animation_search_routes_first(offline_animation_search, query=query)
        for query in (
            "Search Poly Haven for a sunset HDRI and import it into the world.",
            "Import a downloadable Sketchfab Falcon 9 model if auth is present.",
            "Cache an external asset model and bring it into the Blender scene.",
        ):
            offline_asset_search = _send(
                offline_proc,
                {
                    "jsonrpc": "2.0",
                    "id": 97,
                    "method": "tools/call",
                    "params": {
                        "name": "search_blender_tools",
                        "arguments": {"query": query, "limit": 10},
                    },
                },
            )
            _assert_external_asset_search_routes_first(offline_asset_search, query=query)
        for query in (
            "Create a wood texture material on the selected cube.",
            "Assign a procedural texture material to the selected cube.",
        ):
            offline_material_search = _send(
                offline_proc,
                {
                    "jsonrpc": "2.0",
                    "id": 98,
                    "method": "tools/call",
                    "params": {
                        "name": "search_blender_tools",
                        "arguments": {"query": query, "limit": 10},
                    },
                },
            )
            _assert_material_texture_search_avoids_asset_route(offline_material_search, query=query)
        offline_catalog_schema = _send(
            offline_proc,
            {
                "jsonrpc": "2.0",
                "id": 95,
                "method": "tools/call",
                "params": {
                    "name": "blender_tool_catalog",
                    "arguments": {"action": "schema", "name": "run_approved_script"},
                },
            },
        )
        assert offline_catalog_schema["result"]["structuredContent"]["tool"]["name"] == "run_approved_script"
        unavailable = _send(
            offline_proc,
            {
                "jsonrpc": "2.0",
                "id": 90,
                "method": "tools/call",
                "params": {"name": "invoke_blender_tool", "arguments": {"name": "list_scene_objects", "arguments": {}}},
            },
        )
        assert unavailable["result"]["isError"] is True, unavailable
        assert unavailable["result"]["structuredContent"]["code"] == "bridge_unavailable", unavailable
    finally:
        offline_proc.kill()
        try:
            offline_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.remove(offline_audit_path)
        except FileNotFoundError:
            pass

    fake_bridge = ThreadingHTTPServer(("127.0.0.1", 0), FakeBridgeHandler)
    thread = threading.Thread(target=fake_bridge.serve_forever, daemon=True)
    thread.start()
    bridge_url = f"http://127.0.0.1:{fake_bridge.server_address[1]}"
    audit_fd, audit_path = tempfile.mkstemp(prefix="claude-blender-mcp-audit-", suffix=".jsonl")
    os.close(audit_fd)
    os.remove(audit_path)
    proc = _start_mcp(bridge_url, audit_path)
    try:
        _initialize(proc)

        paged_tools = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/list",
                "params": {"limit": 1},
            },
        )
        assert len(paged_tools["result"]["tools"]) == 1, paged_tools
        assert paged_tools["result"]["nextCursor"] == "1", paged_tools

        _assert_compact_tools_visible(proc)
        status_call = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 28,
                "method": "tools/call",
                "params": {"name": "blender_bridge_status", "arguments": {}},
            },
        )
        status_content = status_call["result"]["structuredContent"]
        assert status_content["addon_version"] == build_info.ADDON_VERSION, status_call
        assert status_content["mcp_server_version"] == build_info.MCP_SERVER_VERSION, status_call
        assert status_content["mcp_config_version"] == build_info.MCP_CONFIG_VERSION, status_call
        assert build_info.ADDON_NAME in status_content["build_diagnostics"], status_call
        assert status_content["addon_source_hash"] == build_info.source_tree_hash(), status_call
        assert status_content["addon_loaded_source_hash"] == build_info.LOADED_SOURCE_HASH, status_call
        assert status_content["addon_runtime_source_stale"] is False, status_call
        assert status_content["addon_runtime_source_status"] == "current", status_call
        assert status_content["mcp_server_source_hash"] == build_info.source_tree_hash(), status_call
        assert status_content["addon_mcp_source_hash_match"] is True, status_call
        assert status_content["source_hash_status"] == "match", status_call
        timeout_call = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 29,
                "method": "tools/call",
                "params": {
                    "name": "start_render_job",
                    "arguments": {
                        "frame_start": 1,
                        "frame_end": 1,
                        "job_name": "force_timeout_504",
                    },
                },
            },
        )
        timeout_content = timeout_call["result"]["structuredContent"]
        assert timeout_call["result"]["isError"] is True, timeout_call
        assert timeout_content["code"] == "bridge_timeout", timeout_call
        assert timeout_content["data"]["recoverable"] is True, timeout_call
        assert timeout_content["data"]["request_may_still_be_running"] is True, timeout_call
        assert timeout_content["data"]["status_tool"] == "blender_bridge_status", timeout_call
        assert timeout_content["data"]["resource_tool"] == "get_visual_evidence_resources", timeout_call
        assert timeout_content["data"]["poll_after_seconds"] == 5, timeout_call

        lifecycle_search = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 30,
                "method": "tools/call",
                "params": {
                    "name": "search_blender_tools",
                    "arguments": {"query": "save blend file", "category": "project_files", "limit": 5},
                },
            },
        )
        lifecycle_tools = lifecycle_search["result"]["structuredContent"]["tools"]
        lifecycle_by_name = {tool["name"]: tool for tool in lifecycle_tools}
        assert "save_blend_file" in lifecycle_by_name, lifecycle_search
        save_summary = lifecycle_by_name["save_blend_file"]
        assert save_summary["human_in_loop_required"] is True, save_summary
        assert save_summary["requires_user_path"] is True, save_summary
        assert "user_confirmed_path=true" in save_summary["path_policy"], save_summary
        assert save_summary["timeout_recovery"]["status_tool"] == "blender_bridge_status", save_summary
        assert save_summary["duration_hint"], save_summary

        save_schema = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {"name": "get_blender_tool_schema", "arguments": {"name": "save_blend_file"}},
            },
        )
        save_tool_schema = save_schema["result"]["structuredContent"]["tool"]
        assert save_tool_schema["annotations"]["humanInLoopRequired"] is True, save_schema
        assert save_tool_schema["annotations"]["requiresUserPath"] is True, save_schema
        assert "user_confirmed_path" in save_tool_schema["inputSchema"]["properties"], save_schema
        save_schema_warning_codes = {
            warning["code"] for warning in save_tool_schema["guardrail_warnings"]
        }
        assert "user_confirmed_path_required" in save_schema_warning_codes, save_schema
        assert "long_running_synchronous_call" in save_schema_warning_codes, save_schema

        save_without_path = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 32,
                "method": "tools/call",
                "params": {
                    "name": "invoke_blender_tool",
                    "arguments": {"name": "save_blend_file", "arguments": {}},
                },
            },
        )
        save_without_path_content = save_without_path["result"]["structuredContent"]
        assert save_without_path["result"]["isError"] is True, save_without_path
        assert save_without_path_content["code"] == "user_path_required", save_without_path
        assert save_without_path_content["human_in_loop_required"] is True, save_without_path
        assert save_without_path_content["requires_user_confirmed_path"] is True, save_without_path
        assert "Ask the user" in save_without_path_content["message"], save_without_path
        save_without_path_warning_codes = {
            warning["code"] for warning in save_without_path_content["guardrail_warnings"]
        }
        assert "user_confirmed_path_required" in save_without_path_warning_codes, save_without_path

        full_audit_fd, full_audit_path = tempfile.mkstemp(
            prefix="claude-blender-mcp-full-audit-",
            suffix=".jsonl",
        )
        os.close(full_audit_fd)
        os.remove(full_audit_path)
        full_proc = _start_mcp(
            bridge_url,
            full_audit_path,
            extra_env={"BLENDER_MCP_FULL_TOOL_LIST": "1"},
        )
        try:
            _initialize(full_proc)
            _assert_full_tools_visible(full_proc)
            full_empty_approval = _send(
                full_proc,
                {
                    "jsonrpc": "2.0",
                    "id": 92,
                    "method": "tools/call",
                    "params": {"name": "run_approved_script", "arguments": {"approval_token": ""}},
                },
            )
            assert full_empty_approval["result"]["isError"] is False, full_empty_approval
            assert full_empty_approval["result"]["structuredContent"]["tool"] == "run_approved_script", full_empty_approval
            full_approval_warning_codes = {
                warning["code"]
                for warning in full_empty_approval["result"]["structuredContent"]["guardrail_warnings"]
            }
            assert "approval_required" in full_approval_warning_codes, full_empty_approval
        finally:
            full_proc.kill()
            full_proc.wait(timeout=5)
            try:
                os.remove(full_audit_path)
            except FileNotFoundError:
                pass

        searched = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 21,
                "method": "tools/call",
                "params": {"name": "search_blender_tools", "arguments": {"query": "approved script", "limit": 5}},
            },
        )
        searched_names = {tool["name"] for tool in searched["result"]["structuredContent"]["tools"]}
        assert {"draft_script", "run_approved_script"}.issubset(searched_names), searched
        searched_tools = searched["result"]["structuredContent"]["tools"]
        run_script_summary = next(tool for tool in searched_tools if tool["name"] == "run_approved_script")
        assert run_script_summary["guardrail_warnings"][0]["code"] == "approval_required", searched
        assert searched["result"]["structuredContent"]["include_schemas"] is False, searched
        assert searched["result"]["structuredContent"]["schema_lookup_tool"] == "get_blender_tool_schema", searched
        assert "input_schema" not in searched_tools[0], searched
        assert "output_schema" not in searched_tools[0], searched
        searched_with_schemas = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 211,
                "method": "tools/call",
                "params": {
                    "name": "search_blender_tools",
                    "arguments": {"query": "approved script", "limit": 5, "include_schemas": True},
                },
            },
        )
        searched_schema_tools = searched_with_schemas["result"]["structuredContent"]["tools"]
        assert searched_with_schemas["result"]["structuredContent"]["include_schemas"] is True, searched_with_schemas
        assert "input_schema" in searched_schema_tools[0], searched_with_schemas
        assert "output_schema" in searched_schema_tools[0], searched_with_schemas

        destructive_search = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 212,
                "method": "tools/call",
                "params": {
                    "name": "search_blender_tools",
                    "arguments": {"query": "open_blend_file", "limit": 3},
                },
            },
        )
        open_summary = next(
            tool
            for tool in destructive_search["result"]["structuredContent"]["tools"]
            if tool["name"] == "open_blend_file"
        )
        open_summary_warning_codes = {
            warning["code"] for warning in open_summary["guardrail_warnings"]
        }
        assert "destructive_scene_operation" in open_summary_warning_codes, destructive_search
        assert "user_confirmed_path_required" in open_summary_warning_codes, destructive_search

        for query in (
            "Make the selected cube bounce twice and get smaller each bounce.",
            "Block a jump animation with anticipation, contact, apex, settle.",
            "Review this animation for spacing and contact sliding.",
        ):
            animation_search = _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 97,
                    "method": "tools/call",
                    "params": {
                        "name": "search_blender_tools",
                        "arguments": {"query": query, "limit": 8},
                    },
                },
            )
            _assert_animation_search_routes_first(animation_search, query=query)
        for query in (
            "Search Poly Haven for a sunset HDRI and import it into the world.",
            "Import a downloadable Sketchfab Falcon 9 model if auth is present.",
            "Cache an external asset model and bring it into the Blender scene.",
        ):
            asset_search = _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 98,
                    "method": "tools/call",
                    "params": {
                        "name": "search_blender_tools",
                        "arguments": {"query": query, "limit": 10},
                    },
                },
            )
            _assert_external_asset_search_routes_first(asset_search, query=query)
        for query in (
            "Create a wood texture material on the selected cube.",
            "Assign a procedural texture material to the selected cube.",
        ):
            material_search = _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 99,
                    "method": "tools/call",
                    "params": {
                        "name": "search_blender_tools",
                        "arguments": {"query": query, "limit": 10},
                    },
                },
            )
            _assert_material_texture_search_avoids_asset_route(material_search, query=query)

        catalog_search = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 24,
                "method": "tools/call",
                "params": {
                    "name": "blender_tool_catalog",
                    "arguments": {
                        "action": "search",
                        "query": "move selected",
                        "category": "transform",
                        "permission": "scene:mutate",
                        "limit": 5,
                    },
                },
            },
        )
        catalog_tools = catalog_search["result"]["structuredContent"]["tools"]
        catalog_names = {tool["name"] for tool in catalog_tools}
        assert "set_selected_location_delta" in catalog_names, catalog_search
        assert all(tool["category"] == "transform" for tool in catalog_tools), catalog_search
        assert "input_schema" not in catalog_tools[0], catalog_search

        catalog_categories = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 25,
                "method": "tools/call",
                "params": {
                    "name": "blender_tool_catalog",
                    "arguments": {"action": "categories"},
                },
            },
        )
        category_names = {
            item["name"] for item in catalog_categories["result"]["structuredContent"]["facets"]["categories"]
        }
        assert {"inspect", "script", "simulation", "transform"}.issubset(category_names), catalog_categories

        bake_catalog_schema = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 27,
                "method": "tools/call",
                "params": {
                    "name": "blender_tool_catalog",
                    "arguments": {"action": "schema", "name": "stage_persistent_simulation_bake"},
                },
            },
        )
        bake_catalog_tool = bake_catalog_schema["result"]["structuredContent"]["tool"]
        assert bake_catalog_tool["annotations"]["requiresExplicitOneTimeApproval"] is True, bake_catalog_schema
        assert bake_catalog_tool["annotations"]["trustWindowAutoRunAllowed"] is False, bake_catalog_schema
        assert "requires_explicit_one_time_approval" in bake_catalog_tool["outputSchema"]["properties"], bake_catalog_schema
        bake_warning_codes = {
            warning["code"] for warning in bake_catalog_tool["guardrail_warnings"]
        }
        assert "explicit_one_time_approval_required" in bake_warning_codes, bake_catalog_schema

        simulation_catalog_search = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 28,
                "method": "tools/call",
                "params": {
                    "name": "blender_tool_catalog",
                    "arguments": {"action": "search", "query": "persistent simulation bake", "limit": 5},
                },
            },
        )
        simulation_catalog_tools = simulation_catalog_search["result"]["structuredContent"]["tools"]
        bake_summary = next(tool for tool in simulation_catalog_tools if tool["name"] == "stage_persistent_simulation_bake")
        assert bake_summary["requires_explicit_one_time_approval"] is True, simulation_catalog_search
        assert bake_summary["trust_window_auto_run_allowed"] is False, simulation_catalog_search

        schema = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 22,
                "method": "tools/call",
                "params": {"name": "get_blender_tool_schema", "arguments": {"name": "run_approved_script"}},
            },
        )
        run_schema = schema["result"]["structuredContent"]["tool"]["inputSchema"]
        assert "approval_token" not in run_schema.get("required", []), schema
        assert "minLength" not in run_schema["properties"]["approval_token"], schema

        catalog_schema = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 26,
                "method": "tools/call",
                "params": {
                    "name": "blender_tool_catalog",
                    "arguments": {"action": "schema", "name": "run_approved_script"},
                },
            },
        )
        assert catalog_schema["result"]["structuredContent"]["tool"]["name"] == "run_approved_script", catalog_schema

        called = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_scene_objects", "arguments": {}},
            },
        )
        assert called["result"]["isError"] is False, called
        assert called["result"]["structuredContent"]["objects"][0]["name"] == "Cube", called

        invoked = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 23,
                "method": "tools/call",
                "params": {"name": "invoke_blender_tool", "arguments": {"name": "list_scene_objects", "arguments": {}}},
            },
        )
        assert invoked["result"]["isError"] is False, invoked
        assert invoked["result"]["structuredContent"]["invoked_tool"] == "list_scene_objects", invoked

        invoked_direct_asset = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 231,
                "method": "tools/call",
                "params": {
                    "name": "invoke_blender_tool",
                    "arguments": {"name": "import_poly_haven_asset", "arguments": {"asset_id": "studio_hdri"}},
                },
            },
        )
        direct_asset_warnings = invoked_direct_asset["result"]["structuredContent"]["guardrail_warnings"]
        assert invoked_direct_asset["result"]["isError"] is False, invoked_direct_asset
        assert direct_asset_warnings[0]["code"] == "synchronous_external_asset_fallback", invoked_direct_asset
        assert "start_external_asset_download" in direct_asset_warnings[0]["preferred_workflow"], invoked_direct_asset

        invoked_cache_cleanup = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 232,
                "method": "tools/call",
                "params": {
                    "name": "invoke_blender_tool",
                    "arguments": {"name": "prune_external_asset_cache", "arguments": {"dry_run": False}},
                },
            },
        )
        cache_cleanup_warnings = invoked_cache_cleanup["result"]["structuredContent"]["guardrail_warnings"]
        assert invoked_cache_cleanup["result"]["isError"] is False, invoked_cache_cleanup
        assert cache_cleanup_warnings[0]["code"] == "cache_cleanup_writes", invoked_cache_cleanup
        assert cache_cleanup_warnings[0]["safe_first_arguments"] == {"dry_run": True}, invoked_cache_cleanup

        catalog_invoked = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 27,
                "method": "tools/call",
                "params": {
                    "name": "blender_tool_catalog",
                    "arguments": {"action": "invoke", "name": "list_scene_objects", "arguments": {}},
                },
            },
        )
        assert catalog_invoked["result"]["isError"] is False, catalog_invoked
        assert catalog_invoked["result"]["structuredContent"]["invoked_tool"] == "list_scene_objects", catalog_invoked
        assert catalog_invoked["result"]["structuredContent"]["objects"][0]["name"] == "Cube", catalog_invoked

        invalid = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 30,
                "method": "tools/call",
                "params": {"name": "list_scene_objects", "arguments": {"unexpected": True}},
            },
        )
        assert invalid["result"]["isError"] is True, invalid
        assert invalid["result"]["structuredContent"]["code"] == "invalid_arguments", invalid

        short_vector = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {"name": "set_selected_location_delta", "arguments": {"delta": [1, 2]}},
            },
        )
        assert short_vector["result"]["isError"] is True, short_vector
        assert short_vector["result"]["structuredContent"]["code"] == "unknown_tool", short_vector

        long_vector = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 32,
                "method": "tools/call",
                "params": {"name": "set_selected_location_delta", "arguments": {"delta": [1, 2, 3, 4]}},
            },
        )
        assert long_vector["result"]["isError"] is True, long_vector
        assert long_vector["result"]["structuredContent"]["code"] == "unknown_tool", long_vector

        invalid_invoke_vector = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 34,
                "method": "tools/call",
                "params": {
                    "name": "invoke_blender_tool",
                    "arguments": {"name": "set_selected_location_delta", "arguments": {"delta": [1, 2]}},
                },
            },
        )
        assert invalid_invoke_vector["result"]["isError"] is True, invalid_invoke_vector
        assert invalid_invoke_vector["result"]["structuredContent"]["code"] == "invalid_arguments", invalid_invoke_vector

        hidden_direct_approval = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 33,
                "method": "tools/call",
                "params": {"name": "run_approved_script", "arguments": {"approval_token": ""}},
            },
        )
        assert hidden_direct_approval["result"]["isError"] is True, hidden_direct_approval
        assert hidden_direct_approval["result"]["structuredContent"]["code"] == "unknown_tool", hidden_direct_approval

        empty_approval_invoke = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 35,
                "method": "tools/call",
                "params": {
                    "name": "invoke_blender_tool",
                    "arguments": {"name": "run_approved_script", "arguments": {"approval_token": ""}},
                },
            },
        )
        assert empty_approval_invoke["result"]["isError"] is False, empty_approval_invoke
        assert empty_approval_invoke["result"]["structuredContent"]["invoked_tool"] == "run_approved_script", empty_approval_invoke
        approval_warning_codes = {
            warning["code"]
            for warning in empty_approval_invoke["result"]["structuredContent"]["guardrail_warnings"]
        }
        assert "approval_required" in approval_warning_codes, empty_approval_invoke

        destructive_invoke = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 36,
                "method": "tools/call",
                "params": {
                    "name": "invoke_blender_tool",
                    "arguments": {
                        "name": "open_blend_file",
                        "arguments": {
                            "filepath": "C:/tmp/guardrail-test.blend",
                            "confirm_discard_current": True,
                            "user_confirmed_path": True,
                        },
                    },
                },
            },
        )
        destructive_warning_codes = {
            warning["code"]
            for warning in destructive_invoke["result"]["structuredContent"]["guardrail_warnings"]
        }
        assert destructive_invoke["result"]["isError"] is False, destructive_invoke
        assert "destructive_scene_operation" in destructive_warning_codes, destructive_invoke
        assert "long_running_synchronous_call" in destructive_warning_codes, destructive_invoke

        playblast_invoke = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 37,
                "method": "tools/call",
                "params": {
                    "name": "invoke_blender_tool",
                    "arguments": {"name": "capture_animation_playblast", "arguments": {}},
                },
            },
        )
        playblast_warning_codes = {
            warning["code"]
            for warning in playblast_invoke["result"]["structuredContent"]["guardrail_warnings"]
        }
        assert playblast_invoke["result"]["isError"] is False, playblast_invoke
        assert "long_running_synchronous_call" in playblast_warning_codes, playblast_invoke

        render_job_invoke = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 38,
                "method": "tools/call",
                "params": {"name": "start_render_job", "arguments": {"job_name": "guardrail-smoke"}},
            },
        )
        render_job_warning_codes = {
            warning["code"]
            for warning in render_job_invoke["result"]["structuredContent"]["guardrail_warnings"]
        }
        assert render_job_invoke["result"]["isError"] is False, render_job_invoke
        assert "background_job_polling_required" in render_job_warning_codes, render_job_invoke

        with open(audit_path, "r", encoding="utf-8") as handle:
            audit_events = [json.loads(line) for line in handle if line.strip()]
        tool_events = [event for event in audit_events if event.get("event") == "mcp_tool_call"]
        assert any(event.get("tool_name") == "list_scene_objects" and event.get("ok") for event in tool_events), tool_events
        assert any(event.get("code") == "invalid_arguments" for event in tool_events), tool_events

        resources = _send(proc, {"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
        uris = {item["uri"] for item in resources["result"]["resources"]}
        assert "blender://bridge/status" in uris
        assert "blender://scene/status" in uris
        assert "blender://tools/catalog" in uris
        assert "blender://tools/contracts" not in uris
        assert "blender://audit/summary" in uris
        assert "blender://audit/latest" not in uris
        assert "blender://captures/latest" in uris
        assert "blender://captures/latest/metadata" in uris
        assert "blender://playblasts/latest/metadata" in uris
        assert "blender://inspection-renders/latest/metadata" in uris
        assert "blender://render-thumbnails/latest" in uris
        assert "blender://render-thumbnails/latest/metadata" in uris
        assert "blender://render-jobs/latest/metadata" in uris

        tool_catalog_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 36,
                "method": "resources/read",
                "params": {"uri": "blender://tools/catalog"},
            },
        )
        tool_catalog = json.loads(tool_catalog_resource["result"]["contents"][0]["text"])
        assert tool_catalog["ok"] is True, tool_catalog
        assert tool_catalog["full_contracts_resource"] == "blender://tools/contracts", tool_catalog
        assert "tools" in tool_catalog and tool_catalog["count"] == len(tool_catalog["tools"]), tool_catalog
        assert "input_schema" not in tool_catalog["tools"][0], tool_catalog

        audit_summary_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 37,
                "method": "resources/read",
                "params": {"uri": "blender://audit/summary"},
            },
        )
        audit_summary = json.loads(audit_summary_resource["result"]["contents"][0]["text"])
        assert audit_summary["ok"] is True, audit_summary
        assert "latest_events" in audit_summary, audit_summary
        assert audit_summary["latest_full_resource"] == "blender://audit/latest", audit_summary

        audit_latest_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 38,
                "method": "resources/read",
                "params": {"uri": "blender://audit/latest"},
            },
        )
        audit_latest = json.loads(audit_latest_resource["result"]["contents"][0]["text"])
        assert audit_latest["event_limit"] == 20, audit_latest
        assert len(audit_latest["events"]) <= 20, audit_latest

        templates = _send(proc, {"jsonrpc": "2.0", "id": 40, "method": "resources/templates/list"})
        template_names = {item["name"] for item in templates["result"]["resourceTemplates"]}
        assert "scene-resource" in template_names, templates
        assert "capture-resource" in template_names, templates
        assert "capture-metadata-resource" in template_names, templates
        assert "playblast-metadata-resource" in template_names, templates
        assert "playblast-frame-resource" in template_names, templates
        assert "inspection-render-metadata-resource" in template_names, templates
        assert "inspection-render-image-resource" in template_names, templates
        assert "render-thumbnail-resource" in template_names, templates
        assert "render-thumbnail-metadata-resource" in template_names, templates
        assert "render-job-metadata-resource" in template_names, templates
        assert "render-job-frame-resource" in template_names, templates
        assert "render-job-log-resource" in template_names, templates
        assert "render-job-video-resource" in template_names, templates

        prompts = _send(proc, {"jsonrpc": "2.0", "id": 41, "method": "prompts/list"})
        prompt_names = {item["name"] for item in prompts["result"]["prompts"]}
        assert "safe_scene_change" in prompt_names, prompts
        assert "advanced_animation_workflow" in prompt_names, prompts
        assert "external_asset_workflow" in prompt_names, prompts

        prompt = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 42,
                "method": "prompts/get",
                "params": {"name": "safe_scene_change", "arguments": {"goal": "add a light"}},
            },
        )
        assert "add a light" in prompt["result"]["messages"][0]["content"]["text"], prompt
        animation_prompt = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 43,
                "method": "prompts/get",
                "params": {"name": "advanced_animation_workflow", "arguments": {"goal": "make the cube bounce"}},
            },
        )
        animation_prompt_text = animation_prompt["result"]["messages"][0]["content"]["text"]
        assert "plan_animation_workflow" in animation_prompt_text, animation_prompt
        assert "run_animation_workflow" in animation_prompt_text, animation_prompt
        assert "capture_object_inspection_renders" in animation_prompt_text, animation_prompt
        assert "draft_script only" in animation_prompt_text, animation_prompt
        asset_prompt = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 44,
                "method": "prompts/get",
                "params": {
                    "name": "external_asset_workflow",
                    "arguments": {"goal": "find and import a Poly Haven HDRI"},
                },
            },
        )
        asset_prompt_text = asset_prompt["result"]["messages"][0]["content"]["text"]
        assert "start_external_asset_download" in asset_prompt_text, asset_prompt
        assert "get_external_asset_job_status" in asset_prompt_text, asset_prompt
        assert "start_external_asset_import_job" in asset_prompt_text, asset_prompt
        assert "get_external_asset_import_job_status" in asset_prompt_text, asset_prompt
        assert "synchronous fallback" in asset_prompt_text, asset_prompt

        resource = _send(
            proc,
            {"jsonrpc": "2.0", "id": 5, "method": "resources/read", "params": {"uri": "blender://scene/status"}},
        )
        assert resource["result"]["contents"][0]["mimeType"] == "application/json", resource

        capture_resource = _send(
            proc,
            {"jsonrpc": "2.0", "id": 43, "method": "resources/read", "params": {"uri": "blender://captures/latest"}},
        )
        capture_content = capture_resource["result"]["contents"][0]
        assert capture_content["mimeType"] == "image/png", capture_resource
        assert capture_content["blob"] == "iVBORw0KGgo=", capture_resource
        capture_metadata = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 44,
                "method": "resources/read",
                "params": {"uri": "blender://captures/latest/metadata"},
            },
        )
        metadata_content = capture_metadata["result"]["contents"][0]
        metadata = json.loads(metadata_content["text"])
        assert metadata["exact_resource_uri"] == "blender://captures/test-capture", capture_metadata
        exact_capture_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 45,
                "method": "resources/read",
                "params": {"uri": metadata["exact_resource_uri"]},
            },
        )
        exact_capture_content = exact_capture_resource["result"]["contents"][0]
        assert exact_capture_content["mimeType"] == "image/png", exact_capture_resource
        assert exact_capture_content["blob"] == "iVBORw0KGgo=", exact_capture_resource
        exact_metadata_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 46,
                "method": "resources/read",
                "params": {"uri": metadata["exact_metadata_uri"]},
            },
        )
        exact_metadata = json.loads(exact_metadata_resource["result"]["contents"][0]["text"])
        assert exact_metadata["resource_uri"] == "blender://captures/test-capture", exact_metadata_resource
        playblast_metadata_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 47,
                "method": "resources/read",
                "params": {"uri": "blender://playblasts/latest/metadata"},
            },
        )
        playblast_metadata = json.loads(playblast_metadata_resource["result"]["contents"][0]["text"])
        assert playblast_metadata["metadata_uri"] == "blender://playblasts/test-playblast/metadata", playblast_metadata_resource
        playblast_exact_metadata_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 48,
                "method": "resources/read",
                "params": {"uri": playblast_metadata["metadata_uri"]},
            },
        )
        playblast_exact_metadata = json.loads(playblast_exact_metadata_resource["result"]["contents"][0]["text"])
        assert playblast_exact_metadata["playblast_id"] == "test-playblast", playblast_exact_metadata_resource
        playblast_frame_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 49,
                "method": "resources/read",
                "params": {"uri": playblast_metadata["frames"][0]["resource_uri"]},
            },
        )
        playblast_frame = playblast_frame_resource["result"]["contents"][0]
        assert playblast_frame["mimeType"] == "image/png", playblast_frame_resource
        assert playblast_frame["blob"] == "iVBORw0KGgo=", playblast_frame_resource
        inspection_metadata_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 50,
                "method": "resources/read",
                "params": {"uri": "blender://inspection-renders/latest/metadata"},
            },
        )
        inspection_metadata = json.loads(inspection_metadata_resource["result"]["contents"][0]["text"])
        assert inspection_metadata["metadata_uri"] == "blender://inspection-renders/test-render/metadata", inspection_metadata_resource
        inspection_exact_metadata_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 51,
                "method": "resources/read",
                "params": {"uri": inspection_metadata["metadata_uri"]},
            },
        )
        inspection_exact_metadata = json.loads(inspection_exact_metadata_resource["result"]["contents"][0]["text"])
        assert inspection_exact_metadata["render_id"] == "test-render", inspection_exact_metadata_resource
        inspection_image_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 52,
                "method": "resources/read",
                "params": {"uri": inspection_metadata["images"][0]["resource_uri"]},
            },
        )
        inspection_image = inspection_image_resource["result"]["contents"][0]
        assert inspection_image["mimeType"] == "image/png", inspection_image_resource
        assert inspection_image["blob"] == "iVBORw0KGgo=", inspection_image_resource
        thumbnail_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 53,
                "method": "resources/read",
                "params": {"uri": "blender://render-thumbnails/latest"},
            },
        )
        thumbnail_image = thumbnail_resource["result"]["contents"][0]
        assert thumbnail_image["mimeType"] == "image/png", thumbnail_resource
        assert thumbnail_image["blob"] == "iVBORw0KGgo=", thumbnail_resource
        thumbnail_metadata_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 54,
                "method": "resources/read",
                "params": {"uri": "blender://render-thumbnails/latest/metadata"},
            },
        )
        thumbnail_metadata = json.loads(thumbnail_metadata_resource["result"]["contents"][0]["text"])
        assert thumbnail_metadata["metadata_uri"] == "blender://render-thumbnails/test-thumbnail/metadata", thumbnail_metadata_resource
        thumbnail_exact_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 55,
                "method": "resources/read",
                "params": {"uri": thumbnail_metadata["resource_uri"]},
            },
        )
        assert thumbnail_exact_resource["result"]["contents"][0]["blob"] == "iVBORw0KGgo=", thumbnail_exact_resource
        thumbnail_exact_metadata = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 56,
                "method": "resources/read",
                "params": {"uri": thumbnail_metadata["metadata_uri"]},
            },
        )
        assert json.loads(thumbnail_exact_metadata["result"]["contents"][0]["text"])["thumbnail_id"] == "test-thumbnail", thumbnail_exact_metadata
        render_job_metadata_resource = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 57,
                "method": "resources/read",
                "params": {"uri": "blender://render-jobs/latest/metadata"},
            },
        )
        render_job_metadata = json.loads(render_job_metadata_resource["result"]["contents"][0]["text"])
        assert render_job_metadata["metadata_uri"] == "blender://render-jobs/test-render-job/metadata", render_job_metadata_resource
        render_job_exact = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 58,
                "method": "resources/read",
                "params": {"uri": render_job_metadata["metadata_uri"]},
            },
        )
        assert json.loads(render_job_exact["result"]["contents"][0]["text"])["job_id"] == "test-render-job", render_job_exact
        render_job_frame = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 59,
                "method": "resources/read",
                "params": {"uri": render_job_metadata["newest_frame_resource_uri"]},
            },
        )
        assert render_job_frame["result"]["contents"][0]["mimeType"] == "image/png", render_job_frame
        render_job_log = _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 60,
                "method": "resources/read",
                "params": {"uri": render_job_metadata["log_resource_uri"]},
            },
        )
        assert render_job_log["result"]["contents"][0]["text"] == "render log", render_job_log
        print("smoke_mcp_server: ok")
    finally:
        proc.kill()
        proc.wait(timeout=5)
        fake_bridge.shutdown()
        fake_bridge.server_close()
        try:
            os.remove(audit_path)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
