"""Blender background smoke test for animation control and preset helpers."""

from __future__ import annotations

import json
import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import agent_tools, bridge_protocol, context_bundle, live_preview, tool_dispatcher  # noqa: E402


MILESTONE_5_TOOLS = {
    "set_action_interpolation",
    "retime_actions",
    "add_action_cycles",
    "clear_animation",
    "set_animation_preview_range",
    "create_turntable_animation",
    "create_pulse_animation",
    "create_reveal_animation",
    "create_staggered_motion",
}


def _execute(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert result.get("ok"), f"{name} failed: {result}"
    return result


def _select_object(context, obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _snapshot(scene, cube):
    cube_action = cube.animation_data.action if cube.animation_data and cube.animation_data.action else None
    return {
        "objects": set(bpy.data.objects.keys()),
        "meshes": set(bpy.data.meshes.keys()),
        "materials": set(bpy.data.materials.keys()),
        "actions": set(bpy.data.actions.keys()),
        "cube_location": tuple(round(float(value), 6) for value in cube.location),
        "cube_rotation": tuple(round(float(value), 6) for value in cube.rotation_euler),
        "cube_scale": tuple(round(float(value), 6) for value in cube.scale),
        "cube_materials": [slot.material.name if slot.material else None for slot in cube.material_slots],
        "cube_action": cube_action.name if cube_action else None,
        "cube_action_state": _action_state(cube_action) if cube_action else None,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
        "use_preview_range": scene.use_preview_range,
        "frame_preview_start": scene.frame_preview_start,
        "frame_preview_end": scene.frame_preview_end,
        "selected": [obj.name for obj in bpy.context.selected_objects],
        "active": bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
    }


def _action_frames(action):
    frames = []
    for fcurve in live_preview._iter_action_fcurves(action):
        frames.extend(round(float(point.co.x), 4) for point in fcurve.keyframe_points)
    return sorted(set(frames))


def _cycle_modifier_count(action):
    return sum(
        1
        for fcurve in live_preview._iter_action_fcurves(action)
        for modifier in fcurve.modifiers
        if modifier.type == "CYCLES"
    )


def _action_state(action):
    return {
        "frames": _action_frames(action),
        "interpolations": [
            point.interpolation
            for fcurve in live_preview._iter_action_fcurves(action)
            for point in fcurve.keyframe_points
        ],
        "cycle_modifiers": _cycle_modifier_count(action),
    }


def _assert_interpolation(action, interpolation, easing=None):
    for fcurve in live_preview._iter_action_fcurves(action):
        for point in fcurve.keyframe_points:
            assert point.interpolation == interpolation, (action.name, point.interpolation)
            if easing:
                assert point.easing == easing, (action.name, point.easing)


def main():
    claude_blender.register()
    context = bpy.context
    scene = context.scene
    cube = bpy.data.objects["Cube"]
    _select_object(context, cube)
    cube.location = (0.0, 0.0, 0.0)
    cube.keyframe_insert(data_path="location", frame=1)
    cube.location = (0.0, 0.0, 1.0)
    cube.keyframe_insert(data_path="location", frame=20)
    scene.frame_set(1)
    existing_action = cube.animation_data.action
    existing_action.name = "Agent Bridge Existing Animation Action"
    for fcurve in live_preview._iter_action_fcurves(existing_action):
        for point in fcurve.keyframe_points:
            point.interpolation = "LINEAR"
    initial = _snapshot(scene, cube)

    try:
        bundle = context_bundle.build_context_bundle(context)
        assert MILESTONE_5_TOOLS.issubset(set(bundle["available_tools"]))
        tool_names = {tool["name"] for tool in agent_tools.blender_tool_definitions()}
        assert MILESTONE_5_TOOLS.issubset(tool_names)
        assert MILESTONE_5_TOOLS.issubset(set(bridge_protocol.TOOL_CONTRACTS))
        assert MILESTONE_5_TOOLS.issubset(set(tool_dispatcher.TOOL_FUNCTIONS))

        selected, metadata = agent_tools.select_blender_tool_definitions(
            "Create a looping turntable, retime the action, set easing, add cycles, then create pulse reveal and staggered animation.",
            bundle,
        )
        selected_names = {tool["name"] for tool in selected}
        assert MILESTONE_5_TOOLS.issubset(selected_names), metadata

        _execute(
            context,
            "set_action_interpolation",
            {
                "action_names": [existing_action.name],
                "interpolation": "BEZIER",
            },
        )
        _assert_interpolation(existing_action, "BEZIER")
        _execute(context, "retime_actions", {"action_names": [existing_action.name], "frame_start": 3, "frame_end": 63})
        assert _action_frames(existing_action) == [3.0, 63.0]
        _execute(context, "add_action_cycles", {"action_names": [existing_action.name], "replace_existing": True})
        assert _cycle_modifier_count(existing_action) == len(live_preview._iter_action_fcurves(existing_action))

        turntable = _execute(
            context,
            "create_turntable_animation",
            {
                "object_name": "Cube",
                "frame_start": 1,
                "frame_end": 48,
                "axis": "Z",
                "revolutions": 1.0,
                "add_cycles": True,
            },
        )
        turntable_action = bpy.data.actions[turntable["action"]]
        assert _action_frames(turntable_action) == [1.0, 48.0]
        assert _cycle_modifier_count(turntable_action) > 0

        _execute(
            context,
            "set_action_interpolation",
            {
                "action_names": [turntable_action.name],
                "interpolation": "SINE",
                "easing": "EASE_IN_OUT",
            },
        )
        _assert_interpolation(turntable_action, "SINE", "EASE_IN_OUT")

        _execute(context, "retime_actions", {"action_names": [turntable_action.name], "frame_start": 5, "frame_end": 65})
        assert _action_frames(turntable_action) == [5.0, 65.0]

        _execute(
            context,
            "add_action_cycles",
            {
                "action_names": [turntable_action.name],
                "mode_before": "NONE",
                "mode_after": "MIRROR",
                "replace_existing": True,
            },
        )
        assert _cycle_modifier_count(turntable_action) == len(live_preview._iter_action_fcurves(turntable_action))

        _execute(
            context,
            "set_animation_preview_range",
            {"frame_start": 5, "frame_end": 65, "current_frame": 5, "use_preview_range": True},
        )
        assert scene.use_preview_range
        assert scene.frame_preview_start == 5
        assert scene.frame_preview_end == 65
        assert scene.frame_current == 5

        pulse = _execute(
            context,
            "create_pulse_animation",
            {
                "object_name": "Cube",
                "frame_start": 10,
                "frame_end": 40,
                "scale_factor": 1.25,
                "emission_strength_end": 2.0,
            },
        )
        pulse_action = bpy.data.actions[pulse["action"]]
        assert _action_frames(pulse_action) == [10.0, 25.0, 40.0]
        _assert_interpolation(pulse_action, "SINE")
        assert pulse["material_action"] in bpy.data.actions

        reveal = _execute(
            context,
            "create_reveal_animation",
            {
                "object_name": "Cube",
                "frame_start": 1,
                "frame_end": 24,
                "scale_start": 0.2,
                "scale_end": 1.0,
                "fade_material": True,
            },
        )
        assert reveal["action"] in bpy.data.actions
        assert reveal["material_action"] in bpy.data.actions

        created = _execute(
            context,
            "create_primitive",
            {
                "primitive_type": "CUBE",
                "name": "Agent Bridge Stagger Target",
                "location": [2.0, 0.0, 0.0],
                "rotation": [0.0, 0.0, 0.0],
                "scale": [0.5, 0.5, 0.5],
            },
        )
        stagger = _execute(
            context,
            "create_staggered_motion",
            {
                "object_names": ["Cube", created["object"]],
                "frame_start": 12,
                "duration": 10,
                "frame_step": 4,
                "location_delta": [0.0, 0.0, 1.0],
                "interpolation": "BEZIER",
            },
        )
        assert [item["frame_start"] for item in stagger["objects"]] == [12, 16]
        assert [item["frame_end"] for item in stagger["objects"]] == [22, 26]

        cleared = _execute(
            context,
            "clear_animation",
            {"object_names": ["Cube"], "include_material_animation": True},
        )
        assert cleared["cleared"], cleared
        assert cube.animation_data is None

        state = scene.claude_blender
        assert state.pending_preview
        reverted = _execute(context, "revert_preview", {})
        assert not reverted.get("rollback_warnings"), reverted
        assert not state.pending_preview
        final = _snapshot(scene, cube)
        assert final == initial, {"initial": initial, "final": final, "reverted": reverted}
        restored_action = bpy.data.actions[existing_action.name]
        assert _action_state(restored_action) == initial["cube_action_state"], {
            "initial": initial["cube_action_state"],
            "final": _action_state(restored_action),
        }

        print("smoke_animation_controls: ok")
    finally:
        claude_blender.unregister()


if __name__ == "__main__":
    main()
