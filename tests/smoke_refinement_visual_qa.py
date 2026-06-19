"""Render smoke test for product and character refinement kits."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import tool_dispatcher  # noqa: E402


ARTIFACT_DIR_ENV = "CLAUDE_BLENDER_VISUAL_QA_DIR"


def _execute(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert result.get("ok"), f"{name} failed: {result}"
    return result


def _select_object(context, obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _artifact_dir():
    configured = os.environ.get(ARTIFACT_DIR_ENV)
    if configured:
        path = os.path.abspath(configured)
        os.makedirs(path, exist_ok=True)
        return path, False
    return tempfile.mkdtemp(prefix="claude-blender-refinement-visual-"), True


def _set_fast_render_settings(scene):
    for engine in ("BLENDER_WORKBENCH", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x = 320
    scene.render.resolution_y = 240
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    if scene.world:
        scene.world.color = (0.04, 0.045, 0.05)
    shading = getattr(scene.display, "shading", None)
    if shading:
        for attr, value in (
            ("light", "STUDIO"),
            ("color_type", "MATERIAL"),
            ("background_type", "WORLD"),
        ):
            try:
                setattr(shading, attr, value)
            except (AttributeError, TypeError, ValueError):
                pass


def _render_still(scene, path):
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    assert os.path.isfile(path), path
    assert os.path.getsize(path) > 2048, path


def _assert_png_has_visible_content(path):
    image = bpy.data.images.load(path, check_existing=False)
    try:
        pixels = list(image.pixels)
        assert pixels, path
        stride = max(4, (len(pixels) // 4000) // 4 * 4)
        colors = []
        alpha_max = 0.0
        for index in range(0, len(pixels), stride):
            colors.extend(pixels[index : index + 3])
            if index + 3 < len(pixels):
                alpha_max = max(alpha_max, pixels[index + 3])
        assert alpha_max > 0.5, {"path": path, "alpha_max": alpha_max}
        assert max(colors) - min(colors) > 0.025, {
            "path": path,
            "min": min(colors),
            "max": max(colors),
        }
    finally:
        bpy.data.images.remove(image)


def _widen_active_camera(scene):
    camera = scene.camera
    if camera and getattr(camera.data, "lens", None):
        camera.data.lens = min(float(camera.data.lens), 38.0)
        camera.data.clip_end = max(float(camera.data.clip_end), 1000.0)


def _render_kit(context, artifact_dir, name):
    path = os.path.join(artifact_dir, f"{name}.png")
    _widen_active_camera(context.scene)
    _render_still(context.scene, path)
    _assert_png_has_visible_content(path)
    return path


def main():
    claude_blender.register()
    context = bpy.context
    scene = context.scene
    artifact_dir, cleanup = _artifact_dir()
    success = False
    rendered_paths = []
    try:
        _set_fast_render_settings(scene)
        cube = bpy.data.objects["Cube"]

        cube.scale = (1.45, 0.72, 0.45)
        _select_object(context, cube)
        product = _execute(
            context,
            "apply_product_refinement_template",
            {
                "target_name": "Cube",
                "style": "premium",
                "include_stage": True,
                "include_callouts": True,
            },
        )
        assert "product presentation" in product["expected_changes"], product
        rendered_paths.append(_render_kit(context, artifact_dir, "product-refinement-kit"))
        _execute(context, "revert_preview", {})
        assert not scene.claude_blender.pending_preview

        cube.scale = (0.72, 0.5, 1.22)
        _select_object(context, cube)
        character = _execute(
            context,
            "apply_character_refinement_template",
            {
                "target_name": "Cube",
                "character_style": "toon",
                "detail_level": "medium",
                "create_guides": True,
            },
        )
        assert "character presentation kit" in character["expected_changes"], character
        stage = _execute(
            context,
            "create_studio_product_stage",
            {"target_name": "Cube", "stage_name": "Agent Bridge Character Visual QA Stage"},
        )
        assert stage["camera"], stage
        rendered_paths.append(_render_kit(context, artifact_dir, "character-refinement-kit"))
        _execute(context, "revert_preview", {})
        assert not scene.claude_blender.pending_preview

        manifest_path = os.path.join(artifact_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump({"renders": rendered_paths}, handle, indent=2)
        success = True
        if cleanup:
            print("smoke_refinement_visual_qa: ok")
        else:
            print(f"smoke_refinement_visual_qa: ok ({artifact_dir})")
    finally:
        claude_blender.unregister()
        if cleanup and success:
            shutil.rmtree(artifact_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
