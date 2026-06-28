"""Blender-background smoke test for dispatcher, bridge, catalog, and contract inventory."""

from __future__ import annotations

import os
import sys

import bpy  # noqa: F401


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import agent_tools, bridge_protocol, bridge_server, tool_dispatcher  # noqa: E402


CATALOG_HIDDEN_TOOLS = {"run_approved_script"}


def main():
    claude_blender.register()
    try:
        catalog_names = {tool["name"] for tool in agent_tools.blender_tool_definitions()}
        dispatcher_names = set(tool_dispatcher.TOOL_FUNCTIONS)
        bridge_names = {tool["name"] for tool in bridge_server._tool_definitions()}
        contract_names = set(bridge_protocol.TOOL_CONTRACTS)

        missing_dispatcher = catalog_names - dispatcher_names
        assert not missing_dispatcher, sorted(missing_dispatcher)
        missing_bridge = catalog_names - bridge_names
        assert not missing_bridge, sorted(missing_bridge)
        missing_contracts = (catalog_names | CATALOG_HIDDEN_TOOLS) - contract_names
        assert not missing_contracts, sorted(missing_contracts)

        assert CATALOG_HIDDEN_TOOLS.issubset(bridge_names), bridge_names
        assert CATALOG_HIDDEN_TOOLS.issubset(dispatcher_names), dispatcher_names
        assert not CATALOG_HIDDEN_TOOLS.intersection(catalog_names), catalog_names

        for tool_name in ("create_procedural_object_kit", "create_directed_animation_shot"):
            assert tool_name in catalog_names, tool_name
            assert tool_name in dispatcher_names, tool_name
            assert tool_name in bridge_names, tool_name
            assert bridge_protocol.normalized_tool_contract(tool_name)["requires_live_preview"] is True

        print("smoke_full_tool_inventory: ok")
    finally:
        claude_blender.unregister()


if __name__ == "__main__":
    main()
