"""Pure-Python smoke test for tool catalog and bridge contract consistency."""

from __future__ import annotations

import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import agent_tools, bridge_protocol  # noqa: E402


EXTERNAL_ONLY_TOOLS = {"run_approved_script"}


def main():
    catalog_names = {tool["name"] for tool in agent_tools.blender_tool_definitions()}
    contract_names = set(bridge_protocol.TOOL_CONTRACTS)
    missing_contracts = catalog_names - contract_names
    assert not missing_contracts, sorted(missing_contracts)
    for tool_name in EXTERNAL_ONLY_TOOLS:
        assert tool_name in contract_names, tool_name
        assert tool_name not in catalog_names, tool_name
    for tool_name in ("create_procedural_object_kit", "create_directed_animation_shot"):
        assert tool_name in catalog_names, tool_name
        contract = bridge_protocol.normalized_tool_contract(tool_name)
        assert contract["mutates_scene"] is True, contract
        assert contract["requires_live_preview"] is True, contract
        assert contract["input_schema"].get("additionalProperties") is False, contract
    print("smoke_tool_contract_inventory: ok")


if __name__ == "__main__":
    main()
