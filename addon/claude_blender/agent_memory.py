"""Compact per-blend agent memory for progressive scene work."""

from __future__ import annotations

import datetime as _dt
import re

import bpy

MEMORY_TEXT_NAME = "Blender Agent Bridge Memory"
MAX_MEMORY_CHARS = 14_000
MAX_PROMPT_CHARS = 1_200
MAX_RESPONSE_CHARS = 2_400

_JSONISH_LINE = re.compile(r'^\s*["{}\[\],:0-9.\-]+$')


def _now():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _text_block():
    text = bpy.data.texts.get(MEMORY_TEXT_NAME)
    if text is None:
        text = bpy.data.texts.new(MEMORY_TEXT_NAME)
    return text


def _read():
    text = bpy.data.texts.get(MEMORY_TEXT_NAME)
    return text.as_string() if text else ""


def _meaningful_memory():
    memory = _read().strip()
    if memory in {"", "# Claude Agent Memory", "# Blender Agent Bridge Memory"}:
        return ""
    return memory


def _write(body):
    text = _text_block()
    text.clear()
    text.write(body)
    return text


def _compact(value, max_chars):
    value = str(value or "").strip()
    kept_lines = []
    for line in value.splitlines():
        line = line.strip()
        if not line:
            continue
        if _JSONISH_LINE.match(line):
            continue
        kept_lines.append(line)
    compacted = "\n".join(kept_lines) or value
    if len(compacted) <= max_chars:
        return compacted
    return f"{compacted[:max_chars]}... [truncated]"


def _prune(body):
    if len(body) <= MAX_MEMORY_CHARS:
        return body
    marker = "\n## Turn "
    tail = body[-MAX_MEMORY_CHARS:]
    first_turn = tail.find(marker)
    if first_turn > 0:
        tail = tail[first_turn + 1 :]
    return (
        "# Blender Agent Bridge Memory\n"
        "\n[Older memory was pruned to fit the request budget.]\n\n"
        f"{tail.strip()}\n"
    )


def _set_state(scene, *, status=None):
    state = getattr(scene, "claude_blender", None)
    if not state:
        return
    state.agent_memory_text_name = MEMORY_TEXT_NAME
    size = len(_read())
    state.agent_memory_status = status or (f"{size} chars remembered" if size else "No agent memory yet")


def get_memory(scene=None):
    if scene:
        _set_state(scene)
    return _read()


def clear_memory(scene=None):
    _write("# Blender Agent Bridge Memory\n")
    if scene:
        _set_state(scene, status="Memory cleared")
    return {"ok": True, "message": "Agent memory cleared", "text_datablock": MEMORY_TEXT_NAME}


def add_to_bundle(bundle, context):
    state = getattr(context.scene, "claude_blender", None)
    if not state or not getattr(state, "agent_memory_enabled", True):
        bundle["agent_memory"] = {
            "enabled": False,
            "note": "Agent memory is disabled for this scene.",
        }
        return bundle
    memory = _meaningful_memory()
    bundle["agent_memory"] = {
        "enabled": True,
        "text_datablock": MEMORY_TEXT_NAME,
        "memory": memory or "No prior agent memory for this scene yet.",
        "instruction": (
            "Use this as running project context for progressive scene/object/animation work. "
            "Current scene context is still authoritative if memory conflicts with the open Blender scene."
        ),
    }
    _set_state(context.scene)
    return bundle


def record_turn(scene, *, user_prompt, assistant_response, context_summary=""):
    state = getattr(scene, "claude_blender", None)
    if state and not getattr(state, "agent_memory_enabled", True):
        state.agent_memory_status = "Memory disabled"
        return {"ok": False, "message": "Agent memory disabled"}

    existing = _read().strip()
    if not existing:
        existing = "# Blender Agent Bridge Memory"
    entry = (
        f"\n\n## Turn {_now()}\n"
        f"User goal/request:\n{_compact(user_prompt, MAX_PROMPT_CHARS)}\n\n"
        f"Scene context at request:\n{_compact(context_summary, 600) or 'Not captured'}\n\n"
        f"Agent result / next state:\n{_compact(assistant_response, MAX_RESPONSE_CHARS)}\n"
    )
    text = _write(_prune(existing + entry))
    if state:
        state.agent_memory_text_name = text.name
        state.agent_memory_status = f"{len(text.as_string())} chars remembered"
    return {"ok": True, "message": "Agent memory updated", "text_datablock": text.name}


def register():
    pass


def unregister():
    pass
