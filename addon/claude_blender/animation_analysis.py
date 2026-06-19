"""Read-only animation sampling, validation, and repair-planning helpers."""

from __future__ import annotations

import math
import os

import bpy
import mathutils
from bpy_extras.object_utils import world_to_camera_view

from . import animation_brief, inspection_render, live_preview, playblast_capture


VISUAL_MOTION_DELTA_THRESHOLD = 0.01
VISUAL_SUBJECT_MIN_COVERAGE = 0.01
VISUAL_SUBJECT_TINY_COVERAGE = 0.04
VISUAL_CROP_EDGE_MARGIN = 0.02
INSPECTION_DETAIL_KEYWORDS = {
    "bay",
    "bays",
    "close-up",
    "closeup",
    "detail",
    "gear",
    "landing gear",
    "occluded",
    "side",
    "underside",
    "underneath",
    "wheel",
    "wheels",
}
EVIDENCE_COLLECTION_TOOLS = {"capture_animation_playblast", "capture_object_inspection_renders"}
READ_ONLY_REVIEW_TOOLS = {
    "create_timing_chart",
    "get_rigging_details",
    "review_playblast_against_brief",
    "review_inspection_renders_against_brief",
}
RIG_REPAIR_TERMS = {
    "anticipation",
    "center_of_mass",
    "contact",
    "control",
    "pose",
    "pose_clarity",
    "rig",
    "settle",
    "slide",
    "support",
    "weight",
}


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


def _optional_int(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


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


def _bbox_xy_contains(box, xy, margin=0.0):
    mins, maxs = box
    margin = float(margin or 0.0)
    return (
        float(mins[0]) - margin <= float(xy[0]) <= float(maxs[0]) + margin
        and float(mins[1]) - margin <= float(xy[1]) <= float(maxs[1]) + margin
    )


def _bbox_xy_distance_outside(box, xy, margin=0.0):
    mins, maxs = box
    margin = float(margin or 0.0)
    x = float(xy[0])
    y = float(xy[1])
    dx = max(float(mins[0]) - margin - x, 0.0, x - (float(maxs[0]) + margin))
    dy = max(float(mins[1]) - margin - y, 0.0, y - (float(maxs[1]) + margin))
    return math.sqrt(dx * dx + dy * dy)


def _bbox_world_corners(obj):
    corners = [obj.matrix_world @ mathutils.Vector(corner) for corner in getattr(obj, "bound_box", [])]
    if not corners:
        corners = [obj.matrix_world.translation]
    return corners


def _convex_hull_xy(points):
    unique = sorted({(round(float(point[0]), 8), round(float(point[1]), 8)) for point in points or []})
    if len(unique) <= 2:
        return unique

    def cross(origin, left, right):
        return (left[0] - origin[0]) * (right[1] - origin[1]) - (left[1] - origin[1]) * (right[0] - origin[0])

    lower = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _point_in_polygon_xy(point, polygon):
    if len(polygon or []) < 3:
        return False
    x = float(point[0])
    y = float(point[1])
    inside = False
    previous_x, previous_y = polygon[-1]
    for current_x, current_y in polygon:
        intersects = (current_y > y) != (previous_y > y)
        if intersects:
            x_at_y = (previous_x - current_x) * (y - current_y) / ((previous_y - current_y) or 1e-12) + current_x
            if x < x_at_y:
                inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def _point_segment_distance_xy(point, start, end):
    px, py = float(point[0]), float(point[1])
    sx, sy = float(start[0]), float(start[1])
    ex, ey = float(end[0]), float(end[1])
    dx = ex - sx
    dy = ey - sy
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return math.sqrt((px - sx) ** 2 + (py - sy) ** 2)
    t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / length_sq))
    nearest_x = sx + t * dx
    nearest_y = sy + t * dy
    return math.sqrt((px - nearest_x) ** 2 + (py - nearest_y) ** 2)


def _point_polygon_distance_outside_xy(point, polygon):
    if not polygon:
        return 0.0
    if _point_in_polygon_xy(point, polygon):
        return 0.0
    if len(polygon) == 1:
        return math.sqrt((float(point[0]) - polygon[0][0]) ** 2 + (float(point[1]) - polygon[0][1]) ** 2)
    return min(_point_segment_distance_xy(point, polygon[index], polygon[(index + 1) % len(polygon)]) for index in range(len(polygon)))


def _support_footprint_polygon(supports):
    points = []
    for support in supports or []:
        points.extend((corner[0], corner[1]) for corner in _bbox_world_corners(support))
    return _convex_hull_xy(points)


def _bbox_union(boxes):
    boxes = list(boxes or [])
    if not boxes:
        return None
    mins = [min(box[0][index] for box in boxes) for index in range(3)]
    maxs = [max(box[1][index] for box in boxes) for index in range(3)]
    return mins, maxs


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


def _object_samples_by_name(sample_summary):
    by_object = {}
    for frame in sample_summary.get("frames") or []:
        for obj in frame.get("objects") or []:
            by_object.setdefault(obj.get("name", ""), []).append(obj)
    for items in by_object.values():
        items.sort(key=lambda item: int(item.get("frame", 0) or 0))
    return {name: items for name, items in by_object.items() if name}


def _count_local_extrema(values, *, axis=2, minimum_prominence=0.05, mode="max"):
    count = 0
    extrema_frames = []
    if len(values) < 3:
        return count, extrema_frames
    for index in range(1, len(values) - 1):
        previous = float(values[index - 1]["world_location"][axis])
        current = float(values[index]["world_location"][axis])
        following = float(values[index + 1]["world_location"][axis])
        if mode == "min":
            is_extreme = current < previous and current < following
            prominence = min(previous - current, following - current)
        else:
            is_extreme = current > previous and current > following
            prominence = min(current - previous, current - following)
        if is_extreme and prominence >= float(minimum_prominence):
            count += 1
            extrema_frames.append(int(values[index].get("frame", 0) or 0))
    return count, extrema_frames


def _estimate_repeated_action_count(action, object_samples):
    action = str(action or "").lower()
    if action in {"bounce", "jump"}:
        return _count_local_extrema(object_samples, axis=2, minimum_prominence=0.03, mode="max")
    if action in {"fall", "drop"}:
        return _count_local_extrema(object_samples, axis=2, minimum_prominence=0.03, mode="min")
    return 0, []


def _scale_average(sample):
    scale = sample.get("scale") or []
    if not scale:
        return 1.0
    return sum(float(value) for value in scale[:3]) / min(3, len(scale))


def _action_keyframes(obj):
    action = _action_for_object(obj)
    if not action:
        return []
    frames = []
    for fcurve in _iter_fcurves(action):
        frames.extend(int(round(point.co.x)) for point in fcurve.keyframe_points)
    return sorted(set(frames))


def _settle_distance(object_samples, frame_end):
    if len(object_samples) < 3:
        return 0.0, []
    tail = object_samples[-3:]
    frames = [int(item.get("frame", 0) or 0) for item in tail]
    if frames[-1] < int(frame_end):
        return 0.0, frames
    distance = _distance(tail[-2]["world_location"], tail[-1]["world_location"])
    return round(distance, 6), frames


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


def _likely_support_objects(context, subjects):
    subject_names = {obj.name for obj in subjects}
    candidates = []
    for obj in context.scene.objects:
        if obj.name in subject_names or obj.type != "MESH":
            continue
        dimensions = obj.dimensions
        if float(dimensions.z) <= 0.2 and float(dimensions.x) >= 0.5 and float(dimensions.y) >= 0.5:
            candidates.append(obj)
    return candidates


def analyze_center_of_mass(
    context,
    *,
    object_names=None,
    support_object_names=None,
    frame_start=None,
    frame_end=None,
    sample_step=4,
    support_margin=0.05,
    contact_tolerance=0.12,
    selected_only=False,
):
    objects, missing = _resolve_objects(context, object_names, selected_only=selected_only)
    supports, support_missing = _resolve_objects(context, support_object_names, max_objects=20) if support_object_names else ([], [])
    if not supports:
        supports = _likely_support_objects(context, objects)
    frames = _frame_samples(context.scene, frame_start, frame_end, sample_step, max_samples=48)
    findings = []
    samples = []
    support_samples = []

    def collect(frame):
        support_boxes = [(support, _bbox_world(support)) for support in supports]
        support_union = _bbox_union([box for _support, box in support_boxes])
        support_polygon = _support_footprint_polygon(supports)
        support_top_z = max((box[1][2] for _support, box in support_boxes), default=None)
        support_item = {
            "frame": frame,
            "support_objects": [support.name for support, _box in support_boxes],
            "support_union_xy": [
                [round(float(support_union[0][0]), 6), round(float(support_union[0][1]), 6)],
                [round(float(support_union[1][0]), 6), round(float(support_union[1][1]), 6)],
            ] if support_union else [],
            "support_footprint_xy": [[round(float(x), 6), round(float(y), 6)] for x, y in support_polygon],
            "support_footprint_method": "convex_hull_world_bounds" if len(support_polygon) >= 3 else "axis_aligned_bbox",
            "support_top_z": round(float(support_top_z), 6) if support_top_z is not None else None,
        }
        support_samples.append(support_item)
        for obj in objects:
            mins, maxs = _bbox_world(obj)
            center = _world_center(obj)
            contact_like = bool(support_top_z is not None and abs(float(mins[2]) - float(support_top_z)) <= float(contact_tolerance))
            if len(support_polygon) >= 3:
                margin = float(support_margin or 0.0)
                polygon_distance = _point_polygon_distance_outside_xy((center[0], center[1]), support_polygon)
                supported = bool(polygon_distance <= margin)
                outside_distance = max(0.0, polygon_distance - margin)
            else:
                supported = bool(support_union and _bbox_xy_contains(support_union, (center[0], center[1]), margin=support_margin))
                outside_distance = _bbox_xy_distance_outside(support_union, (center[0], center[1]), margin=support_margin) if support_union else 0.0
            sample = {
                "frame": frame,
                "object": obj.name,
                "center_xy": [round(float(center[0]), 6), round(float(center[1]), 6)],
                "center_z": round(float(center[2]), 6),
                "bottom_z": round(float(mins[2]), 6),
                "top_z": round(float(maxs[2]), 6),
                "contact_like": contact_like,
                "support_available": bool(support_union),
                "center_within_support": supported,
                "outside_support_distance": round(float(outside_distance), 6),
            }
            samples.append(sample)
            if support_union and contact_like and not supported:
                findings.append(
                    {
                        "severity": "warning",
                        "requirement": "center_of_mass",
                        "principle": "weight",
                        "object": obj.name,
                        "frame": frame,
                        "repair_tool": "set_pose_hold",
                        "message": "Subject center is outside the support footprint during a contact-like pose.",
                        "evidence": {
                            "sampled_frames": [frame],
                            "support_objects": support_item["support_objects"],
                            "center_xy": sample["center_xy"],
                            "support_union_xy": support_item["support_union_xy"],
                            "support_footprint_xy": support_item["support_footprint_xy"],
                            "support_footprint_method": support_item["support_footprint_method"],
                            "outside_support_distance": sample["outside_support_distance"],
                        },
                    }
                )

    _set_frame_preserved(context, frames, collect)
    if objects and not supports:
        findings.append(
            {
                "severity": "info",
                "requirement": "center_of_mass",
                "principle": "weight",
                "message": "No support surface candidates were available for center-of-mass validation.",
                "repair_tool": "get_animation_scene_context",
                "evidence": {"sampled_frames": frames},
            }
        )
    return {
        "ok": True,
        "message": f"Analyzed center-of-mass support for {len(objects)} object(s)",
        "sampled_frames": frames,
        "samples": samples,
        "support_samples": support_samples,
        "support_object_names": [obj.name for obj in supports],
        "findings": findings,
        "missing_object_names": missing,
        "missing_support_object_names": support_missing,
    }


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
        by_object = _object_samples_by_name(samples)
        action = str(brief.get("action") or "").lower()
        requested_count = _optional_int(timing.get("requested_count"))
        scale_decreases = any("scale decreases" in str(item).lower() or "smaller" in str(item).lower() for item in (brief.get("secondary_actions") or []))
        scale_increases = any("scale increases" in str(item).lower() or "bigger" in str(item).lower() or "grow" in str(item).lower() for item in (brief.get("secondary_actions") or []))
        for name, items in by_object.items():
            if len(items) < 2:
                continue
            first_location = items[0]["world_location"]
            if any(_distance(first_location, item["world_location"]) > 0.001 for item in items[1:]):
                moved = True
            if requested_count is not None and action in {"bounce", "jump", "fall", "drop"}:
                detected_count, count_frames = _estimate_repeated_action_count(action, items)
                if detected_count != requested_count:
                    findings.append(
                        {
                            "severity": "warning",
                            "requirement": "action_count",
                            "principle": "timing_spacing",
                            "object": name,
                            "repair_tool": "create_progressive_bounce_animation" if scale_decreases and action in {"bounce", "jump"} else "animate_object_bounce",
                            "message": "Detected repeated action count does not match the requested count.",
                            "evidence": {
                                "requested_count": requested_count,
                                "detected_count": detected_count,
                                "detected_count_frames": count_frames,
                                "sampled_frames": samples.get("sampled_frames") or [],
                                "brief_frame_start": start,
                                "brief_frame_end": end,
                            },
                        }
                    )
            if scale_decreases or scale_increases:
                first_scale = _scale_average(items[0])
                last_scale = _scale_average(items[-1])
                if scale_decreases and last_scale >= first_scale - 0.01:
                    findings.append(
                        {
                            "severity": "warning",
                            "requirement": "scale_change",
                            "principle": "secondary_action",
                            "object": name,
                            "repair_tool": "create_progressive_bounce_animation" if action in {"bounce", "jump"} else "block_key_poses",
                            "message": "The brief asks for decreasing scale, but sampled scale does not decrease over the shot.",
                            "evidence": {
                                "first_scale_average": round(first_scale, 6),
                                "last_scale_average": round(last_scale, 6),
                                "sampled_frames": samples.get("sampled_frames") or [],
                                "brief_frame_start": start,
                                "brief_frame_end": end,
                            },
                        }
                    )
                if scale_increases and last_scale <= first_scale + 0.01:
                    findings.append(
                        {
                            "severity": "warning",
                            "requirement": "scale_change",
                            "principle": "secondary_action",
                            "object": name,
                            "repair_tool": "block_key_poses",
                            "message": "The brief asks for increasing scale, but sampled scale does not increase over the shot.",
                            "evidence": {
                                "first_scale_average": round(first_scale, 6),
                                "last_scale_average": round(last_scale, 6),
                                "sampled_frames": samples.get("sampled_frames") or [],
                                "brief_frame_start": start,
                                "brief_frame_end": end,
                            },
                        }
                    )
            settle_distance, settle_frames = _settle_distance(items, end)
            total_motion = max((_distance(items[0]["world_location"], item["world_location"]) for item in items[1:]), default=0.0)
            if action in {"bounce", "jump", "fall", "drop"} and total_motion > 0.001 and settle_distance > max(0.025, total_motion * 0.1):
                findings.append(
                    {
                        "severity": "warning",
                        "requirement": "settle",
                        "principle": "settle",
                        "object": name,
                        "frame": settle_frames[-1] if settle_frames else end,
                        "repair_tool": "add_breakdown_pose",
                        "message": "The final sampled poses still move noticeably, so the action may be missing a settle.",
                        "evidence": {
                            "settle_distance": settle_distance,
                            "settle_frames": settle_frames,
                            "sampled_frames": samples.get("sampled_frames") or [],
                            "brief_frame_start": start,
                            "brief_frame_end": end,
                        },
                    }
                )
            keyframes = _action_keyframes(bpy.data.objects.get(name)) if bpy.data.objects.get(name) else []
            if keyframes and (min(keyframes) > start or max(keyframes) < end):
                findings.append(
                    {
                        "severity": "info",
                        "requirement": "frame_range",
                        "principle": "timing_spacing",
                        "object": name,
                        "repair_tool": "retime_actions",
                        "message": "Object keyframes do not span the full contracted frame range.",
                        "evidence": {
                            "keyframe_start": min(keyframes),
                            "keyframe_end": max(keyframes),
                            "brief_frame_start": start,
                            "brief_frame_end": end,
                            "sampled_frames": samples.get("sampled_frames") or [],
                        },
                    }
                )
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
        center = analyze_center_of_mass(context, object_names=subjects, frame_start=start, frame_end=end, sample_step=validation_sample_step)
        validation_results["center_of_mass"] = center
        findings.extend(center.get("findings") or [])
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
        def pixel_luma_at(x, y):
            offset = (int(y) * width + int(x)) * 4
            return (
                0.2126 * float(pixels[offset])
                + 0.7152 * float(pixels[offset + 1])
                + 0.0722 * float(pixels[offset + 2])
            )

        corner_lumas = [
            pixel_luma_at(0, 0),
            pixel_luma_at(max(0, width - 1), 0),
            pixel_luma_at(0, max(0, height - 1)),
            pixel_luma_at(max(0, width - 1), max(0, height - 1)),
        ]
        background_luma = sum(corner_lumas) / len(corner_lumas)
        stride = max(1, math.ceil(pixel_count / max(1, int(max_samples))))
        sample_count = 0
        sum_r = sum_g = sum_b = sum_a = 0.0
        sum_luma = 0.0
        sum_luma_sq = 0.0
        min_luma = 1.0
        max_luma = 0.0
        foreground_count = 0
        fg_min_x = width - 1
        fg_min_y = height - 1
        fg_max_x = 0
        fg_max_y = 0
        fg_sum_x = 0.0
        fg_sum_y = 0.0
        foreground_threshold = 0.04
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
            if a > 0.05 and abs(luma - background_luma) >= foreground_threshold:
                x = pixel_index % width
                y = pixel_index // width
                foreground_count += 1
                fg_min_x = min(fg_min_x, x)
                fg_min_y = min(fg_min_y, y)
                fg_max_x = max(fg_max_x, x)
                fg_max_y = max(fg_max_y, y)
                fg_sum_x += x
                fg_sum_y += y

        grid = []
        grid_size = max(2, min(8, int(grid_size or 4)))
        for grid_y in range(grid_size):
            y = min(height - 1, max(0, int((grid_y + 0.5) * height / grid_size)))
            for grid_x in range(grid_size):
                x = min(width - 1, max(0, int((grid_x + 0.5) * width / grid_size)))
                offset = (y * width + x) * 4
                luma = 0.2126 * float(pixels[offset]) + 0.7152 * float(pixels[offset + 1]) + 0.0722 * float(pixels[offset + 2])
                grid.append(max(0, min(255, int(round(luma * 255)))))

        edge_total = 0
        edge_count = 0
        for grid_y in range(grid_size):
            for grid_x in range(grid_size):
                value = grid[grid_y * grid_size + grid_x]
                if grid_x + 1 < grid_size:
                    edge_total += abs(value - grid[grid_y * grid_size + grid_x + 1])
                    edge_count += 1
                if grid_y + 1 < grid_size:
                    edge_total += abs(value - grid[(grid_y + 1) * grid_size + grid_x])
                    edge_count += 1
        detail_score = (edge_total / (edge_count * 255.0)) if edge_count else 0.0
        mean_luma = sum_luma / sample_count if sample_count else 0.0
        variance = max(0.0, (sum_luma_sq / sample_count) - (mean_luma * mean_luma)) if sample_count else 0.0
        coverage_ratio = (foreground_count / sample_count) if sample_count else 0.0
        if foreground_count:
            bbox = [
                round(fg_min_x / max(1, width - 1), 6),
                round(fg_min_y / max(1, height - 1), 6),
                round(fg_max_x / max(1, width - 1), 6),
                round(fg_max_y / max(1, height - 1), 6),
            ]
            center = [
                round((fg_sum_x / foreground_count) / max(1, width - 1), 6),
                round((fg_sum_y / foreground_count) / max(1, height - 1), 6),
            ]
        else:
            bbox = []
            center = []
        edge_touch = {
            "left": bool(bbox and bbox[0] <= VISUAL_CROP_EDGE_MARGIN),
            "top": bool(bbox and bbox[1] <= VISUAL_CROP_EDGE_MARGIN),
            "right": bool(bbox and bbox[2] >= 1.0 - VISUAL_CROP_EDGE_MARGIN),
            "bottom": bool(bbox and bbox[3] >= 1.0 - VISUAL_CROP_EDGE_MARGIN),
        }
        edge_touch_count = sum(1 for value in edge_touch.values() if value)
        if (max_luma - min_luma) <= 0.005 and variance <= 0.00001:
            framing_read = "low_contrast"
        elif coverage_ratio < VISUAL_SUBJECT_MIN_COVERAGE:
            framing_read = "no_subject"
        elif coverage_ratio < VISUAL_SUBJECT_TINY_COVERAGE:
            framing_read = "tiny_subject"
        elif edge_touch_count:
            framing_read = "cropped_subject"
        elif detail_score < 0.01:
            framing_read = "soft_or_low_detail"
        else:
            framing_read = "readable"
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
            "visual_subject": {
                "coverage_ratio": round(float(coverage_ratio), 6),
                "foreground_sample_count": int(foreground_count),
                "background_luminance_estimate": round(float(background_luma), 6),
                "foreground_threshold": round(float(foreground_threshold), 6),
                "bbox_normalized": bbox,
                "center_normalized": center,
                "edge_touch": edge_touch,
                "edge_touch_count": int(edge_touch_count),
                "likely_cropped": bool(edge_touch_count),
                "detail_score": round(float(detail_score), 6),
                "framing_read": framing_read,
            },
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


def _visual_subject_from_item(item):
    digest = item.get("image_digest") if isinstance(item, dict) else {}
    return digest.get("visual_subject") if isinstance(digest, dict) else {}


def _visual_interpretation_summary(items):
    subjects = [
        subject
        for subject in (_visual_subject_from_item(item) for item in items or [])
        if isinstance(subject, dict) and subject
    ]
    reads = {}
    for subject in subjects:
        key = str(subject.get("framing_read") or "unknown")
        reads[key] = reads.get(key, 0) + 1
    readable = reads.get("readable", 0)
    usable = len(subjects)
    average_coverage = (
        sum(float(subject.get("coverage_ratio", 0.0) or 0.0) for subject in subjects) / usable
        if usable
        else 0.0
    )
    average_detail = (
        sum(float(subject.get("detail_score", 0.0) or 0.0) for subject in subjects) / usable
        if usable
        else 0.0
    )
    cropped = [item for item in items or [] if (_visual_subject_from_item(item) or {}).get("likely_cropped")]
    weak = [
        item
        for item in items or []
        if str((_visual_subject_from_item(item) or {}).get("framing_read") or "")
        in {"low_contrast", "no_subject", "tiny_subject", "soft_or_low_detail"}
    ]
    return {
        "interpreted_image_count": usable,
        "readable_image_count": readable,
        "framing_reads": reads,
        "average_subject_coverage": round(float(average_coverage), 6),
        "average_detail_score": round(float(average_detail), 6),
        "cropped_image_count": len(cropped),
        "weak_image_count": len(weak),
    }


def _visual_subject_findings(subject, *, principle, frame=None, object_name="", view="", path="", repair_tool="capture_animation_playblast"):
    findings = []
    read = str((subject or {}).get("framing_read") or "")
    if read not in {"cropped_subject", "no_subject", "tiny_subject"}:
        return findings
    if read == "cropped_subject":
        message = "Visual evidence suggests the subject may be cropped by the image frame."
        severity = "warning"
    elif read == "no_subject":
        message = "Visual evidence does not show a readable foreground subject."
        severity = "warning"
    else:
        message = "Visual evidence shows only a very small foreground subject, so pose/detail review may be weak."
        severity = "info"
    findings.append(
        _finding(
            severity,
            message,
            principle=principle,
            frame=frame,
            object_name=object_name,
            repair_tool=repair_tool,
            evidence={
                "path": path,
                "view": view,
                "visual_subject": subject,
            },
        )
    )
    return findings


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


def _count_visual_extrema(points, *, mode, minimum_prominence):
    count = 0
    frames = []
    if len(points) < 3:
        return count, frames
    for index in range(1, len(points) - 1):
        previous = float(points[index - 1]["center_y"])
        current = float(points[index]["center_y"])
        following = float(points[index + 1]["center_y"])
        if mode == "min":
            is_extreme = current < previous and current < following
            prominence = min(previous - current, following - current)
        else:
            is_extreme = current > previous and current > following
            prominence = min(current - previous, current - following)
        if is_extreme and prominence >= float(minimum_prominence):
            count += 1
            frames.append(int(points[index].get("frame", 0) or 0))
    return count, frames


def _visual_action_count_evidence(visual_evidence, brief, *, requested_count=None):
    action = str((brief or {}).get("action") or "").lower() if isinstance(brief, dict) else ""
    requested_count = _optional_int(requested_count)
    if requested_count is None or action not in {"bounce", "jump", "fall", "drop"}:
        return {"available": False, "reason": "no_requested_repeated_visual_action"}
    track = []
    skipped_frames = []
    for frame in visual_evidence or []:
        subject = _visual_subject_from_item(frame)
        center = subject.get("center_normalized") if isinstance(subject, dict) else None
        read = str(subject.get("framing_read") or "") if isinstance(subject, dict) else ""
        if not isinstance(center, list) or len(center) < 2 or read in {"no_subject", "low_contrast"}:
            if frame.get("frame") is not None:
                skipped_frames.append(int(frame.get("frame", 0) or 0))
            continue
        try:
            center_y = float(center[1])
        except (TypeError, ValueError):
            continue
        track.append(
            {
                "frame": int(frame.get("frame", 0) or 0),
                "center_y": round(center_y, 6),
                "coverage_ratio": round(float(subject.get("coverage_ratio", 0.0) or 0.0), 6),
                "framing_read": read or "unknown",
            }
        )
    track.sort(key=lambda item: item["frame"])
    required_samples = max(3, requested_count * 2 + 1)
    sampled_frames = [item["frame"] for item in track]
    if len(track) < required_samples:
        return {
            "available": False,
            "reason": "insufficient_visual_samples",
            "action": action,
            "requested_count": requested_count,
            "required_sample_count": required_samples,
            "usable_sample_count": len(track),
            "sampled_frames": sampled_frames,
            "skipped_frames": skipped_frames,
        }
    center_values = [item["center_y"] for item in track]
    center_y_range = max(center_values) - min(center_values) if center_values else 0.0
    minimum_prominence = max(0.02, center_y_range * 0.2)
    min_count, min_frames = _count_visual_extrema(track, mode="min", minimum_prominence=minimum_prominence)
    max_count, max_frames = _count_visual_extrema(track, mode="max", minimum_prominence=minimum_prominence)
    if action in {"bounce", "jump"}:
        if min_count >= max_count:
            detected_count, extrema_frames, extrema_mode = min_count, min_frames, "min_y"
        else:
            detected_count, extrema_frames, extrema_mode = max_count, max_frames, "max_y"
    elif action in {"fall", "drop"}:
        detected_count, extrema_frames, extrema_mode = max_count, max_frames, "max_y"
    else:
        detected_count, extrema_frames, extrema_mode = 0, [], ""
    confidence = "high" if center_y_range >= 0.08 and detected_count > 0 else "medium" if center_y_range >= 0.03 else "low"
    return {
        "available": True,
        "method": "visual_subject_center_extrema",
        "action": action,
        "requested_count": requested_count,
        "detected_count": int(detected_count),
        "detected_count_frames": extrema_frames,
        "extrema_mode": extrema_mode,
        "min_y_extrema_count": int(min_count),
        "max_y_extrema_count": int(max_count),
        "center_y_range": round(float(center_y_range), 6),
        "minimum_prominence": round(float(minimum_prominence), 6),
        "confidence": confidence,
        "sample_count": len(track),
        "sampled_frames": sampled_frames,
        "skipped_frames": skipped_frames,
        "track": track[:24],
        "note": "Uses screen-space foreground center changes; camera motion, cropping, or weak foreground separation can make this a hint rather than proof.",
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
                findings.extend(
                    _visual_subject_findings(
                        digest.get("visual_subject") or {},
                        principle="visual_review",
                        frame=frame_number,
                        path=path,
                        repair_tool="capture_animation_playblast",
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


def _normalize_inspection_render(context, metadata):
    if isinstance(metadata, dict) and metadata:
        return metadata
    return inspection_render.latest_inspection_render_metadata(context=context)


def _inspection_text(brief, prompt):
    parts = [str(prompt or "")]
    if isinstance(brief, dict):
        parts.extend(str(item) for item in (brief.get("secondary_actions") or []))
        parts.extend(str(item) for item in (brief.get("success_criteria") or []))
        parts.append(str(brief.get("user_visible_interpretation") or ""))
        parts.append(str(brief.get("action") or ""))
    return " ".join(parts).lower()


def _required_inspection_views(brief, prompt):
    text = _inspection_text(brief, prompt)
    views = []
    if any(word in text for word in ("underside", "underneath", "landing gear", "gear", "bay", "bays", "wheel", "wheels")):
        views.extend(["front_below", "underside", "side"])
    if "side" in text:
        views.append("side")
    if any(word in text for word in ("front", "nose")):
        views.append("front")
    result = []
    for view in views:
        if view not in result:
            result.append(view)
    return result


def _inspection_render_evidence(metadata):
    evidence = []
    findings = []
    for image_item in metadata.get("images") or []:
        path = str(image_item.get("path") or "")
        file_exists = bool(path and os.path.isfile(path))
        available = bool(image_item.get("available")) and (not path or file_exists)
        item = {
            "image_id": str(image_item.get("image_id") or ""),
            "object": str(image_item.get("object") or ""),
            "view": str(image_item.get("view") or ""),
            "available": available,
            "resource_uri": str(image_item.get("resource_uri") or ""),
            "path": path,
            "file_exists": file_exists,
            "size_bytes": int(image_item.get("size_bytes", 0) or 0),
            "width": int(image_item.get("width", 0) or 0),
            "height": int(image_item.get("height", 0) or 0),
            "note": str(image_item.get("note") or ""),
        }
        if available and path:
            digest = _image_digest(path)
            if digest:
                item["image_digest"] = digest
                if not digest.get("available"):
                    findings.append(
                        _finding(
                            "warning",
                            "An inspection render is available but its image pixels could not be inspected.",
                            principle="visual_detail_review",
                            object_name=item["object"],
                            repair_tool="capture_object_inspection_renders",
                            evidence={"path": path, "image_id": item["image_id"], "view": item["view"], "note": digest.get("note", "")},
                        )
                    )
                elif digest.get("mean_alpha", 1.0) <= 0.01:
                    findings.append(
                        _finding(
                            "warning",
                            "An inspection render appears transparent or empty.",
                            principle="visual_detail_review",
                            object_name=item["object"],
                            repair_tool="capture_object_inspection_renders",
                            evidence={"path": path, "image_id": item["image_id"], "view": item["view"], "mean_alpha": digest.get("mean_alpha", 0.0)},
                        )
                    )
                elif digest.get("luminance_range", 1.0) <= 0.005 and digest.get("luminance_variance", 1.0) <= 0.00001:
                    findings.append(
                        _finding(
                            "info",
                            "An inspection render has very low visible contrast, so visual-detail review may be weak.",
                            principle="visual_detail_review",
                            object_name=item["object"],
                            repair_tool="capture_object_inspection_renders",
                            evidence={
                                "path": path,
                                "image_id": item["image_id"],
                                "view": item["view"],
                                "luminance_range": digest.get("luminance_range", 0.0),
                                "luminance_variance": digest.get("luminance_variance", 0.0),
                            },
                        )
                    )
                findings.extend(
                    _visual_subject_findings(
                        digest.get("visual_subject") or {},
                        principle="visual_detail_review",
                        object_name=item["object"],
                        view=item["view"],
                        path=path,
                        repair_tool="capture_object_inspection_renders",
                    )
                )
        evidence.append(item)
        if image_item.get("available") and path and not file_exists:
            findings.append(
                _finding(
                    "warning",
                    "An inspection render is marked available but the PNG file is missing.",
                    principle="visual_detail_review",
                    object_name=item["object"],
                    repair_tool="capture_object_inspection_renders",
                    evidence={"path": path, "image_id": item["image_id"], "view": item["view"]},
                )
            )
        if available and (item["width"] <= 0 or item["height"] <= 0 or item["size_bytes"] <= 0):
            findings.append(
                _finding(
                    "warning",
                    "An inspection render has incomplete image metadata.",
                    principle="visual_detail_review",
                    object_name=item["object"],
                    repair_tool="capture_object_inspection_renders",
                    evidence={"image_id": item["image_id"], "view": item["view"], "width": item["width"], "height": item["height"], "size_bytes": item["size_bytes"]},
                )
            )
    return evidence, findings


def review_inspection_renders_against_brief(context, *, inspection_render_metadata=None, brief=None, prompt=""):
    metadata = _normalize_inspection_render(context, inspection_render_metadata)
    brief = brief if isinstance(brief, dict) else {}
    findings = []
    image_evidence, image_findings = _inspection_render_evidence(metadata)
    findings.extend(image_findings)
    usable_images = [item for item in image_evidence if item.get("available")]
    image_interpretation = _visual_interpretation_summary(usable_images)
    object_names = list(metadata.get("object_names") or [])
    if not object_names:
        object_names = sorted({item.get("object", "") for item in image_evidence if item.get("object")})
    if not object_names:
        object_names = _brief_subject_names(brief)
    required_views = _required_inspection_views(brief, prompt)
    available_views = sorted({item.get("view", "") for item in usable_images if item.get("view")})
    missing_views = [view for view in required_views if view not in available_views]
    if not metadata.get("available") or not usable_images:
        findings.append(
            _finding(
                "warning",
                "No usable object inspection renders are available for visual-detail review.",
                principle="visual_detail_review",
                repair_tool="capture_object_inspection_renders",
                evidence={
                    "object_names": object_names,
                    "requested_views": required_views or ["front_below", "side"],
                    "available_views": available_views,
                    "metadata_uri": metadata.get("metadata_uri", ""),
                },
            )
        )
    if required_views and missing_views:
        findings.append(
            _finding(
                "warning",
                "Inspection renders do not include all views needed by the prompt or brief.",
                principle="visual_detail_review",
                repair_tool="capture_object_inspection_renders",
                evidence={
                    "object_names": object_names,
                    "requested_views": required_views,
                    "available_views": available_views,
                    "missing_views": missing_views,
                    "metadata_uri": metadata.get("metadata_uri", ""),
                },
            )
        )
    if usable_images and any(keyword in _inspection_text(brief, prompt) for keyword in INSPECTION_DETAIL_KEYWORDS):
        findings.append(
            _finding(
                "info",
                "Inspection render evidence is available for visual-detail repair decisions.",
                principle="visual_detail_review",
                evidence={
                    "object_names": object_names,
                    "available_views": available_views,
                    "image_resource_uris": [item.get("resource_uri", "") for item in usable_images if item.get("resource_uri")],
                    "metadata_uri": metadata.get("metadata_uri", ""),
                },
            )
        )
    repair_plan = repair_animation_from_findings(context, findings=findings, brief=brief)
    return {
        "ok": True,
        "message": "Reviewed object inspection render evidence against brief",
        "status": "pass" if not [item for item in findings if str(item.get("severity", "")).lower() in {"warning", "error"}] else "needs_repair",
        "render_id": metadata.get("render_id", ""),
        "image_count": len(metadata.get("images") or []),
        "usable_image_count": len(usable_images),
        "visual_detail_review": {
            "available": bool(metadata.get("available")) and bool(usable_images),
            "metadata_uri": metadata.get("metadata_uri", ""),
            "resource_type": metadata.get("resource_type", ""),
            "required_views": required_views,
            "available_views": available_views,
            "missing_views": missing_views,
            "images": image_evidence,
            "image_interpretation": image_interpretation,
        },
        "findings": findings,
        "repair_operations": repair_plan.get("repair_operations", []),
        "suggested_tool_calls": repair_plan.get("suggested_tool_calls", []),
    }


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
    image_interpretation = _visual_interpretation_summary(usable_frames)
    coverage = _playblast_coverage(context, metadata, brief)
    if not metadata.get("available") and not usable_frames:
        findings.append(
            _finding(
                "warning",
                "No playblast frames are available for visual animation review.",
                principle="visual_review",
                repair_tool="capture_animation_playblast",
                evidence=coverage,
            )
        )
    if frames and len(usable_frames) < len(frames):
        unavailable_frames = [int(frame.get("frame", 0) or 0) for frame in visual_evidence if not frame.get("available")]
        findings.append(
            _finding(
                "warning",
                "Some requested playblast frames are unavailable.",
                principle="visual_review",
                repair_tool="capture_animation_playblast",
                evidence={
                    "requested_frame_count": len(frames),
                    "usable_frame_count": len(usable_frames),
                    "unavailable_frames": unavailable_frames,
                    "sampled_frames": coverage["sampled_frames"],
                },
            )
        )
    if usable_frames and len(usable_frames) < 3:
        findings.append(
            _finding(
                "info",
                "Playblast has very few usable sampled frames; timing and spacing review may be weak.",
                principle="visual_review",
                repair_tool="capture_animation_playblast",
                evidence={"usable_frame_count": len(usable_frames), "sampled_frames": coverage["sampled_frames"]},
            )
        )
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
    requested_count = _optional_int(((brief or {}).get("timing") or {}).get("requested_count") if isinstance(brief, dict) else None)
    if requested_count and usable_frames and len(usable_frames) < max(3, requested_count * 2 + 1):
        findings.append(
            _finding(
                "info",
                "Playblast may be undersampled for the requested repeated action count.",
                principle="timing_spacing",
                repair_tool="capture_animation_playblast",
                evidence={
                    "requested_count": requested_count,
                    "usable_frame_count": len(usable_frames),
                    "sampled_frames": coverage["sampled_frames"],
                },
            )
        )
    visual_count_evidence = _visual_action_count_evidence(visual_evidence, brief, requested_count=requested_count)
    if (
        visual_count_evidence.get("available")
        and requested_count
        and visual_count_evidence.get("confidence") != "low"
        and int(visual_count_evidence.get("detected_count", 0) or 0) != requested_count
    ):
        repair_tool = "create_progressive_bounce_animation" if str((brief or {}).get("action") or "").lower() in {"bounce", "jump"} else "block_key_poses"
        findings.append(
            _finding(
                "warning",
                "Visual playblast evidence suggests the repeated action count does not match the brief.",
                principle="timing_spacing",
                requirement="action_count",
                repair_tool=repair_tool,
                evidence={
                    "source": "visual_playblast",
                    "requested_count": requested_count,
                    "detected_count": int(visual_count_evidence.get("detected_count", 0) or 0),
                    "detected_count_frames": visual_count_evidence.get("detected_count_frames") or [],
                    "sampled_frames": visual_count_evidence.get("sampled_frames") or coverage["sampled_frames"],
                    "confidence": visual_count_evidence.get("confidence"),
                    "center_y_range": visual_count_evidence.get("center_y_range"),
                    "brief_frame_start": coverage["brief_frame_start"],
                    "brief_frame_end": coverage["brief_frame_end"],
                },
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
            "motion_evidence": {**motion_evidence, "action_count_evidence": visual_count_evidence},
            "image_interpretation": image_interpretation,
            "review_hints": metadata.get("review_hints") or [],
        },
        "findings": findings,
        "comparison": comparison,
        "repair_operations": repair_plan.get("repair_operations", []),
        "suggested_tool_calls": repair_plan.get("suggested_tool_calls", []),
    }


def _operation(tool, reason, *, arguments=None, source_index=None, finding=None, confidence="medium", target_frames=None, target_frame_range=None):
    arguments = arguments or {}
    mutates_scene = tool not in EVIDENCE_COLLECTION_TOOLS and tool not in READ_ONLY_REVIEW_TOOLS
    execution_phase = "repair_preview" if mutates_scene else "planning"
    if tool in EVIDENCE_COLLECTION_TOOLS:
        execution_phase = "evidence_collection"
    operation = {
        "tool": tool,
        "arguments": arguments,
        "tool_call": {"name": tool, "input": arguments},
        "reason": reason,
        "confidence": confidence,
        "mutates_scene": mutates_scene,
        "preview_safe": bool(mutates_scene),
        "requires_user_commit": bool(mutates_scene),
        "execution_phase": execution_phase,
    }
    if target_frames:
        operation["target_frames"] = [int(frame) for frame in target_frames]
    if target_frame_range:
        operation["target_frame_range"] = [int(target_frame_range[0]), int(target_frame_range[1])]
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


def _unique_frames(frames):
    result = []
    seen = set()
    for frame in frames or []:
        try:
            value = int(frame)
        except (TypeError, ValueError):
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return sorted(result)


def _finding_target_frames(finding):
    evidence = finding.get("evidence") if isinstance(finding, dict) and isinstance(finding.get("evidence"), dict) else {}
    frames = []
    if isinstance(finding, dict) and finding.get("frame") is not None:
        frames.append(finding.get("frame"))
    frames.extend(evidence.get("sampled_frames") or [])
    frames.extend(evidence.get("unavailable_frames") or [])
    for delta in evidence.get("frame_deltas") or []:
        if not isinstance(delta, dict):
            continue
        frames.append(delta.get("from_frame"))
        frames.append(delta.get("to_frame"))
    for key in ("first_sampled_frame", "last_sampled_frame", "brief_frame_start", "brief_frame_end"):
        if evidence.get(key) is not None:
            frames.append(evidence.get(key))
    return _unique_frames(frames)


def _finding_target_range(finding, frame_start, frame_end):
    evidence = finding.get("evidence") if isinstance(finding, dict) and isinstance(finding.get("evidence"), dict) else {}
    start = int(evidence.get("brief_frame_start", frame_start) or frame_start)
    end = int(evidence.get("brief_frame_end", frame_end) or frame_end)
    if evidence.get("covers_start") is False and evidence.get("first_sampled_frame") is not None:
        return [start, int(evidence.get("first_sampled_frame") or start)]
    if evidence.get("covers_end") is False and evidence.get("last_sampled_frame") is not None:
        return [int(evidence.get("last_sampled_frame") or end), end]
    target_frames = _finding_target_frames(finding)
    if target_frames:
        return [min(target_frames), max(target_frames)]
    if evidence and start != end:
        return [start, end]
    return []


def _finding_evidence(finding):
    return finding.get("evidence") if isinstance(finding, dict) and isinstance(finding.get("evidence"), dict) else {}


def _finding_object_names(finding, fallback=None):
    evidence = _finding_evidence(finding)
    names = _name_list(evidence.get("object_names"))
    if not names and finding.get("object"):
        names = [str(finding.get("object"))]
    if not names:
        names = list(fallback or [])
    return names


def _finding_views(finding, fallback=None):
    evidence = _finding_evidence(finding)
    views = (
        _name_list(evidence.get("missing_views"))
        or _name_list(evidence.get("requested_views"))
        or _name_list(evidence.get("view"))
        or list(fallback or [])
    )
    return views or ["front_below", "side"]


def _rig_control_bone_names(armature, *, maximum=6):
    result = []
    pose_bones = list(getattr(getattr(armature, "pose", None), "bones", []) or [])
    for pose_bone in pose_bones:
        data_bone = armature.data.bones.get(pose_bone.name) if armature.data else None
        lower = pose_bone.name.lower()
        if (
            "ctrl" in lower
            or "control" in lower
            or "ik" in lower
            or "fk" in lower
            or "target" in lower
            or getattr(pose_bone, "custom_shape", None)
            or (data_bone and not data_bone.use_deform)
        ):
            result.append(pose_bone.name)
        if len(result) >= maximum:
            break
    if not result:
        result = [pose_bone.name for pose_bone in pose_bones[:maximum]]
    return result


def _rig_repair_target(context, object_names):
    seen = set()
    armatures = []
    for name in object_names or []:
        obj = bpy.data.objects.get(str(name))
        if obj is None:
            continue
        if obj.type == "ARMATURE" and obj.name not in seen:
            armatures.append(obj)
            seen.add(obj.name)
        parent = obj.parent if getattr(obj.parent, "type", None) == "ARMATURE" else None
        if parent and parent.name not in seen:
            armatures.append(parent)
            seen.add(parent.name)
        for modifier in getattr(obj, "modifiers", []) or []:
            if getattr(modifier, "type", "") != "ARMATURE":
                continue
            armature = getattr(modifier, "object", None)
            if armature and armature.name not in seen:
                armatures.append(armature)
                seen.add(armature.name)
    for armature in armatures:
        bone_names = _rig_control_bone_names(armature)
        if bone_names:
            return {
                "armature_name": armature.name,
                "bone_names": bone_names,
                "source_object_names": list(object_names or []),
            }
    return {}


def _text_has_rig_repair_terms(text):
    normalized = str(text or "").lower()
    return any(term in normalized for term in RIG_REPAIR_TERMS)


def _dedupe_operations(operations):
    result = []
    seen = set()
    for operation in operations:
        key = (
            operation.get("tool"),
            repr(sorted((operation.get("arguments") or {}).items())),
            operation.get("reason"),
            repr(operation.get("target_frames") or []),
            repr(operation.get("target_frame_range") or []),
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
    action = str((brief or {}).get("action") or "").lower() if isinstance(brief, dict) else ""
    secondary_actions = [str(item).lower() for item in ((brief or {}).get("secondary_actions") or [])] if isinstance(brief, dict) else []
    scale_decreases = any("scale decreases" in item or "smaller" in item or "scale down" in item for item in secondary_actions)
    requested_count = ((brief or {}).get("timing") or {}).get("requested_count") if isinstance((brief or {}).get("timing"), dict) else None
    try:
        requested_count = int(requested_count) if requested_count is not None else None
    except (TypeError, ValueError):
        requested_count = None
    for index, finding in enumerate(findings or []):
        target_frames = _finding_target_frames(finding)
        target_frame_range = _finding_target_range(finding, frame_start, frame_end)
        repair_tool = str(finding.get("repair_tool") or "").lower()
        evidence = _finding_evidence(finding)
        severity = str(finding.get("severity", "")).lower()
        text = " ".join(
            str(finding.get(key) or "")
            for key in ("message", "principle", "requirement", "repair_tool", "recommendation")
        ).lower()
        target_object_names = _finding_object_names(finding, subject_names)
        rig_target = _rig_repair_target(context, target_object_names)
        if rig_target and _text_has_rig_repair_terms(text):
            hold_frame = int(finding.get("frame", target_frames[0] if target_frames else frame_start) or frame_start)
            operations.append(
                _operation(
                    "get_rigging_details",
                    "Inspect rig controls before applying rig-specific pose repair.",
                    arguments={"object_names": [rig_target["armature_name"]], "max_objects": 4},
                    source_index=index,
                    finding=finding,
                    confidence="high",
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
                )
            )
            operations.append(
                _operation(
                    "set_rig_pose_hold",
                    "Hold keyed rig control bones so the rig-driven subject reads cleanly at the problem pose.",
                    arguments={
                        "armature_name": rig_target["armature_name"],
                        "bone_names": rig_target["bone_names"],
                        "frame": hold_frame,
                        "hold_frames": 4,
                        "interpolation": "CONSTANT",
                    },
                    source_index=index,
                    finding=finding,
                    confidence="medium",
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
                )
            )
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
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
                )
            )
        if repair_tool == "capture_object_inspection_renders" or (
            not repair_tool
            and severity in {"warning", "error"}
            and ("inspection render" in text or "visual-detail" in text or any(keyword in text for keyword in INSPECTION_DETAIL_KEYWORDS))
        ):
            object_names = _finding_object_names(finding, subject_names)
            operations.append(
                _operation(
                    "capture_object_inspection_renders",
                    "Capture focused object close-up renders so visual-detail repair has usable evidence.",
                    arguments={
                        "object_names": object_names,
                        "views": _finding_views(finding),
                        "frame": evidence.get("frame", target_frames[0] if target_frames else frame_start),
                        "resolution_x": 800,
                        "resolution_y": 600,
                        "note": str(finding.get("message") or "Visual-detail inspection evidence")[:240],
                    },
                    source_index=index,
                    finding=finding,
                    confidence="high" if object_names else "medium",
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
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
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
                )
            )
        if "action_count" in text or "requested count" in text or "wrong count" in text or "bounce count" in text:
            if action in {"bounce", "jump"} and primary_subject:
                if scale_decreases:
                    operations.append(
                        _operation(
                            "create_progressive_bounce_animation",
                            "Regenerate the helper-backed bounce with the requested count and scale change.",
                            arguments={
                                "object_name": primary_subject,
                                "frame_start": frame_start,
                                "frame_end": frame_end,
                                "axis": "Z",
                                "cycles": requested_count or 2,
                                "scale_end_factor": 0.6,
                                "interpolation": "BEZIER",
                            },
                            source_index=index,
                            finding=finding,
                            confidence="high",
                            target_frames=target_frames,
                            target_frame_range=target_frame_range,
                        )
                    )
                else:
                    operations.append(
                        _operation(
                            "animate_object_bounce",
                            "Regenerate the helper-backed bounce with the requested count.",
                            arguments={
                                "object_name": primary_subject,
                                "frame_start": frame_start,
                                "frame_end": frame_end,
                                "axis": "Z",
                                "cycles": requested_count or 2,
                                "interpolation": "BEZIER",
                            },
                            source_index=index,
                            finding=finding,
                            confidence="high",
                            target_frames=target_frames,
                            target_frame_range=target_frame_range,
                        )
                    )
            else:
                operations.append(
                    _operation(
                        "block_key_poses",
                        "Reblock key poses to satisfy the requested repeated action count.",
                        arguments={"object_names": subject_names, "poses": [], "interpolation": "CONSTANT"},
                        source_index=index,
                        finding=finding,
                        confidence="low",
                        target_frames=target_frames,
                        target_frame_range=target_frame_range,
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
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
                )
            )
        if "center_of_mass" in text or "support footprint" in text or "support" in text:
            hold_frame = int(finding.get("frame", target_frames[0] if target_frames else frame_start) or frame_start)
            operations.append(
                _operation(
                    "set_pose_hold",
                    "Hold or re-key the support/contact pose so the subject reads as balanced.",
                    arguments={"object_names": subject_names, "frame": hold_frame, "hold_frames": 3, "paths": ["location"]},
                    source_index=index,
                    finding=finding,
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
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
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
                )
            )
        if "frame_range" in text or "contracted frame range" in text or "outside the brief frame range" in text:
            operations.append(
                _operation(
                    "set_scene_frame_range",
                    "Align the scene frame range to the prompt contract before retiming repairs.",
                    arguments={"frame_start": frame_start, "frame_end": frame_end, "current_frame": frame_start},
                    source_index=index,
                    finding=finding,
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
                )
            )
            operations.append(
                _operation(
                    "retime_actions",
                    "Retiming may bring keyed motion back inside the contracted frame range.",
                    arguments={"object_names": subject_names, "frame_start": frame_start, "frame_end": frame_end, "snap_to_integer": True},
                    source_index=index,
                    finding=finding,
                    confidence="low",
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
                )
            )
        if "contact" in text or "slide" in text:
            hold_frame = int(finding.get("frame", target_frames[0] if target_frames else frame_start) or frame_start)
            operations.append(
                _operation(
                    "set_pose_hold",
                    "Hold or re-key contact poses to reduce sliding and improve weight.",
                    arguments={"object_names": subject_names, "frame": hold_frame, "hold_frames": 4, "paths": ["location"]},
                    source_index=index,
                    finding=finding,
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
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
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
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
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
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
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
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
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
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
                    target_frames=target_frames,
                    target_frame_range=target_frame_range,
                )
            )
    actionable_findings = [
        finding
        for finding in findings or []
        if str(finding.get("severity", "")).lower() in {"warning", "error"} or finding.get("repair_tool")
    ]
    if not operations and brief and actionable_findings:
        operations.append(
            _operation(
                "create_timing_chart",
                "Rebuild a timing chart from the prompt contract before targeted repair.",
                arguments={"brief": brief, "frame_start": frame_start, "frame_end": frame_end},
            )
        )
    operations = _dedupe_operations(operations)
    suggestions = []
    for operation in operations:
        suggestion = {"tool": operation["tool"], "arguments": operation["arguments"], "reason": operation["reason"]}
        if operation.get("target_frames"):
            suggestion["target_frames"] = operation["target_frames"]
        if operation.get("target_frame_range"):
            suggestion["target_frame_range"] = operation["target_frame_range"]
        suggestions.append(suggestion)
    return {
        "ok": True,
        "message": f"Created {len(operations)} repair operation suggestion(s)",
        "repair_operations": operations,
        "suggested_tool_calls": suggestions,
        "mutates_scene": False,
    }
