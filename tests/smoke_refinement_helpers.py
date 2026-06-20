"""Blender background smoke test for model refinement helpers."""

from __future__ import annotations

import json
import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import advanced_helpers, agent_tools, bridge_protocol, context_bundle, tool_dispatcher  # noqa: E402


REFINEMENT_TOOLS = {
    "shade_smooth_selected",
    "add_bevel_and_subsurf",
    "create_wheel_assembly",
    "add_panel_seams",
    "add_window_materials",
    "apply_vehicle_refinement_template",
    "apply_product_refinement_template",
    "apply_character_refinement_template",
    "create_studio_product_stage",
    "add_dimension_callouts",
    "apply_lighting_preset",
    "create_material_palette",
    "create_product_turntable_setup",
    "organize_scene_for_production",
}


def _execute(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert result.get("ok"), f"{name} failed: {result}"
    return result


def _execute_failure(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert not result.get("ok"), f"{name} unexpectedly succeeded: {result}"
    return result


def _select_object(context, obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _select_objects(context, objects, active):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    context.view_layer.objects.active = active


def _snapshot(cube):
    return {
        "objects": set(bpy.data.objects.keys()),
        "meshes": set(bpy.data.meshes.keys()),
        "curves": set(bpy.data.curves.keys()),
        "collections": set(bpy.data.collections.keys()),
        "materials": set(bpy.data.materials.keys()),
        "lights": set(bpy.data.lights.keys()),
        "cameras": set(bpy.data.cameras.keys()),
        "actions": set(bpy.data.actions.keys()),
        "scene_camera": bpy.context.scene.camera.name if bpy.context.scene.camera else None,
        "cube_materials": [slot.material.name if slot.material else None for slot in cube.material_slots],
        "cube_modifiers": [modifier.name for modifier in cube.modifiers],
        "cube_smooth": [bool(poly.use_smooth) for poly in cube.data.polygons],
    }


def main():
    claude_blender.register()
    context = bpy.context
    cube = bpy.data.objects["Cube"]
    _select_object(context, cube)
    initial = _snapshot(cube)
    try:
        bundle = context_bundle.build_context_bundle(context)
        assert REFINEMENT_TOOLS.issubset(set(bundle["available_tools"]))
        full_names = {tool["name"] for tool in agent_tools.blender_tool_definitions()}
        assert REFINEMENT_TOOLS.issubset(full_names)
        assert REFINEMENT_TOOLS.issubset(set(bridge_protocol.TOOL_CONTRACTS))

        bpy.ops.object.select_all(action="DESELECT")
        context.view_layer.objects.active = None
        empty_selection = advanced_helpers._selection_snapshot(context)
        _select_object(context, cube)
        advanced_helpers._restore_selection_snapshot(context, empty_selection)
        assert not context.selected_objects
        assert context.view_layer.objects.active is None
        _select_object(context, cube)

        _execute(context, "shade_smooth_selected", {"add_weighted_normals": True})
        assert all(poly.use_smooth for poly in cube.data.polygons)
        assert cube.modifiers.get("Agent Bridge Weighted Normals")

        _execute(context, "add_bevel_and_subsurf", {"bevel_width": 0.05, "bevel_segments": 3, "subsurf_levels": 1})
        assert cube.modifiers.get("Agent Bridge Detail Bevel")
        assert cube.modifiers.get("Agent Bridge Detail Subdivision")

        wheel = _execute(context, "create_wheel_assembly", {"name": "Agent Bridge Test Wheel", "location": [2.2, -1.2, -0.6], "radius": 0.35})
        assert len(wheel["objects"]) == 2

        seams = _execute(context, "add_panel_seams", {"target_name": "Cube"})
        assert seams["objects"]

        glass = _execute(context, "add_window_materials", {"target_name": "Cube", "create_panels": True})
        assert glass["created_objects"]

        stage = _execute(context, "create_studio_product_stage", {"target_name": "Cube", "stage_name": "Agent Bridge Test Stage"})
        assert stage["created_objects"]
        assert len(stage["lights"]) == 3
        assert stage["camera"]
        assert "studio stage" in stage["expected_changes"], stage

        callouts = _execute(context, "add_dimension_callouts", {"target_name": "Cube", "unit_label": "m"})
        assert {"width", "depth", "height"} == set(callouts["measurements"])
        assert len(callouts["created_objects"]) == 6

        lighting = _execute(context, "apply_lighting_preset", {"target_name": "Cube", "preset": "dramatic_rim"})
        assert len(lighting["lights"]) == 3

        _select_object(context, cube)
        palette = _execute(
            context,
            "create_material_palette",
            {"palette_name": "Agent Bridge Test Palette", "palette": "automotive", "assign_to_selected": True},
        )
        assert len(palette["materials"]) == 5
        assert len(palette["swatches"]) == 5
        assert palette["assigned"][0]["object"] == "Cube"

        turntable = _execute(
            context,
            "create_product_turntable_setup",
            {"target_name": "Cube", "frame_start": 1, "frame_end": 48, "setup_name": "Agent Bridge Test Turntable", "create_stage": False},
        )
        assert turntable["animation"]["action"], turntable
        assert turntable["camera_orbit"]["camera"], turntable

        organized = _execute(context, "organize_scene_for_production", {"collection_prefix": "Agent Bridge Test Production"})
        assert organized["collections"], organized

        _execute(context, "revert_preview", {})
        final = _snapshot(cube)
        assert final == initial, {"initial": initial, "final": final}

        camera = bpy.data.objects["Camera"]
        _select_objects(context, [cube, camera], camera)
        original_stage_helper = advanced_helpers.create_studio_product_stage

        def failing_stage(*_args, **_kwargs):
            raise RuntimeError("synthetic product stage failure")

        advanced_helpers.create_studio_product_stage = failing_stage
        try:
            failure = _execute_failure(
                context,
                "apply_product_refinement_template",
                {"target_name": "Cube", "include_stage": True, "include_callouts": False},
            )
            assert "synthetic product stage failure" in failure["message"], failure
            assert failure["auto_reverted_preview"] is True, failure
            assert failure["auto_revert_message"] == "Preview reverted", failure
            assert failure["auto_revert_manifest"]["status"] == "reverted", failure
        finally:
            advanced_helpers.create_studio_product_stage = original_stage_helper
        assert {obj.name for obj in context.selected_objects} == {"Cube", "Camera"}
        assert context.view_layer.objects.active == camera
        assert context.scene.claude_blender.pending_preview is False
        final = _snapshot(cube)
        assert final == initial, {"initial": initial, "final": final}

        _select_object(context, cube)
        product = _execute(
            context,
            "apply_product_refinement_template",
            {"target_name": "Cube", "style": "premium", "include_stage": True, "include_callouts": True},
        )
        assert product["created_objects"], product
        assert "studio stage" in product["features"], product
        assert "product presentation" in product["expected_changes"], product
        assert cube.modifiers.get("Agent Bridge Detail Bevel")
        _execute(context, "revert_preview", {})
        final = _snapshot(cube)
        assert final == initial, {"initial": initial, "final": final}

        _select_object(context, cube)
        character = _execute(
            context,
            "apply_character_refinement_template",
            {"target_name": "Cube", "character_style": "toon", "detail_level": "medium", "create_guides": True},
        )
        assert any("Character Head" in name for name in character["created_objects"])
        assert "gesture guides" in character["features"], character
        assert "character presentation kit" in character["expected_changes"], character
        _execute(context, "revert_preview", {})
        final = _snapshot(cube)
        assert final == initial, {"initial": initial, "final": final}

        _select_object(context, cube)
        vehicle = _execute(context, "apply_vehicle_refinement_template", {"target_name": "Cube", "detail_level": "medium"})
        assert vehicle["created_objects"]
        assert any("Wheel" in name for name in vehicle["created_objects"])
        assert "vehicle detail kit" in vehicle["expected_changes"], vehicle
        assert cube.modifiers.get("Agent Bridge Detail Bevel")
        _execute(context, "revert_preview", {})
        final = _snapshot(cube)
        assert final == initial, {"initial": initial, "final": final}

        print("smoke_refinement_helpers: ok")
    finally:
        claude_blender.unregister()


if __name__ == "__main__":
    main()
