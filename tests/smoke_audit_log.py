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
        status = audit_log.status()
        assert status["exists"], status
        assert status["event_count"] == 1, status
        assert status["last_event"]["event"] == "test_tool_call", status
        assert "1 event" in audit_log.status_summary(), audit_log.status_summary()
        formatted = audit_log.format_recent(5)
        assert audit_log.AUDIT_LOG_TEXT_NAME == "Claude Audit Log"
        assert "test_tool_call" in formatted, formatted
        assert "draft_script" in formatted, formatted
        assert "secret source should not be logged" not in formatted, formatted
        assert "[redacted]" in formatted, formatted

        with open(path, "r", encoding="utf-8") as handle:
            raw = json.loads(handle.readline())
        assert raw["tool_name"] == "draft_script", raw
        cleared = audit_log.clear()
        assert cleared["ok"], cleared
        assert cleared["cleared"], cleared
        assert not os.path.exists(path), path
        assert audit_log.read_recent(5) == []
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"token": "should not echo"\n')
        parse_error = audit_log.read_recent(5)[0]
        assert parse_error["event"] == "audit_log_parse_error", parse_error
        assert parse_error["raw"] == "[unparseable redacted]", parse_error
        assert "should not echo" not in audit_log.format_recent(5), audit_log.format_recent(5)
        print("smoke_audit_log: ok")
    finally:
        audit_log.clear_for_tests(path)
        os.environ.pop("CLAUDE_BLENDER_AUDIT_LOG", None)


if __name__ == "__main__":
    main()
