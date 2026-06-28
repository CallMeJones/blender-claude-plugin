"""Small JSONL audit log for bridge and MCP tool calls."""

from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile

try:
    from . import user_paths
except ImportError:
    user_paths = None

MAX_VALUE_CHARS = 500
MAX_RECENT_LINES = 200
AUDIT_LOG_TEXT_NAME = "Claude Audit Log"

_SENSITIVE_KEY_PARTS = (
    "access_key",
    "api_key",
    "apikey",
    "authorization",
    "body",
    "code",
    "credential",
    "password",
    "private_key",
    "python",
    "script",
    "secret",
    "source",
    "token",
)


def _now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def audit_path():
    if user_paths is not None:
        default_path = user_paths.user_data_path("audit.jsonl")
    else:
        default_path = os.path.join(os.path.expanduser("~"), ".claude_blender", "audit.jsonl")
    return os.environ.get("CLAUDE_BLENDER_AUDIT_LOG", default_path)


def _safe_key(key):
    key = str(key)
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _redact_value(value, depth=0):
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            str(key): "[redacted]" if _safe_key(key) else _redact_value(child, depth + 1)
            for key, child in list(value.items())[:40]
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(item, depth + 1) for item in list(value)[:40]]
    if isinstance(value, str):
        if len(value) > MAX_VALUE_CHARS:
            return f"{value[:MAX_VALUE_CHARS]}... [truncated]"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return repr(value)[:MAX_VALUE_CHARS]


def summarize_arguments(arguments):
    return _redact_value(arguments if isinstance(arguments, dict) else {})


def append_event(event_type, **fields):
    path = audit_path()
    payload = {
        "timestamp": _now(),
        "event": str(event_type),
    }
    payload.update({str(key): _redact_value(value) for key, value in fields.items()})
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    line = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return payload


def read_recent(limit=50):
    path = audit_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except FileNotFoundError:
        return []
    try:
        count = int(limit)
    except (TypeError, ValueError):
        count = 50
    count = max(1, min(MAX_RECENT_LINES, count))
    events = []
    for line in lines[-count:]:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"event": "audit_log_parse_error", "raw": "[unparseable redacted]"})
    return events


def status():
    path = audit_path()
    try:
        size_bytes = os.path.getsize(path)
    except FileNotFoundError:
        return {
            "path": path,
            "exists": False,
            "size_bytes": 0,
            "event_count": 0,
            "last_event": None,
        }
    event_count = 0
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                event_count += 1
    recent = read_recent(1)
    return {
        "path": path,
        "exists": True,
        "size_bytes": size_bytes,
        "event_count": event_count,
        "last_event": recent[-1] if recent else None,
    }


def status_summary():
    info = status()
    if not info["exists"]:
        return f"Audit log empty: {info['path']}"
    parts = [f"Audit log: {info['event_count']} event(s), {info['size_bytes']} bytes"]
    last_event = info.get("last_event") or {}
    if last_event:
        parts.append(f"last {last_event.get('event', 'event')}")
        if last_event.get("tool_name"):
            parts.append(str(last_event["tool_name"]))
        if "ok" in last_event:
            parts.append("ok" if last_event.get("ok") else "failed")
    return " | ".join(parts)


def _event_line(event):
    parts = [
        str(event.get("timestamp") or ""),
        str(event.get("event") or "event"),
    ]
    if event.get("tool_name"):
        parts.append(str(event["tool_name"]))
    if event.get("action"):
        parts.append(str(event["action"]))
    if "ok" in event:
        parts.append("ok" if event.get("ok") else "failed")
    if event.get("code"):
        parts.append(str(event["code"]))
    return " | ".join(part for part in parts if part)


def format_recent(limit=40):
    info = status()
    lines = [
        f"Audit log: {info['path']}",
        status_summary(),
        "",
    ]
    events = read_recent(limit) if info["exists"] else []
    if not events:
        lines.append("No audit events.")
        return "\n".join(lines)
    for event in events:
        lines.append(_event_line(event))
        lines.append(json.dumps(event, indent=2, sort_keys=True, default=str))
        lines.append("")
    return "\n".join(lines).rstrip()


def clear(path=None):
    target = path or audit_path()
    existed = os.path.exists(target)
    try:
        os.remove(target)
    except FileNotFoundError:
        pass
    return {
        "ok": True,
        "path": target,
        "cleared": existed,
        "message": "Audit log cleared" if existed else "Audit log already empty",
    }


def clear_for_tests(path=None):
    clear(path)


def temporary_audit_path():
    fd, path = tempfile.mkstemp(prefix="claude-blender-audit-", suffix=".jsonl")
    os.close(fd)
    clear_for_tests(path)
    return path
