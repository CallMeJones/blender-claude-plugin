"""Blender Agent Bridge extension entrypoint."""

from __future__ import annotations

import importlib

_MODULE_NAMES = (
    "build_info",
    "user_paths",
    "properties",
    "preferences",
    "context_budget",
    "context_bundle",
    "context_planner",
    "world_model",
    "audit_log",
    "script_analysis",
    "animation_brief",
    "animation_analysis",
    "advanced_helpers",
    "viewport_capture",
    "playblast_capture",
    "inspection_render",
    "lab_parity",
    "render_jobs",
    "bridge_protocol",
    "bridge_server",
    "docs_index",
    "agent_tools",
    "transcript",
    "live_preview",
    "script_templates",
    "tool_dispatcher",
    "script_runner",
    "ui",
)

_modules = []


def _load_modules():
    global _modules
    package = __name__
    loaded = []
    for module_name in _MODULE_NAMES:
        full_name = f"{package}.{module_name}"
        module = importlib.import_module(full_name)
        loaded.append(importlib.reload(module))
    _modules = loaded


def register():
    _load_modules()
    for module in _modules:
        register_fn = getattr(module, "register", None)
        if register_fn:
            register_fn()


def unregister():
    for module in reversed(_modules):
        unregister_fn = getattr(module, "unregister", None)
        if unregister_fn:
            try:
                unregister_fn()
            except RuntimeError:
                # Blender may already have unregistered classes during reloads.
                pass
