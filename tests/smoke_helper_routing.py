"""Smoke tests for helper-first script routing metadata."""

from __future__ import annotations

import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

from claude_blender import agent_tools, bridge_protocol, helper_routing  # noqa: E402


def _known_tool_names():
    return {tool["name"] for tool in agent_tools.blender_tool_definitions()} | set(bridge_protocol.TOOL_CONTRACTS)


def main():
    known_tools = _known_tool_names()
    missing_groups = helper_routing.HELPER_FIRST_SCRIPT_GROUPS - set(agent_tools._TOOL_GROUPS)
    assert not missing_groups, missing_groups
    for group in helper_routing.HELPER_FIRST_SCRIPT_GROUPS:
        assert agent_tools._TOOL_GROUPS[group], group

    rules = list(helper_routing.iter_helper_first_script_rules())
    assert rules, "expected helper-first script rules"

    codes = set()
    for rule in rules:
        code = str(rule.get("code") or "")
        assert code and code not in codes, rule
        codes.add(code)
        assert rule.get("message"), rule
        assert rule.get("terms"), rule
        recommended_tools = list(rule.get("recommended_tools") or [])
        assert recommended_tools, rule
        for tool_name in recommended_tools:
            assert tool_name not in {"draft_script", "run_approved_script"}, (code, tool_name)
            assert tool_name in known_tools, (code, tool_name)

    helper_prompt = "Write a Python script to move the selected cube up and make it red."
    assert helper_routing.should_include_draft_script(helper_prompt, ["basic_edit", "materials"])

    custom_prompt = "Draft a custom procedural material node network that helpers cannot express."
    assert helper_routing.should_include_draft_script(custom_prompt, ["materials"])
    assert not helper_routing.should_include_draft_script(
        "Draft a custom Python script to download and import a Poly Haven sunset HDRI.",
        ["external_assets"],
    )
    assert helper_routing.should_include_privileged_script(
        "Draft a custom Python script to download and import a Poly Haven sunset HDRI.",
        ["external_assets"],
    )
    assert not helper_routing.should_include_draft_script(
        "Draft a custom Python script to save this blend file.",
        ["project_files"],
    )
    assert helper_routing.should_include_privileged_script(
        "Draft a custom Python script to save this blend file.",
        ["project_files"],
    )
    assert not helper_routing.should_include_privileged_script(custom_prompt, ["materials"])

    material_guard = helper_routing.helper_first_script_advisory(
        "Make the selected cube red with bpy.data.materials and a material script."
    )
    assert material_guard, material_guard
    assert material_guard["code"] == "material_helper_required", material_guard
    assert not material_guard["blocked"], material_guard
    assert "create_shader_material" in material_guard["recommended_tools"], material_guard
    assert helper_routing.helper_first_script_guard(
        "Make the selected cube red with bpy.data.materials and a material script."
    ) is None

    storyboard_guard = helper_routing.helper_first_script_advisory(
        "Write a Python script to create a storyboard animatic with 2D panels."
    )
    assert storyboard_guard["code"] == "two_d_storyboard_helper_required", storyboard_guard
    assert not storyboard_guard["blocked"], storyboard_guard
    assert "create_storyboard_panels" in storyboard_guard["recommended_tools"], storyboard_guard

    procedural_guard = helper_routing.helper_first_script_advisory(
        "Write Python for a non-destructive procedural array stack with bevels."
    )
    assert procedural_guard["code"] == "procedural_3d_helper_required", procedural_guard
    assert not procedural_guard["blocked"], procedural_guard
    assert "apply_procedural_array_stack" in procedural_guard["recommended_tools"], procedural_guard

    cloth_guard = helper_routing.helper_first_script_advisory(
        "Draft a script to add cloth simulation setup to the selected mesh."
    )
    assert cloth_guard["code"] == "simulation_setup_helper_required", cloth_guard
    assert not cloth_guard["blocked"], cloth_guard
    assert "add_cloth_simulation_to_selected" in cloth_guard["recommended_tools"], cloth_guard

    asset_guard = helper_routing.helper_first_script_guard(
        "Write a Python script to download and import a Poly Haven sunset HDRI."
    )
    assert asset_guard["blocked"], asset_guard
    assert asset_guard["code"] == "external_asset_workflow_required", asset_guard

    custom_asset_guard = helper_routing.helper_first_script_guard(
        "Write a custom Python script to download and import a Poly Haven sunset HDRI."
    )
    assert custom_asset_guard["blocked"], custom_asset_guard
    assert custom_asset_guard["code"] == "external_asset_workflow_required", custom_asset_guard

    bake_guard = helper_routing.helper_first_script_guard(
        "Draft Python to run bpy.ops.ptcache.bake_all and free_bake_all."
    )
    assert bake_guard["blocked"], bake_guard
    assert bake_guard["code"] == "simulation_helper_required", bake_guard

    assert helper_routing.helper_first_script_guard(custom_prompt) is None
    print("smoke_helper_routing: ok")


if __name__ == "__main__":
    main()
