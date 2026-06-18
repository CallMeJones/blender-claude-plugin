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
from claude_blender import agent_loop, anthropic_client, bridge_protocol, context_bundle, live_preview, tool_dispatcher  # noqa: E402


ANIMATION_TOOLS = {
    "create_animation_brief",
    "create_timing_chart",
    "plan_animation_workflow",
    "run_animation_workflow",
    "block_key_poses",
    "add_breakdown_pose",
    "set_pose_hold",
    "create_motion_arc",
    "analyze_motion_arcs",
    "analyze_fcurve_spacing",
    "analyze_pose_clarity",
    "analyze_animation_principles",
    "sample_animation_state",
    "analyze_contact_sliding",
    "analyze_collision_penetration",
    "analyze_camera_framing",
    "analyze_motion_physics",
    "compare_animation_to_brief",
    "review_playblast_against_brief",
    "repair_animation_from_findings",
    "run_animation_repair_loop",
    "animate_object_bounce",
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


def _direct_tool_executor(context):
    def execute(_scene_name, tool_block):
        return tool_dispatcher.execute_tool(context, tool_block["name"], tool_block.get("input") or {})

    return execute


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
    image = bpy.data.images.new(f"Claude Smoke Frame {os.path.basename(path)}", width=8, height=8, alpha=True)
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
        tool_names = {tool["name"] for tool in anthropic_client.blender_tool_definitions()}
        assert ANIMATION_TOOLS.issubset(tool_names)
        contract_names = set(bridge_protocol.TOOL_CONTRACTS)
        assert ANIMATION_TOOLS.issubset(contract_names)

        preflight_context = {}
        clarification = agent_loop._apply_animation_brief_preflight(
            scene.name,
            "Make the cube bounce twice and get smaller.",
            preflight_context,
            tool_executor=_direct_tool_executor(context),
        )
        assert not clarification, clarification
        assert preflight_context["animation_brief"]["timing"]["requested_count"] == 2, preflight_context

        generic_context = {}
        generic = agent_loop._apply_animation_brief_preflight(
            scene.name,
            "Give me a brief summary of this scene.",
            generic_context,
            tool_executor=_direct_tool_executor(context),
        )
        assert not generic, generic
        assert "animation_brief" not in generic_context, generic_context

        ambiguous_context = {}
        question = agent_loop._apply_animation_brief_preflight(
            scene.name,
            "Animate the cube.",
            ambiguous_context,
            tool_executor=_direct_tool_executor(context),
        )
        assert question.startswith("What action"), question
        assert ambiguous_context["animation_brief"]["clarification_needed"] is True, ambiguous_context

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
        assert plan["status"] == "ready_with_helper_gaps", plan
        assert plan["brief"]["action"] == "bounce", plan
        assert plan["brief"]["timing"]["requested_count"] == 2, plan
        assert plan["timing_chart"]["frame_end"] == 72, plan
        call_names = [call["name"] for call in plan["next_tool_calls"]]
        assert "animate_object_bounce" in call_names, plan
        assert "analyze_animation_principles" in call_names, plan
        assert "capture_animation_playblast" in call_names, plan
        assert "review_playblast_against_brief" in call_names, plan
        assert "draft_script" not in call_names, plan
        assert plan["script_fallback_policy"]["allowed"] is True, plan
        assert any("scale" in item for item in plan["generation_blockers"]), plan
        assert not scene.claude_blender.pending_preview

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
        assert any(item["tool"] == "animate_object_bounce" and item["ok"] for item in workflow_run["executed"]), workflow_run
        assert any("scale" in item for item in workflow_run["generation_blockers"]), workflow_run
        assert workflow_run["review"]["principles"]["ok"] is True, workflow_run
        assert workflow_run["review"]["comparison"]["ok"] is True, workflow_run
        assert workflow_run["review"]["repair_plan"]["repair_operations"], workflow_run
        assert any(item.get("principle") == "secondary_action" for item in workflow_run["review"]["findings"]), workflow_run
        reverted_workflow = _execute(context, "revert_preview", {})
        assert not reverted_workflow.get("rollback_warnings"), reverted_workflow
        assert not scene.claude_blender.pending_preview
        _select_object(context, cube)

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
        assert any(item["tool"] == "capture_animation_playblast" for item in playblast_review["repair_operations"]), playblast_review

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
        assert motion_evidence["digest_frame_count"] == 3, static_review
        assert motion_evidence["max_grid_delta"] == 0.0, static_review
        assert any("clear motion" in item["message"] for item in static_review["findings"]), static_review
        assert any(item["tool"] == "block_key_poses" for item in static_review["repair_operations"]), static_review
        assert all(item["tool_call"]["name"] == item["tool"] for item in static_review["repair_operations"]), static_review

        repair_plan = _execute(
            context,
            "repair_animation_from_findings",
            {
                "findings": [
                    {"severity": "warning", "message": "Contact points slide across the ground plane."},
                    {"severity": "warning", "requirement": "motion_physics", "message": "Sampled acceleration spike may be physically implausible."},
                ],
                "brief": contract,
            },
        )
        assert repair_plan["suggested_tool_calls"][0]["tool"] == "set_pose_hold", repair_plan
        assert any(item["tool"] == "retime_actions" for item in repair_plan["repair_operations"]), repair_plan
        assert repair_plan["repair_operations"][0]["arguments"]["object_names"] == ["Cube"], repair_plan
        assert repair_plan["repair_operations"][0]["tool_call"]["input"]["object_names"] == ["Cube"], repair_plan
        assert repair_plan["repair_operations"][0]["source_finding_index"] == 0, repair_plan

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
        assert repair_loop["executed_operations"][0]["tool"] == "set_pose_hold", repair_loop
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
                "path_name": "Claude Camera Motion Path",
                "path_points": [[-4.0, -4.0, 3.0], [0.0, -6.0, 4.0], [4.0, -4.0, 3.0]],
                "frame_start": 1,
                "frame_end": 48,
                "constraint_name": "Claude Camera Follow Path",
            },
        )
        assert follow["path"] in bpy.data.objects
        assert camera.constraints.get("Claude Camera Follow Path")
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
