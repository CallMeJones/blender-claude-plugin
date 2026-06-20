"""Blender smoke tests for external asset import helpers without live network."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import urllib.parse
import zipfile

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import external_assets, live_preview, tool_dispatcher  # noqa: E402

observed_timeouts = []


def _make_png(path):
    image = bpy.data.images.new("ExternalAssetSmokePixel", width=1, height=1, alpha=True)
    image.pixels = [0.9, 0.25, 0.1, 1.0]
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def _fake_fetch_json(url, *, timeout=15):
    path = urllib.parse.urlparse(url).path
    if path == "/files/studio_hdri":
        return {
            "hdri": {
                "1k": {
                    "png": {
                        "url": "https://cdn.example.invalid/studio_hdri_1k.png",
                        "md5": "",
                        "size": 1,
                    }
                }
            }
        }
    if path == "/files/oak_floor":
        return {
            "diffuse": {
                "2k": {
                    "png": {
                        "url": "https://cdn.example.invalid/oak_floor_diff_2k.png",
                        "md5": "",
                        "size": 1,
                    }
                }
            },
            "normal": {
                "2k": {
                    "png": {
                        "url": "https://cdn.example.invalid/oak_floor_nor_2k.png",
                        "md5": "",
                        "size": 1,
                    }
                }
            },
        }
    if path == "/files/model_one":
        return {
            "gltf": {
                "2k": {
                    "gltf": {
                        "url": "https://cdn.example.invalid/model_one.gltf",
                        "md5": "",
                        "size": 1,
                    }
                }
            }
        }
    if path == "/files/blend_only":
        return {
            "blend": {
                "2k": {
                    "blend": {
                        "url": "https://cdn.example.invalid/blend_only.blend",
                        "md5": "",
                        "size": 1,
                    }
                }
            }
        }
    raise AssertionError(f"Unexpected URL: {url}")


def _fake_fetch_json_with_headers(url, *, headers=None, timeout=15):
    observed_timeouts.append(("fetch_json_with_headers", timeout))
    path = urllib.parse.urlparse(url).path
    if path == "/v3/models/sketchfab_one/download":
        assert headers and headers.get("Authorization") == "Token smoke-token", headers
        return {"gltf": {"url": "https://download.example.invalid/sketchfab_one.zip", "expires": 300}}
    raise AssertionError(f"Unexpected authenticated URL: {url}")


def _fake_download_file(url, destination, *, expected_md5="", expected_size=None, headers=None, timeout=60):
    observed_timeouts.append(("download_file", timeout))
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if str(destination).lower().endswith(".zip"):
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("scene.gltf", "{}")
    elif str(destination).lower().endswith((".png", ".jpg", ".jpeg")):
        _make_png(destination)
    else:
        with open(destination, "w", encoding="utf-8") as handle:
            handle.write("{}")
    return {
        "ok": True,
        "url": url,
        "path": destination,
        "cached": False,
        "size": os.path.getsize(destination),
        "md5": "",
        "sha256": "smoke-sha",
    }


def _fake_import_model_file(filepath):
    mesh = bpy.data.meshes.new("SmokeImportedMesh")
    obj = bpy.data.objects.new("SmokeImportedModel", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return {"ok": True}


def _execute(context, name, args):
    return json.loads(tool_dispatcher.execute_tool(context, name, args))


def main():
    cache_dir = tempfile.mkdtemp(prefix="bab-import-assets-")
    original_fetch_json = external_assets._fetch_json
    original_fetch_json_with_headers = external_assets._fetch_json_with_headers
    original_download_file = external_assets._download_file
    original_import_model_file = external_assets._import_model_file
    external_assets._fetch_json = _fake_fetch_json
    external_assets._fetch_json_with_headers = _fake_fetch_json_with_headers
    external_assets._download_file = _fake_download_file
    external_assets._import_model_file = _fake_import_model_file
    try:
        claude_blender.register()
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.object
        cube.name = "TextureTarget"

        hdri = _execute(
            bpy.context,
            "import_poly_haven_asset",
            {"asset_id": "studio_hdri", "asset_type": "hdris", "resolution": "1k", "file_format": "png", "cache_dir": cache_dir},
        )
        assert hdri["ok"] is True, hdri
        assert bpy.context.scene.world and bpy.context.scene.world.name == hdri["world"], hdri
        assert bpy.context.scene.claude_blender.pending_preview is True, hdri
        assert live_preview.revert(bpy.context)["ok"] is True

        texture = _execute(
            bpy.context,
            "import_poly_haven_asset",
            {
                "asset_id": "oak_floor",
                "asset_type": "textures",
                "resolution": "2k",
                "file_format": "png",
                "target_object_name": cube.name,
                "cache_dir": cache_dir,
            },
        )
        assert texture["ok"] is True, texture
        assert cube.material_slots and cube.material_slots[0].material.name == texture["material"], texture
        assert live_preview.revert(bpy.context)["ok"] is True

        model = _execute(
            bpy.context,
            "import_poly_haven_asset",
            {"asset_id": "model_one", "asset_type": "models", "resolution": "2k", "file_format": "gltf", "cache_dir": cache_dir},
        )
        assert model["ok"] is True, model
        assert "SmokeImportedModel" in model["imported_objects"], model
        assert bpy.data.objects.get("SmokeImportedModel") is not None, model
        assert live_preview.revert(bpy.context)["ok"] is True
        assert bpy.data.objects.get("SmokeImportedModel") is None

        previous_transaction_id = live_preview.current_transaction()["id"]
        unsupported_model = _execute(
            bpy.context,
            "import_poly_haven_asset",
            {"asset_id": "blend_only", "asset_type": "models", "resolution": "2k", "file_format": "blend", "cache_dir": cache_dir},
        )
        assert unsupported_model["ok"] is False, unsupported_model
        assert "Direct .blend append" in unsupported_model["message"], unsupported_model
        assert live_preview.current_transaction()["id"] == previous_transaction_id, unsupported_model

        sketchfab = _execute(
            bpy.context,
            "import_sketchfab_model",
            {"uid": "sketchfab_one", "api_token": "smoke-token", "cache_dir": cache_dir, "timeout": 999},
        )
        assert sketchfab["ok"] is True, sketchfab
        assert "SmokeImportedModel" in sketchfab["imported_objects"], sketchfab
        assert observed_timeouts[-2:] == [("fetch_json_with_headers", 300), ("download_file", 300)], observed_timeouts
        assert live_preview.revert(bpy.context)["ok"] is True

        diagnostics = _execute(bpy.context, "get_external_asset_cache_diagnostics", {"cache_dir": cache_dir})
        assert diagnostics["ok"] is True, diagnostics
        assert diagnostics["asset_count"] >= 4, diagnostics
        print("smoke_external_asset_imports: ok")
    finally:
        try:
            claude_blender.unregister()
        except Exception:
            pass
        external_assets._fetch_json = original_fetch_json
        external_assets._fetch_json_with_headers = original_fetch_json_with_headers
        external_assets._download_file = original_download_file
        external_assets._import_model_file = original_import_model_file
        shutil.rmtree(cache_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
