"""Read-only animation sampling, validation, and repair-planning helpers."""

from __future__ import annotations

import math
import os

import bpy
import mathutils
from bpy_extras.object_utils import world_to_camera_view

from . import animation_brief, live_preview, playblast_capture


VISUAL_MOTION_DELTA_THRESHOLD = 0.01


def _name_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    return [str(item).strip() for item in value if str(item).strip()]


def _bounded_int(value, default, *, minimum=1, maximum=240):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), min(int(maximum), value))


def _resolve_objects(context, object_names=None, *, selected_only=False, max_objects=12):
    names = _name_list(object_names)
    missing = []
    if names:
        objects = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj:
                objects.append(obj)
            else:
                missing.append(name)
    elif selected_only and context.selected_objects:
        objects = list(context.selected_objects)
    elif context.active_object:
        objects = [context.active_object]
    else:
        objects = list(context.scene.objects)
    return [obj for obj in objects if obj][:max_objects], missing


def _frame_samples(scene, frame_start=None, frame_end=None, sample_step=4, max_samples=48):
    start = int(frame_start if frame_start is not None else scene.frame_start)
    end = int(frame_end if frame_end is not None else scene.frame_end)
    if end < start:
        start, end = end, start
    step = _bounded_int(sample_step, 4, minimum=1, maximum=240)
    frames = list(range(start, end + 1, step))
    if not frames or frames[-1] != end:
        frames.append(end)
    if len(frames) > max_samples:
        stride = max(1, math.ceil(len(frames) / max_samples))
        frames = frames[::stride]
        if frames[-1] != end:
            frames.append(end)
    return sorted(set(int(frame) for frame in frames))


def _world_center(obj):
    if not getattr(obj, "bound_box", None):
        return tuple(float(value) for value in obj.matrix_world.translation)
    points = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
    return tuple(sum(point[index] for point in points) / len(points) for index in range(3))


def _bbox_world(obj):
    corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in getattr(obj, "bound_box", [])]
    if not corners:
        loc = obj.matrix_world.translation
        corners = [loc]
    mins = [min(point[index] for point in corners) for index in range(3)]
    maxs = [max(point[index] for point in corners) for index in range(3)]
    return mins, maxs


def _bbox_intersects(a, b, tolerance=0.0):
    amin, amax = a
    bmin, bmax = b
    return all(amin[index] <= bmax[index] + tolerance and amax[index] + tolerance >= bmin[index] for index in range(3))


def _distance(a, b):
    return math.sqrt(sum((float(a[index]) - float(b[index])) ** 2 for index in range(3)))


def _scene_fps(scene):
    fps_base = float(getattr(scene.render, "fps_base", 1.0) or 1.0)
    fps = float(getattr(scene.render, "fps", 24.0) or 24.0)
    return max(0.001, fps / fps_base)


def _set_frame_preserved(context, frames, fn):
    scene = context.scene
    current = int(scene.frame_current)
    results = []
    try:
        for frame in frames:
            scene.frame_set(int(frame))
            context.view_layer.update()
            results.append(fn(int(frame)))
    finally:
        scene.frame_set(current)
        context.view_layer.update()
    return results


def sample_animation_state(context, *, object_names=None, frame_start=None, frame_end=None, sample_step=4, selected_only=False):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    frames = _frame_samples(context.scene, frame_start, frame_end, sample_step)
    if not objects:
        return {"ok": False, "message": "No objects found for animation sampling", "missing_object_names": missing}

    def snapshot(frame):
        return {
            "frame": frame,
            "objects": [
                {
                    "name": obj.name,
                    "location": [round(float(value), 6) for value in obj.location],
                    "rotation_euler": [round(float(value), 6) for value in obj.rotation_euler],
                    "scale": [round(float(value), 6) for value in obj.scale],
                    "world_location": [round(float(value), 6) for value in obj.matrix_world.translation],
                }
                for obj in objects
            ],
        }

    return {
        "ok": True,
        "message": f"Sampled {len(objects)} object(s) across {len(frames)} frame(s)",
        "frames": _set_frame_preserved(context, frames, snapshot),
        "sampled_frames": frames,
        "missing_object_names": missing,
    }


def _action_for_object(obj):
    return obj.animation_data.action if obj.animation_data and obj.animation_data.action else None


def _iter_fcurves(action):
    return live_preview._iter_action_fcurves(action) if action else []


def _find_fcurve(action, data_path, index):
    return next((fcurve for fcurve in _iter_fcurves(action) if fcurve.data_path == data_path and int(fcurve.array_index) == int(index)), None)


def analyze_fcurve_spacing(context, *, object_names=None, action_names=None, selected_only=False, paths=None):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    wanted_paths = set(_name_list(paths))
    actions = []
    seen = set()
    for obj in objects:
        action = _action_for_object(obj)
        if action and action.name not in seen:
            actions.append(action)
            seen.add(action.name)
    for name in _name_list(action_names):
        action = bpy.data.actions.get(name)
        if action and action.name not in seen:
            actions.append(action)
            seen.add(action.name)
        elif not action:
            missing.append(name)
    analyses = []
    object_analyses = []
    findings = []
    for action in actions:
        curves = []
        for fcurve in _iter_fcurves(action):
            if wanted_paths and fcurve.data_path not in wanted_paths:
                continue
            points = sorted((float(point.co.x), float(point.co.y)) for point in fcurve.keyframe_points)
            frame_gaps = [round(points[index + 1][0] - points[index][0], 6) for index in range(len(points) - 1)]
            value_gaps = [round(points[index + 1][1] - points[index][1], 6) for index in range(len(points) - 1)]
            interpolation = sorted({point.interpolation for point in fcurve.keyframe_points})
            curves.append(
                {
                    "data_path": fcurve.data_path,
                    "array_index": int(fcurve.array_index),
                    "keyframe_count": len(points),
                    "frame_gaps": frame_gaps,
                    "value_gaps": value_gaps,
                    "interpolation": interpolation,
                }
            )
            if len(points) >= 3 and len(set(frame_gaps)) == 1 and len(set(value_gaps)) == 1:
                findings.append(
                    {
                        "severity": "info",
                        "action": action.name,
                        "data_path": fcurve.data_path,
                        "message": "Even frame and value spacing may read mechanically linear.",
                    }
                )
        analyses.append({"action": action.name, "fcurves": curves})
    for obj in objects:
        action = _action_for_object(obj)
        keyframes = []
        segments = []
        if action:
            keyframes = sorted(
                {
                    int(round(point.co.x))
                    for fcurve in _iter_fcurves(action)
                    if not wanted_paths or fcurve.data_path in wanted_paths
                    for point in fcurve.keyframe_points
                }
            )
            locations = []
            for frame in keyframes:
                values = []
                for index in range(3):
                    fcurve = _find_fcurve(action, "location", index)
                    values.append(float(fcurve.evaluate(frame)) if fcurve else float(obj.location[index]))
                locations.append(tuple(values))
            for index, frame in enumerate(keyframes[:-1]):
                segments.append(
                    {
                        "from": frame,
                        "to": keyframes[index + 1],
                        "distance": round(_distance(locations[index], locations[index + 1]), 6) if locations else 0.0,
                    }
                )
        object_analyses.append(
            {
                "object": obj.name,
                "action": action.name if action else "",
                "paths": sorted(wanted_paths) if wanted_paths else ["location", "rotation_euler", "scale"],
                "keyframes": keyframes,
                "segments": segments,
            }
        )
    return {"ok": True, "message": f"Analyzed {len(actions)} action(s)", "actions": analyses, "objects": object_analyses, "findings": findings, "missing": missing}


def analyze_motion_arcs(context, *, object_names=None, frame_start=None, frame_end=None, sample_step=4, max_samples=48, selected_only=False):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    frames = _frame_samples(context.scene, frame_start, frame_end, sample_step, max_samples=max_samples)
    if not objects:
        return {"ok": False, "message": "No objects found for motion arc analysis", "missing_object_names": missing}
    samples = {obj.name: [] for obj in objects}

    def collect(frame):
        for obj in objects:
            loc = tuple(float(value) for value in obj.matrix_world.translation)
            samples[obj.name].append((frame, loc))

    _set_frame_preserved(context, frames, collect)
    arcs = []
    findings = []
    for obj in objects:
        points = samples[obj.name]
        segments = [_distance(points[index][1], points[index + 1][1]) for index in range(len(points) - 1)]
        total_distance = sum(segments)
        arcs.append(
            {
                "object": obj.name,
                "frame_start": frames[0],
                "frame_end": frames[-1],
                "sample_count": len(points),
                "total_distance": round(total_distance, 6),
                "path_length": round(total_distance, 6),
                "segment_lengths": [round(value, 6) for value in segments],
                "points": [{"frame": frame, "location": [round(component, 6) for component in loc]} for frame, loc in points],
            }
        )
        if total_distance <= 0.0001:
            findings.append({"severity": "warning", "object": obj.name, "message": "Object has no sampled world-space motion."})
    return {"ok": True, "message": f"Analyzed motion arcs for {len(objects)} object(s)", "arcs": arcs, "objects": arcs, "findings": findings, "missing_object_names": missing}


def analyze_pose_clarity(context, *, object_names=None, selected_only=False):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    poses = []
    findings = []
    for obj in objects:
        action = _action_for_object(obj)
        if not action:
            findings.append({"severity": "warning", "object": obj.name, "message": "Object has no action to analyze for pose clarity."})
            continue
        frames = sorted({int(round(point.co.x)) for fcurve in _iter_fcurves(action) for point in fcurve.keyframe_points})
        transform_paths = sorted({fcurve.data_path for fcurve in _iter_fcurves(action) if fcurve.data_path in {"location", "rotation_euler", "scale"}})
        holds = []
        for index, frame in enumerate(frames[:-1]):
            next_frame = frames[index + 1]
            if next_frame - frame <= 6:
                holds.append({"frame": frame, "hold_to": next_frame, "duration": next_frame - frame})
        if len(frames) < 3:
            findings.append({"severity": "info", "object": obj.name, "message": "Animation has fewer than three keyed poses; readability may depend heavily on interpolation."})
        if "location" not in transform_paths and "rotation_euler" not in transform_paths:
            findings.append({"severity": "info", "object": obj.name, "message": "No transform pose changes found on location or rotation curves."})
        poses.append(
            {
                "object": obj.name,
                "action": action.name,
                "keyed_frames": frames,
                "transform_paths": transform_paths,
                "hold_candidates": holds,
                "holds": holds,
                "pose_count": len(frames),
            }
        )
    return {"ok": True, "message": f"Analyzed pose clarity for {len(objects)} object(s)", "objects": poses, "findings": findings, "missing_object_names": missing}


def analyze_animation_principles(context, *, object_names=None, selected_only=False, prompt="", brief=None, timing_chart=None, frame_start=None, frame_end=None):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    subject_names = [obj.name for obj in objects]
    brief = _brief_from_args(
        context,
        brief=brief,
        prompt=prompt,
        subject_names=subject_names or object_names,
        frame_start=frame_start,
        frame_end=frame_end,
    ) if (brief or prompt) else (brief or {})
    timing_chart = timing_chart if isinstance(timing_chart, dict) else {}
    arcs = analyze_motion_arcs(context, object_names=subject_names or object_names, selected_only=selected_only, frame_start=frame_start, frame_end=frame_end)
    spacing = analyze_fcurve_spacing(context, object_names=subject_names or object_names, selected_only=selected_only, paths=["location", "rotation_euler", "scale"])
    clarity = analyze_pose_clarity(context, object_names=subject_names or object_names, selected_only=selected_only)
    findings = []
    findings.extend(arcs.get("findings") or [])
    findings.extend(spacing.get("findings") or [])
    findings.extend(clarity.get("findings") or [])
    action = str((brief or {}).get("action") or "").lower()
    key_poses = timing_chart.get("key_poses") or []
    roles = {str(item.get("role") or "").lower() for item in key_poses if isinstance(item, dict)}
    labels = {str(item.get("label") or "").lower() for item in key_poses if isinstance(item, dict)}
    principle_checks = []
    for obj in objects:
        action_data = _action_for_object(obj)
        has_scale = bool(action_data and any(fcurve.data_path == "scale" for fcurve in _iter_fcurves(action_data)))
        has_location = bool(action_data and any(fcurve.data_path == "location" for fcurve in _iter_fcurves(action_data)))
        check = {
            "object": obj.name,
            "action": action_data.name if action_data else "",
            "staging": "pass" if context.scene.camera or (brief or {}).get("camera") else "info",
            "timing_spacing": "pass",
            "arcs": "pass" if has_location else "warning",
            "pose_clarity": "pass",
            "anticipation": "not_evaluated",
            "squash_stretch": "not_evaluated",
            "follow_through_settle": "not_evaluated",
            "secondary_action": "not_evaluated",
            "contact_weight": "not_evaluated",
        }
        if action in {"bounce", "jump", "fall"}:
            has_anticipation = "anticipation" in roles or any("anticipation" in label for label in labels)
            has_settle = "settle" in roles or any("settle" in label for label in labels)
            check["anticipation"] = "pass" if has_anticipation else "info"
            check["squash_stretch"] = "pass" if has_scale else "info"
            check["follow_through_settle"] = "pass" if has_settle else "warning"
            check["contact_weight"] = "pass" if ("contact" in roles or has_scale) else "info"
            if not has_anticipation:
                findings.append(
                    {
                        "severity": "info",
                        "principle": "anticipation",
                        "object": obj.name,
                        "message": "No explicit anticipation pose was found for the action.",
                        "recommendation": "Add a small wind-up, crouch, or pre-contact pose before the main action.",
                    }
                )
            if not has_scale:
                findings.append(
                    {
                        "severity": "info",
                        "principle": "squash_stretch",
                        "object": obj.name,
                        "message": "No scale keys were found for squash/stretch.",
                        "recommendation": "Add squash on contact and stretch on launch when the style allows it.",
                    }
                )
            if not has_settle:
                findings.append({"severity": "warning", "principle": "settle", "object": obj.name, "message": "Timing chart has no explicit settle pose."})
            if "contact" not in roles and timing_chart:
                findings.append({"severity": "warning", "principle": "contact", "object": obj.name, "message": "Timing chart has no explicit contact pose."})
        secondary_actions = (brief or {}).get("secondary_actions") or []
        if secondary_actions:
            scale_required = any("scale" in str(item).lower() or "smaller" in str(item).lower() or "bigger" in str(item).lower() for item in secondary_actions)
            check["secondary_action"] = "pass" if (not scale_required or has_scale) else "warning"
            if scale_required and not has_scale:
                findings.append({"severity": "warning", "principle": "secondary_action", "object": obj.name, "message": "The brief asks for scale change, but no scale animation was found."})
        principle_checks.append(check)
    warning_count = sum(1 for item in findings if str(item.get("severity", "")).lower() in {"warning", "warn", "error"})
    status = "pass" if warning_count == 0 else "needs_repair"
    return {
        "ok": True,
        "message": "Analyzed animation principles",
        "status": status,
        "brief_contract_id": (brief or {}).get("contract_id", ""),
        "principle_checks": principle_checks,
        "warning_count": warning_count,
        "ready_for_repair": warning_count > 0,
        "principles": {
            "staging": "camera framing should be checked separately with analyze_camera_framing",
            "timing_spacing": spacing,
            "arcs": arcs,
            "pose_clarity": clarity,
        },
        "motion_arcs": arcs.get("objects", []),
        "spacing": spacing.get("objects", []),
        "pose_clarity": clarity.get("objects", []),
        "findings": findings,
        "missing_object_names": missing,
    }


def analyze_contact_sliding(context, *, object_names=None, frame_start=None, frame_end=None, sample_step=2, contact_z=0.0, contact_tolerance=0.05, sliding_tolerance=0.08, selected_only=False):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    frames = _frame_samples(context.scene, frame_start, frame_end, sample_step)
    contacts = {obj.name: [] for obj in objects}

    def collect(frame):
        for obj in objects:
            mins, _maxs = _bbox_world(obj)
            if abs(float(mins[2]) - float(contact_z)) <= float(contact_tolerance):
                contacts[obj.name].append(
                    {
                        "frame": frame,
                        "xy": [round(float(obj.matrix_world.translation.x), 6), round(float(obj.matrix_world.translation.y), 6)],
                        "min_z": round(float(mins[2]), 6),
                    }
                )

    _set_frame_preserved(context, frames, collect)
    findings = []
    for obj in objects:
        contact_points = contacts[obj.name]
        if len(contact_points) < 2:
            continue
        first = contact_points[0]["xy"]
        last = contact_points[-1]["xy"]
        slide = math.sqrt((last[0] - first[0]) ** 2 + (last[1] - first[1]) ** 2)
        if slide > float(sliding_tolerance):
            findings.append(
                {
                    "severity": "warning",
                    "object": obj.name,
                    "message": "Contact points slide across the ground plane.",
                    "slide_distance": round(slide, 6),
                }
            )
    return {"ok": True, "message": f"Analyzed contact sliding for {len(objects)} object(s)", "contacts": contacts, "findings": findings, "missing_object_names": missing}


def analyze_collision_penetration(context, *, object_names=None, frame_start=None, frame_end=None, sample_step=4, tolerance=0.0, selected_only=False):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only, max_objects=20)
    frames = _frame_samples(context.scene, frame_start, frame_end, sample_step, max_samples=32)
    findings = []

    def collect(frame):
        boxes = [(obj, _bbox_world(obj)) for obj in objects]
        for index, (left, left_box) in enumerate(boxes):
            for right, right_box in boxes[index + 1 :]:
                if _bbox_intersects(left_box, right_box, tolerance=float(tolerance)):
                    findings.append({"severity": "warning", "frame": frame, "objects": [left.name, right.name], "message": "World bounding boxes intersect."})

    _set_frame_preserved(context, frames, collect)
    return {"ok": True, "message": f"Checked {len(objects)} object(s) for bbox intersections", "findings": findings, "sampled_frames": frames, "missing_object_names": missing}


def analyze_camera_framing(context, *, object_names=None, camera_name="", frame_start=None, frame_end=None, sample_step=8, margin=0.05, selected_only=False):
    scene = context.scene
    camera = bpy.data.objects.get(camera_name) if camera_name else scene.camera
    if not camera or camera.type != "CAMERA":
        return {"ok": False, "message": "A camera is required for framing analysis"}
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    frames = _frame_samples(scene, frame_start, frame_end, sample_step, max_samples=24)
    findings = []
    samples = []

    def collect(frame):
        for obj in objects:
            center = world_to_camera_view(scene, camera, obj.matrix_world.translation)
            visible = float(margin) <= center.x <= 1.0 - float(margin) and float(margin) <= center.y <= 1.0 - float(margin) and center.z > 0
            sample = {
                "frame": frame,
                "object": obj.name,
                "camera": camera.name,
                "normalized": [round(float(center.x), 6), round(float(center.y), 6), round(float(center.z), 6)],
                "center_visible": bool(visible),
            }
            samples.append(sample)
            if not visible:
                findings.append({"severity": "warning", **sample, "message": "Subject center is outside the camera-safe region."})

    _set_frame_preserved(context, frames, collect)
    return {"ok": True, "message": f"Analyzed camera framing for {len(objects)} object(s)", "samples": samples, "findings": findings, "missing_object_names": missing}


def analyze_motion_physics(
    context,
    *,
    object_names=None,
    frame_start=None,
    frame_end=None,
    sample_step=2,
    max_speed=None,
    max_acceleration=None,
    selected_only=False,
):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    frames = _frame_samples(context.scene, frame_start, frame_end, sample_step, max_samples=64)
    if not objects:
        return {"ok": False, "message": "No objects found for motion physics analysis", "missing_object_names": missing}
    fps = _scene_fps(context.scene)
    max_speed_threshold = float(max_speed) if max_speed is not None else 40.0
    max_acceleration_threshold = float(max_acceleration) if max_acceleration is not None else 160.0
    samples = {obj.name: [] for obj in objects}

    def collect(frame):
        for obj in objects:
            center = _world_center(obj)
            samples[obj.name].append(
                {
                    "frame": frame,
                    "world_center": [round(float(value), 6) for value in center],
                }
            )

    _set_frame_preserved(context, frames, collect)
    findings = []
    reports = []
    for obj in objects:
        object_samples = samples[obj.name]
        speeds = []
        for index, sample in enumerate(object_samples[:-1]):
            next_sample = object_samples[index + 1]
            frame_delta = max(1, int(next_sample["frame"]) - int(sample["frame"]))
            dt = frame_delta / fps
            delta = [float(next_sample["world_center"][axis]) - float(sample["world_center"][axis]) for axis in range(3)]
            distance = _distance(sample["world_center"], next_sample["world_center"])
            velocity = [value / dt for value in delta]
            speeds.append(
                {
                    "from": sample["frame"],
                    "to": next_sample["frame"],
                    "distance": round(distance, 6),
                    "speed": round(distance / dt, 6),
                    "velocity": [round(float(value), 6) for value in velocity],
                }
            )
        accelerations = []
        for index, segment in enumerate(speeds[:-1]):
            next_segment = speeds[index + 1]
            segment_mid = (float(segment["from"]) + float(segment["to"])) / 2.0
            next_mid = (float(next_segment["from"]) + float(next_segment["to"])) / 2.0
            dt = max(1.0 / fps, (next_mid - segment_mid) / fps)
            delta_v = [float(next_segment["velocity"][axis]) - float(segment["velocity"][axis]) for axis in range(3)]
            acceleration = math.sqrt(sum(value * value for value in delta_v)) / dt
            accelerations.append(
                {
                    "from_segment": [segment["from"], segment["to"]],
                    "to_segment": [next_segment["from"], next_segment["to"]],
                    "frame": next_segment["from"],
                    "acceleration": round(acceleration, 6),
                }
            )
        fastest = max(speeds, key=lambda item: item["speed"], default=None)
        sharpest = max(accelerations, key=lambda item: item["acceleration"], default=None)
        if fastest and fastest["speed"] > max_speed_threshold:
            findings.append(
                {
                    "severity": "warning",
                    "requirement": "motion_physics",
                    "principle": "weight",
                    "object": obj.name,
                    "frame": fastest["to"],
                    "speed": fastest["speed"],
                    "threshold": round(max_speed_threshold, 6),
                    "repair_tool": "retime_actions",
                    "message": "Sampled speed exceeds the expected scene-scale threshold.",
                }
            )
        if sharpest and sharpest["acceleration"] > max_acceleration_threshold:
            findings.append(
                {
                    "severity": "warning",
                    "requirement": "motion_physics",
                    "principle": "weight",
                    "object": obj.name,
                    "frame": sharpest["frame"],
                    "acceleration": sharpest["acceleration"],
                    "threshold": round(max_acceleration_threshold, 6),
                    "repair_tool": "retime_actions",
                    "message": "Sampled acceleration spike may be physically implausible for the scene scale.",
                }
            )
        reports.append(
            {
                "object": obj.name,
                "sample_count": len(object_samples),
                "samples": object_samples,
                "speed_segments": speeds,
                "acceleration_segments": accelerations,
                "max_speed": fastest["speed"] if fastest else 0.0,
                "max_acceleration": sharpest["acceleration"] if sharpest else 0.0,
            }
        )
    return {
        "ok": True,
        "message": f"Analyzed sampled speed and acceleration for {len(objects)} object(s)",
        "fps": round(fps, 6),
        "thresholds": {
            "max_speed": round(max_speed_threshold, 6),
            "max_acceleration": round(max_acceleration_threshold, 6),
        },
        "sampled_frames": frames,
        "objects": reports,
        "findings": findings,
        "missing_object_names": missing,
    }


def _brief_from_args(context, brief=None, prompt="", subject_names=None, frame_start=None, frame_end=None):
    if isinstance(brief, dict) and brief:
        return brief
    result = animation_brief.create_animation_brief(
        context,
        prompt=prompt,
        subject_names=subject_names,
        frame_start=frame_start,
        frame_end=frame_end,
    )
    return result.get("brief") if result.get("ok") else {}


def compare_animation_to_brief(context, *, brief=None, prompt="", subject_names=None, frame_start=None, frame_end=None):
    brief = _brief_from_args(context, brief=brief, prompt=prompt, subject_names=subject_names, frame_start=frame_start, frame_end=frame_end)
    if not brief:
        return {"ok": False, "message": "A prompt or animation brief is required"}
    subjects = [item["name"] for item in brief.get("subjects") or []] or brief.get("subject_names") or []
    timing = brief.get("timing") or {}
    start = int(frame_start if frame_start is not None else timing.get("frame_start", context.scene.frame_start))
    end = int(frame_end if frame_end is not None else timing.get("frame_end", context.scene.frame_end))
    findings = []
    if not subjects:
        findings.append({"severity": "error", "requirement": "subject", "message": "No resolved animation subject."})
    missing = [name for name in subjects if bpy.data.objects.get(name) is None]
    for name in missing:
        findings.append({"severity": "error", "requirement": "subject", "object": name, "message": "Subject object is missing."})
    samples = (
        sample_animation_state(context, object_names=subjects, frame_start=start, frame_end=end, sample_step=max(1, int((end - start) / 24) or 1))
        if subjects
        else {"ok": False, "message": "No resolved animation subject."}
    )
    if samples.get("ok"):
        moved = False
        by_object = {}
        for frame in samples["frames"]:
            for obj in frame["objects"]:
                by_object.setdefault(obj["name"], []).append(obj)
        for _name, items in by_object.items():
            if len(items) < 2:
                continue
            first_location = items[0]["world_location"]
            if any(_distance(first_location, item["world_location"]) > 0.001 for item in items[1:]):
                moved = True
        if brief.get("action") and not moved:
            findings.append({"severity": "warning", "requirement": "action", "message": "Sampled subject transforms do not show clear motion."})
    if subjects and brief.get("validation_plan", {}).get("check_camera_framing"):
        camera_findings = analyze_camera_framing(context, object_names=subjects, camera_name=brief.get("camera") or "", frame_start=start, frame_end=end)
        findings.extend(camera_findings.get("findings") or [])
    validation_results = {}
    if subjects and brief.get("validation_plan", {}).get("check_contact_physics"):
        validation_sample_step = max(1, int((end - start) / 24) or 1)
        physics = analyze_motion_physics(context, object_names=subjects, frame_start=start, frame_end=end, sample_step=validation_sample_step)
        validation_results["motion_physics"] = physics
        findings.extend(physics.get("findings") or [])
        contact = analyze_contact_sliding(context, object_names=subjects, frame_start=start, frame_end=end, sample_step=validation_sample_step)
        validation_results["contact_sliding"] = contact
        findings.extend(contact.get("findings") or [])
        if len(subjects) >= 2:
            collisions = analyze_collision_penetration(context, object_names=subjects, frame_start=start, frame_end=end, sample_step=validation_sample_step)
            validation_results["collision_penetration"] = collisions
            findings.extend(collisions.get("findings") or [])
    status = "pass" if not findings else "needs_repair"
    return {
        "ok": True,
        "message": "Compared animation against brief",
        "status": status,
        "brief_contract_id": brief.get("contract_id", ""),
        "findings": findings,
        "sample_summary": samples if samples.get("ok") else {},
        "validation_results": validation_results,
    }


def _brief_subject_names(brief):
    if not isinstance(brief, dict):
        return []
    return [item["name"] for item in brief.get("subjects") or [] if isinstance(item, dict) and item.get("name")] or _name_list(brief.get("subject_names"))


def _brief_frame_range(context, brief):
    timing = brief.get("timing") if isinstance(brief, dict) else {}
    return (
        int(timing.get("frame_start", context.scene.frame_start) if isinstance(timing, dict) else context.scene.frame_start),
        int(timing.get("frame_end", context.scene.frame_end) if isinstance(timing, dict) else context.scene.frame_end),
    )


def _finding(severity, message, *, principle="", requirement="", object_name="", frame=None, recommendation="", repair_tool="", evidence=None):
    item = {
        "severity": severity,
        "message": message,
    }
    if principle:
        item["principle"] = principle
    if requirement:
        item["requirement"] = requirement
    if object_name:
        item["object"] = object_name
    if frame is not None:
        item["frame"] = int(frame)
    if recommendation:
        item["recommendation"] = recommendation
    if repair_tool:
        item["repair_tool"] = repair_tool
    if evidence:
        item["evidence"] = evidence
    return item


def _normalize_playblast(context, playblast):
    if isinstance(playblast, dict) and playblast:
        return playblast
    return playblast_capture.latest_playblast_metadata(context=context)


def _image_digest(path, *, grid_size=4, max_samples=4096):
    if not path or not os.path.isfile(path):
        return {}
    image = None
    try:
        image = bpy.data.images.load(path, check_existing=False)
        width = int(image.size[0])
        height = int(image.size[1])
        pixel_count = width * height
        if width <= 0 or height <= 0 or pixel_count <= 0:
            return {"available": False, "note": "Image has no readable pixels"}

        pixels = image.pixels
        stride = max(1, math.ceil(pixel_count / max(1, int(max_samples))))
        sample_count = 0
        sum_r = sum_g = sum_b = sum_a = 0.0
        sum_luma = 0.0
        sum_luma_sq = 0.0
        min_luma = 1.0
        max_luma = 0.0
        for pixel_index in range(0, pixel_count, stride):
            offset = pixel_index * 4
            r = float(pixels[offset])
            g = float(pixels[offset + 1])
            b = float(pixels[offset + 2])
            a = float(pixels[offset + 3])
            luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
            sample_count += 1
            sum_r += r
            sum_g += g
            sum_b += b
            sum_a += a
            sum_luma += luma
            sum_luma_sq += luma * luma
            min_luma = min(min_luma, luma)
            max_luma = max(max_luma, luma)

        grid = []
        grid_size = max(2, min(8, int(grid_size or 4)))
        for grid_y in range(grid_size):
            y = min(height - 1, max(0, int((grid_y + 0.5) * height / grid_size)))
            for grid_x in range(grid_size):
                x = min(width - 1, max(0, int((grid_x + 0.5) * width / grid_size)))
                offset = (y * width + x) * 4
                luma = 0.2126 * float(pixels[offset]) + 0.7152 * float(pixels[offset + 1]) + 0.0722 * float(pixels[offset + 2])
                grid.append(max(0, min(255, int(round(luma * 255)))))

        mean_luma = sum_luma / sample_count if sample_count else 0.0
        variance = max(0.0, (sum_luma_sq / sample_count) - (mean_luma * mean_luma)) if sample_count else 0.0
        return {
            "available": True,
            "sample_count": int(sample_count),
            "mean_rgb": [
                round(sum_r / sample_count, 6),
                round(sum_g / sample_count, 6),
                round(sum_b / sample_count, 6),
            ] if sample_count else [0.0, 0.0, 0.0],
            "mean_alpha": round(sum_a / sample_count, 6) if sample_count else 0.0,
            "mean_luminance": round(mean_luma, 6),
            "luminance_range": round(max_luma - min_luma, 6),
            "luminance_variance": round(variance, 8),
            "grid_size": [grid_size, grid_size],
            "grid_signature": grid,
        }
    except Exception as exc:
        return {"available": False, "note": f"Image pixels could not be inspected: {type(exc).__name__}: {exc}"}
    finally:
        if image is not None:
            try:
                bpy.data.images.remove(image)
            except Exception:
                pass


def _grid_delta(first_digest, second_digest):
    first = first_digest.get("grid_signature") or []
    second = second_digest.get("grid_signature") or []
    if not first or len(first) != len(second):
        return None
    distance = sum(abs(int(a) - int(b)) for a, b in zip(first, second))
    return round(distance / (len(first) * 255.0), 6)


def _playblast_motion_evidence(visual_evidence):
    digested = [frame for frame in visual_evidence if (frame.get("image_digest") or {}).get("available")]
    deltas = []
    for previous, current in zip(digested, digested[1:]):
        delta = _grid_delta(previous.get("image_digest") or {}, current.get("image_digest") or {})
        if delta is None:
            continue
        deltas.append(
            {
                "from_frame": int(previous.get("frame", 0) or 0),
                "to_frame": int(current.get("frame", 0) or 0),
                "grid_delta": delta,
                "visual_change_detected": delta >= VISUAL_MOTION_DELTA_THRESHOLD,
            }
        )
    max_delta = max((item["grid_delta"] for item in deltas), default=0.0)
    return {
        "digest_frame_count": len(digested),
        "delta_count": len(deltas),
        "motion_threshold": VISUAL_MOTION_DELTA_THRESHOLD,
        "max_grid_delta": round(float(max_delta), 6),
        "visual_change_detected": bool(max_delta >= VISUAL_MOTION_DELTA_THRESHOLD),
        "frame_deltas": deltas,
    }


def _playblast_frame_evidence(playblast):
    evidence = []
    findings = []
    frames = playblast.get("frames") or []
    for frame in frames:
        frame_number = int(frame.get("frame", 0) or 0)
        path = str(frame.get("path") or "")
        file_exists = bool(path and os.path.isfile(path))
        available = bool(frame.get("available")) and (not path or file_exists)
        width = int(frame.get("width", 0) or 0)
        height = int(frame.get("height", 0) or 0)
        size_bytes = int(frame.get("size_bytes", 0) or 0)
        item = {
            "frame": frame_number,
            "available": available,
            "resource_uri": str(frame.get("resource_uri") or ""),
            "path": path,
            "file_exists": file_exists,
            "size_bytes": size_bytes,
            "width": width,
            "height": height,
            "note": str(frame.get("note") or ""),
        }
        if available and path:
            digest = _image_digest(path)
            if digest:
                item["image_digest"] = digest
                if not digest.get("available"):
                    findings.append(
                        _finding(
                            "warning",
                            "A playblast frame is available but its image pixels could not be inspected.",
                            principle="visual_review",
                            frame=frame_number,
                            repair_tool="capture_animation_playblast",
                            evidence={"path": path, "note": digest.get("note", "")},
                        )
                    )
                elif digest.get("mean_alpha", 1.0) <= 0.01:
                    findings.append(
                        _finding(
                            "warning",
                            "A playblast frame appears transparent or empty.",
                            principle="visual_review",
                            frame=frame_number,
                            repair_tool="capture_animation_playblast",
                            evidence={"path": path, "mean_alpha": digest.get("mean_alpha", 0.0)},
                        )
                    )
                elif digest.get("luminance_range", 1.0) <= 0.005 and digest.get("luminance_variance", 1.0) <= 0.00001:
                    findings.append(
                        _finding(
                            "info",
                            "A playblast frame has very low visible contrast, so pose review may be weak.",
                            principle="visual_review",
                            frame=frame_number,
                            repair_tool="capture_animation_playblast",
                            evidence={
                                "path": path,
                                "luminance_range": digest.get("luminance_range", 0.0),
                                "luminance_variance": digest.get("luminance_variance", 0.0),
                            },
                        )
                    )
        evidence.append(item)
        if frame.get("available") and path and not file_exists:
            findings.append(
                _finding(
                    "warning",
                    "A playblast frame is marked available but the PNG file is missing.",
                    principle="visual_review",
                    frame=frame_number,
                    repair_tool="capture_animation_playblast",
                    evidence={"path": path},
                )
            )
        if available and (width <= 0 or height <= 0 or size_bytes <= 0):
            findings.append(
                _finding(
                    "warning",
                    "A playblast frame has incomplete image metadata.",
                    principle="visual_review",
                    frame=frame_number,
                    repair_tool="capture_animation_playblast",
                    evidence={"width": width, "height": height, "size_bytes": size_bytes},
                )
            )
    return evidence, findings


def _playblast_coverage(context, playblast, brief):
    frame_start, frame_end = _brief_frame_range(context, brief)
    sampled_frames = [int(frame) for frame in playblast.get("sampled_frames") or []]
    if not sampled_frames:
        sampled_frames = [int(frame.get("frame", 0) or 0) for frame in playblast.get("frames") or [] if frame.get("frame") is not None]
    sampled_frames = sorted(set(frame for frame in sampled_frames if frame))
    if not sampled_frames:
        return {
            "brief_frame_start": frame_start,
            "brief_frame_end": frame_end,
            "sampled_frames": [],
            "covers_start": False,
            "covers_end": False,
            "covers_range": False,
        }
    return {
        "brief_frame_start": frame_start,
        "brief_frame_end": frame_end,
        "sampled_frames": sampled_frames,
        "first_sampled_frame": sampled_frames[0],
        "last_sampled_frame": sampled_frames[-1],
        "covers_start": sampled_frames[0] <= frame_start,
        "covers_end": sampled_frames[-1] >= frame_end,
        "covers_range": sampled_frames[0] <= frame_start and sampled_frames[-1] >= frame_end,
    }


def review_playblast_against_brief(context, *, playblast=None, brief=None, prompt=""):
    metadata = _normalize_playblast(context, playblast)
    brief = _brief_from_args(context, brief=brief, prompt=prompt, subject_names=None) if (brief or prompt) else (brief or {})
    findings = []
    visual_evidence, frame_findings = _playblast_frame_evidence(metadata)
    findings.extend(frame_findings)
    frames = metadata.get("frames") or []
    usable_frames = [frame for frame in visual_evidence if frame.get("available")]
    motion_evidence = _playblast_motion_evidence(visual_evidence)
    if not metadata.get("available") and not usable_frames:
        findings.append(
            _finding(
                "warning",
                "No playblast frames are available for visual animation review.",
                principle="visual_review",
                repair_tool="capture_animation_playblast",
            )
        )
    if frames and len(usable_frames) < len(frames):
        findings.append(
            _finding(
                "warning",
                "Some requested playblast frames are unavailable.",
                principle="visual_review",
                repair_tool="capture_animation_playblast",
                evidence={"requested_frame_count": len(frames), "usable_frame_count": len(usable_frames)},
            )
        )
    if usable_frames and len(usable_frames) < 3:
        findings.append(
            _finding(
                "info",
                "Playblast has very few usable sampled frames; timing and spacing review may be weak.",
                principle="visual_review",
                repair_tool="capture_animation_playblast",
                evidence={"usable_frame_count": len(usable_frames)},
            )
        )
    coverage = _playblast_coverage(context, metadata, brief)
    if coverage["sampled_frames"] and not coverage["covers_range"]:
        findings.append(
            _finding(
                "warning",
                "Playblast samples do not cover the full animation brief frame range.",
                principle="visual_review",
                repair_tool="capture_animation_playblast",
                evidence=coverage,
            )
        )
    requested_count = ((brief or {}).get("timing") or {}).get("requested_count") if isinstance(brief, dict) else None
    if requested_count and usable_frames and len(usable_frames) < max(3, int(requested_count) * 2 + 1):
        findings.append(
            _finding(
                "info",
                "Playblast may be undersampled for the requested repeated action count.",
                principle="timing_spacing",
                repair_tool="capture_animation_playblast",
                evidence={"requested_count": int(requested_count), "usable_frame_count": len(usable_frames)},
            )
        )
    if (brief or {}).get("action") and motion_evidence["delta_count"] and not motion_evidence["visual_change_detected"]:
        findings.append(
            _finding(
                "warning",
                "Sampled playblast frames do not show clear motion for the requested action.",
                principle="visual_review",
                requirement="action",
                repair_tool="block_key_poses",
                evidence=motion_evidence,
            )
        )
    comparison = compare_animation_to_brief(context, brief=brief, prompt=prompt) if (brief or prompt) else {}
    findings.extend(comparison.get("findings") or [])
    repair_plan = repair_animation_from_findings(context, findings=findings, brief=brief if isinstance(brief, dict) else None)
    return {
        "ok": True,
        "message": "Reviewed playblast visual evidence and current animation state against brief",
        "status": "pass" if not findings else "needs_repair",
        "playblast_id": metadata.get("playblast_id", ""),
        "frame_count": len(frames),
        "usable_frame_count": len(usable_frames),
        "visual_review": {
            "available": bool(metadata.get("available")) and bool(usable_frames),
            "metadata_uri": metadata.get("metadata_uri", ""),
            "resource_type": metadata.get("resource_type", ""),
            "frame_coverage": coverage,
            "frames": visual_evidence,
            "motion_evidence": motion_evidence,
            "review_hints": metadata.get("review_hints") or [],
        },
        "findings": findings,
        "comparison": comparison,
        "repair_operations": repair_plan.get("repair_operations", []),
        "suggested_tool_calls": repair_plan.get("suggested_tool_calls", []),
    }


def _operation(tool, reason, *, arguments=None, source_index=None, finding=None, confidence="medium"):
    arguments = arguments or {}
    mutates_scene = tool not in {"capture_animation_playblast", "create_timing_chart", "review_playblast_against_brief"}
    operation = {
        "tool": tool,
        "arguments": arguments,
        "tool_call": {"name": tool, "input": arguments},
        "reason": reason,
        "confidence": confidence,
        "mutates_scene": mutates_scene,
        "preview_safe": bool(mutates_scene),
        "requires_user_commit": bool(mutates_scene),
        "execution_phase": "repair_preview" if mutates_scene else ("evidence_collection" if tool == "capture_animation_playblast" else "planning"),
    }
    if source_index is not None:
        operation["source_finding_index"] = int(source_index)
    if finding:
        operation["source_finding"] = {
            "severity": finding.get("severity", ""),
            "principle": finding.get("principle", ""),
            "requirement": finding.get("requirement", ""),
            "message": finding.get("message", ""),
        }
    return operation


def _dedupe_operations(operations):
    result = []
    seen = set()
    for operation in operations:
        key = (
            operation.get("tool"),
            repr(sorted((operation.get("arguments") or {}).items())),
            operation.get("reason"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(operation)
    return result


def repair_animation_from_findings(context, *, findings=None, brief=None):
    operations = []
    subject_names = _brief_subject_names(brief)
    frame_start, frame_end = _brief_frame_range(context, brief or {})
    primary_subject = subject_names[0] if subject_names else ""
    for index, finding in enumerate(findings or []):
        repair_tool = str(finding.get("repair_tool") or "").lower()
        text = " ".join(
            str(finding.get(key) or "")
            for key in ("message", "principle", "requirement", "repair_tool", "recommendation")
        ).lower()
        if repair_tool == "capture_animation_playblast" or (
            not repair_tool and ("playblast" in text or ("frame" in text and "unavailable" in text))
        ):
            operations.append(
                _operation(
                    "capture_animation_playblast",
                    "Capture a fresh sampled playblast so visual review has usable frame evidence.",
                    arguments={"frame_start": frame_start, "frame_end": frame_end, "max_frames": 12, "brief": (brief or {}).get("user_visible_interpretation", "")},
                    source_index=index,
                    finding=finding,
                )
            )
        if "camera" in text or "framing" in text:
            operations.append(
                _operation(
                    "create_camera_orbit",
                    "Repair camera framing around the animated subject.",
                    arguments={"target_name": primary_subject, "frame_start": frame_start, "frame_end": frame_end},
                    source_index=index,
                    finding=finding,
                )
            )
        if "linear" in text or "spacing" in text or "slow" in text:
            operations.append(
                _operation(
                    "set_action_interpolation",
                    "Adjust interpolation/easing for less mechanical spacing.",
                    arguments={"object_names": subject_names, "interpolation": "BEZIER"},
                    source_index=index,
                    finding=finding,
                )
            )
        if "speed" in text or "acceleration" in text or "motion_physics" in text:
            operations.append(
                _operation(
                    "retime_actions",
                    "Retiming may reduce physically implausible speed or acceleration spikes.",
                    arguments={"object_names": subject_names, "frame_start": frame_start, "frame_end": frame_end, "snap_to_integer": True},
                    source_index=index,
                    finding=finding,
                    confidence="low",
                )
            )
        if "contact" in text or "slide" in text:
            hold_frame = int(finding.get("frame", frame_start) or frame_start)
            operations.append(
                _operation(
                    "set_pose_hold",
                    "Hold or re-key contact poses to reduce sliding and improve weight.",
                    arguments={"object_names": subject_names, "frame": hold_frame, "hold_frames": 4, "paths": ["location"]},
                    source_index=index,
                    finding=finding,
                )
            )
        if "settle" in text or "follow" in text or "overshoot" in text:
            operations.append(
                _operation(
                    "add_breakdown_pose",
                    "Add a final settle or overshoot breakdown near the end of the action.",
                    arguments={"object_names": subject_names, "frame": max(frame_start, frame_end - 4), "paths": ["location", "scale"], "factor": 0.85},
                    source_index=index,
                    finding=finding,
                    confidence="low",
                )
            )
        if "anticipation" in text:
            operations.append(
                _operation(
                    "add_breakdown_pose",
                    "Add an anticipation breakdown before the main action.",
                    arguments={"object_names": subject_names, "frame": min(frame_end, frame_start + 4), "paths": ["location", "scale"], "factor": 0.15},
                    source_index=index,
                    finding=finding,
                    confidence="low",
                )
            )
        if "squash" in text or "stretch" in text or "scale change" in text or "scale animation" in text:
            operations.append(
                _operation(
                    "block_key_poses",
                    "Revise the blocking pass with explicit scale poses for squash/stretch or requested size change.",
                    arguments={"object_names": subject_names, "poses": [], "interpolation": "CONSTANT"},
                    source_index=index,
                    finding=finding,
                    confidence="low",
                )
            )
        if "no sampled world-space motion" in text or "clear motion" in text:
            operations.append(
                _operation(
                    "create_timing_chart",
                    "Rebuild a timing chart from the prompt contract before reblocking motion.",
                    arguments={"brief": brief or {}, "frame_start": frame_start, "frame_end": frame_end},
                    source_index=index,
                    finding=finding,
                )
            )
            operations.append(
                _operation(
                    "block_key_poses",
                    "Create or revise readable key poses after the timing chart is reviewed.",
                    arguments={"object_names": subject_names, "poses": [], "interpolation": "CONSTANT"},
                    source_index=index,
                    finding=finding,
                    confidence="low",
                )
            )
    if not operations and brief:
        operations.append(
            _operation(
                "create_timing_chart",
                "Rebuild a timing chart from the prompt contract before targeted repair.",
                arguments={"brief": brief, "frame_start": frame_start, "frame_end": frame_end},
            )
        )
    operations = _dedupe_operations(operations)
    suggestions = [
        {"tool": operation["tool"], "arguments": operation["arguments"], "reason": operation["reason"]}
        for operation in operations
    ]
    return {
        "ok": True,
        "message": f"Created {len(operations)} repair operation suggestion(s)",
        "repair_operations": operations,
        "suggested_tool_calls": suggestions,
        "mutates_scene": False,
    }
