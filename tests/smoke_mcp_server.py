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
            self._send({"ok": True, "scene": "Fake Scene", "bridge_version": "test"})
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
                        }
                    ],
                }
            )
        elif parsed.path == "/resource":
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
        "search_blender_tools",
        "get_blender_tool_schema",
        "invoke_blender_tool",
        "list_scene_objects",
    }.issubset(names), listed
    assert "draft_script" not in names, listed
    assert "run_approved_script" not in names, listed
    scene_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "list_scene_objects")
    assert scene_tool["outputSchema"]["type"] == "object", scene_tool
    search_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "search_blender_tools")
    assert search_tool["annotations"]["readOnlyHint"] is True, search_tool
    invoke_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "invoke_blender_tool")
    assert invoke_tool["annotations"]["readOnlyHint"] is False, invoke_tool
    assert "run_approved_script" in bridge_protocol.list_tool_contracts()["tools"]
    return listed


def _assert_full_tools_visible(proc):
    listed = _send(proc, {"jsonrpc": "2.0", "id": 91, "method": "tools/list"})
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert {"blender_bridge_status", "list_scene_objects", "draft_script", "run_approved_script"}.issubset(names), listed
    draft_tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "draft_script")
    assert draft_tool["annotations"]["mutatesScene"] is False, draft_tool
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


def main():
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

        templates = _send(proc, {"jsonrpc": "2.0", "id": 40, "method": "resources/templates/list"})
        template_names = {item["name"] for item in templates["result"]["resourceTemplates"]}
        assert "scene-resource" in template_names, templates

        prompts = _send(proc, {"jsonrpc": "2.0", "id": 41, "method": "prompts/list"})
        prompt_names = {item["name"] for item in prompts["result"]["prompts"]}
        assert "safe_scene_change" in prompt_names, prompts

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

        resource = _send(
            proc,
            {"jsonrpc": "2.0", "id": 5, "method": "resources/read", "params": {"uri": "blender://scene/status"}},
        )
        assert resource["result"]["contents"][0]["mimeType"] == "application/json", resource
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
