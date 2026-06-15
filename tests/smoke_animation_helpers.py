"""Blender background smoke test for animation workflow helper tools."""

from __future__ import annotations

import json
import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import anthropic_client, bridge_protocol, context_bundle, live_preview, tool_dispatcher  # noqa: E402


ANIMATION_TOOLS = {
    "create_animation_brief",
    "animate_object_bounce",
    "animate_material_property",
    "animate_light_property",
    "create_follow_path_animation",
}


def _execute(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert result.get("ok"), f"{name} failed: {result}"
    return result


def _select_object(context, obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _snapshot(scene, cube, camera, light):
    return {
        "objects": set(bpy.data.objects.keys()),
        "curves": set(bpy.data.curves.keys()),
        "materials": set(bpy.data.materials.keys()),
        "actions": set(bpy.data.actions.keys()),
        "cube_location": tuple(round(float(value), 6) for value in cube.location),
        "cube_materials": [slot.material.name if slot.material else None for slot in cube.material_slots],
        "camera_constraints": [constraint.name for constraint in camera.constraints],
        "camera_action": camera.animation_data.action.name if camera.animation_data and camera.animation_data.action else None,
        "light_energy": round(float(light.data.energy), 6),
        "light_action": light.data.animation_data.action.name if light.data.animation_data and light.data.animation_data.action else None,
        "scene_camera": scene.camera.name if scene.camera else None,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
    }


def _action_keyframes(action):
    frames = []
    for fcurve in live_preview._iter_action_fcurves(action):
        frames.extend(round(point.co.x, 4) for point in fcurve.keyframe_points)
    return sorted(set(frames))


def main():
    claude_blender.register()
    context = bpy.context
    scene = context.scene
    cube = bpy.data.objects["Cube"]
    camera = bpy.data.objects["Camera"]
    light = bpy.data.objects["Light"]
    _select_object(context, cube)
    initial = _snapshot(scene, cube, camera, light)

    try:
        bundle = context_bundle.build_context_bundle(context)
        assert ANIMATION_TOOLS.issubset(set(bundle["available_tools"]))
        tool_names = {tool["name"] for tool in anthropic_client.blender_tool_definitions()}
        assert ANIMATION_TOOLS.issubset(tool_names)
        contract_names = set(bridge_protocol.TOOL_CONTRACTS)
        assert ANIMATION_TOOLS.issubset(contract_names)

        brief = _execute(
            context,
            "create_animation_brief",
            {
                "prompt": "Make the cube bounce three times and get smaller each bounce.",
                "subject_names": ["Cube"],
                "frame_start": 1,
                "frame_end": 72,
                "success_criteria": ["End smaller than it started."],
            },
        )
        contract = brief["brief"]
        assert contract["contract_id"].startswith("anim-"), contract
        assert contract["subjects"][0]["name"] == "Cube", contract
        assert contract["action"] == "bounce", contract
        assert contract["timing"]["requested_count"] == 3, contract
        assert "scale decreases over the animation" in contract["secondary_actions"], contract
        assert contract["ready_for_generation"] is True, contract
        assert contract["validation_plan"]["check_contact_physics"] is True, contract
        assert any("exactly 3" in item for item in contract["success_criteria"]), contract
        assert not scene.claude_blender.pending_preview

        no_count = _execute(
            context,
            "create_animation_brief",
            {"prompt": "Make one cube bounce.", "subject_names": ["Cube"], "frame_start": 1, "frame_end": 24},
        )["brief"]
        assert no_count["action"] == "bounce", no_count
        assert no_count["timing"]["requested_count"] is None, no_count

        inflected = _execute(
            context,
            "create_animation_brief",
            {"prompt": "The cube bounces twice.", "subject_names": ["Cube"], "frame_start": 1, "frame_end": 24},
        )["brief"]
        assert inflected["action"] == "bounce", inflected
        assert inflected["timing"]["requested_count"] == 2, inflected

        bounce = _execute(
            context,
            "animate_object_bounce",
            {
                "object_name": "Cube",
                "frame_start": 1,
                "frame_end": 48,
                "axis": "Z",
                "distance": 2.5,
                "cycles": 2,
            },
        )
        cube_action = bpy.data.actions[bounce["action"]]
        assert _action_keyframes(cube_action) == [float(frame) for frame in bounce["frames"]]

        material_result = _execute(
            context,
            "animate_material_property",
            {
                "object_name": "Cube",
                "property_name": "emission_strength",
                "frame_start": 1,
                "frame_end": 48,
                "value_start": 0.0,
                "value_end": 3.0,
            },
        )
        material = bpy.data.materials[material_result["material"]]
        assert material.node_tree.animation_data and material.node_tree.animation_data.action
        assert material.node_tree.animation_data.action.name == material_result["action"]

        light_result = _execute(
            context,
            "animate_light_property",
            {
                "light_name": "Light",
                "property_name": "energy",
                "frame_start": 1,
                "frame_end": 48,
                "value_start": 100.0,
                "value_end": 700.0,
            },
        )
        assert light.data.animation_data and light.data.animation_data.action
        assert light.data.animation_data.action.name == light_result["action"]

        follow = _execute(
            context,
            "create_follow_path_animation",
            {
                "object_name": "Camera",
                "path_name": "Claude Camera Motion Path",
                "path_points": [[-4.0, -4.0, 3.0], [0.0, -6.0, 4.0], [4.0, -4.0, 3.0]],
                "frame_start": 1,
                "frame_end": 48,
                "constraint_name": "Claude Camera Follow Path",
            },
        )
        assert follow["path"] in bpy.data.objects
        assert camera.constraints.get("Claude Camera Follow Path")
        assert camera.animation_data and camera.animation_data.action

        details = _execute(context, "get_animation_details", {"object_names": ["Cube", "Camera", "Light"], "max_actions": 12})
        objects_by_name = {item["name"]: item for item in details["objects"]}
        assert objects_by_name["Cube"]["object_animation"]["action"] == bounce["action"], details
        assert objects_by_name["Cube"]["materials"][0]["node_tree_animation"]["action"] == material_result["action"], details
        assert any(constraint["type"] == "FOLLOW_PATH" for constraint in objects_by_name["Camera"]["constraints"]), details
        assert objects_by_name["Light"]["data_animation"]["action"] == light_result["action"], details
        assert any(
            owner.get("kind") == "material_node_tree" and owner.get("material") == material_result["material"]
            for action in details["actions"]
            for owner in action["owners"]
        ), details
        assert any(
            owner.get("kind") == "object" and owner.get("name") == "Camera"
            for action in details["actions"]
            for owner in action["owners"]
        ), details
        assert any(
            owner.get("kind") == "object_data" and owner.get("object") == "Light"
            for action in details["actions"]
            for owner in action["owners"]
        ), details

        state = scene.claude_blender
        assert state.pending_preview
        assert state.pending_preview_summary

        reverted = _execute(context, "revert_preview", {})
        assert not reverted.get("rollback_warnings"), reverted
        assert not state.pending_preview
        final = _snapshot(scene, cube, camera, light)
        assert final == initial, {"initial": initial, "final": final, "reverted": reverted}

        print("smoke_animation_helpers: ok")
    finally:
        claude_blender.unregister()


if __name__ == "__main__":
    main()
