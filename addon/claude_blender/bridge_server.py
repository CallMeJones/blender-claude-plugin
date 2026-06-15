"""Local localhost JSON bridge for external MCP/agent access."""

from __future__ import annotations

import json
import queue
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bpy

from . import (
    audit_log,
    anthropic_client,
    bridge_protocol,
    build_info,
    context_bundle,
    preferences,
    script_runner,
    tool_dispatcher,
    transcript,
    viewport_capture,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
REQUEST_TIMEOUT_SECONDS = 60

_server = None
_thread = None
_requests = queue.Queue()
_timer_registered = False
_lock = threading.Lock()


def _json_bytes(payload):
    return json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")


def _public_context():
    return context_bundle.public_bundle(context_bundle.build_context_bundle(bpy.context))


def _scene_status():
    bundle = context_bundle.build_context_bundle(bpy.context)
    state = getattr(bpy.context.scene, "claude_blender", None)
    trust = script_runner.external_script_trust_snapshot(bpy.context, state=state) if state else {}
    url = bridge_url() or (getattr(state, "bridge_url", "") if state else "")
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
        "mcp_server_version": diagnostics["mcp_server_version"],
        "mcp_server_path": diagnostics["mcp_server_path"],
        "mcp_config_version": diagnostics["mcp_config_version"],
        "build_diagnostics": build_info.diagnostics_summary(),
        "scene": bpy.context.scene.name,
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
    for tool in anthropic_client.blender_tool_definitions():
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
            "uri": "blender://tools/contracts",
            "name": "tool-contracts",
            "title": "Blender Tool Contracts",
            "description": "Tool safety metadata for the bridge/MCP surface",
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
            "uri": "blender://audit/latest",
            "name": "latest-audit-log",
            "title": "Blender Agent Bridge Audit Log",
            "description": "Recent local JSON audit events for bridge and MCP tool calls",
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
            "text": json.dumps({"ok": True, "events": audit_log.read_recent(80)}, indent=2, sort_keys=True),
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
    return None


def _execute_tool(payload):
    name = str(payload.get("name") or "")
    args = payload.get("arguments")
    if args is None:
        args = payload.get("input")
    if not isinstance(args, dict):
        args = {}
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


def _ensure_timer():
    global _timer_registered
    if not _timer_registered:
        bpy.app.timers.register(_process_requests, first_interval=0.05)
        _timer_registered = True


class _BridgeHandler(BaseHTTPRequestHandler):
    server_version = "ClaudeBlenderBridge/0.2"

    def log_message(self, fmt, *args):
        return

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
        return header == f"Bearer {token}"

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def do_GET(self):
        if not self._authorized():
            self._send_error(401, "Unauthorized")
            return
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path == "/health":
                self._send(200, _call_on_main(_scene_status))
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
        if not self._authorized():
            self._send_error(401, "Unauthorized")
            return
        parsed = urllib.parse.urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/tool":
                self._send(200, _call_on_main(lambda: _execute_tool(payload)))
            else:
                self._send_error(404, f"Unknown endpoint: {parsed.path}")
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
        thread = threading.Thread(target=server.serve_forever, name="ClaudeBlenderBridge", daemon=True)
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
    pass


def unregister():
    stop_bridge()
