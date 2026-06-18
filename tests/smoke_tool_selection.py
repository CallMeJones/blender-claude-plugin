"""Smoke tests for dynamic tool-schema selection."""

from __future__ import annotations

import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import agent_loop, anthropic_client, context_bundle  # noqa: E402


def _names(tools):
    return {tool["name"] for tool in tools}


def main():
    claude_blender.register()
    original_create = anthropic_client.create_message_raw
    try:
        bundle = context_bundle.build_context_bundle(bpy.context)
        full_tools = anthropic_client.blender_tool_definitions()
        full_chars = anthropic_client.estimate_request_chars(messages=[], tools=full_tools)

        simple_tools, simple_meta = anthropic_client.select_blender_tool_definitions(
            "What objects are in my current scene?",
            bundle,
        )
        simple_names = _names(simple_tools)
        assert "inspect_scene" in simple_names
        assert "list_scene_objects" in simple_names
        assert "apply_vehicle_refinement_template" not in simple_names
        assert "apply_product_refinement_template" not in simple_names
        assert "apply_character_refinement_template" not in simple_names
        assert simple_meta["selected_tool_count"] < len(full_tools)
        assert anthropic_client.estimate_request_chars(messages=[], tools=simple_tools) < full_chars

        brief_summary_tools, brief_summary_meta = anthropic_client.select_blender_tool_definitions(
            "Give me a brief summary of the current scene.",
            bundle,
        )
        assert "create_animation_brief" not in _names(brief_summary_tools), brief_summary_meta

        vehicle_tools, vehicle_meta = anthropic_client.select_blender_tool_definitions(
            "Improve this car into a high-poly vehicle with wheels, windows, panel seams, headlights, and smoother bevels.",
            bundle,
        )
        vehicle_names = _names(vehicle_tools)
        for expected in {
            "apply_vehicle_refinement_template",
            "create_wheel_assembly",
            "add_window_materials",
            "add_panel_seams",
            "add_bevel_and_subsurf",
            "shade_smooth_selected",
            "draft_script",
        }:
            assert expected in vehicle_names, (expected, vehicle_meta)
        assert vehicle_meta["schema_chars"] <= anthropic_client.TOOL_SCHEMA_CHAR_BUDGET

        product_tools, product_meta = anthropic_client.select_blender_tool_definitions(
            "Polish this product into a premium catalog studio shot with dimensions and a turntable.",
            bundle,
        )
        product_names = _names(product_tools)
        for expected in {
            "apply_product_refinement_template",
            "create_studio_product_stage",
            "add_dimension_callouts",
            "create_product_turntable_setup",
        }:
            assert expected in product_names, (expected, product_meta)

        character_tools, character_meta = anthropic_client.select_blender_tool_definitions(
            "Turn this body mesh into a toon character blockout with a head, eyes, and guide lines.",
            bundle,
        )
        character_names = _names(character_tools)
        for expected in {
            "apply_character_refinement_template",
            "create_basic_armature",
            "create_curve_path",
        }:
            assert expected in character_names, (expected, character_meta)

        animation_tools, animation_meta = anthropic_client.select_blender_tool_definitions(
            "Create an animation brief and prompt contract before making the cube bounce three times.",
            bundle,
        )
        animation_names = _names(animation_tools)
        assert "plan_animation_workflow" in animation_names, animation_meta
        assert "create_animation_brief" in animation_names, animation_meta
        assert "create_timing_chart" in animation_names, animation_meta
        assert "animate_object_bounce" in animation_names, animation_meta

        blocking_tools, blocking_meta = anthropic_client.select_blender_tool_definitions(
            "Create a timing chart and block key poses for a jump animation.",
            bundle,
        )
        blocking_names = _names(blocking_tools)
        assert "create_timing_chart" in blocking_names, blocking_meta
        assert "block_key_poses" in blocking_names, blocking_meta
        assert "add_breakdown_pose" in blocking_names, blocking_meta
        assert "set_pose_hold" in blocking_names, blocking_meta
        assert "create_motion_arc" in blocking_names, blocking_meta

        principles_tools, principles_meta = anthropic_client.select_blender_tool_definitions(
            "Analyze this jump animation for anticipation, spacing, motion arcs, pose clarity, and settle.",
            bundle,
        )
        principles_names = _names(principles_tools)
        assert "plan_animation_workflow" in principles_names, principles_meta
        assert "get_animation_scene_context" in principles_names, principles_meta
        assert "analyze_animation_principles" in principles_names, principles_meta
        assert "analyze_motion_arcs" in principles_names, principles_meta
        assert "analyze_fcurve_spacing" in principles_names, principles_meta
        assert "analyze_pose_clarity" in principles_names, principles_meta
        assert "sample_animation_state" in principles_names, principles_meta
        assert "analyze_contact_sliding" in principles_names, principles_meta
        assert "analyze_collision_penetration" in principles_names, principles_meta
        assert "analyze_camera_framing" in principles_names, principles_meta
        assert "analyze_motion_physics" in principles_names, principles_meta
        assert "compare_animation_to_brief" in principles_names, principles_meta
        assert "review_playblast_against_brief" in principles_names, principles_meta
        assert "repair_animation_from_findings" in principles_names, principles_meta
        assert "run_animation_repair_loop" in principles_names, principles_meta

        captured_tool_names = []

        def fake_create_message_raw(*, messages, model, tools=None, max_tokens=1024):
            captured_tool_names.extend(tool["name"] for tool in tools or [])
            return {"content": [{"type": "text", "text": "done"}]}

        anthropic_client.create_message_raw = fake_create_message_raw
        text = agent_loop._run_tool_loop(
            scene_name=bpy.context.scene.name,
            prompt="What objects are in my current scene?",
            context_bundle=bundle,
            model="fake-model",
        )
        assert text == "done", text
        assert "apply_vehicle_refinement_template" not in captured_tool_names
        assert "apply_product_refinement_template" not in captured_tool_names
        assert "apply_character_refinement_template" not in captured_tool_names
        assert len(captured_tool_names) < len(full_tools)
        print("smoke_tool_selection: ok")
    finally:
        anthropic_client.create_message_raw = original_create
        claude_blender.unregister()


if __name__ == "__main__":
    main()
