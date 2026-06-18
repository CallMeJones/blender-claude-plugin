"""Transcript storage and sidebar-friendly text previews."""

from __future__ import annotations

import datetime as _dt
import re
import textwrap

import bpy

TRANSCRIPT_NAME = "Blender Agent Bridge Transcript"

_MARKDOWN_PREFIX = re.compile(r"^\s{0,3}(#{1,6}\s+|[-*_]{3,}\s*$|>\s?)")


def _now():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _text_block():
    block = bpy.data.texts.get(TRANSCRIPT_NAME)
    if block is None:
        block = bpy.data.texts.new(TRANSCRIPT_NAME)
    return block


def append_entry(role, content):
    block = _text_block()
    block.write(f"\n[{_now()}] {role}\n")
    block.write((content or "").rstrip())
    block.write("\n")
    return block


def record_user_prompt(prompt, context_summary=""):
    body = prompt or ""
    if context_summary:
        body += f"\n\nContext: {context_summary}"
    append_entry("User", body)


def record_assistant_message(message):
    append_entry("Agent", message or "")


def record_system_message(message):
    append_entry("System", message or "")


def transcript_text():
    block = bpy.data.texts.get(TRANSCRIPT_NAME)
    return block.as_string() if block else ""


def _clean_preview_line(line):
    line = line.strip()
    line = _MARKDOWN_PREFIX.sub("", line).strip()
    line = line.replace("**", "").replace("__", "").replace("`", "")
    line = line.encode("ascii", "ignore").decode("ascii")
    if set(line) <= {"|", "-", ":", " "}:
        return ""
    return line


def preview_lines(text, *, width=88, max_lines=12):
    lines = []
    for raw_line in (text or "").splitlines():
        line = _clean_preview_line(raw_line)
        if not line:
            continue
        for wrapped in textwrap.wrap(line, width=width) or [line]:
            lines.append(wrapped)
            if len(lines) >= max_lines:
                return lines
    return lines


def register():
    pass


def unregister():
    pass
