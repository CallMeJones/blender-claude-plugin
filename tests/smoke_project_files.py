"""Blender background smoke test for .blend project/file lifecycle tools."""

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
from claude_blender import agent_tools, autosave, bridge_protocol, tool_dispatcher  # noqa: E402


def _execute(context, name, args=None):
    return json.loads(tool_dispatcher.execute_tool(context, name, args or {}))


def main():
    work_dir = tempfile.mkdtemp(prefix="claude-blender-project-files-")
    checkpoint_dir = os.path.join(work_dir, "checkpoints")
    claude_blender.register()
    try:
        tool_names = {tool["name"] for tool in agent_tools.blender_tool_definitions()}
        for name in ("save_blend_file", "open_blend_file", "create_new_blender_project", "autosave_current_blend_file"):
            assert name in tool_names, name
            assert name in bridge_protocol.TOOL_CONTRACTS, name
        assert autosave._timer_is_registered()
        bpy.app.timers.unregister(autosave._timer_callback)
        assert not autosave._timer_is_registered()
        autosave._ensure_timer_after_load(None)
        assert autosave._timer_is_registered()

        autosave_unbound = _execute(bpy.context, "autosave_current_blend_file", {"force": True, "reason": "unbound smoke"})
        assert autosave_unbound["ok"] is False, autosave_unbound
        assert autosave_unbound["code"] == "user_path_required", autosave_unbound

        save_unbound = _execute(bpy.context, "save_blend_file", {})
        assert save_unbound["ok"] is False, save_unbound
        assert save_unbound["code"] == "user_path_required", save_unbound

        original_path = os.path.join(work_dir, "original.blend")
        save_without_user_path = _execute(bpy.context, "save_blend_file", {"filepath": original_path})
        assert save_without_user_path["ok"] is False, save_without_user_path
        assert save_without_user_path["code"] == "user_path_required", save_without_user_path

        saved = _execute(bpy.context, "save_blend_file", {"filepath": original_path, "user_confirmed_path": True})
        assert saved["ok"] is True, saved
        assert os.path.isfile(original_path), saved
        assert saved["after"]["absolute_path"] == os.path.abspath(original_path), saved
        assert saved["path_source"] == "user_confirmed", saved
        diagnostics = _execute(bpy.context, "get_blend_file_diagnostics", {})
        assert diagnostics["file"]["is_saved"] is True, diagnostics
        assert diagnostics["file"]["binding_state"] == "bound", diagnostics
        assert diagnostics["file"]["suggested_project_dir_is_hint_only"] is True, diagnostics
        assert diagnostics["file"]["requires_user_confirmed_path"] is False, diagnostics
        assert diagnostics["autosave"]["active_blend_bound"] is True, diagnostics
        assert diagnostics["file"]["can_save_current"] is True, diagnostics
        assert "needs_save" in diagnostics["file"], diagnostics
        assert "script_checkpoints" in diagnostics, diagnostics
        assert "last_checkpoint" in diagnostics["script_checkpoints"], diagnostics
        assert diagnostics["script_checkpoints"]["last_checkpoint"]["exists"] is False, diagnostics
        assert "exists=true" in diagnostics["script_checkpoints"]["path_policy"], diagnostics

        copy_path = os.path.join(work_dir, "copy.blend")
        copy_without_user_path = _execute(bpy.context, "save_blend_file", {"filepath": copy_path, "copy": True})
        assert copy_without_user_path["ok"] is False, copy_without_user_path
        assert copy_without_user_path["code"] == "user_path_required", copy_without_user_path

        copied = _execute(bpy.context, "save_blend_file", {"filepath": copy_path, "copy": True, "user_confirmed_path": True})
        assert copied["ok"] is True, copied
        assert copied["copy"] is True, copied
        assert os.path.isfile(copy_path), copied
        assert bpy.data.filepath == original_path, copied

        save_current = _execute(bpy.context, "save_blend_file", {})
        assert save_current["ok"] is True, save_current
        assert save_current["path_source"] == "active_blend_binding", save_current

        overwrite_refused = _execute(
            bpy.context,
            "save_blend_file",
            {"filepath": copy_path, "copy": True, "user_confirmed_path": True},
        )
        assert overwrite_refused["ok"] is False, overwrite_refused
        assert "overwrite=true" in overwrite_refused["message"], overwrite_refused

        open_without_user_path = _execute(
            bpy.context,
            "open_blend_file",
            {"filepath": copy_path, "confirm_discard_current": True},
        )
        assert open_without_user_path["ok"] is False, open_without_user_path
        assert open_without_user_path["code"] == "user_path_required", open_without_user_path

        open_refused = _execute(bpy.context, "open_blend_file", {"filepath": copy_path, "user_confirmed_path": True})
        assert open_refused["ok"] is False, open_refused
        assert "confirm_discard_current=true" in open_refused["message"], open_refused

        opened = _execute(
            bpy.context,
            "open_blend_file",
            {
                "filepath": copy_path,
                "confirm_discard_current": True,
                "user_confirmed_path": True,
                "create_checkpoint": True,
                "checkpoint_dir": checkpoint_dir,
            },
        )
        assert opened["ok"] is True, opened
        assert opened["checkpoint"]["ok"] is True, opened
        assert os.path.isfile(opened["checkpoint"]["path"]), opened
        assert bpy.data.filepath == copy_path, opened
        assert autosave._timer_is_registered()

        new_refused = _execute(
            bpy.context,
            "create_new_blender_project",
            {"project_dir": work_dir, "project_name": "Smoke Project", "user_confirmed_path": True},
        )
        assert new_refused["ok"] is False, new_refused
        assert "confirm_discard_current=true" in new_refused["message"], new_refused

        new_without_user_path = _execute(
            bpy.context,
            "create_new_blender_project",
            {"project_dir": work_dir, "project_name": "Smoke Project", "confirm_discard_current": True},
        )
        assert new_without_user_path["ok"] is False, new_without_user_path
        assert new_without_user_path["code"] == "user_path_required", new_without_user_path

        project_parent = os.path.join(work_dir, "projects")
        created = _execute(
            bpy.context,
            "create_new_blender_project",
            {
                "project_dir": project_parent,
                "project_name": "Smoke Project",
                "confirm_discard_current": True,
                "user_confirmed_path": True,
                "create_checkpoint": True,
                "checkpoint_dir": checkpoint_dir,
            },
        )
        assert created["ok"] is True, created
        assert created["project_name"] == "Smoke Project", created
        assert os.path.isfile(created["path"]), created
        assert bpy.data.filepath == created["path"], created
        assert autosave._timer_is_registered()
        for folder in ("assets", "refs", "renders", "exports"):
            assert os.path.isdir(os.path.join(created["project_dir"], folder)), created
        assert created["diagnostics"]["file"]["is_saved"] is True, created

        final_project_dir = os.path.join(work_dir, "Final Root")
        escaped_dir = os.path.join(work_dir, "escaped")
        created_from_final_dir = _execute(
            bpy.context,
            "create_new_blender_project",
            {
                "project_dir": final_project_dir,
                "confirm_discard_current": True,
                "user_confirmed_path": True,
                "create_checkpoint": False,
                "standard_dirs": [
                    os.path.join(work_dir, "escaped"),
                    "../outside",
                    "valid/nested",
                    "C:/outside",
                ],
            },
        )
        assert created_from_final_dir["ok"] is True, created_from_final_dir
        assert created_from_final_dir["project_name"] == "Final Root", created_from_final_dir
        assert created_from_final_dir["path"] == os.path.join(final_project_dir, "Final Root.blend"), created_from_final_dir
        assert os.path.isdir(os.path.join(final_project_dir, "valid", "nested")), created_from_final_dir
        assert not os.path.exists(escaped_dir), created_from_final_dir
        assert not os.path.exists(os.path.join(work_dir, "outside")), created_from_final_dir
        project_root = os.path.abspath(created_from_final_dir["project_dir"])
        for folder in created_from_final_dir["created_dirs"]:
            assert os.path.commonpath([project_root, os.path.abspath(folder)]) == project_root, created_from_final_dir

        state = bpy.context.scene.claude_blender
        state.pending_preview = True
        state.pending_preview_label = "Smoke pending preview"
        pending_autosave = _execute(bpy.context, "autosave_current_blend_file", {"reason": "pending preview smoke"})
        assert pending_autosave["ok"] is True, pending_autosave
        assert pending_autosave["skipped"] is True, pending_autosave
        assert pending_autosave["code"] == "pending_preview", pending_autosave
        assert pending_autosave["pending_preview"] is True, pending_autosave
        state.pending_preview = False
        state.pending_preview_label = ""

        autosaved = _execute(bpy.context, "autosave_current_blend_file", {"force": True, "reason": "smoke"})
        assert autosaved["ok"] is True, autosaved
        assert autosaved["mode"] == "in_place", autosaved
        assert autosaved["path"] == created_from_final_dir["path"], autosaved
        assert autosaved["active_file_unchanged"] is True, autosaved
        assert bpy.data.filepath == created_from_final_dir["path"], autosaved
        autosave_root = os.path.join(final_project_dir, ".claude_blender", "autosaves")
        assert not os.path.exists(autosave_root), autosaved
        diagnostics_after_autosave = _execute(bpy.context, "get_blend_file_diagnostics", {})
        assert diagnostics_after_autosave["autosave"]["mode"] == "in_place", diagnostics_after_autosave
        assert diagnostics_after_autosave["autosave"]["last_result"]["path"] == created_from_final_dir["path"], diagnostics_after_autosave

        print("smoke_project_files: ok")
    finally:
        try:
            claude_blender.unregister()
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
