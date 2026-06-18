"""Blender background smoke test for async render jobs."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time

import bpy


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "addon"))

import claude_blender  # noqa: E402
from claude_blender import preferences, render_jobs, tool_dispatcher  # noqa: E402


def _execute(context, name, args=None):
    return json.loads(tool_dispatcher.execute_tool(context, name, args or {}))


def main():
    cache_dir = tempfile.mkdtemp(prefix="claude-blender-render-jobs-")
    claude_blender.register()
    prefs = preferences.get_preferences(bpy.context)
    old_capture_dir = getattr(prefs, "capture_cache_dir", "") if prefs else ""
    try:
        if prefs:
            prefs.capture_cache_dir = cache_dir

        if bpy.context.scene.camera is None:
            bpy.ops.object.camera_add(location=(0.0, -5.0, 3.0), rotation=(1.1, 0.0, 0.0))
            bpy.context.scene.camera = bpy.context.object

        started = _execute(
            bpy.context,
            "start_render_job",
            {
                "frame_start": 1,
                "frame_end": 2,
                "resolution_x": 32,
                "resolution_y": 32,
                "samples": 1,
                "output_kind": "frames",
                "job_name": "smoke render job",
                "note": "tiny async render smoke",
            },
        )
        assert started["ok"] is True, started
        job = started["render_job"]
        job_id = job["job_id"]
        assert job["status"] in {"running", "completed"}, job
        assert job["metadata_uri"].startswith("blender://render-jobs/"), job

        status = job
        deadline = time.time() + 45
        while time.time() < deadline:
            status_payload = _execute(bpy.context, "get_render_job_status", {"job_id": job_id})
            assert status_payload["ok"] is True, status_payload
            status = status_payload["render_job"]
            if status["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.5)

        assert status["status"] == "completed", status
        assert status["frame_count"] == 2, status
        assert status["progress"] == 1.0, status
        assert os.path.isfile(status["newest_frame_path"]), status

        exact = render_jobs.render_job_status(job_id, capture_dir=status["capture_dir"], context=bpy.context)
        assert exact["job_id"] == job_id, exact
        latest = render_jobs.latest_render_job_metadata(capture_dir=status["capture_dir"], context=bpy.context)
        assert latest["job_id"] == job_id, latest
        frame_resource = render_jobs.render_job_frame_resource(
            job_id,
            1,
            capture_dir=status["capture_dir"],
            context=bpy.context,
        )
        assert frame_resource["mimeType"] == "image/png", frame_resource
        assert frame_resource["blob"], frame_resource
        log_resource = render_jobs.render_job_log_resource(
            job_id,
            capture_dir=status["capture_dir"],
            context=bpy.context,
        )
        assert log_resource["mimeType"] == "text/plain", log_resource

        synthetic_id = "tracked-running-complete-frames"
        synthetic_job_dir = os.path.join(status["capture_dir"], "render-jobs", synthetic_id)
        synthetic_frames_dir = os.path.join(synthetic_job_dir, "frames")
        os.makedirs(synthetic_frames_dir, exist_ok=True)
        synthetic_metadata_path = os.path.join(synthetic_job_dir, render_jobs.METADATA_FILENAME)
        with open(os.path.join(synthetic_frames_dir, "frame_0001.png"), "wb") as handle:
            handle.write(b"not-a-real-png")
        with open(synthetic_metadata_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {
                    "ok": True,
                    "available": True,
                    "status": "running",
                    "job_id": synthetic_id,
                    "metadata_path": synthetic_metadata_path,
                    "child_status_path": os.path.join(synthetic_job_dir, render_jobs.CHILD_STATUS_FILENAME),
                    "log_path": os.path.join(synthetic_job_dir, render_jobs.LOG_FILENAME),
                    "frames_dir": synthetic_frames_dir,
                    "output_kind": "frames",
                    "total_frames": 1,
                    "frame_start": 1,
                    "frame_end": 1,
                    "message": "Synthetic tracked process",
                },
                handle,
                indent=2,
                sort_keys=True,
            )

        class RunningProcess:
            def poll(self):
                return None

        render_jobs._PROCESSES[synthetic_id] = RunningProcess()
        try:
            tracked = render_jobs.render_job_status(synthetic_id, capture_dir=status["capture_dir"], context=bpy.context)
            assert tracked["status"] == "running", tracked
            assert tracked["frame_count"] == 1, tracked
        finally:
            render_jobs._PROCESSES.pop(synthetic_id, None)
        restored = render_jobs.render_job_status(synthetic_id, capture_dir=status["capture_dir"], context=bpy.context)
        assert restored["status"] == "completed", restored
        assert restored["message"] == "All expected frame files are present", restored

        guarded = _execute(
            bpy.context,
            "draft_script",
            {
                "intent": "Render the full animation at 1080p and 64 samples.",
                "expected_changes": "Renders frames 1-200 as a quality check.",
                "code": "import bpy\nbpy.ops.render.render(animation=True)\n",
            },
        )
        assert guarded["ok"] is False, guarded
        assert guarded["blocked"] is True, guarded
        assert guarded["recommended_tool"] == "start_render_job", guarded

        print("smoke_render_jobs: ok")
    finally:
        if prefs:
            prefs.capture_cache_dir = old_capture_dir
        claude_blender.unregister()
        shutil.rmtree(cache_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
