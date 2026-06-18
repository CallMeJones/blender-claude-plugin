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

    def _send(self, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self._send(
                {
                    "ok": True,
                    "scene": "Fake Scene",
                    "bridge_version": bridge_protocol.BRIDGE_VERSION,
                    "addon_version": build_info.ADDON_VERSION,
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
            if uri == "blender://captures/latest":
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
    assert {
        "blender_bridge_status",
        "blender_tool_catalog",
        "search_blender_tools",
        "get_blender_tool_schema",
        "invoke_blender_tool",
        "list_scene_objects",
        "plan_animation_workflow",
        "run_animation_workflow",
        "run_animation_task",
        "start_render_job",
        "get_render_job_status",
        "cancel_render_job",
    }.issubset(names), listed
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
    assert "build_diagnostics" in status_properties, status_tool
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
    assert render_tool["annotations"]["riskLevel"] == "read", render_tool
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
    return listed


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


def main():
    assert not mcp_server._contains_any_phrase(
        "Create an architectural arch from cubes",
        mcp_server.ANIMATION_ROUTE_TERMS,
    )
    assert mcp_server._contains_any_phrase(
        "Make the selected cube bounce twice",
        mcp_server.ANIMATION_ROUTE_TERMS,
    )

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
        assert "input_schema" in searched_tools[0], searched
        assert "output_schema" in searched_tools[0], searched

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
        assert {"inspect", "script", "transform"}.issubset(category_names), catalog_categories

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

        with open(audit_path, "r", encoding="utf-8") as handle:
            audit_events = [json.loads(line) for line in handle if line.strip()]
        tool_events = [event for event in audit_events if event.get("event") == "mcp_tool_call"]
        assert any(event.get("tool_name") == "list_scene_objects" and event.get("ok") for event in tool_events), tool_events
        assert any(event.get("code") == "invalid_arguments" for event in tool_events), tool_events

        resources = _send(proc, {"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
        uris = {item["uri"] for item in resources["result"]["resources"]}
        assert "blender://bridge/status" in uris
        assert "blender://scene/status" in uris
        assert "blender://captures/latest" in uris
        assert "blender://captures/latest/metadata" in uris
        assert "blender://playblasts/latest/metadata" in uris
        assert "blender://inspection-renders/latest/metadata" in uris
        assert "blender://render-thumbnails/latest" in uris
        assert "blender://render-thumbnails/latest/metadata" in uris
        assert "blender://render-jobs/latest/metadata" in uris

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
