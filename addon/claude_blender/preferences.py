"""Add-on preferences for Blender Agent Bridge."""

from __future__ import annotations

import os

import bpy

from . import build_info


def _default_cache_dir():
    return os.path.join(os.path.expanduser("~"), ".claude_blender", "docs_cache")


def _default_capture_dir():
    return os.path.join(os.path.expanduser("~"), ".claude_blender", "captures")


def _default_checkpoint_dir():
    return os.path.join(os.path.expanduser("~"), ".claude_blender", "checkpoints")


class CLAUDEBLENDER_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    execution_mode: bpy.props.EnumProperty(
        name="Execution",
        description="Default execution behavior",
        items=(
            ("LIVE_HELPERS", "Live Helpers", "Safe helper tools apply immediately with revert support"),
            ("APPROVAL_REQUIRED", "Approval Required", "Generated Python requires explicit approval"),
            ("SUGGEST_ONLY", "Suggest Only", "External agents can advise and draft, but cannot mutate the scene"),
        ),
        default="LIVE_HELPERS",
    )
    screenshot_default: bpy.props.BoolProperty(
        name="Screenshot Toggle Default",
        description="Default state for viewport screenshot inclusion",
        default=False,
    )
    local_docs_first: bpy.props.BoolProperty(
        name="Local Docs First",
        description="Use cached/local Blender docs before online lookup",
        default=True,
    )
    docs_cache_dir: bpy.props.StringProperty(
        name="Docs Cache",
        description="Directory for cached Blender documentation snippets",
        subtype="DIR_PATH",
        default=_default_cache_dir(),
    )
    capture_cache_dir: bpy.props.StringProperty(
        name="Capture Cache",
        description="Optional custom base directory for viewport screenshots. Blank or default uses project-local captures when possible.",
        subtype="DIR_PATH",
        default=_default_capture_dir(),
    )
    checkpoint_dir: bpy.props.StringProperty(
        name="Checkpoint Directory",
        description="Directory for timestamped blend backups before approved scripts run",
        subtype="DIR_PATH",
        default=_default_checkpoint_dir(),
    )
    max_screenshot_bytes: bpy.props.IntProperty(
        name="Max Screenshot Bytes",
        description="Maximum PNG screenshot size to attach to an API request",
        default=5 * 1024 * 1024,
        min=256 * 1024,
        soft_max=10 * 1024 * 1024,
    )
    checkpoints_enabled: bpy.props.BoolProperty(
        name="Checkpoints",
        description="Save blend checkpoints before risky changes",
        default=True,
    )
    bridge_port: bpy.props.IntProperty(
        name="Bridge Port",
        description="Localhost HTTP bridge port for external MCP access",
        default=8765,
        min=1024,
        max=65535,
    )
    bridge_auth_token: bpy.props.StringProperty(
        name="Bridge Token",
        description="Optional bearer token required by the localhost bridge. Leave empty for no token.",
        subtype="PASSWORD",
        default="",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text=build_info.diagnostics_summary())
        layout.label(text=f"Add-on path: {build_info.addon_root()}")
        layout.separator()
        layout.prop(self, "execution_mode")
        layout.prop(self, "screenshot_default")
        layout.prop(self, "local_docs_first")
        layout.prop(self, "docs_cache_dir")
        layout.prop(self, "capture_cache_dir")
        layout.prop(self, "checkpoint_dir")
        layout.prop(self, "max_screenshot_bytes")
        layout.prop(self, "checkpoints_enabled")
        layout.separator()
        layout.label(text="External Bridge / MCP")
        layout.prop(self, "bridge_port")
        layout.prop(self, "bridge_auth_token")


def get_preferences(context):
    addon = context.preferences.addons.get(__package__)
    if addon is None:
        return None
    return addon.preferences


classes = (
    CLAUDEBLENDER_AP_preferences,
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
