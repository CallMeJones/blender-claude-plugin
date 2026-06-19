"""Smoke tests for agent targeting and scene-control tools."""

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


def main():
    claude_blender.register()
    try:
        context = bpy.context
        scene = context.scene
        cube = bpy.data.objects["Cube"]
        camera = bpy.data.objects["Camera"]

        objects = _execute(context, "list_scene_objects", {"max_objects": 10})
        names = {item["name"] for item in objects["objects"]}
        assert {"Cube", "Camera"}.issubset(names), objects

        selected = _execute(
            context,
            "select_objects",
            {"object_names": ["Cube"], "active_object_name": "Cube"},
        )
        assert selected["active_object"] == "Cube", selected
        assert context.active_object == cube
        assert cube.select_get()

        current = _execute(context, "set_current_frame", {"frame": 12})
        assert current["frame_current"] == 12, current
        assert scene.frame_current == 12

        extra_camera_data = bpy.data.cameras.new("Agent Bridge Tool Camera Data")
        extra_camera = bpy.data.objects.new("Agent Bridge Tool Camera", extra_camera_data)
        scene.collection.objects.link(extra_camera)
        original_camera = scene.camera.name if scene.camera else None
        changed = _execute(context, "set_active_camera", {"camera_name": extra_camera.name})
        assert changed["camera"] == extra_camera.name, changed
        assert scene.camera == extra_camera
        reverted = _execute(context, "revert_preview", {})
        assert reverted["ok"], reverted
        assert (scene.camera.name if scene.camera else None) == original_camera

        bpy.data.objects.remove(extra_camera, do_unlink=True)
        bpy.data.cameras.remove(extra_camera_data)
        claude_blender.unregister()
        print("smoke_agent_tools: ok")
    finally:
        if "Agent Bridge Tool Camera" in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects["Agent Bridge Tool Camera"], do_unlink=True)
        if "Agent Bridge Tool Camera Data" in bpy.data.cameras:
            bpy.data.cameras.remove(bpy.data.cameras["Agent Bridge Tool Camera Data"])


if __name__ == "__main__":
    main()
