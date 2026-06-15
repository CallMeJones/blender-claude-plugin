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
from claude_blender import bridge_server, playblast_capture, viewport_capture  # noqa: E402


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

        health = _request_with_pump(lambda: _get(base + "/health"))
        assert health["ok"], health
        assert health["scene"] == bpy.context.scene.name

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
        resource_url = base + "/resource?" + urllib.parse.urlencode({"uri": "blender://scene/status"})
        resource = _request_with_pump(lambda: _get(resource_url))
        assert resource["ok"], resource
        assert json.loads(resource["text"])["scene"] == bpy.context.scene.name

        capture_dir = tempfile.mkdtemp(prefix="claude-blender-captures-")
        capture_path = os.path.join(capture_dir, "viewport-test.png")
        image = bpy.data.images.new("Claude Test Capture", width=1, height=1)
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
        shutil.rmtree(capture_dir, ignore_errors=True)

        stopped = bridge_server.stop_bridge()
        assert stopped["ok"], stopped
        print("smoke_bridge_server: ok")
    finally:
        bridge_server.stop_bridge()
        claude_blender.unregister()


if __name__ == "__main__":
    main()
