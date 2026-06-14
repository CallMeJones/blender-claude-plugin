"""Blender background smoke test for common safe editing helper tools."""

from __future__ import annotations

import json
import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import anthropic_client, bridge_protocol, context_bundle, tool_dispatcher  # noqa: E402


SAFE_EDIT_TOOLS = {
    "create_empty",
    "set_object_visibility",
    "set_object_display",
    "duplicate_selected_objects",
    "parent_selected_to_empty",
    "align_selected_objects",
    "distribute_selected_objects",
}


def _execute(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert result.get("ok"), f"{name} failed: {result}"
    return result


def _execute_failure(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert not result.get("ok"), f"{name} unexpectedly succeeded: {result}"
    return result


def _select_objects(context, objects, active):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    context.view_layer.objects.active = active


def _snapshot(context, objects):
    return {
        "objects": set(bpy.data.objects.keys()),
        "meshes": set(bpy.data.meshes.keys()),
        "actions": set(bpy.data.actions.keys()),
        "parents": {obj.name: obj.parent.name if obj.parent else None for obj in objects},
        "locations": {obj.name: tuple(round(float(value), 6) for value in obj.location) for obj in objects},
        "visibility": {
            obj.name: {
                "hide_viewport": bool(obj.hide_viewport),
                "hide_render": bool(obj.hide_render),
                "hide_select": bool(obj.hide_select),
                "hide_get": bool(obj.hide_get()),
            }
            for obj in objects
        },
        "display": {
            obj.name: {
                "display_type": obj.display_type,
                "show_name": bool(obj.show_name),
                "show_wire": bool(getattr(obj, "show_wire", False)),
                "show_in_front": bool(obj.show_in_front),
                "color": tuple(round(float(component), 6) for component in obj.color),
            }
            for obj in objects
        },
        "selected": [obj.name for obj in context.selected_objects],
        "active": context.view_layer.objects.active.name if context.view_layer.objects.active else None,
    }


def main():
    claude_blender.register()
    context = bpy.context
    cube = bpy.data.objects["Cube"]
    cube.location = (-1.0, 0.0, 0.0)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(3.0, 0.0, 2.0))
    second = context.object
    second.name = "Claude Layout Source"
    second.data.name = "Claude Layout Source Mesh"
    _select_objects(context, [cube, second], cube)
    initial = _snapshot(context, [cube, second])

    try:
        bundle = context_bundle.build_context_bundle(context)
        assert SAFE_EDIT_TOOLS.issubset(set(bundle["available_tools"]))
        tool_names = {tool["name"] for tool in anthropic_client.blender_tool_definitions()}
        assert SAFE_EDIT_TOOLS.issubset(tool_names)
        assert SAFE_EDIT_TOOLS.issubset(set(bridge_protocol.TOOL_CONTRACTS))

        _execute_failure(context, "set_object_visibility", {"selected_only": False, "hide_render": True})
        _execute_failure(context, "set_object_display", {"selected_only": False, "show_name": True})

        empty_result = _execute(
            context,
            "create_empty",
            {
                "name": "Claude Layout Marker",
                "location": [0.0, 2.0, 1.0],
                "rotation": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
                "empty_display_type": "CUBE",
                "empty_display_size": 1.2,
            },
        )
        empty = bpy.data.objects[empty_result["object"]]
        assert empty.type == "EMPTY"
        assert empty.empty_display_type == "CUBE"

        _execute(
            context,
            "set_object_display",
            {
                "object_names": [empty.name],
                "selected_only": False,
                "display_type": "WIRE",
                "show_name": True,
                "show_in_front": True,
                "color": [1.0, 0.25, 0.1, 0.5],
                "empty_display_type": "SPHERE",
                "empty_display_size": 2.0,
            },
        )
        assert empty.display_type == "WIRE"
        assert empty.show_name
        assert empty.show_in_front
        assert tuple(round(float(component), 4) for component in empty.color) == (1.0, 0.25, 0.1, 0.5)
        assert empty.empty_display_type == "SPHERE"
        assert round(float(empty.empty_display_size), 4) == 2.0

        _execute(
            context,
            "set_object_visibility",
            {
                "object_names": [empty.name],
                "selected_only": False,
                "hide_viewport": True,
                "hide_render": True,
                "hide_select": True,
            },
        )
        assert empty.hide_viewport
        assert empty.hide_render
        assert empty.hide_select
        assert empty.hide_get()

        _select_objects(context, [cube, second], cube)

        _execute(context, "align_selected_objects", {"axis": "Z", "mode": "VALUE", "value": 1.25})
        assert round(cube.location.z, 4) == 1.25
        assert round(second.location.z, 4) == 1.25

        distributed = _execute(context, "distribute_selected_objects", {"axis": "X", "start": -2.0, "end": 2.0})
        assert distributed["positions"]["Cube"] == -2.0
        assert distributed["positions"]["Claude Layout Source"] == 2.0

        duplicated = _execute(
            context,
            "duplicate_selected_objects",
            {"name_prefix": "Claude Layout Copy ", "offset": [0.0, 2.0, 0.0], "linked_data": False},
        )
        duplicate_objects = [bpy.data.objects[name] for name in duplicated["objects"]]
        assert len(duplicate_objects) == 2
        assert all(obj.data.name in bpy.data.meshes for obj in duplicate_objects)
        assert duplicate_objects[0].data is not cube.data

        parented = _execute(context, "parent_selected_to_empty", {"name": "Claude Layout Parent"})
        empty = bpy.data.objects[parented["empty"]]
        assert empty.type == "EMPTY"
        assert all(obj.parent == empty for obj in duplicate_objects)

        _execute(
            context,
            "set_object_display",
            {
                "object_names": ["Cube"],
                "selected_only": False,
                "display_type": "WIRE",
                "show_name": True,
                "show_wire": True,
                "show_in_front": True,
                "color": [0.2, 0.3, 0.4, 0.5],
            },
        )
        assert cube.display_type == "WIRE"
        assert cube.show_name
        assert cube.show_wire
        assert cube.show_in_front
        assert tuple(round(float(component), 4) for component in cube.color) == (0.2, 0.3, 0.4, 0.5)

        existing_visibility = _execute(
            context,
            "set_object_visibility",
            {
                "object_names": ["Claude Layout Source"],
                "selected_only": False,
                "hide_viewport": True,
                "hide_render": True,
                "hide_select": True,
            },
        )
        assert not existing_visibility.get("warnings"), existing_visibility
        assert second.hide_viewport
        assert second.hide_render
        assert second.hide_select
        assert second.hide_get()

        state = context.scene.claude_blender
        assert state.pending_preview
        assert state.pending_preview_summary

        reverted = _execute(context, "revert_preview", {})
        assert not reverted.get("rollback_warnings"), reverted
        assert not state.pending_preview
        final = _snapshot(context, [cube, second])
        assert final == initial, {"initial": initial, "final": final, "reverted": reverted}

        print("smoke_safe_editing_helpers: ok")
    finally:
        claude_blender.unregister()


if __name__ == "__main__":
    main()
