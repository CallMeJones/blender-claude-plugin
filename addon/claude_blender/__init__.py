"""Claude for Blender extension entrypoint."""

from __future__ import annotations

import importlib

bl_info = {
    "name": "Claude for Blender",
    "author": "Michael",
    "version": (0, 1, 0),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar > Claude",
    "description": "Scene-aware Claude assistant for Blender",
    "category": "3D View",
}

_MODULE_NAMES = (
    "properties",
    "preferences",
    "context_budget",
    "agent_memory",
    "chat_history",
    "context_bundle",
    "context_planner",
    "world_model",
    "audit_log",
    "script_analysis",
    "advanced_helpers",
    "viewport_capture",
    "bridge_protocol",
    "bridge_server",
    "docs_index",
    "anthropic_client",
    "transcript",
    "agent_loop",
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
