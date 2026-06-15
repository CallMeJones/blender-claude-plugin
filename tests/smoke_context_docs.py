"""Blender background smoke test for context, docs, and image payload wiring."""

from __future__ import annotations

import os
import random
import shutil
import sys
import tempfile
import zipfile
import base64
import json

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import anthropic_client, bridge_protocol, context_budget, context_bundle, docs_index, playblast_capture, tool_dispatcher, viewport_capture  # noqa: E402


def main():
    cache_dir = tempfile.mkdtemp(prefix="claude-blender-docs-")
    try:
        claude_blender.register()

        bundle = context_bundle.build_context_bundle(bpy.context, include_visual=True)
        public = context_bundle.public_bundle(bundle)
        assert "_attachments" not in public
        assert public["visual_context"]["requested"] is True
        assert public["visual_context"]["available"] is False
        assert "capture_viewport" in bundle["available_tools"]
        assert "capture_animation_playblast" in bundle["available_tools"]
        assert "capture_viewport" in {tool["name"] for tool in anthropic_client.blender_tool_definitions()}
        assert "capture_animation_playblast" in {tool["name"] for tool in anthropic_client.blender_tool_definitions()}
        assert "capture_viewport" in bridge_protocol.TOOL_CONTRACTS
        assert "capture_animation_playblast" in bridge_protocol.TOOL_CONTRACTS

        captured = json.loads(tool_dispatcher.execute_tool(bpy.context, "capture_viewport", {"max_bytes": 512 * 1024}))
        assert captured["ok"] is False, captured
        assert captured["visual_context"]["requested"] is True, captured
        assert captured["visual_context"]["available"] is False, captured
        assert "interactive Blender window" in captured["message"], captured
        playblast = json.loads(
            tool_dispatcher.execute_tool(
                bpy.context,
                "capture_animation_playblast",
                {"frame_start": 1, "frame_end": 12, "max_frames": 4, "brief": "background smoke"},
            )
        )
        assert playblast["ok"] is False, playblast
        assert playblast["playblast"]["requested"] is True, playblast
        assert playblast["playblast"]["available"] is False, playblast
        assert playblast["playblast"]["sampled_frames"] == [1, 5, 8, 12], playblast
        assert "interactive Blender window" in playblast["message"], playblast

        original_has_ui_context = viewport_capture.has_ui_context
        original_capture_viewport_to_file = viewport_capture.capture_viewport_to_file
        playblast_failure_dir = tempfile.mkdtemp(prefix="claude-blender-playblast-failure-", dir=cache_dir)
        try:
            viewport_capture.has_ui_context = lambda _context: True

            def _fail_frame_capture(_context, _filepath):
                raise RuntimeError("synthetic frame failure")

            viewport_capture.capture_viewport_to_file = _fail_frame_capture
            failed_playblast = playblast_capture.capture_animation_playblast(
                bpy.context,
                frame_start=1,
                frame_end=2,
                max_frames=2,
                brief="frame failure smoke",
                capture_dir=playblast_failure_dir,
            )
            assert failed_playblast["ok"] is False, failed_playblast
            assert failed_playblast["available"] is False, failed_playblast
            assert failed_playblast["frames"][0]["available"] is False, failed_playblast
            assert "synthetic frame failure" in failed_playblast["frames"][0]["note"], failed_playblast
            assert os.path.isfile(failed_playblast["metadata_path"]), failed_playblast
        finally:
            viewport_capture.has_ui_context = original_has_ui_context
            viewport_capture.capture_viewport_to_file = original_capture_viewport_to_file
            shutil.rmtree(playblast_failure_dir, ignore_errors=True)

        project_dir = tempfile.mkdtemp(prefix="claude-blender-project-", dir=cache_dir)
        project_blend = os.path.join(project_dir, "Capture Project.blend")
        bpy.ops.wm.save_as_mainfile(filepath=project_blend)
        resolved_capture_dir = viewport_capture.resolve_capture_dir(
            bpy.context,
            preferred_dir=viewport_capture.default_capture_dir(),
        )
        assert resolved_capture_dir["storage_scope"] == "project", resolved_capture_dir
        assert resolved_capture_dir["project_id"], resolved_capture_dir
        assert resolved_capture_dir["session_id"], resolved_capture_dir
        assert resolved_capture_dir["capture_dir"].startswith(
            os.path.join(project_dir, ".claude_blender", "captures")
        ), resolved_capture_dir
        project_capture_path = os.path.join(resolved_capture_dir["capture_dir"], "viewport-old-project.png")
        os.makedirs(os.path.dirname(project_capture_path), exist_ok=True)
        with open(project_capture_path, "wb") as handle:
            handle.write(b"project")
        fallback_capture_dir = os.path.join(
            viewport_capture.default_capture_dir(),
            resolved_capture_dir["project_id"],
            resolved_capture_dir["session_id"],
        )
        fallback_capture_path = os.path.join(fallback_capture_dir, "viewport-new-fallback.png")
        os.makedirs(fallback_capture_dir, exist_ok=True)
        with open(fallback_capture_path, "wb") as handle:
            handle.write(b"fallback")
        os.utime(project_capture_path, (1000, 1000))
        os.utime(fallback_capture_path, (2000, 2000))
        latest_path = viewport_capture.latest_capture_path(
            context=bpy.context,
            preferred_dir=viewport_capture.default_capture_dir(),
        )
        assert latest_path == fallback_capture_path, latest_path
        shutil.rmtree(
            os.path.join(viewport_capture.default_capture_dir(), resolved_capture_dir["project_id"]),
            ignore_errors=True,
        )

        tiny_png = os.path.join(cache_dir, "tiny.png")
        with open(tiny_png, "wb") as handle:
            handle.write(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
                )
            )
        image = viewport_capture.load_preview_image(tiny_png)
        assert image.name == viewport_capture.PREVIEW_IMAGE_NAME
        assert bpy.data.images.get(viewport_capture.PREVIEW_IMAGE_NAME) is not None

        large_png = os.path.join(cache_dir, "large.png")
        large_image = bpy.data.images.new("Claude Resize Source", width=256, height=256)
        rng = random.Random(42)
        large_image.pixels[:] = [
            value
            for _index in range(256 * 256)
            for value in (rng.random(), rng.random(), rng.random(), 1.0)
        ]
        large_image.filepath_raw = large_png
        large_image.file_format = "PNG"
        large_image.save()
        bpy.data.images.remove(large_image)
        assert os.path.getsize(large_png) > 48 * 1024, os.path.getsize(large_png)
        resized_metadata, resized_attachments = viewport_capture.prepare_image_attachment(
            large_png,
            max_bytes=48 * 1024,
            capture_method="test-large-png",
        )
        assert resized_metadata["available"], resized_metadata
        assert resized_metadata["resized"], resized_metadata
        assert resized_metadata["original_size_bytes"] > resized_metadata["size_bytes"], resized_metadata
        assert resized_metadata["size_bytes"] <= 48 * 1024, resized_metadata
        assert resized_metadata["width"] < resized_metadata["original_width"], resized_metadata
        assert resized_attachments["viewport_image"]["source"]["media_type"] == "image/png"

        docs = docs_index.search_blender_docs("keyframe camera orbit action fcurves", cache_dir=cache_dir)
        assert docs["results"], docs
        assert os.path.exists(docs["cache_file"])
        assert any("Action" in result["title"] or "keyframe" in result["snippet"] for result in docs["results"])
        assert docs["citations"], docs
        assert docs["citation_report"].startswith("Docs used:"), docs

        synthetic_api_zip = os.path.join(cache_dir, "synthetic_api_docs.zip")
        with zipfile.ZipFile(synthetic_api_zip, "w") as archive:
            archive.writestr(
                "blender_python_reference/index.html",
                "<html><head><title>Blender Python API</title></head>"
                "<body><h1>Blender Python API</h1><p>Index page.</p></body></html>",
            )
            archive.writestr(
                "blender_python_reference/bpy.types.Object.html",
                "<html><head><title>Object(ID) - Blender Python API</title></head>"
                "<body><h1>Object(ID)</h1><p>Object location rotation_euler scale animation_data constraints.</p></body></html>",
            )
        synthetic_manual_zip = os.path.join(cache_dir, "synthetic_manual_docs.zip")
        with zipfile.ZipFile(synthetic_manual_zip, "w") as archive:
            archive.writestr(
                "blender_manual_html/index.html",
                "<html><head><title>Blender Manual</title></head>"
                "<body><h1>Blender Manual</h1><p>Manual index page.</p></body></html>",
            )
            archive.writestr(
                "blender_manual_html/modeling/modifiers/generate/bevel.html",
                "<html><head><title>Bevel Modifier - Blender Manual</title></head>"
                "<body><h1>Bevel Modifier</h1><p>The bevel modifier creates chamfered edges for product polish workflows.</p></body></html>",
            )

        original_download = docs_index._download_zip

        def fake_download(url, destination):
            if url == docs_index.manual_zip_url(docs_index.blender_docs_version()):
                shutil.copyfile(synthetic_manual_zip, destination)
            else:
                shutil.copyfile(synthetic_api_zip, destination)

        docs_index._download_zip = fake_download
        try:
            status = docs_index.build_full_docs_cache(cache_dir=cache_dir, version=docs_index.blender_docs_version(), force=True)
        finally:
            docs_index._download_zip = original_download
        assert status["full_index_exists"], status
        assert status["full_index_entries"] >= 2, status
        assert status["manual_index_exists"], status
        assert status["manual_index_entries"] >= 2, status
        indexed = docs_index.search_blender_docs("rotation_euler animation_data constraints", cache_dir=cache_dir)
        assert indexed["full_index_entries"] >= 2, indexed
        assert any(result["source"] == "full_api_index" for result in indexed["results"]), indexed
        assert indexed["citations"][0]["url"].startswith("https://docs.blender.org/api/"), indexed
        assert indexed["searched_indexes"][2]["name"] == "manual_full_index", indexed
        assert indexed["search_report"].startswith("Searched local docs"), indexed
        assert len(str(indexed)) < context_budget.MAX_DOC_RESULT_CHARS, indexed

        manual_indexed = docs_index.search_blender_docs("bevel product polish workflow", cache_dir=cache_dir)
        assert manual_indexed["manual_index_entries"] >= 2, manual_indexed
        assert any(result["source"] == "full_manual_index" for result in manual_indexed["results"]), manual_indexed
        assert any(citation["kind"] == "manual" for citation in manual_indexed["citations"]), manual_indexed
        assert "full_manual_index" in manual_indexed["citation_report"], manual_indexed

        partial_cache_dir = tempfile.mkdtemp(prefix="claude-blender-partial-docs-", dir=cache_dir)

        def fail_manual_download(url, destination):
            if url == docs_index.manual_zip_url(docs_index.blender_docs_version()):
                raise RuntimeError("synthetic manual download failure")
            shutil.copyfile(synthetic_api_zip, destination)

        docs_index._download_zip = fail_manual_download
        try:
            partial_status = docs_index.build_full_docs_cache(
                cache_dir=partial_cache_dir,
                version=docs_index.blender_docs_version(),
                force=True,
            )
        finally:
            docs_index._download_zip = original_download
        assert partial_status["full_index_exists"], partial_status
        assert partial_status["full_index_entries"] >= 2, partial_status
        assert not partial_status["manual_index_exists"], partial_status
        assert not partial_status["build_ok"], partial_status
        assert "synthetic manual download failure" in partial_status["manual_build_error"], partial_status
        partial_search = docs_index.search_blender_docs("rotation_euler constraints", cache_dir=partial_cache_dir)
        assert any(result["source"] == "full_api_index" for result in partial_search["results"]), partial_search

        fallback_docs = docs_index.search_blender_docs("zzzz_unmatched_docs_query", cache_dir=cache_dir)
        fallback_sources = {result["source"] for result in fallback_docs["results"]}
        assert "official_manual_url_candidate" in fallback_sources, fallback_docs
        assert fallback_docs["used_official_fallbacks"], fallback_docs
        assert {citation["kind"] for citation in fallback_docs["citations"]} == {"official"}, fallback_docs

        image_bundle = {
            "scene_summary": {"object_count": 0},
            "visual_context": {"requested": True, "available": True},
            "_attachments": {
                "viewport_image": {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "aGVsbG8=",
                    },
                }
            },
        }
        messages = anthropic_client.initial_messages("describe the viewport", image_bundle)
        content = messages[0]["content"]
        assert content[0]["type"] == "text"
        assert "_attachments" not in content[0]["text"]
        assert any(block.get("type") == "image" for block in content)

        huge_bundle = {
            "scene_summary": {"object_count": 5000},
            "selection_summary": {
                "selected_objects": [
                    {
                        "name": f"Object_{index}",
                        "type": "MESH",
                        "custom_properties": "x" * 10_000,
                    }
                    for index in range(200)
                ],
            },
            "huge_local_docs_mistake": "docs " * 100_000,
        }
        huge_messages = anthropic_client.initial_messages("budget this", huge_bundle)
        huge_text = huge_messages[0]["content"][0]["text"]
        assert len(huge_text) < context_budget.MAX_CONTEXT_JSON_CHARS + 1_000
        assert "truncated" in huge_text
        assert anthropic_client.estimate_request_chars(
            messages=huge_messages,
            tools=anthropic_client.blender_tool_definitions(),
        ) < context_budget.MAX_CONTEXT_JSON_CHARS + 80_000

        claude_blender.unregister()
        print("smoke_context_docs: ok")
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
