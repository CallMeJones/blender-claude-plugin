"""Blender background smoke test for Claude live helper tools."""

from __future__ import annotations

import json
import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import tool_dispatcher  # noqa: E402


def _execute(context, name, args):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args))
    assert result.get("ok"), f"{name} failed: {result}"
    return result


def _select_object(context, obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


def main():
    claude_blender.register()
    context = bpy.context
    scene = context.scene
    cube = bpy.data.objects["Cube"]
    _select_object(context, cube)

    initial = {
        "objects": set(bpy.data.objects.keys()),
        "meshes": set(bpy.data.meshes.keys()),
        "materials": set(bpy.data.materials.keys()),
        "cameras": set(bpy.data.cameras.keys()),
        "collections": set(bpy.data.collections.keys()),
        "actions": set(bpy.data.actions.keys()),
        "scene_camera": scene.camera.name if scene.camera else None,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
        "fps": scene.render.fps,
        "cube_location": tuple(cube.location),
        "default_camera_constraints": len(bpy.data.objects["Camera"].constraints),
        "selected": [obj.name for obj in context.selected_objects],
        "active": context.view_layer.objects.active.name if context.view_layer.objects.active else None,
    }

    created = _execute(
        context,
        "create_primitive",
        {
            "primitive_type": "UV_SPHERE",
            "name": "Claude Smoke Sphere",
            "location": [3.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
        },
    )
    sphere = bpy.data.objects[created["object"]]
    _select_object(context, sphere)

    _execute(context, "set_selected_transform", {"location": [3.0, 0.0, 1.0], "scale": [0.5, 0.5, 0.5]})
    _execute(context, "assign_material_to_selected", {"name": "Claude Smoke Blue", "color": [0.1, 0.25, 1.0, 1.0]})
    _execute(
        context,
        "assign_emission_material_to_selected",
        {"name": "Claude Smoke Glow", "color": [0.05, 0.6, 1.0, 1.0], "strength": 2.0},
    )
    _execute(context, "create_collection", {"name": "Claude Smoke Collection"})
    _execute(context, "link_selected_to_collection", {"collection_name": "Claude Smoke Collection"})
    _execute(
        context,
        "add_modifier_to_selected",
        {"modifier_type": "BEVEL", "name": "Claude Smoke Bevel", "amount": 0.05, "segments": 2},
    )
    _execute(context, "set_scene_frame_range", {"frame_start": 1, "frame_end": 80, "current_frame": 1, "fps": 24})
    _execute(
        context,
        "animate_selected_transform",
        {
            "frame_start": 1,
            "frame_end": 40,
            "location_start": [3.0, 0.0, 1.0],
            "location_end": [3.0, 0.0, 3.0],
        },
    )
    assert sphere.animation_data and sphere.animation_data.action

    _select_object(context, bpy.data.objects["Camera"])
    _execute(
        context,
        "add_track_to_constraint",
        {"target_name": "Cube", "name": "Claude Smoke Track To", "track_axis": "TRACK_NEGATIVE_Z", "up_axis": "UP_Y"},
    )
    assert len(bpy.data.objects["Camera"].constraints) == initial["default_camera_constraints"] + 1

    _execute(
        context,
        "create_camera_orbit",
        {
            "target_name": "Cube",
            "frame_start": 1,
            "frame_end": 80,
            "radius": 5.0,
            "height": 2.5,
            "name": "Claude Smoke Orbit Camera",
            "lens": 35.0,
        },
    )

    assert "Claude Smoke Sphere" in bpy.data.objects
    assert scene.camera and scene.camera.name.startswith("Claude Smoke Orbit Camera")
    state = scene.claude_blender
    assert state.pending_preview
    assert state.pending_preview_summary, "Missing pending preview rollback summary"
    assert "rollback snapshot" in state.pending_preview_summary, state.pending_preview_summary

    reverted = _execute(context, "revert_preview", {})
    assert reverted.get("manifest_summary"), reverted
    assert not reverted.get("rollback_warnings"), reverted
    assert not state.pending_preview
    assert not state.pending_preview_summary
    assert state.last_preview_summary, "Missing last preview rollback summary"
    assert "reverted" in state.last_preview_summary, state.last_preview_summary
    assert not state.last_preview_warnings, state.last_preview_warnings

    assert set(bpy.data.objects.keys()) == initial["objects"]
    assert set(bpy.data.meshes.keys()) == initial["meshes"]
    assert set(bpy.data.materials.keys()) == initial["materials"]
    assert set(bpy.data.cameras.keys()) == initial["cameras"]
    assert set(bpy.data.collections.keys()) == initial["collections"]
    assert set(bpy.data.actions.keys()) == initial["actions"]
    assert (scene.camera.name if scene.camera else None) == initial["scene_camera"]
    assert scene.frame_start == initial["frame_start"]
    assert scene.frame_end == initial["frame_end"]
    assert scene.frame_current == initial["frame_current"]
    assert scene.render.fps == initial["fps"]
    assert tuple(cube.location) == initial["cube_location"]
    assert len(bpy.data.objects["Camera"].constraints) == initial["default_camera_constraints"]
    final_selected = [obj.name for obj in context.selected_objects]
    final_active = context.view_layer.objects.active.name if context.view_layer.objects.active else None
    assert final_selected == initial["selected"], {
        "expected_selected": initial["selected"],
        "actual_selected": final_selected,
        "active": final_active,
        "warnings": reverted.get("rollback_warnings"),
    }
    assert final_active == initial["active"], {
        "expected_active": initial["active"],
        "actual_active": final_active,
        "warnings": reverted.get("rollback_warnings"),
    }

    claude_blender.unregister()
    print("smoke_live_helpers: ok")


if __name__ == "__main__":
    main()
