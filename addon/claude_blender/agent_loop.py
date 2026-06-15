"""Async-ish agent loop glue for Blender UI calls."""

from __future__ import annotations

import queue
import threading
import uuid
import json

import bpy

from . import agent_memory
from . import animation_brief
from . import anthropic_client
from . import chat_history
from . import context_budget
from . import tool_dispatcher
from . import transcript

_results = queue.Queue()
_tool_requests = queue.Queue()
_timer_registered = False
_active_workers = 0
_lock = threading.Lock()

TOOL_LIMIT_FINAL_PROMPT = (
    "You reached the Blender tool-call budget for this request. Do not call more tools. "
    "Briefly summarize what you changed, mention that live preview changes may still be pending, "
    "and say what the user should do next. If the scene is incomplete, say exactly what remains."
)


def _parse_tool_json(result):
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"ok": False, "message": result}
    return result if isinstance(result, dict) else {"ok": False, "message": "Unexpected tool result"}


def _animation_brief_tool_input(prompt):
    return {"prompt": prompt}


def _apply_animation_brief_preflight(scene_name, prompt, request_context, *, tool_executor=None):
    if not animation_brief.should_create_brief(prompt):
        return ""
    executor = tool_executor or _execute_tool_sync
    result = _parse_tool_json(
        executor(
            scene_name,
            {
                "name": "create_animation_brief",
                "input": _animation_brief_tool_input(prompt),
            },
        )
    )
    if not result.get("ok"):
        transcript.record_system_message(f"Animation brief preflight failed: {result.get('message', 'Unknown error')}")
        return ""
    brief = result.get("brief") or {}
    request_context["animation_brief"] = brief
    brief_text = json.dumps(context_budget.compact_jsonable(brief), indent=2, sort_keys=True)
    transcript.record_system_message(
        "Animation brief preflight:\n"
        f"{context_budget.truncate_text(brief_text, 8000)}"
    )
    if brief.get("clarification_needed"):
        return animation_brief.clarification_question(brief)
    return ""


def _apply_result(scene_name, ok, message, prompt="", context_summary=""):
    scene = bpy.data.scenes.get(scene_name)
    if scene is None or not hasattr(scene, "claude_blender"):
        return
    state = scene.claude_blender
    if ok and "tool-call budget" in (message or "").lower():
        state.status = "Needs continuation"
    else:
        state.status = "Ready" if ok else "Error"
    state.active_tool_name = ""
    state.last_response = message
    transcript.record_assistant_message(message)
    chat_history.append_message(
        scene,
        role="assistant" if ok else "error",
        content=message,
        title="Claude" if ok else "Error",
        context_summary=context_summary,
    )
    if ok:
        agent_memory.record_turn(
            scene,
            user_prompt=prompt,
            assistant_response=message,
            context_summary=context_summary,
        )


def _set_tool_status(scene_name, tool_name):
    scene = bpy.data.scenes.get(scene_name)
    if scene is None or not hasattr(scene, "claude_blender"):
        return
    state = scene.claude_blender
    state.status = f"Running Blender tool: {tool_name}"
    state.last_response = f"Running Blender tool: {tool_name}"
    state.active_tool_name = str(tool_name or "")
    state.last_tool_name = str(tool_name or "")
    state.tool_call_count += 1


def _process_tool_requests():
    while True:
        try:
            request = _tool_requests.get_nowait()
        except queue.Empty:
            break
        _set_tool_status(request["scene_name"], request["name"])
        request["result"] = tool_dispatcher.execute_tool(
            bpy.context,
            request["name"],
            request.get("input") or {},
        )
        request["event"].set()


def _process_events():
    global _timer_registered
    _process_tool_requests()
    while True:
        try:
            scene_name, ok, message, prompt, context_summary = _results.get_nowait()
        except queue.Empty:
            break
        _apply_result(scene_name, ok, message, prompt, context_summary)
    with _lock:
        active = _active_workers
    if _results.empty() and _tool_requests.empty() and active == 0:
        _timer_registered = False
        return None
    return 0.1


def _ensure_timer():
    global _timer_registered
    if not _timer_registered:
        bpy.app.timers.register(_process_events, first_interval=0.1)
        _timer_registered = True


def _execute_tool_sync(scene_name, tool_block):
    request = {
        "id": str(uuid.uuid4()),
        "scene_name": scene_name,
        "name": tool_block.get("name"),
        "input": tool_block.get("input") or {},
        "event": threading.Event(),
        "result": None,
    }
    _tool_requests.put(request)
    if not request["event"].wait(timeout=60):
        return '{"ok": false, "message": "Tool execution timed out"}'
    return request["result"] or '{"ok": false, "message": "Tool returned no result"}'


def _finalize_after_tool_limit(*, messages, model, tool_call_count):
    final_messages = list(messages)
    final_messages.append(
        {
            "role": "user",
            "content": [{"type": "text", "text": TOOL_LIMIT_FINAL_PROMPT}],
        }
    )
    try:
        response = anthropic_client.create_message_raw(
            messages=final_messages,
            model=model,
            tools=None,
            max_tokens=768,
        )
        text = anthropic_client.extract_text(response).strip()
        if text and not text.startswith("{"):
            return (
                f"{text}\n\n"
                f"Tool-call budget reached after {tool_call_count} Blender tool call(s)."
            )
    except Exception as exc:
        transcript.record_system_message(f"Tool-limit final summary failed: {type(exc).__name__}: {exc}")
    return (
        f"Tool-call budget reached after {tool_call_count} Blender tool call(s). "
        "Some scene changes may already be visible as a pending live preview. "
        "Use Commit/Revert, or send a follow-up prompt asking Claude to continue from the current scene."
    )


def _run_tool_loop(*, scene_name, prompt, context_bundle, model):
    tools, tool_metadata = anthropic_client.select_blender_tool_definitions(
        prompt=prompt,
        context_bundle=context_bundle,
    )
    request_context = dict(context_bundle or {})
    request_context["available_tools"] = list(tool_metadata["selected_tool_names"])
    request_context["tool_selection"] = {
        "policy": "Request-specific tool schemas selected to reduce prompt tokens. Ask with a more specific follow-up if a missing tool is needed.",
        "selected_tool_names": list(tool_metadata["selected_tool_names"]),
        "omitted_tool_count": len(tool_metadata["omitted_tool_names"]),
        "schema_chars": int(tool_metadata["schema_chars"]),
        "estimated_schema_tokens": int(tool_metadata["estimated_schema_tokens"]),
        "matched_groups": list(tool_metadata["matched_groups"]),
    }
    if isinstance(request_context.get("context_plan"), dict):
        request_context["context_plan"]["tool_schema_selection"] = {
            "selected_tool_count": int(tool_metadata["selected_tool_count"]),
            "available_tool_count": int(tool_metadata["available_tool_count"]),
            "estimated_schema_tokens": int(tool_metadata["estimated_schema_tokens"]),
            "matched_groups": list(tool_metadata["matched_groups"]),
        }
    clarification = _apply_animation_brief_preflight(scene_name, prompt, request_context)
    if clarification:
        return clarification
    messages = anthropic_client.initial_messages(prompt, request_context)
    tool_call_count = 0

    for _ in range(anthropic_client.MAX_TOOL_LOOPS):
        response = anthropic_client.create_message_raw(
            messages=messages,
            model=model,
            tools=tools,
            max_tokens=anthropic_client.TOOL_LOOP_MAX_TOKENS,
        )
        content = response.get("content", [])
        tool_uses = [block for block in content if block.get("type") == "tool_use"]
        if not tool_uses:
            return anthropic_client.extract_text(response)

        messages.append({"role": "assistant", "content": content})
        tool_results = []
        for tool_use in tool_uses:
            tool_call_count += 1
            result = _execute_tool_sync(scene_name, tool_use)
            limited_result = context_budget.limit_json_result_text(result)
            transcript.record_system_message(
                f"Tool call: {tool_use.get('name')}\n"
                f"Input: {tool_use.get('input')}\n"
                f"Result: {limited_result}"
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use["id"],
                    "content": limited_result,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return _finalize_after_tool_limit(
        messages=messages,
        model=model,
        tool_call_count=tool_call_count,
    )


def submit_prompt(*, scene_name, prompt, context_bundle, model, context_summary=""):
    global _active_workers
    with _lock:
        _active_workers += 1
    _ensure_timer()

    def worker():
        global _active_workers
        try:
            text = _run_tool_loop(
                scene_name=scene_name,
                prompt=prompt,
                context_bundle=context_bundle,
                model=model,
            )
            _results.put((scene_name, True, text, prompt, context_summary))
        except Exception as exc:
            _results.put((scene_name, False, str(exc), prompt, context_summary))
        finally:
            with _lock:
                _active_workers -= 1

    thread = threading.Thread(target=worker, name="ClaudeBlenderRequest", daemon=True)
    thread.start()


def register():
    pass


def unregister():
    pass
