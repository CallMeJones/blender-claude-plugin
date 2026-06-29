"""Scene-level state for the Blender Agent Bridge UI."""

from __future__ import annotations

import bpy


class CLAUDEBLENDER_PG_scene_state(bpy.types.PropertyGroup):
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
    preview_manifest_status: bpy.props.StringProperty(
        name="Preview Manifest",
        default="No preview transaction",
    )
    preview_manifest_text_name: bpy.props.StringProperty(
        name="Preview Manifest Text",
        default="Claude Preview Manifest",
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
    pending_script_privileged: bpy.props.BoolProperty(
        name="Privileged Script",
        default=False,
    )
    pending_script_privileged_kind: bpy.props.StringProperty(
        name="Privileged Script Kind",
        default="",
    )
    pending_script_privileged_capabilities: bpy.props.StringProperty(
        name="Privileged Script Capabilities",
        default="",
    )
    pending_script_approval_summary: bpy.props.StringProperty(
        name="Script Approval Summary",
        default="",
    )
    pending_script_declared_paths: bpy.props.StringProperty(
        name="Script Declared Paths",
        default="",
    )
    pending_script_declared_urls: bpy.props.StringProperty(
        name="Script Declared URLs",
        default="",
    )
    pending_script_destructive_actions: bpy.props.StringProperty(
        name="Script Destructive Actions",
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
    bridge_diagnostics_status: bpy.props.StringProperty(
        name="Bridge Diagnostics",
        default="Bridge diagnostics not checked",
    )
    bridge_source_status: bpy.props.StringProperty(
        name="Source Hash",
        default="Source hash not checked",
    )
    bridge_operation_status: bpy.props.StringProperty(
        name="Bridge Operation",
        default="No bridge operation recorded",
    )
    bridge_refresh_hint: bpy.props.StringProperty(
        name="MCP Refresh Hint",
        default="Restart or refresh the MCP client after copying new config.",
    )
    audit_log_status: bpy.props.StringProperty(
        name="Audit Log",
        default="Audit log not checked",
    )
    audit_log_text_name: bpy.props.StringProperty(
        name="Audit Log Text",
        default="Claude Audit Log",
    )
    visual_evidence_status: bpy.props.StringProperty(
        name="Visual Evidence",
        default="Visual evidence not checked",
    )
    visual_evidence_text_name: bpy.props.StringProperty(
        name="Visual Evidence Text",
        default="Claude Visual Evidence",
    )
    visual_evidence_latest_path: bpy.props.StringProperty(
        name="Latest Evidence Path",
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
