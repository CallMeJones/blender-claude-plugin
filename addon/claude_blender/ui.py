"""Blender UI panels and operators."""

from __future__ import annotations

import json
import os
import queue
import threading

import bpy

from . import (
    agent_memory,
    bridge_server,
    build_info,
    context_bundle,
    context_planner,
    docs_index,
    live_preview,
    preferences,
    script_runner,
    transcript,
    viewport_capture,
)


_docs_results = queue.Queue()
_docs_timer_registered = False

TRUST_DURATION_SECONDS = {
    "MIN_15": 15 * 60,
    "HOUR_1": 60 * 60,
    "HOUR_4": 4 * 60 * 60,
}

TRUST_DURATION_BUTTON_TEXT = {
    "MIN_15": "Trust 15 Min",
    "HOUR_1": "Trust 1 Hour",
    "HOUR_4": "Trust 4 Hours",
    "SESSION": "Trust Session",
}


def _prefs(context):
    return preferences.get_preferences(context)


def _format_docs_status(status):
    errors = status.get("build_errors") or {}
    if not status.get("full_index_exists") and not status.get("manual_index_exists"):
        message = f"Docs {status['version']}: curated cache only"
    else:
        api_count = int(status.get("full_index_entries", 0) or 0)
        manual_count = int(status.get("manual_index_entries", 0) or 0)
        message = (
            f"Docs {status['version']}: "
            f"API {api_count} pages, Manual {manual_count} pages"
        )
    if errors:
        error_text = "; ".join(f"{name} failed: {detail}" for name, detail in sorted(errors.items()))
        message = f"{message} ({error_text})"
    return message[:1000]


def _format_bytes(size):
    size = int(size or 0)
    if size <= 0:
        return ""
    units = ("B", "KB", "MB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{size} {unit}"
        value /= 1024
    return f"{size} B"


def _draw_wrapped(layout, text, *, width=46, max_lines=4, empty="None"):
    lines = transcript.preview_lines(text or empty, width=width, max_lines=max_lines)
    if not lines:
        lines = [empty]
    for line in lines:
        layout.label(text=line)


def _draw_field(layout, label, text, *, width=44, max_lines=4, empty="None"):
    layout.label(text=f"{label}:")
    _draw_wrapped(layout, text, width=width, max_lines=max_lines, empty=empty)


def _draw_section(layout, title):
    box = layout.box()
    box.label(text=title)
    return box


def _update_screenshot_state(state, bundle):
    visual = bundle.get("visual_context") or {}
    if not visual.get("requested"):
        state.last_screenshot_status = "Viewport toggle is off"
        state.last_screenshot_path = ""
        state.last_screenshot_image_name = ""
        state.last_screenshot_size = 0
        return
    state.last_screenshot_path = str(visual.get("path") or "")
    state.last_screenshot_image_name = str(visual.get("preview_image") or "")
    state.last_screenshot_size = int(visual.get("size_bytes") or 0)
    if visual.get("available"):
        state.last_screenshot_status = "Screenshot captured and attached"
    else:
        state.last_screenshot_status = str(visual.get("note") or "Screenshot unavailable")


def _process_docs_results():
    global _docs_timer_registered
    while True:
        try:
            scene_name, ok, message = _docs_results.get_nowait()
        except queue.Empty:
            break
        scene = bpy.data.scenes.get(scene_name)
        if scene and hasattr(scene, "claude_blender"):
            scene.claude_blender.docs_cache_building = False
            scene.claude_blender.docs_cache_status = message
            scene.claude_blender.status = message if ok else f"Docs error: {message}"
    if _docs_results.empty():
        for scene in bpy.data.scenes:
            if hasattr(scene, "claude_blender") and scene.claude_blender.docs_cache_building:
                return 0.5
        _docs_timer_registered = False
        return None
    return 0.2


def _ensure_docs_timer():
    global _docs_timer_registered
    if not _docs_timer_registered:
        bpy.app.timers.register(_process_docs_results, first_interval=0.2)
        _docs_timer_registered = True


def _update_context_plan_state(state, metadata):
    state.context_plan_chars = int(metadata.get("chars") or 0)
    state.context_plan_tokens = int(metadata.get("estimated_tokens") or 0)
    state.context_plan_status = context_planner.summarize_plan(metadata)
    included = metadata.get("included") or []
    omitted = metadata.get("omitted") or []
    parts = []
    if included:
        parts.append("Included: " + ", ".join(included[:8]))
    if omitted:
        parts.append("Omitted: " + "; ".join(omitted[:3]))
    state.context_plan_items = " | ".join(parts)[:1000]


def _build_context_bundle(context, state, prefs, *, prompt=""):
    bundle = context_bundle.build_context_bundle(
        context,
        include_visual=state.include_screenshot,
        capture_dir=getattr(prefs, "capture_cache_dir", None),
        max_screenshot_bytes=getattr(prefs, "max_screenshot_bytes", None),
    )
    agent_memory.add_to_bundle(bundle, context)
    planned, metadata = context_planner.plan_context_bundle(prompt, bundle)
    _update_context_plan_state(state, metadata)
    return planned


class CLAUDEBLENDER_OT_capture_context(bpy.types.Operator):
    bl_idname = "claude_blender.capture_context"
    bl_label = "Capture Context"
    bl_description = "Capture the current Blender context bundle"

    def execute(self, context):
        state = context.scene.claude_blender
        prefs = _prefs(context)
        bundle = _build_context_bundle(context, state, prefs, prompt="")
        _update_screenshot_state(state, bundle)
        state.last_context_summary = context_bundle.summarize_for_status(bundle)
        state.last_response = (
            "Scene context captured.\n"
            f"{state.last_context_summary}\n"
            "Full context bundle was saved to the transcript text datablock."
        )
        transcript.record_system_message(
            "Captured context bundle:\n"
            f"{json.dumps(context_bundle.public_bundle(bundle), indent=2, sort_keys=True)}"
        )
        state.status = "Context captured"
        return {"FINISHED"}


class CLAUDEBLENDER_OT_commit_preview(bpy.types.Operator):
    bl_idname = "claude_blender.commit_preview"
    bl_label = "Commit"
    bl_description = "Commit the current live preview transaction"

    def execute(self, context):
        result = live_preview.commit(context)
        context.scene.claude_blender.status = result["message"]
        return {"FINISHED"} if result["ok"] else {"CANCELLED"}


class CLAUDEBLENDER_OT_revert_preview(bpy.types.Operator):
    bl_idname = "claude_blender.revert_preview"
    bl_label = "Revert"
    bl_description = "Revert the current live preview transaction"

    def execute(self, context):
        result = live_preview.revert(context)
        context.scene.claude_blender.status = result["message"]
        return {"FINISHED"} if result["ok"] else {"CANCELLED"}


class CLAUDEBLENDER_OT_undo_last(bpy.types.Operator):
    bl_idname = "claude_blender.undo_last"
    bl_label = "Undo Last Change"
    bl_description = "Undo the latest Blender change, reverting pending live previews first"

    def execute(self, context):
        state = context.scene.claude_blender
        transaction = live_preview.current_transaction()
        if transaction and transaction.get("status") == "pending":
            result = live_preview.revert(context)
            state.status = "Preview reverted by Undo" if result["ok"] else result["message"]
            return {"FINISHED"} if result["ok"] else {"CANCELLED"}
        try:
            result = bpy.ops.ed.undo()
        except RuntimeError as exc:
            state.status = f"Undo failed: {exc}"
            return {"CANCELLED"}
        state.pending_preview = False
        state.pending_preview_label = ""
        state.pending_preview_summary = ""
        state.pending_preview_warnings = ""
        live_preview.redraw(context)
        state.status = "Undo complete" if "FINISHED" in result else "Nothing to undo"
        return {"FINISHED"} if "FINISHED" in result else {"CANCELLED"}


class CLAUDEBLENDER_OT_clear_agent_memory(bpy.types.Operator):
    bl_idname = "claude_blender.clear_agent_memory"
    bl_label = "Clear Memory"
    bl_description = "Clear the bridge memory for this Blender scene"

    def execute(self, context):
        result = agent_memory.clear_memory(context.scene)
        context.scene.claude_blender.status = result["message"]
        context.scene.claude_blender.last_response = result["message"]
        return {"FINISHED"}


def _draw_ask_section(layout, state, prefs):
    ask_box = _draw_section(layout, "Bridge")
    bridge_running = bridge_server.is_running()
    _draw_wrapped(ask_box, build_info.diagnostics_summary(), width=46, max_lines=2)
    ask_box.label(text=f"Bridge: {'On' if bridge_running else 'Off'}")
    bridge_row = ask_box.row(align=True)
    if bridge_running:
        bridge_row.operator("claude_blender.stop_bridge", text="Stop Bridge")
    else:
        bridge_row.operator("claude_blender.start_bridge", text="Start Bridge")
    bridge_row.operator("claude_blender.copy_mcp_config", text="Copy MCP")
    trust_snapshot = script_runner.external_script_trust_snapshot(bpy.context, state=state)
    trust_active = trust_snapshot["active"]
    trust_status = trust_snapshot["status"]
    trust_row = ask_box.row(align=True)
    trust_row.prop(state, "external_script_trust_duration", text="")
    trust_preset = str(getattr(state, "external_script_trust_duration", "HOUR_1") or "HOUR_1")
    trust = trust_row.operator(
        "claude_blender.approve_external_script_trust",
        text=TRUST_DURATION_BUTTON_TEXT.get(trust_preset, "Trust"),
        icon="KEYTYPE_KEYFRAME_VEC",
    )
    trust.ttl_seconds = TRUST_DURATION_SECONDS.get(trust_preset, script_runner.EXTERNAL_TRUST_TTL_SECONDS)
    trust.session_trust = trust_preset == "SESSION"
    revoke_row = trust_row.row(align=True)
    revoke_row.enabled = trust_active or trust_snapshot["expired"]
    revoke_row.operator("claude_blender.revoke_external_script_trust", text="Revoke Trust", icon="CANCEL")
    if trust_status != script_runner.NO_EXTERNAL_TRUST_STATUS:
        _draw_field(ask_box, "Script Trust", trust_status, width=44, max_lines=2)

    toggle_row = ask_box.row(align=True)
    toggle_row.prop(state, "include_screenshot", toggle=True)
    toggle_row.prop(state, "live_helpers", toggle=True)
    toggle_row.prop(state, "agent_memory_enabled", toggle=True)

    ask_box.operator("claude_blender.capture_context", text="Capture Context", icon="VIEWZOOM")

    if prefs:
        ask_box.label(text=f"Execution: {prefs.execution_mode.replace('_', ' ').title()}")


def _draw_status_section(layout, state):
    status_box = _draw_section(layout, "Scene Context")
    _draw_field(status_box, "Status", state.status, max_lines=3, empty="Ready")
    if state.last_context_summary:
        _draw_field(status_box, "Context", state.last_context_summary, max_lines=4)
    else:
        status_box.label(text="Context: not captured yet")
    _draw_field(status_box, "Plan", state.context_plan_status, max_lines=3, empty="Context not planned yet")
    if state.context_plan_items:
        _draw_field(status_box, "Items", state.context_plan_items, max_lines=4)


def _draw_memory_section(layout, state):
    memory_box = _draw_section(layout, "Agent Memory")
    memory_box.prop(state, "agent_memory_enabled", toggle=True)
    _draw_wrapped(memory_box, state.agent_memory_status, max_lines=2, empty="No agent memory yet")
    if state.agent_memory_text_name:
        memory_box.label(text=f"Text: {state.agent_memory_text_name}")
    row = memory_box.row(align=True)
    row.enabled = bool(state.agent_memory_text_name)
    row.operator("claude_blender.clear_agent_memory", icon="TRASH")


def _draw_screenshot_section(layout, state):
    screenshot_box = _draw_section(layout, "Viewport Screenshot")
    _draw_wrapped(screenshot_box, state.last_screenshot_status, max_lines=3)
    details = []
    size = _format_bytes(state.last_screenshot_size)
    if state.last_screenshot_image_name:
        details.append(state.last_screenshot_image_name)
    if size:
        details.append(size)
    if state.last_screenshot_path:
        details.append(os.path.basename(state.last_screenshot_path))
    if details:
        _draw_wrapped(screenshot_box, " | ".join(details), max_lines=2)

    row = screenshot_box.row(align=True)
    row.enabled = state.include_screenshot
    row.operator("claude_blender.capture_viewport_preview", text="Capture", icon="IMAGE_DATA")
    open_row = screenshot_box.row(align=True)
    open_row.enabled = bool(state.last_screenshot_path)
    open_row.operator("claude_blender.open_last_screenshot", text="Open", icon="FILE_FOLDER")


def _draw_preview_section(layout, state):
    preview = _draw_section(layout, "Live Changes")
    if state.pending_preview:
        _draw_field(preview, "Pending", state.pending_preview_label or "Live preview", max_lines=3)
        if state.pending_preview_summary:
            _draw_field(preview, "Rollback", state.pending_preview_summary, width=42, max_lines=4)
        if state.pending_preview_warnings:
            _draw_field(preview, "Warnings", state.pending_preview_warnings, width=42, max_lines=4)
        row = preview.row(align=True)
        row.operator("claude_blender.commit_preview", icon="CHECKMARK")
        row.operator("claude_blender.revert_preview", icon="LOOP_BACK")
    else:
        preview.label(text="No pending live changes")
        if state.last_preview_summary:
            _draw_field(preview, "Last Preview", state.last_preview_summary, width=42, max_lines=3)
        if state.last_preview_warnings:
            _draw_field(preview, "Last Warnings", state.last_preview_warnings, width=42, max_lines=4)
    preview.operator("claude_blender.undo_last", text="Undo Last", icon="LOOP_BACK")


def _draw_docs_section(layout, state):
    docs_box = _draw_section(layout, "Docs")
    _draw_wrapped(docs_box, state.docs_cache_status, max_lines=3)
    row = docs_box.row(align=True)
    row.operator("claude_blender.check_docs_cache", text="Check", icon="VIEWZOOM")
    build_row = row.row(align=True)
    build_row.enabled = not state.docs_cache_building
    build = build_row.operator("claude_blender.build_docs_cache", text="Build", icon="FILE_REFRESH")
    build.force = False


def _draw_script_section(layout, state):
    script_box = _draw_section(layout, "Script Approval")
    if state.pending_script:
        _draw_field(script_box, "Status", state.pending_script_status, max_lines=2)
        if state.pending_script_risk:
            _draw_field(script_box, "Risk", state.pending_script_risk, max_lines=2)
        if state.pending_script_text_name:
            script_box.label(text=f"Text: {state.pending_script_text_name}")
        if state.pending_script_issues:
            _draw_field(script_box, "Issues", state.pending_script_issues, width=42, max_lines=4)
        if state.pending_script_warnings:
            _draw_field(script_box, "Warnings", state.pending_script_warnings, width=42, max_lines=4)
        if state.pending_script_intent:
            _draw_field(script_box, "Intent", state.pending_script_intent, width=42, max_lines=3)
        if state.pending_script_expected_changes:
            _draw_field(script_box, "Expected", state.pending_script_expected_changes, width=42, max_lines=4)

        run_row = script_box.row(align=True)
        run_row.enabled = not state.pending_script_blocked
        run_row.operator("claude_blender.run_approved_script", icon="PLAY")
        external_row = script_box.row(align=True)
        external_row.enabled = not state.pending_script_blocked
        external_row.operator("claude_blender.approve_external_script_run", icon="KEYINGSET")
        script_box.operator("claude_blender.reject_script", icon="LOOP_BACK")
        if state.pending_script_external_approval_status != "No external script approval":
            _draw_field(script_box, "External Approval", state.pending_script_external_approval_status, width=42, max_lines=2)
        trust_snapshot = script_runner.external_script_trust_snapshot(bpy.context, state=state)
        if trust_snapshot["active"] or trust_snapshot["expired"]:
            _draw_field(script_box, "Trust Window", trust_snapshot["status"], width=42, max_lines=2)

        if state.pending_script_status == "Script failed" or state.last_script_error_summary:
            if state.last_script_error_summary:
                _draw_field(script_box, "Last Error", state.last_script_error_summary, width=42, max_lines=4)
    else:
        script_box.label(text="No pending script")

    checkpoint = state.last_checkpoint_path or state.last_checkpoint_status
    if checkpoint and checkpoint != "No script checkpoint yet":
        _draw_field(script_box, "Checkpoint", checkpoint, width=42, max_lines=3)
        restore_row = script_box.row(align=True)
        restore_row.enabled = bool(state.last_checkpoint_path)
        restore_row.operator("claude_blender.restore_last_checkpoint", icon="FILE_REFRESH")
    if state.last_checkpoint_restored_path or state.last_checkpoint_restored_status != "No checkpoint restored":
        restored = state.last_checkpoint_restored_path or state.last_checkpoint_restored_status
        _draw_field(script_box, "Restored", restored, width=42, max_lines=2)


def _draw_action_center(layout, state):
    actions = _draw_section(layout, "Action Center")
    has_action = False

    if state.active_tool_name:
        has_action = True
        actions.label(text=f"Running: {state.active_tool_name}")
    elif state.last_tool_name:
        actions.label(text=f"Last tool: {state.last_tool_name}")
    if state.tool_call_count:
        actions.label(text=f"Tool calls this session: {state.tool_call_count}")

    if state.pending_script:
        has_action = True
        actions.label(text=f"Script: {state.pending_script_status}")
        if state.pending_script_risk:
            actions.label(text=f"Risk: {state.pending_script_risk}")
        if state.pending_script_text_name:
            actions.label(text=f"Text: {state.pending_script_text_name}")
        if state.pending_script_intent:
            _draw_field(actions, "Intent", state.pending_script_intent, width=44, max_lines=2)
        if state.pending_script_expected_changes:
            _draw_field(actions, "Expected", state.pending_script_expected_changes, width=44, max_lines=3)
        if state.pending_script_issues:
            _draw_field(actions, "Issues", state.pending_script_issues, width=44, max_lines=3)
        if state.pending_script_warnings:
            _draw_field(actions, "Warnings", state.pending_script_warnings, width=44, max_lines=3)
        row = actions.row(align=True)
        row.enabled = not state.pending_script_blocked
        row.operator("claude_blender.run_approved_script", text="Run", icon="PLAY")
        external_row = actions.row(align=True)
        external_row.enabled = not state.pending_script_blocked
        external_row.operator("claude_blender.approve_external_script_run", text="Approve External", icon="KEYINGSET")
        actions.operator("claude_blender.reject_script", text="Reject", icon="LOOP_BACK")
        if state.pending_script_external_approval_status != "No external script approval":
            _draw_field(actions, "External Approval", state.pending_script_external_approval_status, width=44, max_lines=2)
        trust_snapshot = script_runner.external_script_trust_snapshot(bpy.context, state=state)
        if trust_snapshot["active"] or trust_snapshot["expired"]:
            _draw_field(actions, "Trust Window", trust_snapshot["status"], width=44, max_lines=2)
        if state.pending_script_status == "Script failed" or state.last_script_error_summary:
            if state.last_script_error_summary:
                _draw_field(actions, "Last Error", state.last_script_error_summary, width=44, max_lines=3)

    if state.pending_preview:
        has_action = True
        _draw_field(actions, "Live Preview", state.pending_preview_label or "Pending live changes", max_lines=2)
        if state.pending_preview_summary:
            _draw_field(actions, "Rollback", state.pending_preview_summary, width=44, max_lines=4)
        if state.pending_preview_warnings:
            _draw_field(actions, "Warnings", state.pending_preview_warnings, width=44, max_lines=4)
        row = actions.row(align=True)
        row.operator("claude_blender.commit_preview", text="Commit", icon="CHECKMARK")
        row.operator("claude_blender.revert_preview", text="Revert", icon="LOOP_BACK")
    elif state.last_preview_warnings:
        has_action = True
        _draw_field(actions, "Last Preview Warnings", state.last_preview_warnings, width=44, max_lines=4)
    actions.operator("claude_blender.undo_last", text="Undo Last", icon="LOOP_BACK")

    screenshot_line = state.last_screenshot_status or "No viewport screenshot captured"
    if state.include_screenshot or state.last_screenshot_path:
        has_action = True
        _draw_wrapped(actions, screenshot_line, max_lines=2)
        details = []
        size = _format_bytes(state.last_screenshot_size)
        if state.last_screenshot_image_name:
            details.append(state.last_screenshot_image_name)
        if size:
            details.append(size)
        if state.last_screenshot_path:
            details.append(os.path.basename(state.last_screenshot_path))
        if details:
            _draw_wrapped(actions, " | ".join(details), max_lines=2)
    row = actions.row(align=True)
    row.enabled = state.include_screenshot
    row.operator("claude_blender.capture_viewport_preview", text="Capture", icon="IMAGE_DATA")
    open_row = actions.row(align=True)
    open_row.enabled = bool(state.last_screenshot_path)
    open_row.operator("claude_blender.open_last_screenshot", text="Open Screenshot", icon="FILE_FOLDER")

    _draw_wrapped(actions, state.docs_cache_status, max_lines=2)
    docs_row = actions.row(align=True)
    docs_row.operator("claude_blender.check_docs_cache", text="Check Docs", icon="VIEWZOOM")
    build_row = docs_row.row(align=True)
    build_row.enabled = not state.docs_cache_building
    build = build_row.operator("claude_blender.build_docs_cache", text="Build Docs", icon="FILE_REFRESH")
    build.force = False

    checkpoint = state.last_checkpoint_path or state.last_checkpoint_status
    if checkpoint and checkpoint != "No script checkpoint yet":
        has_action = True
        _draw_field(actions, "Checkpoint", checkpoint, width=44, max_lines=2)
        restore_row = actions.row(align=True)
        restore_row.enabled = bool(state.last_checkpoint_path)
        restore_row.operator("claude_blender.restore_last_checkpoint", text="Restore Checkpoint", icon="FILE_REFRESH")

    if not has_action and not state.active_tool_name:
        actions.label(text="No pending agent actions")


class CLAUDEBLENDER_OT_copy_last_response(bpy.types.Operator):
    bl_idname = "claude_blender.copy_last_response"
    bl_label = "Copy Last Response"
    bl_description = "Copy the latest bridge response/status to the system clipboard"

    def execute(self, context):
        state = context.scene.claude_blender
        context.window_manager.clipboard = state.last_response or ""
        state.status = "Copied latest response"
        return {"FINISHED"}


class CLAUDEBLENDER_OT_run_approved_script(bpy.types.Operator):
    bl_idname = "claude_blender.run_approved_script"
    bl_label = "Run Approved Script"
    bl_description = "Run the pending agent-generated Blender Python script"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        state = context.scene.claude_blender
        prefs = _prefs(context)
        result = script_runner.run_pending_script(
            context,
            checkpoint_enabled=bool(getattr(prefs, "checkpoints_enabled", True)),
            checkpoint_dir=getattr(prefs, "checkpoint_dir", None),
        )
        state.status = result.get("message", "Script finished")
        if result.get("ok"):
            state.last_response = (
                "Approved script executed.\n"
                f"Log: {result.get('log_datablock', script_runner.SCRIPT_LOG_NAME)}\n"
                f"Checkpoint: {state.last_checkpoint_path or state.last_checkpoint_status}"
            )
        else:
            state.last_response = (
                "Approved script did not run.\n"
                f"{result.get('message', 'Unknown script error')}\n"
                f"Details: {result.get('log_datablock', script_runner.SCRIPT_LOG_NAME)}"
            )
        return {"FINISHED"} if result.get("ok") else {"CANCELLED"}


class CLAUDEBLENDER_OT_approve_external_script_run(bpy.types.Operator):
    bl_idname = "claude_blender.approve_external_script_run"
    bl_label = "Approve External Run"
    bl_description = "Issue a one-time token for an external client to run the pending script"
    bl_options = {"REGISTER"}

    def execute(self, context):
        state = context.scene.claude_blender
        result = script_runner.approve_pending_script_for_external_run(context)
        message = result.get("message", "External approval finished")
        if result.get("ok"):
            context.window_manager.clipboard = result.get("approval_token", "")
            state.last_response = (
                "External script run approved.\n"
                "The one-time token was copied to the clipboard and is not stored in bridge logs.\n"
                f"Expires in {result.get('ttl_seconds', script_runner.EXTERNAL_APPROVAL_TTL_SECONDS)} second(s)."
            )
            self.report({"INFO"}, "External run token copied to clipboard")
            return {"FINISHED"}
        state.last_response = f"External script run was not approved.\n{message}"
        self.report({"ERROR"}, message)
        return {"CANCELLED"}


class CLAUDEBLENDER_OT_approve_external_script_trust(bpy.types.Operator):
    bl_idname = "claude_blender.approve_external_script_trust"
    bl_label = "Trust External Scripts"
    bl_description = "Allow external clients to run staged, static-check-passing scripts for the selected time"
    bl_options = {"REGISTER"}

    ttl_seconds: bpy.props.IntProperty(
        name="Seconds",
        default=script_runner.EXTERNAL_TRUST_TTL_SECONDS,
        min=1,
    )
    session_trust: bpy.props.BoolProperty(
        name="Session Trust",
        default=False,
    )

    def execute(self, context):
        state = context.scene.claude_blender
        result = script_runner.approve_external_script_trust_window(
            context,
            ttl_seconds=self.ttl_seconds,
            session=self.session_trust,
        )
        message = result.get("message", "External script trust window finished")
        if result.get("ok"):
            pending_auto_run = None
            if getattr(state, "pending_script", False):
                prefs = _prefs(context)
                pending_auto_run = script_runner.run_externally_approved_script(
                    context,
                    "",
                    checkpoint_enabled=bool(getattr(prefs, "checkpoints_enabled", True)),
                    checkpoint_dir=getattr(prefs, "checkpoint_dir", None),
                )
            if result.get("session"):
                state.last_response = (
                    "External script trust approved for this Blender session.\n"
                    "External clients can run staged scripts without a per-script token until Revoke, reload, file load, or bridge restart."
                )
            else:
                state.last_response = (
                    "External script trust window approved.\n"
                    "External clients can run staged scripts without a per-script token while this window is active.\n"
                    f"Expires in {result.get('ttl_seconds', script_runner.EXTERNAL_TRUST_TTL_SECONDS)} second(s)."
                )
            if pending_auto_run is not None:
                if pending_auto_run.get("ok"):
                    state.last_response += (
                        "\n\nPending script ran automatically under the active trust grant.\n"
                        f"Log: {pending_auto_run.get('log_datablock', script_runner.SCRIPT_LOG_NAME)}\n"
                        f"Checkpoint: {state.last_checkpoint_path or state.last_checkpoint_status}"
                    )
                    self.report({"INFO"}, "Trust approved; pending script ran")
                    return {"FINISHED"}
                else:
                    state.last_response += (
                        "\n\nPending script did not auto-run.\n"
                        f"{pending_auto_run.get('message', 'Unknown script error')}"
                    )
                    self.report({"WARNING"}, "Trust approved; pending script did not run")
                    return {"FINISHED"}
            self.report({"INFO"}, "External script trust window approved")
            return {"FINISHED"}
        state.last_response = f"External script trust window was not approved.\n{message}"
        self.report({"ERROR"}, message)
        return {"CANCELLED"}


class CLAUDEBLENDER_OT_revoke_external_script_trust(bpy.types.Operator):
    bl_idname = "claude_blender.revoke_external_script_trust"
    bl_label = "Revoke External Trust"
    bl_description = "Revoke the active external script trust grant"
    bl_options = {"REGISTER"}

    def execute(self, context):
        state = context.scene.claude_blender
        result = script_runner.revoke_external_script_trust_window(context)
        message = result.get("message", "External script trust window revoked")
        state.last_response = message
        if result.get("ok"):
            self.report({"INFO"}, message)
            return {"FINISHED"}
        self.report({"ERROR"}, message)
        return {"CANCELLED"}


class CLAUDEBLENDER_OT_reject_script(bpy.types.Operator):
    bl_idname = "claude_blender.reject_script"
    bl_label = "Reject Script"
    bl_description = "Clear the pending agent-generated script without running it"

    def execute(self, context):
        state = context.scene.claude_blender
        result = script_runner.reject_pending_script(context)
        state.status = result.get("message", "Pending script rejected")
        state.last_response = state.status
        return {"FINISHED"}


class CLAUDEBLENDER_OT_restore_last_checkpoint(bpy.types.Operator):
    bl_idname = "claude_blender.restore_last_checkpoint"
    bl_label = "Restore Checkpoint"
    bl_description = "Open the last saved script checkpoint blend file"
    bl_options = {"REGISTER"}

    def execute(self, context):
        result = script_runner.restore_checkpoint(context)
        state = getattr(getattr(bpy.context, "scene", None), "claude_blender", None)
        message = result.get("message", "Checkpoint restore finished")
        if state:
            state.last_response = message
        self.report({"INFO"} if result.get("ok") else {"ERROR"}, message)
        return {"FINISHED"} if result.get("ok") else {"CANCELLED"}


class CLAUDEBLENDER_OT_capture_viewport_preview(bpy.types.Operator):
    bl_idname = "claude_blender.capture_viewport_preview"
    bl_label = "Capture Preview"
    bl_description = "Capture the viewport screenshot used when the Viewport toggle is on"

    def execute(self, context):
        state = context.scene.claude_blender
        if not state.include_screenshot:
            state.last_screenshot_status = "Viewport toggle is off"
            state.status = state.last_screenshot_status
            return {"CANCELLED"}
        prefs = _prefs(context)
        metadata, _attachments = viewport_capture.capture_viewport(
            context,
            capture_dir=getattr(prefs, "capture_cache_dir", None),
            max_bytes=getattr(prefs, "max_screenshot_bytes", viewport_capture.DEFAULT_MAX_BYTES),
        )
        _update_screenshot_state(state, {"visual_context": metadata})
        state.status = state.last_screenshot_status
        return {"FINISHED"} if metadata.get("available") else {"CANCELLED"}


class CLAUDEBLENDER_OT_open_last_screenshot(bpy.types.Operator):
    bl_idname = "claude_blender.open_last_screenshot"
    bl_label = "Open Screenshot"
    bl_description = "Open the last captured viewport screenshot"

    def execute(self, context):
        state = context.scene.claude_blender
        if not state.last_screenshot_path:
            state.status = "No screenshot path available"
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=state.last_screenshot_path)
        state.status = "Opened screenshot"
        return {"FINISHED"}


class CLAUDEBLENDER_OT_check_docs_cache(bpy.types.Operator):
    bl_idname = "claude_blender.check_docs_cache"
    bl_label = "Check"
    bl_description = "Check local Blender Python docs cache status"

    def execute(self, context):
        state = context.scene.claude_blender
        prefs = _prefs(context)
        status = docs_index.docs_cache_status(cache_dir=getattr(prefs, "docs_cache_dir", None))
        state.docs_cache_status = _format_docs_status(status)
        state.status = state.docs_cache_status
        return {"FINISHED"}


class CLAUDEBLENDER_OT_build_docs_cache(bpy.types.Operator):
    bl_idname = "claude_blender.build_docs_cache"
    bl_label = "Build Full Docs Cache"
    bl_description = "Download and index the official Blender Python API and Manual docs for this Blender version"

    force: bpy.props.BoolProperty(
        name="Force Rebuild",
        default=False,
    )

    def execute(self, context):
        state = context.scene.claude_blender
        if state.docs_cache_building:
            state.status = "Docs cache build already running"
            return {"CANCELLED"}
        prefs = _prefs(context)
        cache_dir = getattr(prefs, "docs_cache_dir", None)
        version = docs_index.blender_docs_version()
        scene_name = context.scene.name
        force = bool(self.force)
        state.docs_cache_building = True
        state.docs_cache_status = f"Docs {version}: building..."
        state.status = state.docs_cache_status
        _ensure_docs_timer()

        def worker():
            try:
                status = docs_index.build_full_docs_cache(
                    cache_dir=cache_dir,
                    version=version,
                    force=force,
                )
                _docs_results.put((scene_name, True, _format_docs_status(status)))
            except Exception as exc:
                _docs_results.put((scene_name, False, f"{type(exc).__name__}: {exc}"))

        threading.Thread(target=worker, name="BlenderAgentBridgeDocsCache", daemon=True).start()
        return {"FINISHED"}


class CLAUDEBLENDER_OT_start_bridge(bpy.types.Operator):
    bl_idname = "claude_blender.start_bridge"
    bl_label = "Start Bridge"
    bl_description = "Start the localhost JSON bridge for external MCP clients"
    bl_options = {"REGISTER"}

    def execute(self, context):
        prefs = _prefs(context)
        result = bridge_server.start_bridge(
            port=getattr(prefs, "bridge_port", bridge_server.DEFAULT_PORT),
            auth_token=getattr(prefs, "bridge_auth_token", ""),
        )
        state = context.scene.claude_blender
        state.bridge_running = bool(result.get("ok"))
        state.bridge_url = str(result.get("url") or "")
        state.bridge_status = str(result.get("message") or "")
        state.status = state.bridge_status
        return {"FINISHED"} if result.get("ok") else {"CANCELLED"}


class CLAUDEBLENDER_OT_stop_bridge(bpy.types.Operator):
    bl_idname = "claude_blender.stop_bridge"
    bl_label = "Stop Bridge"
    bl_description = "Stop the localhost JSON bridge"
    bl_options = {"REGISTER"}

    def execute(self, context):
        result = bridge_server.stop_bridge()
        state = context.scene.claude_blender
        state.bridge_running = False
        state.bridge_url = ""
        state.bridge_status = str(result.get("message") or "Bridge stopped")
        state.status = state.bridge_status
        return {"FINISHED"}


class CLAUDEBLENDER_OT_copy_mcp_config(bpy.types.Operator):
    bl_idname = "claude_blender.copy_mcp_config"
    bl_label = "Copy MCP Config"
    bl_description = "Copy a JSON MCP server config for external MCP clients"
    bl_options = {"REGISTER"}

    def execute(self, context):
        prefs = _prefs(context)
        url = context.scene.claude_blender.bridge_url or f"http://127.0.0.1:{getattr(prefs, 'bridge_port', bridge_server.DEFAULT_PORT)}"
        token = getattr(prefs, "bridge_auth_token", "")
        config = build_info.mcp_config(url, token=token)
        context.window_manager.clipboard = json.dumps(config, indent=2)
        context.scene.claude_blender.status = (
            f"Copied MCP config v{build_info.MCP_CONFIG_VERSION} for add-on {build_info.ADDON_VERSION}"
        )
        return {"FINISHED"}


class CLAUDEBLENDER_PT_sidebar(bpy.types.Panel):
    bl_idname = "CLAUDEBLENDER_PT_sidebar"
    bl_label = "Agent Bridge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Agent Bridge"

    def draw(self, context):
        layout = self.layout
        state = context.scene.claude_blender
        prefs = _prefs(context)

        _draw_ask_section(layout, state, prefs)
        _draw_action_center(layout, state)
        _draw_status_section(layout, state)
        _draw_memory_section(layout, state)


classes = (
    CLAUDEBLENDER_OT_capture_context,
    CLAUDEBLENDER_OT_commit_preview,
    CLAUDEBLENDER_OT_revert_preview,
    CLAUDEBLENDER_OT_undo_last,
    CLAUDEBLENDER_OT_clear_agent_memory,
    CLAUDEBLENDER_OT_copy_last_response,
    CLAUDEBLENDER_OT_run_approved_script,
    CLAUDEBLENDER_OT_approve_external_script_run,
    CLAUDEBLENDER_OT_approve_external_script_trust,
    CLAUDEBLENDER_OT_revoke_external_script_trust,
    CLAUDEBLENDER_OT_reject_script,
    CLAUDEBLENDER_OT_restore_last_checkpoint,
    CLAUDEBLENDER_OT_capture_viewport_preview,
    CLAUDEBLENDER_OT_open_last_screenshot,
    CLAUDEBLENDER_OT_check_docs_cache,
    CLAUDEBLENDER_OT_build_docs_cache,
    CLAUDEBLENDER_OT_start_bridge,
    CLAUDEBLENDER_OT_stop_bridge,
    CLAUDEBLENDER_OT_copy_mcp_config,
    CLAUDEBLENDER_PT_sidebar,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
