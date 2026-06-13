"""Smoke test for JSONL audit logging and redaction."""

from __future__ import annotations

import json
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon", "claude_blender"))

import audit_log  # noqa: E402


def main():
    path = audit_log.temporary_audit_path()
    os.environ["CLAUDE_BLENDER_AUDIT_LOG"] = path
    try:
        audit_log.append_event(
            "test_tool_call",
            tool_name="draft_script",
            arguments={
                "intent": "create a cube",
                "code": "print('secret source should not be logged')",
                "key_name": "Lift",
                "nested": {"bridge_token": "abc123"},
            },
        )
        recent = audit_log.read_recent(5)
        assert len(recent) == 1, recent
        event = recent[0]
        assert event["event"] == "test_tool_call", event
        assert event["arguments"]["intent"] == "create a cube", event
        assert event["arguments"]["key_name"] == "Lift", event
        assert event["arguments"]["code"] == "[redacted]", event
        assert event["arguments"]["nested"]["bridge_token"] == "[redacted]", event

        with open(path, "r", encoding="utf-8") as handle:
            raw = json.loads(handle.readline())
        assert raw["tool_name"] == "draft_script", raw
        print("smoke_audit_log: ok")
    finally:
        audit_log.clear_for_tests(path)
        os.environ.pop("CLAUDE_BLENDER_AUDIT_LOG", None)


if __name__ == "__main__":
    main()
