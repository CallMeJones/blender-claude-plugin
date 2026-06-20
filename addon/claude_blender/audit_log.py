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
            events.append({"event": "audit_log_parse_error", "raw": line[:MAX_VALUE_CHARS]})
    return events


def clear_for_tests(path=None):
    target = path or audit_path()
    try:
        os.remove(target)
    except FileNotFoundError:
        pass


def temporary_audit_path():
    fd, path = tempfile.mkstemp(prefix="claude-blender-audit-", suffix=".jsonl")
    os.close(fd)
    clear_for_tests(path)
    return path
