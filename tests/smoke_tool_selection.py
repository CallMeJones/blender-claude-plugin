"""Smoke tests for dynamic tool-schema selection."""

from __future__ import annotations

import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import agent_tools, context_bundle  # noqa: E402


def _names(tools):
    return {tool["name"] for tool in tools}


def main():
    claude_blender.register()
    try:
        bundle = context_bundle.build_context_bundle(bpy.context)
        full_tools = agent_tools.blender_tool_definitions()
        full_chars = agent_tools.estimate_request_chars(messages=[], tools=full_tools)

        simple_tools, simple_meta = agent_tools.select_blender_tool_definitions(
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
        assert agent_tools.estimate_request_chars(messages=[], tools=simple_tools) < full_chars

        brief_summary_tools, brief_summary_meta = agent_tools.select_blender_tool_definitions(
            "Give me a brief summary of the current scene.",
            bundle,
        )
        assert "create_animation_brief" not in _names(brief_summary_tools), brief_summary_meta

        vehicle_tools, vehicle_meta = agent_tools.select_blender_tool_definitions(
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
        }:
            assert expected in vehicle_names, (expected, vehicle_meta)
        assert "draft_script" not in vehicle_names, vehicle_meta
        assert vehicle_meta["schema_chars"] <= agent_tools.TOOL_SCHEMA_CHAR_BUDGET

        script_tools, script_meta = agent_tools.select_blender_tool_definitions(
            "Draft a Python script to build a custom procedural rig helper.",
            bundle,
        )
        assert "draft_script" in _names(script_tools), script_meta

        helper_script_tools, helper_script_meta = agent_tools.select_blender_tool_definitions(
            "Write a Python script to move the selected cube up and make it red.",
            bundle,
        )
        helper_script_names = _names(helper_script_tools)
        assert "set_selected_location_delta" in helper_script_names, helper_script_meta
        assert "assign_material_to_selected" in helper_script_names, helper_script_meta
        assert "draft_script" in helper_script_names, helper_script_meta

        asset_script_tools, asset_script_meta = agent_tools.select_blender_tool_definitions(
            "Write a Python script to download and import a Poly Haven sunset HDRI.",
            bundle,
        )
        asset_script_names = _names(asset_script_tools)
        assert "start_external_asset_download" in asset_script_names, asset_script_meta
        assert "start_external_asset_import_job" in asset_script_names, asset_script_meta
        assert "draft_script" not in asset_script_names, asset_script_meta
        assert "draft_privileged_script" in asset_script_names, asset_script_meta

        custom_asset_script_tools, custom_asset_script_meta = agent_tools.select_blender_tool_definitions(
            "Write a custom Python script to download and import a Poly Haven sunset HDRI.",
            bundle,
        )
        custom_asset_script_names = _names(custom_asset_script_tools)
        assert "start_external_asset_download" in custom_asset_script_names, custom_asset_script_meta
        assert "draft_script" not in custom_asset_script_names, custom_asset_script_meta
        assert "draft_privileged_script" in custom_asset_script_names, custom_asset_script_meta

        project_file_script_tools, project_file_script_meta = agent_tools.select_blender_tool_definitions(
            "Write a custom Python script to save this project as a new .blend file.",
            bundle,
        )
        project_file_script_names = _names(project_file_script_tools)
        assert "save_blend_file" in project_file_script_names, project_file_script_meta
        assert "draft_script" not in project_file_script_names, project_file_script_meta
        assert "draft_privileged_script" in project_file_script_names, project_file_script_meta

        product_tools, product_meta = agent_tools.select_blender_tool_definitions(
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

        character_tools, character_meta = agent_tools.select_blender_tool_definitions(
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

        animation_tools, animation_meta = agent_tools.select_blender_tool_definitions(
            "Create an animation brief and prompt contract before making the cube bounce three times.",
            bundle,
        )
        animation_names = _names(animation_tools)
        assert "plan_animation_workflow" in animation_names, animation_meta
        assert "run_animation_workflow" in animation_names, animation_meta
        assert "run_animation_task" in animation_names, animation_meta
        assert "create_animation_brief" in animation_names, animation_meta
        assert "create_timing_chart" in animation_names, animation_meta
        assert "animate_object_bounce" in animation_names, animation_meta
        assert "create_progressive_bounce_animation" in animation_names, animation_meta
        assert "draft_script" not in animation_names, animation_meta

        blocking_tools, blocking_meta = agent_tools.select_blender_tool_definitions(
            "Create a timing chart and block key poses for a jump animation.",
            bundle,
        )
        blocking_names = _names(blocking_tools)
        assert "create_timing_chart" in blocking_names, blocking_meta
        assert "block_key_poses" in blocking_names, blocking_meta
        assert "add_breakdown_pose" in blocking_names, blocking_meta
        assert "set_pose_hold" in blocking_names, blocking_meta
        assert "create_motion_arc" in blocking_names, blocking_meta

        principles_tools, principles_meta = agent_tools.select_blender_tool_definitions(
            "Analyze this jump animation for anticipation, spacing, motion arcs, pose clarity, and settle.",
            bundle,
        )
        principles_names = _names(principles_tools)
        assert "plan_animation_workflow" in principles_names, principles_meta
        assert "run_animation_workflow" in principles_names, principles_meta
        assert "run_animation_task" in principles_names, principles_meta
        assert "get_animation_scene_context" in principles_names, principles_meta
        assert "analyze_animation_principles" in principles_names, principles_meta
        assert "analyze_motion_arcs" in principles_names, principles_meta
        assert "analyze_fcurve_spacing" in principles_names, principles_meta
        assert "analyze_pose_clarity" in principles_names, principles_meta
        assert "sample_animation_state" in principles_names, principles_meta
        assert "analyze_contact_sliding" in principles_names, principles_meta
        assert "analyze_collision_penetration" in principles_names, principles_meta
        assert "analyze_center_of_mass" in principles_names, principles_meta
        assert "analyze_camera_framing" in principles_names, principles_meta
        assert "analyze_motion_physics" in principles_names, principles_meta
        assert "compare_animation_to_brief" in principles_names, principles_meta
        assert "review_playblast_against_brief" in principles_names, principles_meta
        assert "review_inspection_renders_against_brief" in principles_names, principles_meta
        assert "repair_animation_from_findings" in principles_names, principles_meta
        assert "run_animation_repair_loop" in principles_names, principles_meta
        assert "create_progressive_bounce_animation" in principles_names, principles_meta

        simulation_tools, simulation_meta = agent_tools.select_blender_tool_definitions(
            "Inspect the rigid body simulation cache and physics bake before repairing this animation.",
            bundle,
        )
        simulation_names = _names(simulation_tools)
        assert "get_simulation_details" in simulation_names, simulation_meta
        assert "inspect_simulation_bake" in simulation_names, simulation_meta
        assert "stage_persistent_simulation_bake" in simulation_names, simulation_meta

        bake_tools, bake_meta = agent_tools.select_blender_tool_definitions(
            "Bake the persistent rigid body point cache after inspecting the physics simulation.",
            bundle,
        )
        bake_names = _names(bake_tools)
        assert "inspect_simulation_bake" in bake_names, bake_meta
        assert "stage_persistent_simulation_bake" in bake_names, bake_meta

        rig_repair_tools, rig_repair_meta = agent_tools.select_blender_tool_definitions(
            "Review the character rig pose clarity, inspect controls, and hold a keyed armature control pose.",
            bundle,
        )
        rig_repair_names = _names(rig_repair_tools)
        assert "get_animation_scene_context" in rig_repair_names, rig_repair_meta
        assert "get_rigging_details" in rig_repair_names, rig_repair_meta
        assert "set_rig_pose_hold" in rig_repair_names, rig_repair_meta
        assert "apply_rig_pose_from_action" in rig_repair_names, rig_repair_meta
        assert "offset_rig_limb_controls" in rig_repair_names, rig_repair_meta

        inspection_render_tools, inspection_render_meta = agent_tools.select_blender_tool_definitions(
            "Render close-up underside views to inspect landing gear and open bays before repair.",
            bundle,
        )
        inspection_render_names = _names(inspection_render_tools)
        assert "capture_object_inspection_renders" in inspection_render_names, inspection_render_meta

        advanced_tools, advanced_meta = agent_tools.select_blender_tool_definitions(
            "Plan the helper path for advanced 3D, 2D storyboard, animation, simulation, and compositor work.",
            bundle,
        )
        advanced_names = _names(advanced_tools)
        assert "plan_advanced_scene_workflow" in advanced_names, advanced_meta
        assert "get_2d_animation_details" in advanced_names, advanced_meta
        assert "get_render_camera_compositor_details" in advanced_names, advanced_meta

        storyboard_tools, storyboard_meta = agent_tools.select_blender_tool_definitions(
            "Create a 2D storyboard animatic with panels, cutout layers, and a camera move.",
            bundle,
        )
        storyboard_names = _names(storyboard_tools)
        for expected in {
            "plan_advanced_scene_workflow",
            "get_2d_animation_details",
            "create_storyboard_panels",
            "create_2d_cutout_layer",
            "create_camera_dolly_animation",
        }:
            assert expected in storyboard_names, (expected, storyboard_meta)
        assert "draft_script" not in storyboard_names, storyboard_meta

        storyboard_script_tools, storyboard_script_meta = agent_tools.select_blender_tool_definitions(
            "Write a Python script to create a storyboard animatic with 2D panels.",
            bundle,
        )
        storyboard_script_names = _names(storyboard_script_tools)
        assert "create_storyboard_panels" in storyboard_script_names, storyboard_script_meta
        assert "draft_script" in storyboard_script_names, storyboard_script_meta

        procedural_tools, procedural_meta = agent_tools.select_blender_tool_definitions(
            "Make this an advanced 3D procedural hard-surface array stack with bevels and weighted normals.",
            bundle,
        )
        procedural_names = _names(procedural_tools)
        assert "apply_procedural_array_stack" in procedural_names, procedural_meta
        assert "get_geometry_nodes_details" in procedural_names, procedural_meta

        cloth_tools, cloth_meta = agent_tools.select_blender_tool_definitions(
            "Add cloth simulation setup and inspect the physics cache before any bake.",
            bundle,
        )
        cloth_names = _names(cloth_tools)
        assert "add_cloth_simulation_to_selected" in cloth_names, cloth_meta
        assert "inspect_simulation_bake" in cloth_names, cloth_meta

        dolly_tools, dolly_meta = agent_tools.select_blender_tool_definitions(
            "Create a dolly shot camera animation with lens keyframes and playblast review.",
            bundle,
        )
        dolly_names = _names(dolly_tools)
        assert "create_camera_dolly_animation" in dolly_names, dolly_meta
        assert "capture_animation_playblast" in dolly_names, dolly_meta

        request_tools = agent_tools.blender_tool_definitions_for_request(
            "What objects are in my current scene?",
            bundle,
        )
        request_tool_names = _names(request_tools)
        assert "apply_vehicle_refinement_template" not in request_tool_names
        assert "apply_product_refinement_template" not in request_tool_names
        assert "apply_character_refinement_template" not in request_tool_names
        assert len(request_tool_names) < len(full_tools)
        print("smoke_tool_selection: ok")
    finally:
        claude_blender.unregister()


if __name__ == "__main__":
    main()
