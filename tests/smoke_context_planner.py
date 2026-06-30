"""Smoke tests for token-aware context planning and local retrieval tools."""

from __future__ import annotations

import json
import os
import sys

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import context_bundle, context_planner, tool_dispatcher  # noqa: E402


def _ensure_cube_selected():
    cube = bpy.data.objects.get("Cube")
    if cube is None:
        bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
        cube = bpy.context.object
        cube.name = "Cube"
    bpy.ops.object.select_all(action="DESELECT")
    cube.select_set(True)
    bpy.context.view_layer.objects.active = cube
    return cube


def _json_tool(name, args):
    return json.loads(tool_dispatcher.execute_tool(bpy.context, name, args))


def main():
    claude_blender.register()
    try:
        cube = _ensure_cube_selected()

        material = bpy.data.materials.get("Planner Test Blue") or bpy.data.materials.new("Planner Test Blue")
        material.diffuse_color = (0.1, 0.25, 1.0, 1.0)
        cube.data.materials.clear()
        cube.data.materials.append(material)

        cube.location = (0, 0, 0)
        cube.keyframe_insert(data_path="location", frame=1)
        cube.location = (0, 0, 3)
        cube.keyframe_insert(data_path="location", frame=24)

        bundle = context_bundle.build_context_bundle(bpy.context, include_visual=False)
        bundle["_attachments"] = {
            "viewport_image": {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": "a" * 50_000,
                },
            }
        }
        bundle["selection_summary"]["selected_objects"] = [
            {
                "name": f"Object_{index}",
                "type": "MESH",
                "location": {"x": index, "y": 0, "z": 0},
                "custom_properties": "x" * 3_000,
            }
            for index in range(40)
        ]

        planned, metadata = context_planner.plan_context_bundle(
            "Animate the selected object and make the material glow blue.",
            bundle,
            max_context_chars=18_000,
        )
        assert planned.get("_attachments") == bundle["_attachments"]
        assert "context_plan" in planned
        assert metadata["chars"] < 25_000, metadata
        assert metadata["estimated_tokens"] == context_planner.estimate_tokens(metadata["chars"])
        assert "agent_memory" not in planned
        selected = planned["selection_summary"]["selected_objects"]
        assert len(selected) <= 17, selected
        assert any(
            "_truncated_selected_objects" in item or "_truncated_items" in item
            for item in selected
        ), selected
        assert "animation_summary" in planned or any("animation_summary" in item for item in metadata["omitted"])
        assert "material_summary" in planned or any("material_summary" in item for item in metadata["omitted"])

        object_details = _json_tool("get_object_details", {"object_names": ["Cube"]})
        assert object_details["ok"] is True
        assert object_details["objects"][0]["name"] == "Cube"
        assert "mesh_data_layers" in object_details["objects"][0]

        animation_details = _json_tool("get_animation_details", {"object_names": ["Cube"]})
        assert animation_details["ok"] is True
        assert animation_details["actions"], animation_details
        assert animation_details["actions"][0]["fcurves"], animation_details

        material_details = _json_tool("get_material_node_details", {"material_names": ["Planner Test Blue"]})
        assert material_details["ok"] is True
        assert material_details["materials"][0]["name"] == "Planner Test Blue"
        assert "nodes" in material_details["materials"][0]

        print("smoke_context_planner: ok")
    finally:
        claude_blender.unregister()


if __name__ == "__main__":
    main()
