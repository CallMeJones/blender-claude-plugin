"""Scene-level state for the Blender Agent Bridge UI."""

from __future__ import annotations

import bpy


class CLAUDEBLENDER_PG_scene_state(bpy.types.PropertyGroup):
    prompt: bpy.props.StringProperty(
        name="Prompt",
        description="Instruction to send to Claude",
        default="",
    )
    include_screenshot: bpy.props.BoolProperty(
        name="Viewport",
        description="Include viewport screenshot context when available",
        default=False,
    )
    live_helpers: bpy.props.BoolProperty(
        name="Live Helpers",
        description="Apply safe helper changes immediately with revert support",
        default=True,
    )
    agent_memory_enabled: bpy.props.BoolProperty(
        name="Memory",
        description="Send compact running agent memory with each prompt",
        default=True,
    )
    agent_memory_status: bpy.props.StringProperty(
        name="Memory Status",
        default="No agent memory yet",
    )
    agent_memory_text_name: bpy.props.StringProperty(
        name="Memory Text",
        default="Claude Agent Memory",
    )
    chat_history_status: bpy.props.StringProperty(
        name="Chat Status",
        default="No chat history yet",
    )
    chat_history_text_name: bpy.props.StringProperty(
        name="Chat Text",
        default="Claude Chat History",
    )
    chat_history_turn_count: bpy.props.IntProperty(
        name="Chat Messages",
        default=0,
    )
    chat_history_limit: bpy.props.IntProperty(
        name="Visible Messages",
        description="Number of recent chat messages to show in the sidebar",
        default=8,
        min=2,
        max=20,
    )
    status: bpy.props.StringProperty(
        name="Status",
        default="Ready",
    )
    last_response: bpy.props.StringProperty(
        name="Last Response",
        default="",
    )
    last_user_prompt: bpy.props.StringProperty(
        name="Last User Prompt",
        default="",
    )
    last_effective_prompt: bpy.props.StringProperty(
        name="Last Effective Prompt",
        default="",
    )
    last_context_summary: bpy.props.StringProperty(
        name="Last Context",
        default="",
    )
    context_plan_status: bpy.props.StringProperty(
        name="Context Plan",
        default="Context not planned yet",
    )
    context_plan_chars: bpy.props.IntProperty(
        name="Context Chars",
        default=0,
    )
    context_plan_tokens: bpy.props.IntProperty(
        name="Context Tokens",
        default=0,
    )
    context_plan_items: bpy.props.StringProperty(
        name="Context Items",
        default="",
    )
    active_tool_name: bpy.props.StringProperty(
        name="Active Tool",
        default="",
    )
    last_tool_name: bpy.props.StringProperty(
        name="Last Tool",
        default="",
    )
    tool_call_count: bpy.props.IntProperty(
        name="Tool Calls",
        default=0,
    )
    pending_preview: bpy.props.BoolProperty(
        name="Pending Preview",
        default=False,
    )
    pending_preview_label: bpy.props.StringProperty(
        name="Preview",
        default="",
    )
    pending_preview_summary: bpy.props.StringProperty(
        name="Preview Rollback Summary",
        default="",
    )
    pending_preview_warnings: bpy.props.StringProperty(
        name="Preview Rollback Warnings",
        default="",
    )
    last_preview_summary: bpy.props.StringProperty(
        name="Last Preview Summary",
        default="",
    )
    last_preview_warnings: bpy.props.StringProperty(
        name="Last Preview Warnings",
        default="",
    )
    pending_script: bpy.props.BoolProperty(
        name="Pending Script",
        default=False,
    )
    pending_script_blocked: bpy.props.BoolProperty(
        name="Script Blocked",
        default=False,
    )
    pending_script_text_name: bpy.props.StringProperty(
        name="Script Text",
        default="",
    )
    pending_script_intent: bpy.props.StringProperty(
        name="Script Intent",
        default="",
    )
    pending_script_expected_changes: bpy.props.StringProperty(
        name="Expected Changes",
        default="",
    )
    pending_script_risk: bpy.props.StringProperty(
        name="Script Risk",
        default="",
    )
    pending_script_status: bpy.props.StringProperty(
        name="Script Status",
        default="No pending script",
    )
    pending_script_issues: bpy.props.StringProperty(
        name="Script Issues",
        default="",
    )
    pending_script_warnings: bpy.props.StringProperty(
        name="Script Warnings",
        default="",
    )
    pending_script_external_approval_status: bpy.props.StringProperty(
        name="External Script Approval Status",
        default="No external script approval",
    )
    pending_script_external_approval_hash: bpy.props.StringProperty(
        name="External Script Approval Hash",
        default="",
    )
    pending_script_external_approval_text_name: bpy.props.StringProperty(
        name="External Script Approval Text",
        default="",
    )
    pending_script_external_approval_source_hash: bpy.props.StringProperty(
        name="External Script Approval Source Hash",
        default="",
    )
    pending_script_external_approval_expires_at: bpy.props.StringProperty(
        name="External Script Approval Expires",
        default="",
    )
    external_script_trust_status: bpy.props.StringProperty(
        name="External Script Trust Status",
        default="No external script trust window",
    )
    external_script_trust_expires_at: bpy.props.StringProperty(
        name="External Script Trust Expires",
        default="",
    )
    external_script_trust_duration: bpy.props.EnumProperty(
        name="Trust Duration",
        description="How long external clients may run staged scripts without a per-script token",
        items=[
            ("MIN_15", "15 Min", "Trust external staged-script runs for 15 minutes"),
            ("HOUR_1", "1 Hour", "Trust external staged-script runs for 1 hour"),
            ("HOUR_4", "4 Hours", "Trust external staged-script runs for 4 hours"),
            ("SESSION", "Session", "Trust external staged-script runs until revoke, reload, or bridge restart"),
        ],
        default="HOUR_1",
    )
    last_script_error_summary: bpy.props.StringProperty(
        name="Last Script Error",
        default="",
    )
    last_script_log_name: bpy.props.StringProperty(
        name="Last Script Log",
        default="",
    )
    last_checkpoint_status: bpy.props.StringProperty(
        name="Checkpoint Status",
        default="No script checkpoint yet",
    )
    last_checkpoint_path: bpy.props.StringProperty(
        name="Checkpoint Path",
        default="",
    )
    last_checkpoint_restored_status: bpy.props.StringProperty(
        name="Checkpoint Restore Status",
        default="No checkpoint restored",
    )
    last_checkpoint_restored_path: bpy.props.StringProperty(
        name="Restored Checkpoint Path",
        default="",
    )
    docs_cache_status: bpy.props.StringProperty(
        name="Docs Cache",
        default="Docs cache not checked",
    )
    docs_cache_building: bpy.props.BoolProperty(
        name="Docs Cache Building",
        default=False,
    )
    last_screenshot_status: bpy.props.StringProperty(
        name="Screenshot Status",
        default="No viewport screenshot captured",
    )
    last_screenshot_path: bpy.props.StringProperty(
        name="Screenshot Path",
        default="",
    )
    last_screenshot_image_name: bpy.props.StringProperty(
        name="Screenshot Image",
        default="",
    )
    last_screenshot_size: bpy.props.IntProperty(
        name="Screenshot Bytes",
        default=0,
    )
    bridge_running: bpy.props.BoolProperty(
        name="Bridge Running",
        default=False,
    )
    bridge_status: bpy.props.StringProperty(
        name="Bridge Status",
        default="Bridge stopped",
    )
    bridge_url: bpy.props.StringProperty(
        name="Bridge URL",
        default="",
    )


classes = (
    CLAUDEBLENDER_PG_scene_state,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.claude_blender = bpy.props.PointerProperty(type=CLAUDEBLENDER_PG_scene_state)


def unregister():
    if hasattr(bpy.types.Scene, "claude_blender"):
        del bpy.types.Scene.claude_blender
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
