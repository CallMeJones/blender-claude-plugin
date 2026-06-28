"""Blender background smoke test for animation workflow helper tools."""

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
from claude_blender import (  # noqa: E402
    agent_tools,
    animation_analysis,
    animation_brief,
    bridge_protocol,
    context_bundle,
    live_preview,
    script_runner,
    tool_dispatcher,
)


ANIMATION_TOOLS = {
    "create_animation_brief",
    "create_timing_chart",
    "plan_animation_workflow",
    "run_animation_workflow",
    "run_animation_task",
    "block_key_poses",
    "add_breakdown_pose",
    "set_pose_hold",
    "set_rig_pose_hold",
    "set_rig_custom_property_keyframes",
    "get_rig_pose_library_details",
    "apply_rig_pose_from_action",
    "apply_rig_pose_marker",
    "apply_rig_action_clip",
    "offset_rig_limb_controls",
    "create_motion_arc",
    "analyze_motion_arcs",
    "analyze_fcurve_spacing",
    "analyze_pose_clarity",
    "analyze_animation_principles",
    "sample_animation_state",
    "analyze_contact_sliding",
    "analyze_collision_penetration",
    "analyze_center_of_mass",
    "analyze_camera_framing",
    "analyze_motion_physics",
    "compare_animation_to_brief",
    "review_playblast_against_brief",
    "review_inspection_renders_against_brief",
    "stage_persistent_simulation_bake",
    "repair_animation_from_findings",
    "run_animation_repair_loop",
    "animate_object_bounce",
    "create_progressive_bounce_animation",
    "animate_material_property",
    "animate_light_property",
    "create_follow_path_animation",
}


def _execute(context, name, args=None):
    result = json.loads(tool_dispatcher.execute_tool(context, name, args or {}))
    assert result.get("ok"), f"{name} failed: {result}"
    return result


def _select_object(context, obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _snapshot(scene, cube, camera, light):
    return {
        "objects": set(bpy.data.objects.keys()),
        "curves": set(bpy.data.curves.keys()),
        "materials": set(bpy.data.materials.keys()),
        "actions": set(bpy.data.actions.keys()),
        "cube_location": tuple(round(float(value), 6) for value in cube.location),
        "cube_materials": [slot.material.name if slot.material else None for slot in cube.material_slots],
        "camera_constraints": [constraint.name for constraint in camera.constraints],
        "camera_action": camera.animation_data.action.name if camera.animation_data and camera.animation_data.action else None,
        "light_energy": round(float(light.data.energy), 6),
        "light_action": light.data.animation_data.action.name if light.data.animation_data and light.data.animation_data.action else None,
        "scene_camera": scene.camera.name if scene.camera else None,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
    }


def _action_keyframes(action):
    frames = []
    for fcurve in live_preview._iter_action_fcurves(action):
        frames.extend(round(point.co.x, 4) for point in fcurve.keyframe_points)
    return sorted(set(frames))


def _write_pattern_png(path):
    image = bpy.data.images.new(f"Agent Smoke Frame {os.path.basename(path)}", width=8, height=8, alpha=True)
    try:
        pixels = []
        for y in range(8):
            for x in range(8):
                bright = 0.85 if (x < 4 and y < 4) or (x >= 4 and y >= 4) else 0.15
                pixels.extend([bright, 0.25, 1.0 - bright, 1.0])
        image.pixels[:] = pixels
        image.filepath_raw = path
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)


def _write_subject_png(path, *, center_y):
    width = 16
    height = 16
    image = bpy.data.images.new(f"Agent Smoke Subject {os.path.basename(path)}", width=width, height=height, alpha=True)
    try:
        y_center = max(3, min(height - 4, int(center_y)))
        pixels = []
        for y in range(height):
            for x in range(width):
                is_subject = 6 <= x <= 9 and y_center - 2 <= y <= y_center + 2
                if is_subject:
                    bright = 0.9 if (x + y) % 2 else 0.65
                    pixels.extend([bright, 0.9, 0.1, 1.0])
                else:
                    pixels.extend([0.04, 0.04, 0.04, 1.0])
        image.pixels[:] = pixels
        image.filepath_raw = path
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)


def _write_sampled_playblast_png(path, *, center_x, center_y):
    width = 320
    height = 180
    image = bpy.data.images.new(f"Agent Smoke Playblast {os.path.basename(path)}", width=width, height=height, alpha=True)
    try:
        subject_half = 18
        pixels = []
        for y in range(height):
            for x in range(width):
                is_subject = abs(x - int(center_x)) <= subject_half and abs(y - int(center_y)) <= subject_half
                if is_subject:
                    checker = 0.15 if ((x // 6) + (y // 6)) % 2 else 0.0
                    pixels.extend([min(1.0, 0.82 + checker), 0.72, 0.12, 1.0])
                else:
                    stripe = 0.025 if ((x // 24) + (y // 24)) % 2 else 0.0
                    pixels.extend([0.035 + stripe, 0.04 + stripe, 0.055 + stripe, 1.0])
        image.pixels[:] = pixels
        image.filepath_raw = path
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)


def main():
    claude_blender.register()
    context = bpy.context
    scene = context.scene
    cube = bpy.data.objects["Cube"]
    camera = bpy.data.objects["Camera"]
    light = bpy.data.objects["Light"]
    _select_object(context, cube)
    initial = _snapshot(scene, cube, camera, light)
    visual_dir = ""

    try:
        bundle = context_bundle.build_context_bundle(context)
        assert ANIMATION_TOOLS.issubset(set(bundle["available_tools"]))
        tool_names = {tool["name"] for tool in agent_tools.blender_tool_definitions()}
        assert ANIMATION_TOOLS.issubset(tool_names)
        contract_names = set(bridge_protocol.TOOL_CONTRACTS)
        assert ANIMATION_TOOLS.issubset(contract_names)
        assert not tool_dispatcher._looks_like_animation_intent("Create an architectural arch from cubes.")
        assert tool_dispatcher._looks_like_animation_intent("Make the cube bounce twice.")

        script_runner.clear_external_script_trust_for_all_scenes(
            status=script_runner.NO_EXTERNAL_TRUST_STATUS,
            audit_action="smoke_animation_routing_clear",
        )
        guarded_script = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "draft_script",
                {
                    "intent": "Animate the cube with a two-bounce keyframe sequence.",
                    "expected_changes": "Cube bounces twice with smaller squash/stretch poses.",
                    "risk_level": "low",
                    "code": "print('animation fallback should not run before workflow')",
                },
            )
        )
        assert guarded_script["ok"] is False, guarded_script
        assert guarded_script["code"] == "animation_workflow_required", guarded_script
        assert "run_animation_workflow" in guarded_script["recommended_tools"], guarded_script

        explicit_gap_script = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "draft_script",
                {
                    "intent": "Animate the cube with a custom helper gap; helper tools cannot express this diagnostic fallback.",
                    "expected_changes": "A diagnostic custom property is set; no animation helper can express the exact test condition.",
                    "risk_level": "low",
                    "code": "scene['claude_animation_helper_gap_smoke'] = 'staged'",
                },
            )
        )
        assert explicit_gap_script["ok"], explicit_gap_script
        assert explicit_gap_script["requires_user_approval"] is True, explicit_gap_script
        rejected_gap_script = script_runner.reject_pending_script(context)
        assert rejected_gap_script["ok"], rejected_gap_script

        preflight_brief = _execute(
            context,
            "create_animation_brief",
            {"prompt": "Make the cube bounce twice and get smaller."},
        )
        assert preflight_brief["brief"]["timing"]["requested_count"] == 2, preflight_brief
        assert not preflight_brief["brief"].get("clarification_needed"), preflight_brief
        assert not animation_brief.should_create_brief("Give me a brief summary of this scene.")

        ambiguous = _execute(context, "create_animation_brief", {"prompt": "Animate the cube."})
        question = animation_brief.clarification_question(ambiguous["brief"])
        assert question.startswith("What action"), question
        assert ambiguous["brief"]["clarification_needed"] is True, ambiguous

        brief = _execute(
            context,
            "create_animation_brief",
            {
                "prompt": "Make the cube bounce three times and get smaller each bounce.",
                "subject_names": ["Cube"],
                "frame_start": 1,
                "frame_end": 72,
                "success_criteria": ["End smaller than it started."],
            },
        )
        contract = brief["brief"]
        assert contract["contract_id"].startswith("anim-"), contract
        assert contract["subjects"][0]["name"] == "Cube", contract
        assert contract["action"] == "bounce", contract
        assert contract["timing"]["requested_count"] == 3, contract
        assert "scale decreases over the animation" in contract["secondary_actions"], contract
        assert contract["ready_for_generation"] is True, contract
        assert contract["validation_plan"]["check_contact_physics"] is True, contract
        assert any("exactly 3" in item for item in contract["success_criteria"]), contract
        assert not scene.claude_blender.pending_preview

        workflow = _execute(
            context,
            "plan_animation_workflow",
            {
                "prompt": "Make the cube bounce twice over 72 frames, getting smaller each bounce. Check it against the brief and leave it as a preview.",
                "subject_names": ["Cube"],
                "frame_start": 1,
                "frame_end": 72,
                "mode": "full",
            },
        )
        plan = workflow["workflow"]
        assert plan["status"] == "ready", plan
        assert plan["brief"]["action"] == "bounce", plan
        assert plan["brief"]["timing"]["requested_count"] == 2, plan
        assert plan["timing_chart"]["frame_end"] == 72, plan
        call_names = [call["name"] for call in plan["next_tool_calls"]]
        assert "create_progressive_bounce_animation" in call_names, plan
        assert "animate_object_bounce" not in call_names, plan
        assert "analyze_animation_principles" in call_names, plan
        assert "capture_animation_playblast" in call_names, plan
        assert "review_playblast_against_brief" in call_names, plan
        assert "draft_script" not in call_names, plan
        assert plan["script_fallback_policy"]["allowed"] is True, plan
        assert not any("scale" in item for item in plan["generation_blockers"]), plan
        assert not scene.claude_blender.pending_preview

        move_workflow = _execute(
            context,
            "plan_animation_workflow",
            {
                "prompt": "Move the cube across the frame over 48 frames with a camera shot.",
                "subject_names": ["Cube"],
                "frame_start": 1,
                "frame_end": 48,
                "mode": "full",
            },
        )
        move_plan = move_workflow["workflow"]
        move_call_names = [call["name"] for call in move_plan["next_tool_calls"]]
        assert "create_directed_animation_shot" in move_call_names, move_plan
        assert not move_plan["generation_blockers"], move_plan

        workflow_run = _execute(
            context,
            "run_animation_workflow",
            {
                "prompt": "Make the cube bounce twice over 72 frames, getting smaller each bounce. Check it against the brief and leave it as a preview.",
                "subject_names": ["Cube"],
                "frame_start": 1,
                "frame_end": 72,
                "mode": "full",
                "capture_playblast": False,
                "apply_repairs": False,
            },
        )
        assert workflow_run["result_type"] == "live_preview_helper_workflow", workflow_run
        assert workflow_run["status"] == "generated_needs_repair", workflow_run
        assert workflow_run["pending_preview"] is True, workflow_run
        progressive_exec = next(item for item in workflow_run["executed"] if item["tool"] == "create_progressive_bounce_animation")
        assert progressive_exec["ok"] is True, workflow_run
        assert progressive_exec["result"]["scale_keys"][-1]["factor"] == 0.6, progressive_exec
        assert not any("scale" in item for item in workflow_run["generation_blockers"]), workflow_run
        assert workflow_run["review"]["principles"]["ok"] is True, workflow_run
        assert workflow_run["review"]["comparison"]["ok"] is True, workflow_run
        assert workflow_run["review"]["repair_plan"]["repair_operations"], workflow_run
        assert workflow_run["review"]["principles"]["principle_checks"][0]["secondary_action"] == "pass", workflow_run
        assert not any(item.get("principle") == "secondary_action" for item in workflow_run["review"]["findings"]), workflow_run
        reverted_workflow = _execute(context, "revert_preview", {})
        assert not reverted_workflow.get("rollback_warnings"), reverted_workflow
        assert not scene.claude_blender.pending_preview
        _select_object(context, cube)

        task_run = _execute(
            context,
            "run_animation_task",
            {
                "prompt": "Make the selected cube bounce twice over 72 frames, getting smaller each bounce.",
            },
        )
        assert task_run["invoked_workflow_tool"] == "run_animation_workflow", task_run
        assert task_run["workflow"]["brief"]["action"] == "bounce", task_run
        assert task_run["workflow"]["brief"]["timing"]["requested_count"] == 2, task_run
        assert task_run["pending_preview"] is True, task_run
        reverted_task = _execute(context, "revert_preview", {})
        assert not reverted_task.get("rollback_warnings"), reverted_task
        assert not scene.claude_blender.pending_preview
        _select_object(context, cube)

        review_task = _execute(
            context,
            "run_animation_task",
            {
                "prompt": "Review this bounce animation for spacing and contact.",
            },
        )
        assert review_task["invoked_workflow_tool"] == "run_animation_workflow", review_task
        assert review_task["workflow"]["mode"] == "review", review_task
        assert review_task["status"] != "needs_clarification", review_task
        assert review_task["executed"] == [], review_task
        review_call_names = [call["name"] for call in review_task["workflow"]["next_tool_calls"]]
        assert "analyze_animation_principles" in review_call_names, review_task
        assert "review_playblast_against_brief" in review_call_names, review_task
        assert review_task["review"]["principles"]["ok"] is True, review_task
        assert review_task["workflow"]["script_fallback_policy"]["allowed"] is False, review_task

        ambiguous_workflow = _execute(
            context,
            "plan_animation_workflow",
            {
                "prompt": "Animate the cube.",
                "subject_names": ["Cube"],
                "mode": "generate",
            },
        )
        ambiguous_plan = ambiguous_workflow["workflow"]
        assert ambiguous_plan["status"] == "needs_clarification", ambiguous_plan
        assert ambiguous_plan["next_tool_calls"] == [], ambiguous_plan
        assert ambiguous_plan["script_fallback_policy"]["allowed"] is False, ambiguous_plan
        blocked_after_ambiguous = json.loads(
            tool_dispatcher.execute_tool(
                context,
                "draft_script",
                {
                    "intent": "Animate the cube with a quick Python fallback after an ambiguous workflow.",
                    "expected_changes": "No script should be staged because the workflow still needs clarification.",
                    "risk_level": "low",
                    "code": "print('ambiguous animation fallback should stay blocked')",
                },
            )
        )
        assert blocked_after_ambiguous["ok"] is False, blocked_after_ambiguous
        assert blocked_after_ambiguous["code"] == "animation_workflow_required", blocked_after_ambiguous
        assert blocked_after_ambiguous["animation_workflow_seen"] is True, blocked_after_ambiguous

        no_count = _execute(
            context,
            "create_animation_brief",
            {"prompt": "Make one cube bounce.", "subject_names": ["Cube"], "frame_start": 1, "frame_end": 24},
        )["brief"]
        assert no_count["action"] == "bounce", no_count
        assert no_count["timing"]["requested_count"] is None, no_count

        inflected = _execute(
            context,
            "create_animation_brief",
            {"prompt": "The cube bounces twice.", "subject_names": ["Cube"], "frame_start": 1, "frame_end": 24},
        )["brief"]
        assert inflected["action"] == "bounce", inflected
        assert inflected["timing"]["requested_count"] == 2, inflected

        chart = _execute(
            context,
            "create_timing_chart",
            {
                "prompt": "Make the cube bounce twice and get smaller.",
                "subject_names": ["Cube"],
                "frame_start": 1,
                "frame_end": 48,
            },
        )["chart"]
        assert chart["ready_for_blocking"] is True, chart
        assert chart["action"] == "bounce", chart
        assert len(chart["key_poses"]) >= 5, chart
        assert any(pose["role"] == "contact" for pose in chart["key_poses"]), chart

        blocked = _execute(
            context,
            "block_key_poses",
            {
                "object_names": ["Cube"],
                "poses": [
                    {"frame": 1, "location": [0.0, 0.0, 0.0], "scale": [1.0, 1.0, 1.0]},
                    {"frame": 12, "location": [0.0, 0.0, 2.0], "scale": [0.9, 0.9, 0.9]},
                    {"frame": 24, "location": [0.0, 0.0, 0.0], "scale": [0.8, 0.8, 0.8], "hold_frames": 2},
                ],
                "interpolation": "CONSTANT",
            },
        )
        block_action = bpy.data.actions[blocked["objects"][0]["action"]]
        assert _action_keyframes(block_action) == [1.0, 12.0, 24.0, 26.0], blocked
        assert scene.frame_end >= 26, blocked

        breakdown = _execute(
            context,
            "add_breakdown_pose",
            {
                "object_names": ["Cube"],
                "frame": 6,
                "previous_frame": 1,
                "next_frame": 12,
                "factor": 0.5,
                "paths": ["location", "scale"],
                "interpolation": "CONSTANT",
            },
        )
        assert breakdown["objects"][0]["values"]["location"] == [0.0, 0.0, 1.0], breakdown
        assert 6.0 in _action_keyframes(block_action), breakdown

        hold = _execute(
            context,
            "set_pose_hold",
            {
                "object_names": ["Cube"],
                "frame": 12,
                "hold_frames": 3,
                "paths": ["location"],
            },
        )
        assert hold["objects"][0]["hold_frame"] == 15, hold
        assert 15.0 in _action_keyframes(block_action), hold

        arc = _execute(
            context,
            "create_motion_arc",
            {"object_names": ["Cube"], "frame_start": 1, "frame_end": 24, "sample_step": 6},
        )
        assert arc["arcs"][0]["arc_object"] in bpy.data.objects, arc
        assert arc["arcs"][0]["sample_count"] >= 5, arc

        arc_analysis = _execute(
            context,
            "analyze_motion_arcs",
            {"object_names": ["Cube"], "frame_start": 1, "frame_end": 24, "max_samples": 8},
        )
        assert arc_analysis["objects"][0]["path_length"] > 0, arc_analysis

        spacing_analysis = _execute(context, "analyze_fcurve_spacing", {"object_names": ["Cube"], "paths": ["location"]})
        assert spacing_analysis["objects"][0]["keyframes"], spacing_analysis
        assert spacing_analysis["objects"][0]["segments"], spacing_analysis

        pose_analysis = _execute(context, "analyze_pose_clarity", {"object_names": ["Cube"]})
        assert pose_analysis["objects"][0]["pose_count"] >= 4, pose_analysis
        assert pose_analysis["objects"][0]["holds"], pose_analysis

        principles = _execute(
            context,
            "analyze_animation_principles",
            {
                "object_names": ["Cube"],
                "brief": contract,
                "timing_chart": chart,
                "frame_start": 1,
                "frame_end": 48,
            },
        )
        assert principles["brief_contract_id"] == contract["contract_id"], principles
        assert principles["principle_checks"][0]["squash_stretch"] == "pass", principles
        assert any(item["principle"] == "anticipation" for item in principles["findings"]), principles

        samples = _execute(
            context,
            "sample_animation_state",
            {"object_names": ["Cube"], "frame_start": 1, "frame_end": 24, "sample_step": 12},
        )
        assert samples["sampled_frames"] == [1, 13, 24], samples
        assert samples["frames"][0]["objects"][0]["name"] == "Cube", samples

        contact = _execute(
            context,
            "analyze_contact_sliding",
            {
                "object_names": ["Cube"],
                "frame_start": 1,
                "frame_end": 26,
                "sample_step": 12,
                "contact_z": -1.0,
                "contact_tolerance": 0.05,
            },
        )
        assert "Cube" in contact["contacts"], contact

        collisions = _execute(
            context,
            "analyze_collision_penetration",
            {"object_names": ["Cube"], "frame_start": 1, "frame_end": 24, "sample_step": 12},
        )
        assert collisions["sampled_frames"] == [1, 13, 24], collisions

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(2.0, 0.0, -1.05))
        support = context.object
        support.name = "Agent Bridge Off Support"
        support.scale = (0.5, 0.5, 0.05)
        context.view_layer.update()
        try:
            center = _execute(
                context,
                "analyze_center_of_mass",
                {
                    "object_names": ["Cube"],
                    "support_object_names": ["Agent Bridge Off Support"],
                    "frame_start": 1,
                    "frame_end": 1,
                    "sample_step": 1,
                    "support_margin": 0.0,
                    "contact_tolerance": 0.2,
                },
            )
            assert center["support_object_names"] == ["Agent Bridge Off Support"], center
            assert any(item.get("requirement") == "center_of_mass" for item in center["findings"]), center
        finally:
            bpy.data.objects.remove(support, do_unlink=True)

        bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0.7, -0.7, -0.425))
        balance_subject = context.object
        balance_subject.name = "Agent Bridge Balance Subject"
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, -0.55), rotation=(0.0, 0.0, 0.7853981633974483))
        rotated_support = context.object
        rotated_support.name = "Agent Bridge Rotated Support"
        rotated_support.scale = (2.2, 0.12, 0.05)
        context.view_layer.update()
        try:
            polygon_center = _execute(
                context,
                "analyze_center_of_mass",
                {
                    "object_names": ["Agent Bridge Balance Subject"],
                    "support_object_names": ["Agent Bridge Rotated Support"],
                    "frame_start": 1,
                    "frame_end": 1,
                    "sample_step": 1,
                    "support_margin": 0.0,
                    "contact_tolerance": 0.05,
                },
            )
            polygon_support = polygon_center["support_samples"][0]
            assert polygon_support["support_footprint_method"] == "convex_hull_world_bounds", polygon_center
            assert len(polygon_support["support_footprint_xy"]) >= 4, polygon_center
            polygon_sample = next(item for item in polygon_center["samples"] if item["object"] == "Agent Bridge Balance Subject")
            assert polygon_sample["support_available"] is True, polygon_center
            assert polygon_sample["contact_like"] is True, polygon_center
            assert polygon_sample["center_within_support"] is False, polygon_center
            margin_center = _execute(
                context,
                "analyze_center_of_mass",
                {
                    "object_names": ["Agent Bridge Balance Subject"],
                    "support_object_names": ["Agent Bridge Rotated Support"],
                    "frame_start": 1,
                    "frame_end": 1,
                    "sample_step": 1,
                    "support_margin": 1.0,
                    "contact_tolerance": 0.05,
                },
            )
            margin_sample = next(item for item in margin_center["samples"] if item["object"] == "Agent Bridge Balance Subject")
            assert margin_sample["center_within_support"] is True, margin_center
            assert margin_sample["outside_support_distance"] == 0.0, margin_center
            assert any(
                item.get("requirement") == "center_of_mass"
                and item.get("evidence", {}).get("support_footprint_method") == "convex_hull_world_bounds"
                for item in polygon_center["findings"]
            ), polygon_center
        finally:
            for obj in (balance_subject, rotated_support):
                if obj.name in bpy.data.objects:
                    bpy.data.objects.remove(obj, do_unlink=True)

        bpy.ops.object.armature_add(location=(0.0, 3.0, 0.0))
        weighted_rig = context.object
        weighted_rig.name = "Agent Bridge Weighted Character Rig"
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 3.0, -0.42))
        weighted_foot = context.object
        weighted_foot.name = "Agent Bridge Weighted Foot"
        weighted_foot.scale = (0.25, 0.18, 0.1)
        weighted_foot.parent = weighted_rig
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(1.2, 3.0, 0.05))
        weighted_torso = context.object
        weighted_torso.name = "Agent Bridge Weighted Torso"
        weighted_torso.scale = (0.55, 0.3, 0.8)
        weighted_torso.parent = weighted_rig
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(1.55, 3.0, 0.7))
        weighted_head = context.object
        weighted_head.name = "Agent Bridge Weighted Head"
        weighted_head.scale = (0.35, 0.28, 0.35)
        weighted_head.parent = weighted_rig
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 3.0, -0.55))
        weighted_support = context.object
        weighted_support.name = "Agent Bridge Weighted Support"
        weighted_support.scale = (0.55, 0.5, 0.05)
        context.view_layer.update()
        try:
            weighted_center = _execute(
                context,
                "analyze_center_of_mass",
                {
                    "object_names": [weighted_rig.name],
                    "support_object_names": [weighted_support.name],
                    "frame_start": 1,
                    "frame_end": 1,
                    "sample_step": 1,
                    "support_margin": 0.0,
                    "contact_tolerance": 0.08,
                },
            )
            weighted_sample = next(item for item in weighted_center["samples"] if item["object"] == weighted_rig.name)
            assert weighted_sample["center_method"] == "weighted_child_mesh_bounds", weighted_center
            assert weighted_sample["center_source_count"] == 3, weighted_center
            assert weighted_sample["contact_like"] is True, weighted_center
            assert weighted_sample["center_within_support"] is False, weighted_center
            assert "Agent Bridge Weighted Torso" in weighted_sample["center_source_objects"], weighted_center
            assert any(
                item.get("requirement") == "center_of_mass"
                and item.get("evidence", {}).get("center_method") == "weighted_child_mesh_bounds"
                for item in weighted_center["findings"]
            ), weighted_center
        finally:
            for obj in (weighted_foot, weighted_torso, weighted_head, weighted_support, weighted_rig):
                if obj.name in bpy.data.objects:
                    bpy.data.objects.remove(obj, do_unlink=True)

        framing = _execute(
            context,
            "analyze_camera_framing",
            {"object_names": ["Cube"], "camera_name": "Camera", "frame_start": 1, "frame_end": 24, "sample_step": 12},
        )
        assert framing["samples"], framing
        assert framing["samples"][0]["camera"] == "Camera", framing

        physics = _execute(
            context,
            "analyze_motion_physics",
            {"object_names": ["Cube"], "frame_start": 1, "frame_end": 24, "sample_step": 12, "max_speed": 1.0, "max_acceleration": 1.0},
        )
        assert physics["objects"][0]["speed_segments"], physics
        assert any(item.get("requirement") == "motion_physics" for item in physics["findings"]), physics

        comparison = _execute(
            context,
            "compare_animation_to_brief",
            {"brief": contract, "frame_start": 1, "frame_end": 24},
        )
        assert comparison["brief_contract_id"] == contract["contract_id"], comparison
        assert "motion_physics" in comparison["validation_results"], comparison
        assert not any(item.get("requirement") == "action" for item in comparison["findings"]), comparison

        unresolved_comparison = _execute(
            context,
            "compare_animation_to_brief",
            {
                "brief": {
                    "contract_id": "anim-unresolved-smoke",
                    "subjects": [],
                    "subject_names": [],
                    "action": "bounce",
                    "timing": {"frame_start": 1, "frame_end": 24},
                    "validation_plan": {"check_contact_physics": True},
                }
            },
        )
        assert unresolved_comparison["status"] == "needs_repair", unresolved_comparison
        assert unresolved_comparison["sample_summary"] == {}, unresolved_comparison
        assert unresolved_comparison["validation_results"] == {}, unresolved_comparison
        assert any(item.get("requirement") == "subject" for item in unresolved_comparison["findings"]), unresolved_comparison

        playblast_review = _execute(
            context,
            "review_playblast_against_brief",
            {
                "brief": contract,
                "playblast": {
                    "available": True,
                    "playblast_id": "smoke",
                    "sampled_frames": [1, 12, 24],
                    "frames": [
                        {"frame": 1, "available": True, "path": "", "resource_uri": "blender://playblasts/smoke/frames/1", "size_bytes": 1, "width": 64, "height": 64},
                        {"frame": 12, "available": True, "path": "", "resource_uri": "blender://playblasts/smoke/frames/12", "size_bytes": 1, "width": 64, "height": 64},
                        {"frame": 24, "available": True, "path": "", "resource_uri": "blender://playblasts/smoke/frames/24", "size_bytes": 1, "width": 64, "height": 64},
                    ],
                },
            },
        )
        assert playblast_review["playblast_id"] == "smoke", playblast_review
        assert playblast_review["visual_review"]["frames"][0]["resource_uri"].endswith("/1"), playblast_review
        assert playblast_review["visual_review"]["frame_coverage"]["covers_start"] is True, playblast_review
        assert playblast_review["visual_review"]["frame_coverage"]["covers_end"] is False, playblast_review
        coverage_capture = next(item for item in playblast_review["repair_operations"] if item["tool"] == "capture_animation_playblast")
        assert coverage_capture["target_frame_range"] == [24, 72], playblast_review
        assert coverage_capture["target_frames"] == [1, 12, 24, 72], playblast_review

        visual_dir = tempfile.mkdtemp(prefix="claude-blender-playblast-")
        static_frames = []
        for frame_number in (1, 36, 72):
            path = os.path.join(visual_dir, f"frame-{frame_number:04d}.png")
            _write_pattern_png(path)
            static_frames.append(
                {
                    "frame": frame_number,
                    "available": True,
                    "path": path,
                    "resource_uri": f"blender://playblasts/static/frames/{frame_number}",
                    "size_bytes": os.path.getsize(path),
                    "width": 8,
                    "height": 8,
                }
            )
        static_review = _execute(
            context,
            "review_playblast_against_brief",
            {
                "brief": contract,
                "playblast": {
                    "available": True,
                    "playblast_id": "static",
                    "sampled_frames": [1, 36, 72],
                    "frames": static_frames,
                },
            },
        )
        motion_evidence = static_review["visual_review"]["motion_evidence"]
        image_interpretation = static_review["visual_review"]["image_interpretation"]
        assert motion_evidence["digest_frame_count"] == 3, static_review
        assert motion_evidence["max_grid_delta"] == 0.0, static_review
        assert image_interpretation["interpreted_image_count"] == 3, static_review
        assert image_interpretation["framing_reads"].get("cropped_subject") == 3, static_review
        assert static_review["visual_review"]["frames"][0]["image_digest"]["visual_subject"]["bbox_normalized"], static_review
        assert any("clear motion" in item["message"] for item in static_review["findings"]), static_review
        static_block = next(item for item in static_review["repair_operations"] if item["tool"] == "block_key_poses")
        assert static_block["target_frames"] == [1, 36, 72], static_review
        assert static_block["target_frame_range"] == [1, 72], static_review
        assert all(item["tool_call"]["name"] == item["tool"] for item in static_review["repair_operations"]), static_review
        assert any(item.get("target_frames") == [1, 36, 72] for item in static_review["suggested_tool_calls"]), static_review

        visual_count_frames = []
        for frame_number, center_y in ((1, 12), (12, 4), (24, 12), (36, 4), (48, 12), (60, 12), (72, 12)):
            path = os.path.join(visual_dir, f"visual-count-{frame_number:04d}.png")
            _write_subject_png(path, center_y=center_y)
            visual_count_frames.append(
                {
                    "frame": frame_number,
                    "available": True,
                    "path": path,
                    "resource_uri": f"blender://playblasts/visual-count/frames/{frame_number}",
                    "size_bytes": os.path.getsize(path),
                    "width": 16,
                    "height": 16,
                }
            )
        visual_count_review = _execute(
            context,
            "review_playblast_against_brief",
            {
                "brief": contract,
                "playblast": {
                    "available": True,
                    "playblast_id": "visual-count",
                    "sampled_frames": [1, 12, 24, 36, 48, 60, 72],
                    "frames": visual_count_frames,
                },
            },
        )
        action_count_evidence = visual_count_review["visual_review"]["motion_evidence"]["action_count_evidence"]
        assert action_count_evidence["available"] is True, visual_count_review
        assert action_count_evidence["requested_count"] == 3, visual_count_review
        assert action_count_evidence["detected_count"] == 2, visual_count_review
        assert action_count_evidence["detected_count_frames"] == [12, 36], visual_count_review
        assert action_count_evidence["confidence"] in {"medium", "high"}, visual_count_review
        assert any(
            item.get("requirement") == "action_count" and item.get("evidence", {}).get("source") == "visual_playblast"
            for item in visual_count_review["findings"]
        ), visual_count_review
        assert any(item["tool"] == "create_progressive_bounce_animation" for item in visual_count_review["repair_operations"]), visual_count_review

        sampled_review_frames = []
        sampled_motion = (
            (1, 58, 138),
            (37, 92, 76),
            (72, 128, 138),
            (108, 158, 92),
            (143, 184, 138),
            (179, 212, 103),
            (214, 238, 138),
            (250, 266, 138),
        )
        sampled_contract = dict(contract)
        sampled_contract["timing"] = dict(contract.get("timing") or {})
        sampled_contract["timing"]["frame_end"] = 250
        for frame_number, center_x, center_y in sampled_motion:
            path = os.path.join(visual_dir, f"sampled-review-{frame_number:04d}.png")
            _write_sampled_playblast_png(path, center_x=center_x, center_y=center_y)
            sampled_review_frames.append(
                {
                    "frame": frame_number,
                    "captured_scene_frame": frame_number,
                    "available": True,
                    "path": path,
                    "resource_uri": f"blender://playblasts/sampled-review/frames/{frame_number}",
                    "size_bytes": os.path.getsize(path),
                    "width": 320,
                    "height": 180,
                }
            )
        sampled_visual_review = _execute(
            context,
            "review_playblast_against_brief",
            {
                "prompt": "review this bounce animation for spacing and contact",
                "brief": sampled_contract,
                "playblast": {
                    "available": True,
                    "playblast_id": "sampled-review",
                    "sampled_frames": [item[0] for item in sampled_motion],
                    "frames": sampled_review_frames,
                },
            },
        )
        sampled_motion_evidence = sampled_visual_review["visual_review"]["motion_evidence"]
        assert sampled_motion_evidence["digest_frame_count"] == len(sampled_motion), sampled_visual_review
        assert sampled_motion_evidence["max_grid_delta"] > 0.0, sampled_visual_review
        assert sampled_visual_review["visual_review"]["image_interpretation"]["interpreted_image_count"] == len(sampled_motion), sampled_visual_review
        assert all(
            frame["image_digest"]["available"] is True
            for frame in sampled_visual_review["visual_review"]["frames"]
        ), sampled_visual_review

        original_digest_budget = animation_analysis.VISUAL_DIGEST_MAX_TOTAL_PIXELS
        try:
            animation_analysis.VISUAL_DIGEST_MAX_TOTAL_PIXELS = 100_000
            budgeted_visual_review = _execute(
                context,
                "review_playblast_against_brief",
                {
                    "prompt": "review this bounce animation for spacing and contact",
                    "brief": sampled_contract,
                    "playblast": {
                        "available": True,
                        "playblast_id": "sampled-review-budgeted",
                        "sampled_frames": [item[0] for item in sampled_motion],
                        "frames": sampled_review_frames,
                    },
                },
            )
        finally:
            animation_analysis.VISUAL_DIGEST_MAX_TOTAL_PIXELS = original_digest_budget
        budgeted_frames = budgeted_visual_review["visual_review"]["frames"]
        skipped_digests = [
            frame.get("image_digest") or {}
            for frame in budgeted_frames
            if (frame.get("image_digest") or {}).get("skipped")
        ]
        assert budgeted_visual_review["visual_review"]["motion_evidence"]["digest_frame_count"] == 1, budgeted_visual_review
        assert skipped_digests, budgeted_visual_review
        assert all(digest.get("available") is False for digest in skipped_digests), budgeted_visual_review
        assert any(
            "pixel inspection was skipped" in item.get("message", "")
            for item in budgeted_visual_review["findings"]
        ), budgeted_visual_review

        inspection_path = os.path.join(visual_dir, "inspection-front-below.png")
        _write_pattern_png(inspection_path)
        inspection_review = _execute(
            context,
            "review_inspection_renders_against_brief",
            {
                "prompt": "Inspect the cube underside and landing gear detail before repair.",
                "brief": contract,
                "inspection_render": {
                    "available": True,
                    "render_id": "inspect-smoke",
                    "metadata_uri": "blender://inspection-renders/inspect-smoke/metadata",
                    "object_names": ["Cube"],
                    "images": [
                        {
                            "image_id": "Cube-front_below",
                            "object": "Cube",
                            "view": "front_below",
                            "available": True,
                            "path": inspection_path,
                            "resource_uri": "blender://inspection-renders/inspect-smoke/images/Cube-front_below",
                            "size_bytes": os.path.getsize(inspection_path),
                            "width": 8,
                            "height": 8,
                        }
                    ],
                },
            },
        )
        assert inspection_review["visual_detail_review"]["missing_views"] == ["underside", "side"], inspection_review
        assert inspection_review["visual_detail_review"]["image_interpretation"]["interpreted_image_count"] == 1, inspection_review
        assert inspection_review["visual_detail_review"]["image_interpretation"]["cropped_image_count"] == 1, inspection_review
        inspection_capture = next(
            item
            for item in inspection_review["repair_operations"]
            if item["tool"] == "capture_object_inspection_renders" and item["arguments"]["views"] == ["underside", "side"]
        )
        assert inspection_capture["mutates_scene"] is False, inspection_review
        assert inspection_capture["arguments"]["object_names"] == ["Cube"], inspection_review
        assert inspection_capture["arguments"]["views"] == ["underside", "side"], inspection_review

        repair_plan = _execute(
            context,
            "repair_animation_from_findings",
            {
                "findings": [
                    {"severity": "warning", "message": "Contact points slide across the ground plane."},
                    {"severity": "warning", "requirement": "motion_physics", "message": "Sampled acceleration spike may be physically implausible."},
                    {
                        "severity": "warning",
                        "requirement": "action_count",
                        "message": "Detected repeated action count does not match the requested count.",
                        "evidence": {"requested_count": 2, "detected_count": 1, "sampled_frames": [1, 36, 72]},
                    },
                ],
                "brief": contract,
            },
        )
        count_repair = next(item for item in repair_plan["repair_operations"] if item["tool"] == "create_progressive_bounce_animation")
        assert repair_plan["suggested_tool_calls"][0]["tool"] == "create_progressive_bounce_animation", repair_plan
        assert repair_plan["repair_operations"][0]["tool"] == "create_progressive_bounce_animation", repair_plan
        assert count_repair["metadata"]["replaces_existing_action"] is True, repair_plan
        assert count_repair["source_finding_index"] == 2, repair_plan
        contact_advisory = next(
            item
            for item in repair_plan["repair_operations"]
            if item.get("source_finding_index") == 0 and item["tool"] == "get_rigging_details"
        )
        assert contact_advisory["mutates_scene"] is False, repair_plan
        assert contact_advisory["metadata"]["advisory"] is True, repair_plan
        assert contact_advisory["metadata"]["needs_user_planning"] is True, repair_plan
        assert any(item["tool"] == "retime_actions" for item in repair_plan["repair_operations"]), repair_plan

        rig_create = _execute(
            context,
            "create_basic_armature",
            {
                "name": "Agent Bridge Rig Repair Armature",
                "location": [3.0, 0.0, 0.0],
                "rotation": [0.0, 0.0, 0.0],
            },
        )
        rig = bpy.data.objects[rig_create["object"]]
        if rig.data and rig.data.bones:
            rig.data.bones[0].name = "CTRL_Main"
            rig.data.bones["CTRL_Main"].use_deform = False
        control_bone = rig.pose.bones.get("CTRL_Main") if rig.pose else None
        if control_bone:
            control_bone.rotation_mode = "QUATERNION"
            control_bone.rotation_quaternion = (0.707107, 0.707107, 0.0, 0.0)
        bpy.ops.mesh.primitive_cube_add(size=0.5, location=(3.0, 0.0, 0.0))
        rig_subject = context.object
        rig_subject.name = "Agent Bridge Rig Repair Subject"
        rig_subject.data.name = "Agent Bridge Rig Repair Subject Mesh"
        rig_subject.parent = rig
        live_preview._record_created_id("object", rig_subject.name)
        live_preview._record_created_id("mesh", rig_subject.data.name)
        context.view_layer.update()
        rig_details = _execute(context, "get_rigging_details", {"object_names": [rig.name], "max_objects": 1})
        rig_armature = next(item for item in rig_details["objects"] if item["name"] == rig.name)
        assert rig_armature["armature"]["control_hints"]["control_candidate_count"] >= 1, rig_details
        rig_brief = {
            "contract_id": "anim-rig-smoke",
            "subjects": [{"name": rig_subject.name}],
            "subject_names": [rig_subject.name],
            "action": "jump",
            "timing": {"frame_start": 1, "frame_end": 24},
        }
        rig_repair_plan = _execute(
            context,
            "repair_animation_from_findings",
            {
                "findings": [
                    {
                        "severity": "warning",
                        "principle": "pose_clarity",
                        "object": rig_subject.name,
                        "frame": 8,
                        "message": "Rig-driven pose clarity needs a held control pose.",
                    }
                ],
                "brief": rig_brief,
            },
        )
        rig_operations = rig_repair_plan["repair_operations"]
        assert rig_operations[0]["tool"] == "get_rigging_details", rig_repair_plan
        assert rig_operations[1]["tool"] == "set_rig_pose_hold", rig_repair_plan
        assert rig_operations[1]["arguments"]["armature_name"] == rig.name, rig_repair_plan
        assert rig_operations[1]["arguments"]["bone_names"] == ["CTRL_Main"], rig_repair_plan
        rig_loop = _execute(
            context,
            "run_animation_repair_loop",
            {
                "brief": rig_brief,
                "repair_operations": rig_operations,
                "allowed_tools": ["get_rigging_details", "set_rig_pose_hold"],
                "max_iterations": 1,
                "max_operations": 2,
                "recapture_after_mutation": False,
            },
        )
        assert [item["tool"] for item in rig_loop["executed_operations"]] == ["get_rigging_details", "set_rig_pose_hold"], rig_loop
        assert rig_loop["pending_preview"] is True, rig_loop
        assert rig.animation_data and rig.animation_data.action, rig_loop
        rig_fcurve_paths = {fcurve.data_path for fcurve in live_preview._iter_action_fcurves(rig.animation_data.action)}
        assert 'pose.bones["CTRL_Main"].location' in rig_fcurve_paths, rig_loop
        assert 'pose.bones["CTRL_Main"].rotation_quaternion' in rig_fcurve_paths, rig_loop
        assert rig_loop["executed_operations"][1]["result"]["bones"][0]["paths"] == ["location", "rotation_quaternion"], rig_loop

        ikfk_create = _execute(
            context,
            "create_basic_armature",
            {
                "name": "Agent Bridge IKFK Repair Armature",
                "location": [5.0, 0.0, 0.0],
                "rotation": [0.0, 0.0, 0.0],
            },
        )
        ikfk_rig = bpy.data.objects[ikfk_create["object"]]
        _select_object(context, ikfk_rig)
        bpy.ops.object.mode_set(mode="EDIT")
        edit_bones = ikfk_rig.data.edit_bones
        upper = edit_bones[0]
        upper.name = "DEF_UpperArm"
        upper.head = (0.0, 0.0, 0.0)
        upper.tail = (0.0, 0.0, 1.0)
        upper.use_deform = True
        forearm = edit_bones.new("DEF_Forearm")
        forearm.head = upper.tail
        forearm.tail = (0.0, 0.0, 2.0)
        forearm.parent = upper
        forearm.use_connect = True
        forearm.use_deform = True
        ik_control = edit_bones.new("CTRL_IK_Hand")
        ik_control.head = (0.6, 0.0, 2.0)
        ik_control.tail = (0.6, 0.0, 2.35)
        ik_control.use_deform = False
        fk_control = edit_bones.new("CTRL_FK_Forearm")
        fk_control.head = (-0.55, 0.0, 1.0)
        fk_control.tail = (-0.55, 0.0, 1.35)
        fk_control.use_deform = False
        pole_control = edit_bones.new("CTRL_Pole_Elbow")
        pole_control.head = (0.0, -0.8, 1.0)
        pole_control.tail = (0.0, -0.8, 1.35)
        pole_control.use_deform = False
        bpy.ops.object.mode_set(mode="POSE")
        forearm_pose = ikfk_rig.pose.bones.get("DEF_Forearm")
        if forearm_pose:
            ik_constraint = forearm_pose.constraints.new(type="IK")
            ik_constraint.name = "IK Hand Target"
            ik_constraint.target = ikfk_rig
            ik_constraint.subtarget = "CTRL_IK_Hand"
            ik_constraint.pole_target = ikfk_rig
            ik_constraint.pole_subtarget = "CTRL_Pole_Elbow"
            ik_constraint.chain_count = 2
        upper_pose = ikfk_rig.pose.bones.get("DEF_UpperArm")
        if upper_pose:
            copy_rotation = upper_pose.constraints.new(type="COPY_ROTATION")
            copy_rotation.name = "FK Forearm Rotation"
            copy_rotation.target = ikfk_rig
            copy_rotation.subtarget = "CTRL_FK_Forearm"
        for name, offset in (("CTRL_IK_Hand", 0.25), ("CTRL_Pole_Elbow", -0.18), ("CTRL_FK_Forearm", 0.0)):
            pose_bone = ikfk_rig.pose.bones.get(name)
            if pose_bone:
                pose_bone.rotation_mode = "QUATERNION"
                pose_bone.location.x = offset
                if name == "CTRL_IK_Hand":
                    pose_bone["IK_FK_local"] = 1.0
        ikfk_rig["IK_FK_Arm_L"] = 1.0
        ikfk_rig.data["left_arm_space_switch"] = 0
        ikfk_rig.data["parent"] = 1
        pose_action = bpy.data.actions.new("Agent Bridge IKFK Repair Pose Library")
        live_preview._record_created_id("action", pose_action.name)
        pose_marker = pose_action.pose_markers.new("Left Hand Contact Repair")
        pose_marker.frame = 10
        ikfk_rig.animation_data_create().action = pose_action
        ik_pose = ikfk_rig.pose.bones.get("CTRL_IK_Hand")
        ik_pose.location.x = 0.0
        ik_pose.keyframe_insert(data_path="location", frame=1)
        ik_pose.location.x = 0.25
        ik_pose.keyframe_insert(data_path="location", frame=10)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.mesh.primitive_cube_add(size=0.45, location=(5.0, 0.0, 0.0))
        ikfk_subject = context.object
        ikfk_subject.name = "Agent Bridge IKFK Repair Subject"
        ikfk_subject.data.name = "Agent Bridge IKFK Repair Subject Mesh"
        ikfk_subject.parent = ikfk_rig
        live_preview._record_created_id("object", ikfk_subject.name)
        live_preview._record_created_id("mesh", ikfk_subject.data.name)
        context.view_layer.update()
        ikfk_brief = {
            "contract_id": "anim-ikfk-repair-smoke",
            "subjects": [{"name": ikfk_subject.name}],
            "subject_names": [ikfk_subject.name],
            "action": "jump",
            "timing": {"frame_start": 1, "frame_end": 32},
        }
        ikfk_plan = _execute(
            context,
            "repair_animation_from_findings",
            {
                "findings": [
                    {
                        "severity": "warning",
                        "principle": "pose_clarity",
                        "requirement": "center_of_mass",
                        "object": ikfk_subject.name,
                        "frame": 10,
                        "message": "Left hand IK contact/support pose needs repair; the elbow pole is drifting.",
                    }
                ],
                "brief": ikfk_brief,
            },
        )
        ikfk_operations = ikfk_plan["repair_operations"]
        assert [item["tool"] for item in ikfk_operations[:5]] == [
            "get_rigging_details",
            "apply_rig_pose_from_action",
            "set_rig_custom_property_keyframes",
            "offset_rig_limb_controls",
            "set_rig_pose_hold",
        ], ikfk_plan
        assert "set_pose_hold" not in [item["tool"] for item in ikfk_operations], ikfk_plan
        ikfk_pose = ikfk_operations[1]
        assert ikfk_pose["arguments"]["armature_name"] == ikfk_rig.name, ikfk_plan
        assert ikfk_pose["arguments"]["action_name"] == pose_action.name, ikfk_plan
        assert ikfk_pose["arguments"]["pose_marker"] == "Left Hand Contact Repair", ikfk_plan
        assert ikfk_pose["arguments"]["bone_names"] == ["CTRL_IK_Hand", "CTRL_Pole_Elbow"], ikfk_plan
        ikfk_switch = ikfk_operations[2]
        assert ikfk_switch["arguments"]["armature_name"] == ikfk_rig.name, ikfk_plan
        assert {item["property_name"] for item in ikfk_switch["arguments"]["property_targets"]} >= {
            "IK_FK_Arm_L",
            "IK_FK_local",
        }, ikfk_plan
        assert not any(item["property_name"] == "left_arm_space_switch" for item in ikfk_switch["arguments"]["property_targets"]), ikfk_plan
        ikfk_offset = ikfk_operations[3]
        assert ikfk_offset["arguments"]["armature_name"] == ikfk_rig.name, ikfk_plan
        assert {item["bone_name"] for item in ikfk_offset["arguments"]["control_offsets"]} >= {"CTRL_IK_Hand", "CTRL_Pole_Elbow"}, ikfk_plan
        assert any(item["property_name"] == "left_arm_space_switch" for item in ikfk_offset["arguments"]["property_targets"]), ikfk_plan
        ikfk_hold = ikfk_operations[4]
        assert ikfk_hold["arguments"]["armature_name"] == ikfk_rig.name, ikfk_plan
        assert ikfk_hold["arguments"]["bone_names"] == ["CTRL_IK_Hand", "CTRL_Pole_Elbow"], ikfk_plan
        assert ikfk_hold["metadata"]["rig_targeting"]["selection_strategy"] == "role_scored", ikfk_plan
        selected_controls = {item["name"]: item for item in ikfk_hold["metadata"]["rig_targeting"]["selected_controls"]}
        assert {"CTRL_IK_Hand", "CTRL_Pole_Elbow"}.issubset(selected_controls), ikfk_plan
        assert "ik" in selected_controls["CTRL_IK_Hand"]["roles"], ikfk_plan
        assert "pole" in selected_controls["CTRL_Pole_Elbow"]["roles"], ikfk_plan
        rig_targeting = ikfk_hold["metadata"]["rig_targeting"]
        switch_properties = rig_targeting["switch_property_candidates"]
        assert any(item["property_name"] == "IK_FK_Arm_L" for item in switch_properties), ikfk_plan
        assert any(item["property_name"] == "IK_FK_local" for item in switch_properties), ikfk_plan
        assert any(item["property_name"] == "left_arm_space_switch" for item in switch_properties), ikfk_plan
        assert not any(item["property_name"] == "parent" for item in switch_properties), ikfk_plan
        assert rig_targeting["ik_fk_switch_review_required"] is True, ikfk_plan
        pose_libraries = rig_targeting["pose_library_candidates"]
        assert any(item["name"] == pose_action.name for item in pose_libraries), ikfk_plan
        assert any(
            marker["name"] == "Left Hand Contact Repair"
            for item in pose_libraries
            for marker in item["pose_markers"]
        ), ikfk_plan
        assert rig_targeting["pose_library_review_required"] is True, ikfk_plan
        assert rig_targeting["planning_notes"], ikfk_plan
        pose_library_details = _execute(
            context,
            "get_rig_pose_library_details",
            {
                "armature_name": ikfk_rig.name,
                "bone_names": ["CTRL_IK_Hand", "CTRL_Pole_Elbow"],
                "max_actions": 10,
            },
        )
        pose_candidates = {item["name"]: item for item in pose_library_details["candidates"]}
        assert pose_action.name in pose_candidates, pose_library_details
        assert pose_candidates[pose_action.name]["applicable"] is True, pose_library_details
        assert pose_candidates[pose_action.name]["matched_bone_count"] >= 1, pose_library_details
        assert any(
            call["tool"] == "apply_rig_pose_marker"
            and call["arguments"]["pose_marker"] == "Left Hand Contact Repair"
            for call in pose_library_details["suggested_tool_calls"]
        ), pose_library_details
        marker_apply = _execute(
            context,
            "apply_rig_pose_marker",
            {
                "armature_name": ikfk_rig.name,
                "pose_marker": "Left Hand Contact Repair",
                "target_frame": 14,
                "hold_frames": 2,
                "bone_names": ["CTRL_IK_Hand"],
                "paths": ["location"],
            },
        )
        assert marker_apply["ok"] is True, marker_apply
        assert marker_apply["source_action"] == pose_action.name, marker_apply
        assert marker_apply["resolved_source_action"] == pose_action.name, marker_apply
        assert marker_apply["pose_marker"] == "Left Hand Contact Repair", marker_apply
        assert marker_apply["applied_bones"][0]["bone"] == "CTRL_IK_Hand", marker_apply
        assert marker_apply["target_frame"] == 14, marker_apply
        ikfk_loop = _execute(
            context,
            "run_animation_repair_loop",
            {
                "brief": ikfk_brief,
                "repair_operations": ikfk_operations,
                "allowed_tools": [
                    "get_rigging_details",
                    "apply_rig_pose_from_action",
                    "set_rig_custom_property_keyframes",
                    "offset_rig_limb_controls",
                    "set_rig_pose_hold",
                ],
                "max_iterations": 1,
                "max_operations": 5,
                "recapture_after_mutation": False,
            },
        )
        assert [item["tool"] for item in ikfk_loop["executed_operations"]] == [
            "get_rigging_details",
            "apply_rig_pose_from_action",
            "set_rig_custom_property_keyframes",
            "offset_rig_limb_controls",
            "set_rig_pose_hold",
        ], ikfk_loop
        ikfk_fcurve_paths = {fcurve.data_path for fcurve in live_preview._iter_action_fcurves(ikfk_rig.animation_data.action)}
        assert '["IK_FK_Arm_L"]' in ikfk_fcurve_paths, ikfk_loop
        assert 'pose.bones["CTRL_IK_Hand"]["IK_FK_local"]' in ikfk_fcurve_paths, ikfk_loop
        assert 'pose.bones["CTRL_IK_Hand"].location' in ikfk_fcurve_paths, ikfk_loop
        assert 'pose.bones["CTRL_Pole_Elbow"].location' in ikfk_fcurve_paths, ikfk_loop
        ikfk_data_fcurve_paths = {fcurve.data_path for fcurve in live_preview._iter_action_fcurves(ikfk_rig.data.animation_data.action)}
        assert '["left_arm_space_switch"]' in ikfk_data_fcurve_paths, ikfk_loop
        clip_result = _execute(
            context,
            "apply_rig_action_clip",
            {
                "armature_name": ikfk_rig.name,
                "action_name": pose_action.name,
                "frame_start": 20,
                "frame_end": 28,
                "interpolation": "CONSTANT",
            },
        )
        assert clip_result["source_action"] == pose_action.name, clip_result
        assert clip_result["applied_action"] != pose_action.name, clip_result
        assert ikfk_rig.animation_data.action.name == clip_result["applied_action"], clip_result
        clip_frames = sorted(
            round(point.co.x)
            for fcurve in live_preview._iter_action_fcurves(ikfk_rig.animation_data.action)
            for point in fcurve.keyframe_points
        )
        assert clip_frames[0] == 20 and clip_frames[-1] == 28, clip_result
        partial_clip_result = _execute(
            context,
            "apply_rig_action_clip",
            {
                "armature_name": ikfk_rig.name,
                "action_name": pose_action.name,
                "source_frame_start": 1,
                "source_frame_end": 10,
                "frame_start": 40,
                "frame_end": 44,
                "interpolation": "CONSTANT",
            },
        )
        assert partial_clip_result["source_frame_start"] == 1.0, partial_clip_result
        assert partial_clip_result["source_frame_end"] == 10.0, partial_clip_result
        partial_clip_frames = sorted(
            round(point.co.x)
            for fcurve in live_preview._iter_action_fcurves(ikfk_rig.animation_data.action)
            for point in fcurve.keyframe_points
        )
        assert partial_clip_frames[0] == 40 and partial_clip_frames[-1] == 44, partial_clip_result
        _select_object(context, cube)

        retime_disabled_loop = _execute(
            context,
            "run_animation_repair_loop",
            {
                "brief": contract,
                "repair_operations": [item for item in repair_plan["repair_operations"] if item["tool"] == "retime_actions"][:1],
                "apply_mutating_repairs": False,
                "max_iterations": 1,
                "max_operations": 1,
            },
        )
        assert retime_disabled_loop["executed_count"] == 0, retime_disabled_loop
        assert "mutating repairs are disabled" in retime_disabled_loop["skipped_operations"][0]["reason"], retime_disabled_loop

        widened_loop = _execute(
            context,
            "run_animation_repair_loop",
            {
                "brief": contract,
                "repair_operations": [{"tool": "set_current_frame", "arguments": {"frame": 12}}],
                "allowed_tools": ["set_current_frame"],
                "max_iterations": 1,
                "max_operations": 1,
            },
        )
        assert widened_loop["executed_count"] == 0, widened_loop
        assert "not in allowed_tools" in widened_loop["skipped_operations"][0]["reason"], widened_loop

        mutating_lie_loop = _execute(
            context,
            "run_animation_repair_loop",
            {
                "brief": contract,
                "repair_operations": [
                    {
                        "tool": "set_pose_hold",
                        "arguments": {"object_names": ["Cube"], "frame": 12, "hold_frames": 1, "paths": ["location"]},
                        "mutates_scene": False,
                    }
                ],
                "apply_mutating_repairs": False,
                "max_iterations": 1,
                "max_operations": 1,
            },
        )
        assert mutating_lie_loop["executed_count"] == 0, mutating_lie_loop
        assert "mutating repairs are disabled" in mutating_lie_loop["skipped_operations"][0]["reason"], mutating_lie_loop

        repair_loop = _execute(
            context,
            "run_animation_repair_loop",
            {
                "brief": contract,
                "findings": [{"severity": "warning", "message": "Contact points slide across the ground plane."}],
                "repair_operations": repair_plan["repair_operations"],
                "max_iterations": 1,
                "max_operations": 1,
                "recapture_after_mutation": False,
            },
        )
        assert repair_loop["executed_operations"][0]["tool"] == "create_progressive_bounce_animation", repair_loop
        assert repair_loop["executed_operations"][0]["ok"] is True, repair_loop
        assert repair_loop["final_review"]["ok"] is True, repair_loop
        assert repair_loop["mutates_scene"] is True, repair_loop
        assert repair_loop["pending_preview"] is True, repair_loop

        bounce = _execute(
            context,
            "animate_object_bounce",
            {
                "object_name": "Cube",
                "frame_start": 1,
                "frame_end": 48,
                "axis": "Z",
                "distance": 2.5,
                "cycles": 2,
            },
        )
        cube_action = bpy.data.actions[bounce["action"]]
        assert _action_keyframes(cube_action) == [float(frame) for frame in bounce["frames"]]

        material_result = _execute(
            context,
            "animate_material_property",
            {
                "object_name": "Cube",
                "property_name": "emission_strength",
                "frame_start": 1,
                "frame_end": 48,
                "value_start": 0.0,
                "value_end": 3.0,
            },
        )
        material = bpy.data.materials[material_result["material"]]
        assert material.node_tree.animation_data and material.node_tree.animation_data.action
        assert material.node_tree.animation_data.action.name == material_result["action"]

        light_result = _execute(
            context,
            "animate_light_property",
            {
                "light_name": "Light",
                "property_name": "energy",
                "frame_start": 1,
                "frame_end": 48,
                "value_start": 100.0,
                "value_end": 700.0,
            },
        )
        assert light.data.animation_data and light.data.animation_data.action
        assert light.data.animation_data.action.name == light_result["action"]

        follow = _execute(
            context,
            "create_follow_path_animation",
            {
                "object_name": "Camera",
                "path_name": "Agent Bridge Camera Motion Path",
                "path_points": [[-4.0, -4.0, 3.0], [0.0, -6.0, 4.0], [4.0, -4.0, 3.0]],
                "frame_start": 1,
                "frame_end": 48,
                "constraint_name": "Agent Bridge Camera Follow Path",
            },
        )
        assert follow["path"] in bpy.data.objects
        assert camera.constraints.get("Agent Bridge Camera Follow Path")
        assert camera.animation_data and camera.animation_data.action

        details = _execute(context, "get_animation_details", {"object_names": ["Cube", "Camera", "Light"], "max_actions": 12})
        objects_by_name = {item["name"]: item for item in details["objects"]}
        assert objects_by_name["Cube"]["object_animation"]["action"] == bounce["action"], details
        assert objects_by_name["Cube"]["materials"][0]["node_tree_animation"]["action"] == material_result["action"], details
        assert any(constraint["type"] == "FOLLOW_PATH" for constraint in objects_by_name["Camera"]["constraints"]), details
        assert objects_by_name["Light"]["data_animation"]["action"] == light_result["action"], details
        assert any(
            owner.get("kind") == "material_node_tree" and owner.get("material") == material_result["material"]
            for action in details["actions"]
            for owner in action["owners"]
        ), details
        assert any(
            owner.get("kind") == "object" and owner.get("name") == "Camera"
            for action in details["actions"]
            for owner in action["owners"]
        ), details
        assert any(
            owner.get("kind") == "object_data" and owner.get("object") == "Light"
            for action in details["actions"]
            for owner in action["owners"]
        ), details

        state = scene.claude_blender
        assert state.pending_preview
        assert state.pending_preview_summary

        reverted = _execute(context, "revert_preview", {})
        assert not reverted.get("rollback_warnings"), reverted
        assert not state.pending_preview
        final = _snapshot(scene, cube, camera, light)
        assert final == initial, {"initial": initial, "final": final, "reverted": reverted}

        print("smoke_animation_helpers: ok")
    finally:
        if visual_dir:
            shutil.rmtree(visual_dir, ignore_errors=True)
        claude_blender.unregister()


if __name__ == "__main__":
    main()
