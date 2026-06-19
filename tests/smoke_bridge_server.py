"""Blender background smoke test for the localhost bridge server."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import build_info, bridge_server, inspection_render, lab_parity, playblast_capture, viewport_capture  # noqa: E402


def _request_with_pump(fn, timeout=10):
    box = {"result": None, "error": None}

    def worker():
        try:
            box["result"] = fn()
        except Exception as exc:
            box["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    deadline = time.time() + timeout
    while thread.is_alive() and time.time() < deadline:
        bridge_server._process_requests()
        time.sleep(0.02)
    thread.join(timeout=0.1)
    if thread.is_alive():
        raise TimeoutError("HTTP bridge request did not finish")
    if box["error"]:
        raise box["error"]
    return box["result"]


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    claude_blender.register()
    try:
        result = bridge_server.start_bridge(port=0)
        assert result["ok"], result
        base = result["url"]
        assert base.startswith("http://127.0.0.1:"), base

        tools = _get(base + "/tools")
        names = {tool["name"] for tool in tools["tools"]}
        assert "list_scene_objects" in names, names
        assert "capture_viewport" in names, names
        assert "apply_vehicle_refinement_template" in names, names
        assert "apply_product_refinement_template" in names, names
        assert "apply_character_refinement_template" in names, names
        assert "create_studio_product_stage" in names, names
        assert "add_dimension_callouts" in names, names
        assert "apply_lighting_preset" in names, names
        assert "create_material_palette" in names, names
        assert "create_product_turntable_setup" in names, names
        assert "organize_scene_for_production" in names, names
        assert "capture_animation_playblast" in names, names
        assert "capture_object_inspection_renders" in names, names
        assert "get_blend_file_diagnostics" in names, names
        assert "get_workspace_layout" in names, names
        assert "render_scene_thumbnail" in names, names
        assert "start_render_job" in names, names
        assert "get_render_job_status" in names, names
        assert "cancel_render_job" in names, names
        assert "assemble_render_job_video" in names, names
        assert "validate_render_job_output" in names, names
        assert "jump_to_workspace" in names, names
        assert "focus_object_in_viewport" in names, names

        health = _request_with_pump(lambda: _get(base + "/health"))
        assert health["ok"], health
        assert health["scene"] == bpy.context.scene.name
        assert health["addon_source_hash"] == build_info.source_tree_hash(), health
        assert "Source " in health["build_diagnostics"], health

        objects = _request_with_pump(
            lambda: _post(base + "/tool", {"name": "list_scene_objects", "arguments": {"max_objects": 5}})
        )
        assert objects["ok"], objects
        assert objects["result"]["ok"], objects
        assert any(item["name"] == "Cube" for item in objects["result"]["objects"]), objects

        resources = _get(base + "/resources")
        uris = {item["uri"] for item in resources["resources"]}
        assert "blender://scene/context" in uris, resources
        assert "blender://captures/latest" in uris, resources
        assert "blender://captures/latest/metadata" in uris, resources
        assert "blender://playblasts/latest/metadata" in uris, resources
        assert "blender://inspection-renders/latest/metadata" in uris, resources
        assert "blender://render-thumbnails/latest" in uris, resources
        assert "blender://render-thumbnails/latest/metadata" in uris, resources
        assert "blender://render-jobs/latest/metadata" in uris, resources
        resource_url = base + "/resource?" + urllib.parse.urlencode({"uri": "blender://scene/status"})
        resource = _request_with_pump(lambda: _get(resource_url))
        assert resource["ok"], resource
        status_resource = json.loads(resource["text"])
        assert status_resource["scene"] == bpy.context.scene.name
        assert status_resource["addon_source_hash"] == build_info.source_tree_hash(), status_resource

        capture_dir = tempfile.mkdtemp(prefix="claude-blender-captures-")
        capture_path = os.path.join(capture_dir, "viewport-test.png")
        image = bpy.data.images.new("Agent Bridge Test Capture", width=1, height=1)
        image.pixels[:] = [1.0, 1.0, 1.0, 1.0]
        image.filepath_raw = capture_path
        image.file_format = "PNG"
        image.save()
        bpy.data.images.remove(image)
        latest = viewport_capture.latest_capture_resource(capture_dir=capture_dir)
        assert latest["mimeType"] == "image/png", latest
        assert latest["blob"], latest
        assert latest["captureId"], latest
        exact = viewport_capture.capture_resource(latest["captureId"], capture_dir=capture_dir)
        assert exact["blob"] == latest["blob"], exact
        metadata = viewport_capture.latest_capture_metadata(capture_dir=capture_dir)
        assert metadata["resource_uri"] == "blender://captures/latest", metadata
        assert metadata["exact_resource_uri"].endswith(latest["captureId"]), metadata
        exact_metadata = viewport_capture.capture_metadata(latest["captureId"], capture_dir=capture_dir)
        assert exact_metadata["resource_uri"].endswith(latest["captureId"]), exact_metadata
        playblast_dir = os.path.join(capture_dir, "playblasts", "test-playblast")
        os.makedirs(playblast_dir, exist_ok=True)
        frame_path = os.path.join(playblast_dir, "frame-0001.png")
        shutil.copyfile(capture_path, frame_path)
        playblast_metadata = {
            "ok": True,
            "available": True,
            "playblast_id": "test-playblast",
            "created_at": time.time(),
            "metadata_uri": "blender://playblasts/test-playblast/metadata",
            "latest_metadata_uri": "blender://playblasts/latest/metadata",
            "playblast_dir": playblast_dir,
            "frames": [
                {
                    "frame": 1,
                    "available": True,
                    "path": frame_path,
                    "resource_uri": "blender://playblasts/test-playblast/frames/1",
                    "size_bytes": os.path.getsize(frame_path),
                    "width": 1,
                    "height": 1,
                }
            ],
        }
        with open(os.path.join(playblast_dir, "metadata.json"), "w", encoding="utf-8") as handle:
            json.dump(playblast_metadata, handle)
        latest_playblast = playblast_capture.latest_playblast_metadata(capture_dir=capture_dir)
        assert latest_playblast["playblast_id"] == "test-playblast", latest_playblast
        frame_resource = playblast_capture.playblast_frame_resource("test-playblast", 1, capture_dir=capture_dir)
        assert frame_resource["mimeType"] == "image/png", frame_resource
        assert frame_resource["blob"], frame_resource
        render_dir = os.path.join(capture_dir, "inspection-renders", "test-render")
        os.makedirs(render_dir, exist_ok=True)
        render_path = os.path.join(render_dir, "cube-front_below.png")
        shutil.copyfile(capture_path, render_path)
        inspection_metadata = {
            "ok": True,
            "available": True,
            "render_id": "test-render",
            "created_at": time.time(),
            "metadata_uri": "blender://inspection-renders/test-render/metadata",
            "latest_metadata_uri": "blender://inspection-renders/latest/metadata",
            "render_dir": render_dir,
            "images": [
                {
                    "image_id": "cube-front_below",
                    "object": "Cube",
                    "view": "front_below",
                    "available": True,
                    "path": render_path,
                    "resource_uri": "blender://inspection-renders/test-render/images/cube-front_below",
                    "size_bytes": os.path.getsize(render_path),
                    "width": 1,
                    "height": 1,
                }
            ],
        }
        with open(os.path.join(render_dir, "metadata.json"), "w", encoding="utf-8") as handle:
            json.dump(inspection_metadata, handle)
        latest_render = inspection_render.latest_inspection_render_metadata(capture_dir=capture_dir)
        assert latest_render["render_id"] == "test-render", latest_render
        image_resource = inspection_render.inspection_render_image_resource(
            "test-render",
            "cube-front_below",
            capture_dir=capture_dir,
        )
        assert image_resource["mimeType"] == "image/png", image_resource
        assert image_resource["blob"], image_resource
        thumbnail_dir = os.path.join(capture_dir, "render-thumbnails", "test-thumbnail")
        os.makedirs(thumbnail_dir, exist_ok=True)
        thumbnail_path = os.path.join(thumbnail_dir, "thumbnail.png")
        shutil.copyfile(capture_path, thumbnail_path)
        thumbnail_metadata = {
            "ok": True,
            "available": True,
            "thumbnail_id": "test-thumbnail",
            "created_at": time.time(),
            "resource_uri": "blender://render-thumbnails/test-thumbnail",
            "metadata_uri": "blender://render-thumbnails/test-thumbnail/metadata",
            "latest_resource_uri": "blender://render-thumbnails/latest",
            "latest_metadata_uri": "blender://render-thumbnails/latest/metadata",
            "render_dir": thumbnail_dir,
            "path": thumbnail_path,
            "size_bytes": os.path.getsize(thumbnail_path),
            "width": 1,
            "height": 1,
        }
        with open(os.path.join(thumbnail_dir, "metadata.json"), "w", encoding="utf-8") as handle:
            json.dump(thumbnail_metadata, handle)
        latest_thumbnail = lab_parity.latest_render_thumbnail_metadata(capture_dir=capture_dir)
        assert latest_thumbnail["thumbnail_id"] == "test-thumbnail", latest_thumbnail
        thumbnail_resource = lab_parity.render_thumbnail_resource("test-thumbnail", capture_dir=capture_dir)
        assert thumbnail_resource["mimeType"] == "image/png", thumbnail_resource
        assert thumbnail_resource["blob"], thumbnail_resource
        shutil.rmtree(capture_dir, ignore_errors=True)

        stopped = bridge_server.stop_bridge()
        assert stopped["ok"], stopped
        print("smoke_bridge_server: ok")
    finally:
        bridge_server.stop_bridge()
        claude_blender.unregister()


if __name__ == "__main__":
    main()
