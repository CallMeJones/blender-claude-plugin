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

RENDER_JOB_SMOKE_TIMEOUT_SECONDS = int(os.environ.get("BAB_RENDER_JOB_SMOKE_TIMEOUT_SECONDS", "90"))


def _execute(context, name, args=None):
    return json.loads(tool_dispatcher.execute_tool(context, name, args or {}))


def main():
    cache_dir = tempfile.mkdtemp(prefix="claude-blender-render-jobs-")
    claude_blender.register()
    original_get_preferences = preferences.get_preferences
    prefs = type("_SmokePreferences", (), {"capture_cache_dir": cache_dir})()
    old_bridge_token = os.environ.get("BLENDER_BRIDGE_TOKEN")
    old_bridge_url = os.environ.get("BLENDER_BRIDGE_URL")
    try:
        preferences.get_preferences = lambda _context: prefs

        os.environ["BLENDER_BRIDGE_TOKEN"] = "secret-token-for-smoke"
        os.environ["BLENDER_BRIDGE_URL"] = "http://127.0.0.1:8765"
        child_env = render_jobs._child_env()
        assert "BLENDER_BRIDGE_TOKEN" not in child_env, child_env
        assert "BLENDER_BRIDGE_URL" not in child_env, child_env

        if bpy.context.scene.camera is None:
            bpy.ops.object.camera_add(location=(0.0, -5.0, 3.0), rotation=(1.1, 0.0, 0.0))
            bpy.context.scene.camera = bpy.context.object

        guarded_thumbnail = _execute(
            bpy.context,
            "render_scene_thumbnail",
            {"resolution_x": 1920, "resolution_y": 1080, "note": "guard high-res blocking thumbnail"},
        )
        assert guarded_thumbnail["ok"] is False, guarded_thumbnail
        assert guarded_thumbnail["code"] == "render_job_recommended", guarded_thumbnail
        assert guarded_thumbnail["recommended_tool"] == "start_render_job", guarded_thumbnail
        assert guarded_thumbnail["suggested_arguments"]["frame_start"] == bpy.context.scene.frame_current, guarded_thumbnail
        assert guarded_thumbnail["estimated_seconds"] >= 1, guarded_thumbnail
        assert guarded_thumbnail["estimated_duration"], guarded_thumbnail
        assert guarded_thumbnail["poll_after_seconds"] >= 1, guarded_thumbnail
        preview_profile = render_jobs._quality_profile("auto", "frames", "quick playblast preview", "")
        assert preview_profile["profile"] == "preview", preview_profile
        assert preview_profile["resolution_x"] == 640, preview_profile
        assert preview_profile["resolution_y"] == 360, preview_profile
        assert preview_profile["samples"] == 8, preview_profile
        assert preview_profile["preview_default_applied"] is True, preview_profile
        final_profile = render_jobs._quality_profile("auto", "frames", "final product render", "")
        assert final_profile["profile"] == "final", final_profile
        assert final_profile["resolution_x"] == 1920, final_profile
        assert final_profile["resolution_y"] == 1080, final_profile

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
        assert job["timeout_safe"] is True, job
        assert job["estimated_seconds"] >= 1, job
        assert job["poll_after_seconds"] >= 0, job
        assert "background Blender process" in job["client_guidance"], job

        status = job
        deadline = time.time() + RENDER_JOB_SMOKE_TIMEOUT_SECONDS
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
        assert status["elapsed_seconds"] >= 0, status
        assert status["estimated_seconds_remaining"] == 0, status
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

        assembled = _execute(
            bpy.context,
            "assemble_render_job_video",
            {
                "job_id": job_id,
                "fps": 12,
                "quality": "LOW",
            },
        )
        assert assembled["ok"] is True, assembled
        deadline = time.time() + RENDER_JOB_SMOKE_TIMEOUT_SECONDS
        while time.time() < deadline:
            status_payload = _execute(bpy.context, "get_render_job_status", {"job_id": job_id})
            assert status_payload["ok"] is True, status_payload
            status = status_payload["render_job"]
            if status["status"] in {"completed", "failed", "cancelled"} and status.get("video_available"):
                break
            time.sleep(0.5)

        assert status["status"] == "completed", status
        assert status["video_available"] is True, status
        assert os.path.isfile(status["video_path"]), status
        validated = _execute(
            bpy.context,
            "validate_render_job_output",
            {
                "job_id": job_id,
                "require_video": True,
            },
        )
        assert validated["ok"] is True, validated
        assert validated["validation"]["checks"]["video_available"] is True, validated
        video_resource = render_jobs.render_job_video_resource(
            job_id,
            capture_dir=status["capture_dir"],
            context=bpy.context,
        )
        assert video_resource["mimeType"] == "video/mp4", video_resource
        assert video_resource["blob"], video_resource

        started_video = _execute(
            bpy.context,
            "start_render_job",
            {
                "frame_start": 1,
                "frame_end": 1,
                "resolution_x": 32,
                "resolution_y": 32,
                "samples": 1,
                "output_kind": "video",
                "job_name": "smoke direct mp4 render job",
            },
        )
        assert started_video["ok"] is True, started_video
        video_job_id = started_video["render_job"]["job_id"]
        video_status = started_video["render_job"]
        deadline = time.time() + RENDER_JOB_SMOKE_TIMEOUT_SECONDS
        while time.time() < deadline:
            status_payload = _execute(bpy.context, "get_render_job_status", {"job_id": video_job_id})
            assert status_payload["ok"] is True, status_payload
            video_status = status_payload["render_job"]
            if video_status["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.5)
        assert video_status["status"] == "completed", video_status
        assert video_status["video_available"] is True, video_status

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

        finished_id = "tracked-finished-reaped"
        finished_job_dir = os.path.join(status["capture_dir"], "render-jobs", finished_id)
        os.makedirs(finished_job_dir, exist_ok=True)
        finished_metadata_path = os.path.join(finished_job_dir, render_jobs.METADATA_FILENAME)
        with open(finished_metadata_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {
                    "ok": True,
                    "available": True,
                    "status": "completed",
                    "job_id": finished_id,
                    "metadata_path": finished_metadata_path,
                    "log_path": os.path.join(finished_job_dir, render_jobs.LOG_FILENAME),
                    "output_kind": "frames",
                    "total_frames": 0,
                    "frame_start": 1,
                    "frame_end": 1,
                    "message": "Synthetic finished process",
                },
                handle,
                indent=2,
                sort_keys=True,
            )

        class FinishedProcess:
            def __init__(self):
                self.waited = False

            def poll(self):
                return 0

            def wait(self, timeout=0):
                self.waited = True
                return 0

        finished_process = FinishedProcess()
        render_jobs._PROCESSES[finished_id] = finished_process
        finished = render_jobs.render_job_status(finished_id, capture_dir=status["capture_dir"], context=bpy.context)
        assert finished["status"] == "completed", finished
        assert finished["returncode"] == 0, finished
        assert finished_process.waited, finished
        assert finished_id not in render_jobs._PROCESSES, finished

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
        if old_bridge_token is None:
            os.environ.pop("BLENDER_BRIDGE_TOKEN", None)
        else:
            os.environ["BLENDER_BRIDGE_TOKEN"] = old_bridge_token
        if old_bridge_url is None:
            os.environ.pop("BLENDER_BRIDGE_URL", None)
        else:
            os.environ["BLENDER_BRIDGE_URL"] = old_bridge_url
        preferences.get_preferences = original_get_preferences
        claude_blender.unregister()
        shutil.rmtree(cache_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
