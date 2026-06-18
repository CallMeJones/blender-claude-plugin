"""Execute Claude-requested Blender tools on the main Blender thread."""

from __future__ import annotations

import json
import re
import time

import bpy

from . import animation_analysis, animation_brief, animation_workflow, advanced_helpers, context_bundle, docs_index, inspection_render, lab_parity, live_preview, playblast_capture, preferences, render_jobs, script_runner, viewport_capture, world_model


def _float_list(values, length, default):
    if values is None:
        return list(default)
    result = list(values)[:length]
    while len(result) < length:
        result.append(default[len(result)])
    return [float(value) for value in result]


def _optional_float_list(values, length, default):
    if values is None:
        return None
    return _float_list(values, length, default)


def _optional_float(value):
    if value is None or value == "":
        return None
    return float(value)


def _json_result(result):
    return json.dumps(result, indent=2, sort_keys=True)


_PYTHON_FENCE_RE = re.compile(r"```(?:python|py)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_ANIMATION_WORKFLOW_MARKERS = {}
_ANIMATION_WORKFLOW_TTL_SECONDS = 15 * 60
_ANIMATION_INTENT_TERMS = {
    "animate",
    "animation",
    "bounce",
    "jump",
    "keyframe",
    "keyframes",
    "pose",
    "timing",
    "arc",
    "motion arc",
    "settle",
    "squash",
    "stretch",
    "playblast",
    "f-curve",
    "fcurve",
    "block key",
    "blocking",
    "anticipation",
    "contact sliding",
}
_ANIMATION_HELPER_GAP_TERMS = {
    "helper gap",
    "helpers cannot express",
    "helper tools cannot express",
    "workflow cannot express",
    "no helper can express",
    "no helper tool can express",
    "script_fallback_policy",
    "script fallback policy",
    "fallback allowed",
    "requires custom blender python",
    "requires custom python",
}
_RENDER_JOB_INTENT_TERMS = {
    "render animation",
    "full render",
    "quality render",
    "playblast",
    "1080p",
    "4k",
    "frames",
    "frame sequence",
    "samples",
    "bpy.ops.render.render",
    "animation=true",
    "write_still=false",
}


def _name_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if str(item).strip()]


def _bounded_int(value, default, *, minimum=1, maximum=100):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    return max(int(minimum), min(int(maximum), result))


def _bounded_float(value, default, *, minimum=0.0, maximum=1000.0):
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = float(default)
    return max(float(minimum), min(float(maximum), result))


def _extract_script_code(args):
    for key in ("code", "script", "source", "python", "body"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for key in ("expected_changes", "intent"):
        value = args.get(key)
        if not isinstance(value, str):
            continue
        match = _PYTHON_FENCE_RE.search(value)
        if match and match.group(1).strip():
            return match.group(1)
    return ""


def _animation_workflow_marker_key(context):
    scene = getattr(context, "scene", None)
    return getattr(scene, "name", "") or "active_scene"


def _mark_animation_workflow_seen(context, result=None):
    workflow = result.get("workflow") if isinstance(result, dict) and isinstance(result.get("workflow"), dict) else {}
    fallback_policy = workflow.get("script_fallback_policy") if isinstance(workflow.get("script_fallback_policy"), dict) else {}
    _ANIMATION_WORKFLOW_MARKERS[_animation_workflow_marker_key(context)] = {
        "marked_at": time.monotonic(),
        "status": str(workflow.get("status") or ""),
        "script_fallback_allowed": bool(fallback_policy.get("allowed", True)) and workflow.get("status") != "needs_clarification",
    }


def _animation_workflow_recent_context(context):
    marker = _ANIMATION_WORKFLOW_MARKERS.get(_animation_workflow_marker_key(context))
    if not marker:
        return {}
    if isinstance(marker, dict):
        marked_at = marker.get("marked_at")
    else:
        marked_at = marker
        marker = {"marked_at": marked_at, "script_fallback_allowed": True}
    if not marked_at:
        return {}
    if (time.monotonic() - float(marked_at)) > _ANIMATION_WORKFLOW_TTL_SECONDS:
        return {}
    return dict(marker)


def _animation_workflow_recently_seen(context):
    return bool(_animation_workflow_recent_context(context))


def _animation_script_fallback_recently_allowed(context):
    marker = _animation_workflow_recent_context(context)
    if not marker:
        return False
    return bool(marker.get("script_fallback_allowed", False))


def _looks_like_animation_intent(text):
    normalized = str(text or "").lower()
    for term in _ANIMATION_INTENT_TERMS:
        term_text = str(term or "").strip().lower()
        if not term_text:
            continue
        pattern = re.escape(term_text).replace(r"\ ", r"\s+")
        if re.search(rf"(?<![a-z0-9_]){pattern}(?![a-z0-9_])", normalized):
            return True
    return False


def _has_explicit_animation_helper_gap(text):
    normalized = str(text or "").lower()
    return any(term in normalized for term in _ANIMATION_HELPER_GAP_TERMS)


def _looks_like_render_job_intent(text):
    normalized = str(text or "").lower()
    if "render" not in normalized and "playblast" not in normalized and "bpy.ops.render.render" not in normalized:
        return False
    return any(term in normalized for term in _RENDER_JOB_INTENT_TERMS)


def _resolve_objects(context, args, *, default_to_scene=False):
    names = _name_list(args.get("object_names"))
    max_objects = _bounded_int(args.get("max_objects"), 12, maximum=50)
    missing = []
    if names:
        objects = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj:
                objects.append(obj)
            else:
                missing.append(name)
        return objects[:max_objects], missing
    if args.get("selected_only"):
        return list(context.selected_objects)[:max_objects], missing
    if context.active_object:
        return [context.active_object], missing
    if default_to_scene:
        return list(context.scene.objects)[:max_objects], missing
    return [], missing


def _idprops_summary(data_block):
    result = {}
    for key in list(data_block.keys())[:20]:
        value = data_block.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[str(key)] = value
        else:
            result[str(key)] = repr(value)[:160]
    return result


def _mesh_data_layers(mesh):
    if mesh is None:
        return {}
    return {
        "uv_layers": [layer.name for layer in list(mesh.uv_layers)[:12]],
        "color_attributes": [attribute.name for attribute in list(mesh.color_attributes)[:12]],
        "shape_keys": [block.name for block in list(mesh.shape_keys.key_blocks)[:12]] if mesh.shape_keys else [],
    }


def _socket_value(value):
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    try:
        return [round(float(item), 5) for item in value]
    except (TypeError, ValueError):
        return repr(value)[:160]


def _socket_summary(socket):
    result = {
        "name": socket.name,
        "type": socket.type,
        "is_linked": bool(socket.is_linked),
    }
    try:
        result["default_value"] = _socket_value(socket.default_value)
    except AttributeError:
        pass
    return result


def _keyframe_summary(point):
    co = getattr(point, "co", (0.0, 0.0))
    return {
        "frame": round(float(co[0]), 4),
        "value": round(float(co[1]), 5),
        "interpolation": getattr(point, "interpolation", None),
    }


def _driver_summary(data_block, *, max_drivers=12):
    animation_data = getattr(data_block, "animation_data", None)
    drivers = list(getattr(animation_data, "drivers", []) or []) if animation_data else []
    return [
        {
            "data_path": driver.data_path,
            "array_index": int(driver.array_index),
            "expression": getattr(driver.driver, "expression", ""),
            "type": getattr(driver.driver, "type", None),
            "variables": [
                {
                    "name": variable.name,
                    "type": variable.type,
                    "targets": [
                        {
                            "id": getattr(target.id, "name", None),
                            "data_path": target.data_path,
                            "transform_type": getattr(target, "transform_type", None),
                        }
                        for target in list(variable.targets)[:4]
                    ],
                }
                for variable in list(getattr(driver.driver, "variables", []))[:8]
            ],
        }
        for driver in drivers[:max_drivers]
    ]


def _animation_data_summary(data_block, *, max_drivers=8):
    animation_data = getattr(data_block, "animation_data", None)
    if animation_data is None:
        return {"has_animation_data": False, "action": None, "driver_count": 0, "nla_track_count": 0}
    action = animation_data.action
    drivers = list(getattr(animation_data, "drivers", []) or [])
    nla_tracks = list(getattr(animation_data, "nla_tracks", []) or [])
    result = {
        "has_animation_data": True,
        "action": action.name if action else None,
        "driver_count": len(drivers),
        "nla_track_count": len(nla_tracks),
        "drivers": _driver_summary(data_block, max_drivers=max_drivers),
    }
    if action:
        frame_range = list(getattr(action, "frame_range", (0, 0)))
        result["action_frame_range"] = [round(float(value), 4) for value in frame_range]
    if nla_tracks:
        result["nla_tracks"] = [
            {
                "name": track.name,
                "mute": bool(getattr(track, "mute", False)),
                "solo": bool(getattr(track, "is_solo", False)),
                "strip_count": len(getattr(track, "strips", []) or []),
            }
            for track in nla_tracks[:12]
        ]
    return result


def _constraint_summary(constraint):
    item = {
        "name": constraint.name,
        "type": constraint.type,
        "influence": round(float(getattr(constraint, "influence", 0.0)), 5),
        "mute": bool(getattr(constraint, "mute", False)),
        "target": getattr(getattr(constraint, "target", None), "name", None),
        "subtarget": getattr(constraint, "subtarget", ""),
    }
    for attr in (
        "track_axis",
        "up_axis",
        "owner_space",
        "target_space",
        "use_curve_follow",
        "use_fixed_location",
        "offset_factor",
        "forward_axis",
    ):
        if hasattr(constraint, attr):
            value = getattr(constraint, attr)
            item[attr] = round(float(value), 5) if isinstance(value, float) else value
    return item


def _action_from(data_block):
    animation_data = getattr(data_block, "animation_data", None)
    return animation_data.action if animation_data else None


def _append_action(actions, seen, action):
    if action and action.name not in seen:
        seen.add(action.name)
        actions.append(action)


def _object_related_actions(obj):
    actions = [_action_from(obj)]
    data = getattr(obj, "data", None)
    if data:
        actions.append(_action_from(data))
    if obj.type == "MESH" and data and getattr(data, "shape_keys", None):
        actions.append(_action_from(data.shape_keys))
    for slot in obj.material_slots:
        material = slot.material
        if material:
            actions.append(_action_from(material))
            node_tree = material.node_tree if material.use_nodes else None
            if node_tree:
                actions.append(_action_from(node_tree))
    return [action for action in actions if action]


def _action_owners(action):
    owners = []
    for obj in bpy.data.objects:
        if _action_from(obj) == action:
            owners.append({"kind": "object", "name": obj.name, "type": obj.type})
        data = getattr(obj, "data", None)
        if data and _action_from(data) == action:
            owners.append({"kind": "object_data", "object": obj.name, "name": data.name, "type": obj.type})
        if obj.type == "MESH" and data and getattr(data, "shape_keys", None) and _action_from(data.shape_keys) == action:
            owners.append({"kind": "shape_keys", "object": obj.name, "name": data.shape_keys.name})
    for material in bpy.data.materials:
        if _action_from(material) == action:
            owners.append({"kind": "material", "name": material.name})
        node_tree = material.node_tree if material.use_nodes else None
        if node_tree and _action_from(node_tree) == action:
            owners.append({"kind": "material_node_tree", "material": material.name, "name": node_tree.name})
    return owners[:40]


def _action_summary(action, *, max_keyframes_per_curve=8):
    fcurves = context_bundle._iter_action_fcurves(action)
    frame_range = list(getattr(action, "frame_range", (0, 0)))
    return {
        "name": action.name,
        "users": int(getattr(action, "users", 0)),
        "frame_range": [round(float(value), 4) for value in frame_range],
        "fcurve_count": len(fcurves),
        "owners": _action_owners(action),
        "fcurves": [
            {
                "data_path": fcurve.data_path,
                "array_index": int(fcurve.array_index),
                "extrapolation": getattr(fcurve, "extrapolation", None),
                "mute": bool(getattr(fcurve, "mute", False)),
                "keyframe_count": len(fcurve.keyframe_points),
                "frame_range": [
                    round(float(min((point.co[0] for point in fcurve.keyframe_points), default=0.0)), 4),
                    round(float(max((point.co[0] for point in fcurve.keyframe_points), default=0.0)), 4),
                ],
                "keyframes": [
                    _keyframe_summary(point)
                    for point in list(fcurve.keyframe_points)[:max_keyframes_per_curve]
                ],
            }
            for fcurve in fcurves[:40]
        ],
    }


def inspect_scene(context, args):
    bundle = context_bundle.build_context_bundle(
        context,
        include_visual=bool(args.get("include_visual", False)),
    )
    return context_bundle.public_bundle(bundle)


def list_scene_objects(context, args):
    type_filter = str(args.get("type_filter") or "").upper()
    max_objects = _bounded_int(args.get("max_objects"), 80, maximum=250)
    objects = []
    for obj in context.scene.objects:
        if type_filter and obj.type != type_filter:
            continue
        objects.append(
            {
                "name": obj.name,
                "type": obj.type,
                "selected": bool(obj.select_get()),
                "active": context.active_object == obj,
                "hidden_viewport": bool(obj.hide_viewport),
                "hidden_render": bool(obj.hide_render),
                "location": context_bundle._xyz(obj.location),
                "collection_names": [collection.name for collection in obj.users_collection],
            }
        )
        if len(objects) >= max_objects:
            break
    return {
        "ok": True,
        "objects": objects,
        "total_scene_objects": len(context.scene.objects),
        "truncated": len(objects) < len(context.scene.objects) and not type_filter,
    }


def get_object_details(context, args):
    objects, missing = _resolve_objects(context, args, default_to_scene=True)
    details = []
    for obj in objects:
        item = context_bundle._object_summary(obj)
        item.update(
            {
                "parent": obj.parent.name if obj.parent else None,
                "children": [child.name for child in list(obj.children)[:25]],
                "custom_properties": _idprops_summary(obj),
            }
        )
        if obj.type == "MESH" and obj.data:
            item["mesh_data_layers"] = _mesh_data_layers(obj.data)
            item["mesh_custom_properties"] = _idprops_summary(obj.data)
        details.append(item)
    return {
        "ok": True,
        "objects": details,
        "missing_object_names": missing,
        "note": "Raw mesh vertex/edge/polygon arrays are omitted; summaries and layer names are returned.",
    }


def get_animation_details(context, args):
    max_actions = _bounded_int(args.get("max_actions"), 8, maximum=25)
    max_keyframes = _bounded_int(args.get("max_keyframes_per_curve"), 8, maximum=32)
    action_names = _name_list(args.get("action_names"))
    objects, missing_objects = _resolve_objects(context, args)
    actions = []
    missing_actions = []
    seen = set()

    for obj in objects:
        for action in _object_related_actions(obj):
            _append_action(actions, seen, action)

    if action_names:
        for name in action_names:
            action = bpy.data.actions.get(name)
            if action:
                _append_action(actions, seen, action)
            else:
                missing_actions.append(name)
    elif not actions:
        actions.extend(list(bpy.data.actions)[:max_actions])

    return {
        "ok": True,
        "scene": {
            "frame_current": int(context.scene.frame_current),
            "frame_start": int(context.scene.frame_start),
            "frame_end": int(context.scene.frame_end),
            "fps": int(context.scene.render.fps),
        },
        "objects": [
            {
                "name": obj.name,
                "type": obj.type,
                "animation_data": context_bundle._object_summary(obj).get("animation"),
                "object_animation": _animation_data_summary(obj),
                "data_animation": _animation_data_summary(obj.data) if getattr(obj, "data", None) else None,
                "constraints": [_constraint_summary(constraint) for constraint in list(obj.constraints)[:24]],
                "drivers": _driver_summary(obj),
                "shape_key_animation": _animation_data_summary(obj.data.shape_keys)
                if obj.type == "MESH" and obj.data and obj.data.shape_keys
                else None,
                "materials": [
                    {
                        "slot_index": index,
                        "name": slot.material.name if slot.material else None,
                        "material_animation": _animation_data_summary(slot.material) if slot.material else None,
                        "node_tree_animation": _animation_data_summary(slot.material.node_tree)
                        if slot.material and slot.material.use_nodes and slot.material.node_tree
                        else None,
                    }
                    for index, slot in enumerate(obj.material_slots)
                ],
            }
            for obj in objects
        ],
        "actions": [
            _action_summary(action, max_keyframes_per_curve=max_keyframes)
            for action in actions[:max_actions]
        ],
        "total_action_count": len(bpy.data.actions),
        "missing_object_names": missing_objects,
        "missing_action_names": missing_actions,
    }


def get_animation_scene_context(context, args):
    return world_model.animation_scene_context(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        max_objects=_bounded_int(args.get("max_objects"), 20, maximum=80),
    )


def create_animation_brief(context, args):
    return animation_brief.create_animation_brief(
        context,
        prompt=str(args.get("prompt") or ""),
        subject_names=_name_list(args.get("subject_names")),
        action=str(args.get("action") or ""),
        style=str(args.get("style") or ""),
        camera=str(args.get("camera") or ""),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        constraints=_name_list(args.get("constraints")),
        success_criteria=_name_list(args.get("success_criteria")),
    )


def create_timing_chart(context, args):
    return animation_brief.create_timing_chart(
        context,
        prompt=str(args.get("prompt") or ""),
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
        subject_names=_name_list(args.get("subject_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        beats=args.get("beats") if isinstance(args.get("beats"), list) else None,
    )


def plan_animation_workflow(context, args):
    result = animation_workflow.plan_animation_workflow(
        context,
        prompt=str(args.get("prompt") or ""),
        subject_names=_name_list(args.get("subject_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        mode=str(args.get("mode") or "full"),
        selected_only=bool(args.get("selected_only", False)),
        max_objects=_bounded_int(args.get("max_objects"), 20, minimum=1, maximum=80),
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
        timing_chart=args.get("timing_chart") if isinstance(args.get("timing_chart"), dict) else None,
        playblast=args.get("playblast") if isinstance(args.get("playblast"), dict) else None,
        findings=args.get("findings") if isinstance(args.get("findings"), list) else None,
    )
    if isinstance(result, dict) and result.get("ok"):
        _mark_animation_workflow_seen(context, result)
    return result


_WORKFLOW_GENERATION_TOOLS = {
    "select_objects",
    "set_scene_frame_range",
    "set_animation_preview_range",
    "animate_object_bounce",
    "create_progressive_bounce_animation",
    "create_turntable_animation",
    "create_reveal_animation",
    "create_pulse_animation",
}


def _workflow_tool_parts(tool_call):
    tool_call = tool_call if isinstance(tool_call, dict) else {}
    tool = str(tool_call.get("name") or "")
    tool_args = tool_call.get("input") if isinstance(tool_call.get("input"), dict) else {}
    return tool, dict(tool_args or {})


def _execute_workflow_tool(context, tool, tool_args):
    fn = TOOL_FUNCTIONS.get(tool)
    if fn is None:
        return {"ok": False, "message": f"Unknown Blender tool: {tool}"}
    try:
        result = fn(context, tool_args)
    except Exception as exc:
        return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {"ok": False, "message": result}
    if not isinstance(result, dict):
        result = {"ok": False, "message": "Tool returned an unexpected result"}
    return _attach_preview_change_report(result)


def _workflow_findings(*results):
    findings = []
    seen = set()
    for result in results:
        if isinstance(result, dict):
            for item in result.get("findings") or []:
                if not isinstance(item, dict):
                    continue
                key = (
                    str(item.get("severity") or ""),
                    str(item.get("principle") or ""),
                    str(item.get("requirement") or ""),
                    str(item.get("object") or ""),
                    str(item.get("frame") or ""),
                    str(item.get("message") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                findings.append(item)
    return findings


def _workflow_review(context, *, prompt, brief, timing_chart, frame_start, frame_end, capture_playblast, playblast=None):
    subject_names = _name_list((brief or {}).get("subject_names"))
    if not subject_names and isinstance(brief, dict):
        subject_names = [
            str(item.get("name"))
            for item in (brief.get("subjects") or [])
            if isinstance(item, dict) and item.get("name")
        ]
    principles = animation_analysis.analyze_animation_principles(
        context,
        object_names=subject_names,
        prompt=prompt,
        brief=brief,
        timing_chart=timing_chart,
        frame_start=frame_start,
        frame_end=frame_end,
    )
    comparison = animation_analysis.compare_animation_to_brief(
        context,
        brief=brief,
        prompt=prompt,
        subject_names=subject_names,
        frame_start=frame_start,
        frame_end=frame_end,
    )
    playblast_result = {}
    review_playblast = playblast if isinstance(playblast, dict) else None
    if capture_playblast:
        playblast_result = capture_animation_playblast(
            context,
            {
                "frame_start": frame_start,
                "frame_end": frame_end,
                "max_frames": 12,
                "brief": (brief or {}).get("user_visible_interpretation") or prompt,
            },
        )
        if isinstance(playblast_result.get("playblast"), dict):
            review_playblast = playblast_result["playblast"]
    if review_playblast is None:
        review_playblast = {
            "available": False,
            "playblast_id": "workflow-no-playblast",
            "frames": [],
            "sampled_frames": [],
        }
    visual_review = animation_analysis.review_playblast_against_brief(
        context,
        playblast=review_playblast,
        brief=brief,
        prompt=prompt,
    )
    findings = _workflow_findings(principles, comparison, visual_review)
    repair_plan = animation_analysis.repair_animation_from_findings(context, findings=findings, brief=brief)
    return {
        "principles": principles,
        "comparison": comparison,
        "playblast_capture": playblast_result,
        "visual_review": visual_review,
        "findings": findings,
        "finding_count": len(findings),
        "repair_plan": repair_plan,
    }


def run_animation_workflow(context, args):
    prompt = str(args.get("prompt") or "")
    mode = str(args.get("mode") or "full").strip().lower()
    max_generation_steps = _bounded_int(args.get("max_generation_steps"), 8, minimum=1, maximum=20)
    apply_generation = bool(args.get("apply_generation", True))
    run_review = bool(args.get("run_review", True))
    capture_playblast = bool(args.get("capture_playblast", False))
    apply_repairs = bool(args.get("apply_repairs", False))

    plan_result = plan_animation_workflow(
        context,
        {
            "prompt": prompt,
            "subject_names": _name_list(args.get("subject_names")),
            "frame_start": args.get("frame_start"),
            "frame_end": args.get("frame_end"),
            "mode": mode,
            "selected_only": bool(args.get("selected_only", False)),
            "max_objects": _bounded_int(args.get("max_objects"), 20, minimum=1, maximum=80),
            "brief": args.get("brief") if isinstance(args.get("brief"), dict) else None,
            "timing_chart": args.get("timing_chart") if isinstance(args.get("timing_chart"), dict) else None,
            "playblast": args.get("playblast") if isinstance(args.get("playblast"), dict) else None,
            "findings": args.get("findings") if isinstance(args.get("findings"), list) else None,
        },
    )
    if not plan_result.get("ok"):
        return plan_result
    workflow = plan_result.get("workflow") if isinstance(plan_result.get("workflow"), dict) else {}
    if workflow.get("status") == "needs_clarification":
        return {
            "ok": True,
            "message": "Animation workflow needs clarification before mutating the scene",
            "status": "needs_clarification",
            "workflow": workflow,
            "executed": [],
            "skipped": [],
            "review": {},
            "repair_loop": {},
            "pending_preview": bool(getattr(context.scene.claude_blender, "pending_preview", False)) if hasattr(context.scene, "claude_blender") else False,
            "result_type": "live_preview_helper_workflow",
        }

    executed = []
    skipped = []
    generation_count = 0
    if apply_generation and mode in {"generate", "full", "repair", "review"}:
        for index, tool_call in enumerate(workflow.get("next_tool_calls") or []):
            tool, tool_args = _workflow_tool_parts(tool_call)
            if tool not in _WORKFLOW_GENERATION_TOOLS:
                if tool:
                    skipped.append({"index": index, "tool": tool, "reason": "tool is handled by review/repair or outside workflow generation allowlist"})
                continue
            if generation_count >= max_generation_steps:
                skipped.append({"index": index, "tool": tool, "reason": "max_generation_steps reached"})
                continue
            result = _execute_workflow_tool(context, tool, tool_args)
            executed.append(
                {
                    "index": index,
                    "tool": tool,
                    "arguments": tool_args,
                    "ok": bool(result.get("ok")),
                    "message": str(result.get("message") or ""),
                    "result": result,
                }
            )
            generation_count += 1
    elif not apply_generation:
        for index, tool_call in enumerate(workflow.get("next_tool_calls") or []):
            tool, _tool_args = _workflow_tool_parts(tool_call)
            if tool in _WORKFLOW_GENERATION_TOOLS:
                skipped.append({"index": index, "tool": tool, "reason": "apply_generation is false"})

    brief = workflow.get("brief") if isinstance(workflow.get("brief"), dict) else {}
    timing_chart = workflow.get("timing_chart") if isinstance(workflow.get("timing_chart"), dict) else {}
    frame_start, frame_end = animation_workflow._frame_range(context, brief)
    review = {}
    repair_loop = {}
    if run_review:
        review = _workflow_review(
            context,
            prompt=prompt,
            brief=brief,
            timing_chart=timing_chart,
            frame_start=frame_start,
            frame_end=frame_end,
            capture_playblast=capture_playblast,
            playblast=args.get("playblast") if isinstance(args.get("playblast"), dict) else None,
        )
        repair_operations = (review.get("repair_plan") or {}).get("repair_operations") or []
        if apply_repairs and repair_operations:
            repair_loop = run_animation_repair_loop(
                context,
                {
                    "brief": brief,
                    "prompt": prompt,
                    "findings": review.get("findings") or [],
                    "repair_operations": repair_operations,
                    "max_iterations": _bounded_int(args.get("max_repair_iterations"), 1, minimum=1, maximum=4),
                    "max_operations": _bounded_int(args.get("max_repair_operations"), 3, minimum=1, maximum=12),
                    "apply_mutating_repairs": True,
                    "recapture_after_mutation": bool(args.get("recapture_after_repair", False)),
                },
            )
    failed = [item for item in executed if not item.get("ok")]
    if failed:
        status = "generation_failed"
    elif repair_loop:
        status = repair_loop.get("status") or "repairs_applied_needs_review"
    elif run_review and (review.get("finding_count") or 0) > 0:
        status = "generated_needs_repair"
    elif executed:
        status = "generated_reviewed"
    else:
        status = "planned"
    return {
        "ok": True,
        "message": f"Animation workflow finished with status: {status}",
        "status": status,
        "workflow": workflow,
        "executed": executed,
        "skipped": skipped,
        "review": review,
        "repair_loop": repair_loop,
        "generation_blockers": workflow.get("generation_blockers") or [],
        "pending_preview": bool(getattr(context.scene.claude_blender, "pending_preview", False)) if hasattr(context.scene, "claude_blender") else False,
        "result_type": "live_preview_helper_workflow",
    }


def run_animation_task(context, args):
    prompt = str(args.get("prompt") or "")
    result = run_animation_workflow(
        context,
        {
            "prompt": prompt,
            "mode": "full",
            "apply_generation": True,
            "run_review": True,
            "capture_playblast": False,
            "apply_repairs": False,
        },
    )
    if isinstance(result, dict):
        enriched = dict(result)
        enriched.setdefault("message", "Animation task routed through run_animation_workflow")
        enriched["invoked_workflow_tool"] = "run_animation_workflow"
        enriched["task_prompt"] = prompt
        return enriched
    return result


def analyze_motion_arcs(context, args):
    return animation_analysis.analyze_motion_arcs(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        max_samples=_bounded_int(args.get("max_samples"), 16, minimum=2, maximum=120),
    )


def analyze_fcurve_spacing(context, args):
    return animation_analysis.analyze_fcurve_spacing(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        paths=_name_list(args.get("paths")),
    )


def analyze_pose_clarity(context, args):
    return animation_analysis.analyze_pose_clarity(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
    )


def analyze_animation_principles(context, args):
    return animation_analysis.analyze_animation_principles(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        prompt=str(args.get("prompt") or ""),
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
        timing_chart=args.get("timing_chart") if isinstance(args.get("timing_chart"), dict) else None,
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
    )


def sample_animation_state(context, args):
    return animation_analysis.sample_animation_state(
        context,
        object_names=_name_list(args.get("object_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 4, minimum=1, maximum=10000),
        selected_only=bool(args.get("selected_only", False)),
    )


def analyze_contact_sliding(context, args):
    return animation_analysis.analyze_contact_sliding(
        context,
        object_names=_name_list(args.get("object_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 2, minimum=1, maximum=10000),
        contact_z=float(args.get("contact_z", 0.0)),
        contact_tolerance=float(args.get("contact_tolerance", 0.05)),
        sliding_tolerance=float(args.get("sliding_tolerance", 0.08)),
        selected_only=bool(args.get("selected_only", False)),
    )


def analyze_collision_penetration(context, args):
    return animation_analysis.analyze_collision_penetration(
        context,
        object_names=_name_list(args.get("object_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 4, minimum=1, maximum=10000),
        tolerance=float(args.get("tolerance", 0.0)),
        selected_only=bool(args.get("selected_only", False)),
    )


def analyze_center_of_mass(context, args):
    return animation_analysis.analyze_center_of_mass(
        context,
        object_names=_name_list(args.get("object_names")),
        support_object_names=_name_list(args.get("support_object_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 4, minimum=1, maximum=10000),
        support_margin=_bounded_float(args.get("support_margin"), 0.05, minimum=0.0, maximum=1000.0),
        contact_tolerance=_bounded_float(args.get("contact_tolerance"), 0.12, minimum=0.0, maximum=1000.0),
        selected_only=bool(args.get("selected_only", False)),
    )


def analyze_camera_framing(context, args):
    return animation_analysis.analyze_camera_framing(
        context,
        object_names=_name_list(args.get("object_names")),
        camera_name=str(args.get("camera_name") or ""),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 8, minimum=1, maximum=10000),
        margin=float(args.get("margin", 0.05)),
        selected_only=bool(args.get("selected_only", False)),
    )


def analyze_motion_physics(context, args):
    return animation_analysis.analyze_motion_physics(
        context,
        object_names=_name_list(args.get("object_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 2, minimum=1, maximum=10000),
        max_speed=_optional_float(args.get("max_speed")),
        max_acceleration=_optional_float(args.get("max_acceleration")),
        selected_only=bool(args.get("selected_only", False)),
    )


def compare_animation_to_brief(context, args):
    return animation_analysis.compare_animation_to_brief(
        context,
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
        prompt=str(args.get("prompt") or ""),
        subject_names=_name_list(args.get("subject_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
    )


def review_playblast_against_brief(context, args):
    return animation_analysis.review_playblast_against_brief(
        context,
        playblast=args.get("playblast") if isinstance(args.get("playblast"), dict) else None,
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
        prompt=str(args.get("prompt") or ""),
    )


def review_inspection_renders_against_brief(context, args):
    return animation_analysis.review_inspection_renders_against_brief(
        context,
        inspection_render_metadata=args.get("inspection_render") if isinstance(args.get("inspection_render"), dict) else None,
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
        prompt=str(args.get("prompt") or ""),
    )


def repair_animation_from_findings(context, args):
    return animation_analysis.repair_animation_from_findings(
        context,
        findings=args.get("findings") if isinstance(args.get("findings"), list) else [],
        brief=args.get("brief") if isinstance(args.get("brief"), dict) else None,
    )


_REPAIR_LOOP_READ_ONLY_TOOLS = {
    "capture_animation_playblast",
    "capture_object_inspection_renders",
    "create_timing_chart",
    "get_rigging_details",
    "review_playblast_against_brief",
    "review_inspection_renders_against_brief",
    "repair_animation_from_findings",
}

_REPAIR_LOOP_DEFAULT_TOOLS = {
    "capture_animation_playblast",
    "capture_object_inspection_renders",
    "create_timing_chart",
    "set_action_interpolation",
    "set_pose_hold",
    "set_rig_pose_hold",
    "add_breakdown_pose",
    "block_key_poses",
    "create_camera_orbit",
    "animate_object_bounce",
    "create_progressive_bounce_animation",
    "set_scene_frame_range",
    "retime_actions",
    "get_rigging_details",
}


def _brief_frame_range(context, brief):
    timing = (brief or {}).get("timing") if isinstance(brief, dict) else {}
    if not isinstance(timing, dict):
        timing = {}
    return (
        int(timing.get("frame_start", context.scene.frame_start)),
        int(timing.get("frame_end", context.scene.frame_end)),
    )


def _repair_loop_brief_text(brief, prompt):
    text = str((brief or {}).get("user_visible_interpretation") or prompt or "").strip()
    return text[:1000]


def _repair_operation_parts(operation):
    operation = operation if isinstance(operation, dict) else {}
    tool_call = operation.get("tool_call") if isinstance(operation.get("tool_call"), dict) else {}
    tool = str(tool_call.get("name") or operation.get("tool") or "")
    tool_args = tool_call.get("input") if isinstance(tool_call.get("input"), dict) else None
    if tool_args is None:
        tool_args = operation.get("arguments") if isinstance(operation.get("arguments"), dict) else {}
    return tool, dict(tool_args or {})


def _repair_operation_key(tool, tool_args):
    return (tool, json.dumps(tool_args, sort_keys=True, default=str))


def _repair_operation_mutates(tool, operation):
    return tool not in _REPAIR_LOOP_READ_ONLY_TOOLS


def _repair_operation_blocker(tool, tool_args):
    if not tool:
        return "repair operation has no tool name"
    if tool == "review_playblast_against_brief":
        return "review operations are handled by the loop itself"
    if tool == "repair_animation_from_findings":
        return "repair planning operations are handled by the loop itself"
    if tool == "block_key_poses" and not tool_args.get("poses"):
        return "block_key_poses requires explicit poses; this repair needs a planning pass first"
    if tool in {"set_pose_hold", "set_action_interpolation", "add_breakdown_pose"} and not tool_args.get("object_names"):
        return f"{tool} requires object_names"
    if tool == "set_rig_pose_hold" and not tool_args.get("armature_name"):
        return "set_rig_pose_hold requires armature_name"
    if tool == "capture_object_inspection_renders" and not tool_args.get("object_names"):
        return "capture_object_inspection_renders requires object_names"
    if tool in {"animate_object_bounce", "create_progressive_bounce_animation"} and not tool_args.get("object_name"):
        return f"{tool} requires object_name"
    if tool == "retime_actions" and not (tool_args.get("object_names") or tool_args.get("action_names")):
        return "retime_actions requires object_names or action_names"
    if tool == "create_camera_orbit" and not tool_args.get("target_name"):
        return "create_camera_orbit requires target_name"
    return ""


def _execute_repair_tool(context, tool, tool_args):
    fn = TOOL_FUNCTIONS.get(tool)
    if fn is None:
        return {"ok": False, "message": f"Unknown Blender tool: {tool}"}
    try:
        result = fn(context, tool_args)
    except Exception as exc:
        return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {"ok": False, "message": result}
    if not isinstance(result, dict):
        result = {"ok": False, "message": "Tool returned an unexpected result"}
    return _attach_preview_change_report(result)


def _repair_loop_review(context, *, playblast=None, brief=None, prompt=""):
    return animation_analysis.review_playblast_against_brief(
        context,
        playblast=playblast if isinstance(playblast, dict) else None,
        brief=brief if isinstance(brief, dict) else None,
        prompt=str(prompt or ""),
    )


def run_animation_repair_loop(context, args):
    brief = args.get("brief") if isinstance(args.get("brief"), dict) else None
    prompt = str(args.get("prompt") or "")
    latest_playblast = args.get("playblast") if isinstance(args.get("playblast"), dict) else None
    seed_findings = args.get("findings") if isinstance(args.get("findings"), list) else []
    seed_operations = args.get("repair_operations") if isinstance(args.get("repair_operations"), list) else []
    max_iterations = _bounded_int(args.get("max_iterations"), 2, minimum=1, maximum=4)
    max_operations = _bounded_int(args.get("max_operations"), 4, minimum=1, maximum=12)
    apply_mutating = bool(args.get("apply_mutating_repairs", True))
    recapture_after_mutation = bool(args.get("recapture_after_mutation", True))
    requested_allowed_tools = set(_name_list(args.get("allowed_tools")))
    allowed_tools = set(_REPAIR_LOOP_DEFAULT_TOOLS)
    if requested_allowed_tools:
        allowed_tools.intersection_update(requested_allowed_tools)
    frame_start, frame_end = _brief_frame_range(context, brief or {})

    reviews = []
    executed = []
    skipped = []
    executed_keys = set()
    final_review = {}
    pending_seed_operations = list(seed_operations)

    for iteration in range(1, max_iterations + 1):
        if pending_seed_operations:
            review = {
                "ok": True,
                "status": "needs_repair",
                "message": "Using caller-provided repair operations",
                "findings": seed_findings,
                "repair_operations": pending_seed_operations,
            }
        else:
            review = _repair_loop_review(context, playblast=latest_playblast, brief=brief, prompt=prompt)
        final_review = review
        operations = list(review.get("repair_operations") or [])
        reviews.append(
            {
                "iteration": iteration,
                "status": review.get("status", ""),
                "finding_count": len(review.get("findings") or []),
                "repair_operation_count": len(operations),
            }
        )
        pending_seed_operations = []
        if review.get("status") == "pass":
            break

        executed_this_iteration = []
        mutating_this_iteration = False
        captured_this_iteration = False
        for operation_index, operation in enumerate(operations):
            if len(executed) >= max_operations:
                break
            tool, tool_args = _repair_operation_parts(operation)
            key = _repair_operation_key(tool, tool_args)
            mutates = _repair_operation_mutates(tool, operation)
            blocker = _repair_operation_blocker(tool, tool_args)
            reason = ""
            if key in executed_keys:
                reason = "operation already executed in this repair loop"
            elif tool not in allowed_tools:
                reason = "tool is not in allowed_tools for this repair loop"
            elif mutates and not apply_mutating:
                reason = "mutating repairs are disabled for this repair loop"
            elif blocker:
                reason = blocker
            if reason:
                skipped.append({"iteration": iteration, "operation_index": operation_index, "tool": tool, "reason": reason, "operation": operation})
                continue

            result = _execute_repair_tool(context, tool, tool_args)
            executed_keys.add(key)
            item = {
                "iteration": iteration,
                "operation_index": operation_index,
                "tool": tool,
                "arguments": tool_args,
                "ok": bool(result.get("ok")),
                "message": str(result.get("message") or ""),
                "mutates_scene": mutates,
                "source_finding_index": operation.get("source_finding_index") if isinstance(operation, dict) else None,
                "result": result,
            }
            executed.append(item)
            executed_this_iteration.append(item)
            mutating_this_iteration = mutating_this_iteration or mutates
            captured_this_iteration = captured_this_iteration or tool == "capture_animation_playblast"
            if isinstance(result.get("playblast"), dict):
                latest_playblast = result["playblast"]

        if (
            mutating_this_iteration
            and recapture_after_mutation
            and not captured_this_iteration
            and len(executed) < max_operations
            and "capture_animation_playblast" in allowed_tools
        ):
            capture_args = {
                "frame_start": frame_start,
                "frame_end": frame_end,
                "max_frames": 12,
                "brief": _repair_loop_brief_text(brief or {}, prompt),
            }
            result = _execute_repair_tool(context, "capture_animation_playblast", capture_args)
            item = {
                "iteration": iteration,
                "operation_index": -1,
                "tool": "capture_animation_playblast",
                "arguments": capture_args,
                "ok": bool(result.get("ok")),
                "message": str(result.get("message") or ""),
                "mutates_scene": False,
                "source_finding_index": None,
                "result": result,
            }
            executed.append(item)
            executed_this_iteration.append(item)
            captured_this_iteration = True
            if isinstance(result.get("playblast"), dict):
                latest_playblast = result["playblast"]

        if not executed_this_iteration:
            break
        final_review = _repair_loop_review(context, playblast=latest_playblast, brief=brief, prompt=prompt)
        reviews.append(
            {
                "iteration": f"{iteration}.review",
                "status": final_review.get("status", ""),
                "finding_count": len(final_review.get("findings") or []),
                "repair_operation_count": len(final_review.get("repair_operations") or []),
            }
        )
        if final_review.get("status") == "pass":
            break

    if final_review.get("status") == "pass":
        status = "pass"
    elif executed:
        status = "repairs_applied_needs_review"
    elif skipped:
        status = "needs_user_planning"
    else:
        status = "needs_repair"
    return {
        "ok": True,
        "message": f"Animation repair loop finished with status: {status}",
        "status": status,
        "executed_count": len(executed),
        "skipped_count": len(skipped),
        "reviews": reviews,
        "executed_operations": executed,
        "skipped_operations": skipped,
        "final_review": final_review,
        "latest_playblast": latest_playblast or {},
        "mutates_scene": any(item.get("mutates_scene") for item in executed),
        "pending_preview": bool(getattr(context.scene.claude_blender, "pending_preview", False)) if hasattr(context.scene, "claude_blender") else False,
    }


def get_material_node_details(context, args):
    names = _name_list(args.get("material_names"))
    max_materials = _bounded_int(args.get("max_materials"), 8, maximum=25)
    max_nodes = _bounded_int(args.get("max_nodes"), 18, maximum=60)
    materials = []
    missing = []
    seen = set()

    if names:
        for name in names:
            material = bpy.data.materials.get(name)
            if material:
                materials.append(material)
                seen.add(material.name)
            else:
                missing.append(name)
    else:
        source_objects = list(context.selected_objects) if args.get("selected_only", True) else list(context.scene.objects)
        for obj in source_objects:
            for slot in obj.material_slots:
                material = slot.material
                if material and material.name not in seen:
                    materials.append(material)
                    seen.add(material.name)
                if len(materials) >= max_materials:
                    break
            if len(materials) >= max_materials:
                break

    details = []
    for material in materials[:max_materials]:
        item = context_bundle._material_summary(material)
        item["custom_properties"] = _idprops_summary(material)
        if material.use_nodes and material.node_tree:
            nodes = list(material.node_tree.nodes)
            links = list(material.node_tree.links)
            item["nodes"] = [
                {
                    "name": node.name,
                    "label": node.label,
                    "type": node.type,
                    "inputs": [_socket_summary(socket) for socket in list(node.inputs)[:12]],
                    "outputs": [_socket_summary(socket) for socket in list(node.outputs)[:12]],
                }
                for node in nodes[:max_nodes]
            ]
            item["links"] = [
                {
                    "from_node": link.from_node.name,
                    "from_socket": link.from_socket.name,
                    "to_node": link.to_node.name,
                    "to_socket": link.to_socket.name,
                }
                for link in links[:40]
            ]
            if len(nodes) > max_nodes:
                item["truncated_nodes"] = len(nodes) - max_nodes
            if len(links) > 40:
                item["truncated_links"] = len(links) - 40
        details.append(item)

    return {
        "ok": True,
        "materials": details,
        "missing_material_names": missing,
    }


def get_geometry_nodes_details(context, args):
    return world_model.geometry_nodes_details(
        context,
        object_names=_name_list(args.get("object_names")),
        max_objects=_bounded_int(args.get("max_objects"), 12, maximum=50),
    )


def get_shader_nodes_details(context, args):
    return world_model.shader_nodes_details(
        context,
        material_names=_name_list(args.get("material_names")),
        selected_only=bool(args.get("selected_only", True)),
        max_materials=_bounded_int(args.get("max_materials"), 12, maximum=50),
    )


def get_rigging_details(context, args):
    return world_model.rigging_details(
        context,
        object_names=_name_list(args.get("object_names")),
        max_objects=_bounded_int(args.get("max_objects"), 12, maximum=50),
    )


def get_shape_key_details(context, args):
    return world_model.shape_key_details(
        context,
        object_names=_name_list(args.get("object_names")),
        max_objects=_bounded_int(args.get("max_objects"), 12, maximum=50),
    )


def get_curve_text_details(context, args):
    return world_model.curve_text_details(
        context,
        object_names=_name_list(args.get("object_names")),
        max_objects=_bounded_int(args.get("max_objects"), 20, maximum=80),
    )


def get_simulation_details(context, args):
    return world_model.simulation_details(
        context,
        object_names=_name_list(args.get("object_names")),
        max_objects=_bounded_int(args.get("max_objects"), 20, maximum=80),
    )


def get_collection_layer_details(context, args):
    return world_model.collection_layer_details(
        context,
        max_depth=_bounded_int(args.get("max_depth"), 4, maximum=8),
    )


def get_render_camera_compositor_details(context, args):
    return world_model.render_camera_compositor_details(context)


def select_objects(context, args):
    names = _name_list(args.get("object_names"))
    extend = bool(args.get("extend", False))
    active_name = str(args.get("active_object_name") or "").strip()
    if not names and active_name:
        names = [active_name]
    if not names:
        return {"ok": False, "message": "No object names were provided"}
    if not extend:
        bpy.ops.object.select_all(action="DESELECT")
    selected = []
    missing = []
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            missing.append(name)
            continue
        obj.select_set(True)
        selected.append(obj.name)
    active = bpy.data.objects.get(active_name) if active_name else None
    if active is None and selected:
        active = bpy.data.objects.get(selected[0])
    if active:
        active.select_set(True)
        context.view_layer.objects.active = active
    live_preview.redraw(context)
    state = getattr(context.scene, "claude_blender", None)
    if state:
        state.status = f"Selected {len(selected)} object(s)"
    return {
        "ok": bool(selected),
        "message": f"Selected {len(selected)} object(s)",
        "selected_objects": selected,
        "active_object": active.name if active else None,
        "missing_object_names": missing,
    }


def set_current_frame(context, args):
    frame = int(args.get("frame", context.scene.frame_current))
    context.scene.frame_set(frame)
    live_preview.redraw(context)
    state = getattr(context.scene, "claude_blender", None)
    if state:
        state.status = f"Current frame: {context.scene.frame_current}"
    return {
        "ok": True,
        "message": f"Set current frame to {context.scene.frame_current}",
        "frame_current": int(context.scene.frame_current),
    }


def set_selected_location_delta(context, args):
    delta = _float_list(args.get("delta"), 3, (0.0, 0.0, 0.0))
    return live_preview.apply_location_delta(
        context,
        delta,
        label=args.get("label", "Move selected objects"),
    )


def set_selected_transform(context, args):
    return live_preview.set_selected_transform(
        context,
        location=_optional_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        rotation=_optional_float_list(args.get("rotation"), 3, (0.0, 0.0, 0.0)),
        scale=_optional_float_list(args.get("scale"), 3, (1.0, 1.0, 1.0)),
        label=args.get("label", "Set selected transform"),
    )


def create_primitive(context, args):
    return live_preview.create_primitive(
        context,
        primitive_type=str(args.get("primitive_type") or "CUBE"),
        name=str(args.get("name") or "Claude Object"),
        location=_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        rotation=_float_list(args.get("rotation"), 3, (0.0, 0.0, 0.0)),
        scale=_float_list(args.get("scale"), 3, (1.0, 1.0, 1.0)),
        label=args.get("label", "Create primitive"),
    )


def assign_material_to_selected(context, args):
    name = str(args.get("name") or "Claude Material")
    color = _float_list(args.get("color"), 4, (0.8, 0.1, 0.1, 1.0))
    return live_preview.assign_material_to_selected(
        context,
        name=name,
        color=color,
        label=args.get("label", "Assign material"),
    )


def assign_emission_material_to_selected(context, args):
    name = str(args.get("name") or "Claude Emission")
    color = _float_list(args.get("color"), 4, (0.2, 0.6, 1.0, 1.0))
    return live_preview.assign_emission_material_to_selected(
        context,
        name=name,
        color=color,
        strength=float(args.get("strength", 1.5)),
        label=args.get("label", "Assign emission material"),
    )


def create_collection(context, args):
    return live_preview.create_collection(
        context,
        name=str(args.get("name") or "Claude Collection"),
        label=args.get("label", "Create collection"),
    )


def link_selected_to_collection(context, args):
    return live_preview.link_selected_to_collection(
        context,
        collection_name=str(args.get("collection_name") or "Claude Collection"),
        label=args.get("label", "Link selected to collection"),
    )


def add_modifier_to_selected(context, args):
    return live_preview.add_modifier_to_selected(
        context,
        modifier_type=str(args.get("modifier_type") or "BEVEL"),
        name=str(args.get("name") or ""),
        amount=float(args.get("amount", 0.1)),
        segments=int(args.get("segments", 2)),
        levels=int(args.get("levels", 1)),
        count=int(args.get("count", 3)),
        relative_offset=_float_list(args.get("relative_offset"), 3, (1.2, 0.0, 0.0)),
        label=args.get("label", "Add modifier"),
    )


def create_shader_material(context, args):
    return advanced_helpers.create_shader_material(
        context,
        name=str(args.get("name") or "Claude Shader Material"),
        base_color=_float_list(args.get("base_color"), 4, (0.8, 0.8, 0.8, 1.0)),
        metallic=float(args.get("metallic", 0.0)),
        roughness=float(args.get("roughness", 0.5)),
        alpha=float(args.get("alpha", 1.0)),
        emission_color=_optional_float_list(args.get("emission_color"), 4, (0.0, 0.0, 0.0, 1.0)),
        emission_strength=float(args.get("emission_strength", 0.0)),
        assign_to_selected=bool(args.get("assign_to_selected", True)),
        label=args.get("label", "Create shader material"),
    )


def add_geometry_nodes_modifier(context, args):
    return advanced_helpers.add_geometry_nodes_modifier(
        context,
        name=str(args.get("name") or "Claude Geometry Nodes"),
        node_group_name=str(args.get("node_group_name") or "Claude Geometry Nodes"),
        selected_only=bool(args.get("selected_only", True)),
        label=args.get("label", "Add Geometry Nodes modifier"),
    )


def create_shape_key(context, args):
    return advanced_helpers.create_shape_key(
        context,
        object_name=str(args.get("object_name") or ""),
        key_name=str(args.get("key_name") or "Claude Shape"),
        value=float(args.get("value", 0.0)),
        label=args.get("label", "Create shape key"),
    )


def animate_shape_key(context, args):
    return advanced_helpers.animate_shape_key(
        context,
        object_name=str(args.get("object_name") or ""),
        key_name=str(args.get("key_name") or "Claude Shape"),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        value_start=float(args.get("value_start", 0.0)),
        value_end=float(args.get("value_end", 1.0)),
        create_if_missing=bool(args.get("create_if_missing", True)),
        label=args.get("label", "Animate shape key"),
    )


def animate_object_bounce(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.animate_object_bounce(
        context,
        object_name=str(args.get("object_name") or active),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        axis=str(args.get("axis") or "Z"),
        distance=float(args.get("distance", 2.0)),
        cycles=_bounded_int(args.get("cycles"), 1, minimum=1, maximum=24),
        interpolation=str(args.get("interpolation") or "BEZIER"),
        label=args.get("label", "Animate object bounce"),
    )


def create_progressive_bounce_animation(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.create_progressive_bounce_animation(
        context,
        object_name=str(args.get("object_name") or active),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        axis=str(args.get("axis") or "Z"),
        distance=float(args.get("distance", 2.0)),
        cycles=_bounded_int(args.get("cycles"), 2, minimum=1, maximum=24),
        scale_end_factor=float(args.get("scale_end_factor", 0.6)),
        interpolation=str(args.get("interpolation") or "BEZIER"),
        label=args.get("label", "Create progressive bounce animation"),
    )


def animate_material_property(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.animate_material_property(
        context,
        material_name=str(args.get("material_name") or ""),
        object_name=str(args.get("object_name") or active),
        property_name=str(args.get("property_name") or "base_color"),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        value_start=args.get("value_start"),
        value_end=args.get("value_end"),
        create_if_missing=bool(args.get("create_if_missing", True)),
        interpolation=str(args.get("interpolation") or "LINEAR"),
        label=args.get("label", "Animate material property"),
    )


def animate_light_property(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.animate_light_property(
        context,
        light_name=str(args.get("light_name") or active),
        property_name=str(args.get("property_name") or "energy"),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        value_start=args.get("value_start"),
        value_end=args.get("value_end"),
        interpolation=str(args.get("interpolation") or "LINEAR"),
        label=args.get("label", "Animate light property"),
    )


def create_follow_path_animation(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.create_follow_path_animation(
        context,
        object_name=str(args.get("object_name") or active),
        path_name=str(args.get("path_name") or ""),
        path_points=args.get("path_points") or [],
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        constraint_name=str(args.get("constraint_name") or "Claude Follow Path"),
        follow_curve=bool(args.get("follow_curve", True)),
        interpolation=str(args.get("interpolation") or "LINEAR"),
        label=args.get("label", "Create follow path animation"),
    )


def set_action_interpolation(context, args):
    return advanced_helpers.set_action_interpolation(
        context,
        action_names=_name_list(args.get("action_names")),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        interpolation=str(args.get("interpolation") or "LINEAR"),
        easing=str(args.get("easing") or ""),
        label=args.get("label", "Set action interpolation"),
    )


def retime_actions(context, args):
    return advanced_helpers.retime_actions(
        context,
        action_names=_name_list(args.get("action_names")),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        snap_to_integer=bool(args.get("snap_to_integer", True)),
        label=args.get("label", "Retime actions"),
    )


def add_action_cycles(context, args):
    return advanced_helpers.add_action_cycles(
        context,
        action_names=_name_list(args.get("action_names")),
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", False)),
        mode_before=str(args.get("mode_before") or "NONE"),
        mode_after=str(args.get("mode_after") or "REPEAT"),
        replace_existing=bool(args.get("replace_existing", False)),
        label=args.get("label", "Add action cycles"),
    )


def clear_animation(context, args):
    return advanced_helpers.clear_animation(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        include_object_animation=bool(args.get("include_object_animation", True)),
        include_data_animation=bool(args.get("include_data_animation", True)),
        include_shape_key_animation=bool(args.get("include_shape_key_animation", True)),
        include_material_animation=bool(args.get("include_material_animation", False)),
        label=args.get("label", "Clear animation"),
    )


def set_animation_preview_range(context, args):
    return advanced_helpers.set_animation_preview_range(
        context,
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        current_frame=args.get("current_frame"),
        use_preview_range=bool(args.get("use_preview_range", True)),
        label=args.get("label", "Set animation preview range"),
    )


def create_turntable_animation(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.create_turntable_animation(
        context,
        object_name=str(args.get("object_name") or active),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        axis=str(args.get("axis") or "Z"),
        revolutions=float(args.get("revolutions", 1.0)),
        add_cycles=bool(args.get("add_cycles", False)),
        label=args.get("label", "Create turntable animation"),
    )


def create_pulse_animation(context, args):
    active = context.active_object.name if context.active_object else ""
    emission_strength_end = args.get("emission_strength_end")
    return advanced_helpers.create_pulse_animation(
        context,
        object_name=str(args.get("object_name") or active),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        scale_factor=float(args.get("scale_factor", 1.15)),
        emission_strength_end=float(emission_strength_end) if emission_strength_end is not None else None,
        label=args.get("label", "Create pulse animation"),
    )


def create_reveal_animation(context, args):
    active = context.active_object.name if context.active_object else ""
    return advanced_helpers.create_reveal_animation(
        context,
        object_name=str(args.get("object_name") or active),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        scale_start=float(args.get("scale_start", 0.01)),
        scale_end=float(args.get("scale_end", 1.0)),
        fade_material=bool(args.get("fade_material", True)),
        label=args.get("label", "Create reveal animation"),
    )


def create_staggered_motion(context, args):
    return advanced_helpers.create_staggered_motion(
        context,
        object_names=_name_list(args.get("object_names")),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        duration=_bounded_int(args.get("duration"), 24, minimum=1, maximum=10000),
        frame_step=_bounded_int(args.get("frame_step"), 6, minimum=0, maximum=10000),
        location_delta=_float_list(args.get("location_delta"), 3, (0.0, 0.0, 1.0)),
        interpolation=str(args.get("interpolation") or "BEZIER"),
        label=args.get("label", "Create staggered motion"),
    )


def block_key_poses(context, args):
    return advanced_helpers.block_key_poses(
        context,
        object_names=_name_list(args.get("object_names")),
        poses=args.get("poses") if isinstance(args.get("poses"), list) else [],
        selected_only=bool(args.get("selected_only", False)),
        interpolation=str(args.get("interpolation") or "CONSTANT"),
        label=args.get("label", "Block key poses"),
    )


def add_breakdown_pose(context, args):
    return advanced_helpers.add_breakdown_pose(
        context,
        object_names=_name_list(args.get("object_names")),
        frame=args.get("frame"),
        previous_frame=args.get("previous_frame"),
        next_frame=args.get("next_frame"),
        factor=float(args.get("factor", 0.5)),
        location=_optional_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        rotation=_optional_float_list(args.get("rotation"), 3, (0.0, 0.0, 0.0)),
        scale=_optional_float_list(args.get("scale"), 3, (1.0, 1.0, 1.0)),
        paths=_name_list(args.get("paths")),
        selected_only=bool(args.get("selected_only", False)),
        interpolation=str(args.get("interpolation") or "CONSTANT"),
        label=args.get("label", "Add breakdown pose"),
    )


def set_pose_hold(context, args):
    return advanced_helpers.set_pose_hold(
        context,
        object_names=_name_list(args.get("object_names")),
        frame=args.get("frame"),
        hold_frames=_bounded_int(args.get("hold_frames"), 4, minimum=1, maximum=10000),
        paths=_name_list(args.get("paths")),
        selected_only=bool(args.get("selected_only", False)),
        interpolation=str(args.get("interpolation") or "CONSTANT"),
        label=args.get("label", "Set pose hold"),
    )


def set_rig_pose_hold(context, args):
    return advanced_helpers.set_rig_pose_hold(
        context,
        armature_name=str(args.get("armature_name") or ""),
        bone_names=_name_list(args.get("bone_names")),
        frame=args.get("frame"),
        hold_frames=_bounded_int(args.get("hold_frames"), 4, minimum=1, maximum=60),
        paths=_name_list(args.get("paths")),
        interpolation=str(args.get("interpolation") or "CONSTANT"),
        label=args.get("label", "Set rig pose hold"),
    )


def create_motion_arc(context, args):
    return advanced_helpers.create_motion_arc(
        context,
        object_names=_name_list(args.get("object_names")),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        sample_step=_bounded_int(args.get("sample_step"), 4, minimum=1, maximum=10000),
        selected_only=bool(args.get("selected_only", False)),
        name_prefix=str(args.get("name_prefix") or "Claude Motion Arc"),
        bevel_depth=float(args.get("bevel_depth", 0.015)),
        color=_float_list(args.get("color"), 4, (0.08, 0.45, 1.0, 1.0)),
        label=args.get("label", "Create motion arc"),
    )


def create_text_object(context, args):
    return advanced_helpers.create_text_object(
        context,
        name=str(args.get("name") or "Claude Text"),
        body=str(args.get("body") or "Text"),
        location=_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        rotation=_float_list(args.get("rotation"), 3, (0.0, 0.0, 0.0)),
        scale=_float_list(args.get("scale"), 3, (1.0, 1.0, 1.0)),
        size=float(args.get("size", 1.0)),
        align_x=str(args.get("align_x") or "CENTER"),
        align_y=str(args.get("align_y") or "CENTER"),
        material_name=str(args.get("material_name") or ""),
        color=_optional_float_list(args.get("color"), 4, (1.0, 1.0, 1.0, 1.0)),
        label=args.get("label", "Create text object"),
    )


def create_curve_path(context, args):
    points = args.get("points") or []
    return advanced_helpers.create_curve_path(
        context,
        name=str(args.get("name") or "Claude Curve"),
        points=points,
        bevel_depth=float(args.get("bevel_depth", 0.02)),
        cyclic=bool(args.get("cyclic", False)),
        material_name=str(args.get("material_name") or ""),
        color=_optional_float_list(args.get("color"), 4, (1.0, 1.0, 1.0, 1.0)),
        label=args.get("label", "Create curve path"),
    )


def add_particle_system_to_selected(context, args):
    return advanced_helpers.add_particle_system_to_selected(
        context,
        name=str(args.get("name") or "Claude Particles"),
        count=_bounded_int(args.get("count"), 200, maximum=20000),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        lifetime=float(args.get("lifetime", 80.0)),
        particle_size=float(args.get("particle_size", 0.05)),
        label=args.get("label", "Add particle system"),
    )


def create_basic_armature(context, args):
    return advanced_helpers.create_basic_armature(
        context,
        name=str(args.get("name") or "Claude Armature"),
        location=_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        rotation=_float_list(args.get("rotation"), 3, (0.0, 0.0, 0.0)),
        show_in_front=bool(args.get("show_in_front", True)),
        label=args.get("label", "Create basic armature"),
    )


def add_copy_transform_constraint(context, args):
    return advanced_helpers.add_copy_transform_constraint(
        context,
        target_name=str(args.get("target_name") or ""),
        constraint_type=str(args.get("constraint_type") or "COPY_LOCATION"),
        name=str(args.get("name") or "Claude Copy Transform"),
        influence=float(args.get("influence", 1.0)),
        label=args.get("label", "Add copy transform constraint"),
    )


def set_render_settings(context, args):
    return advanced_helpers.set_render_settings(
        context,
        engine=str(args.get("engine") or ""),
        resolution=args.get("resolution"),
        fps=args.get("fps"),
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        film_transparent=args.get("film_transparent"),
        label=args.get("label", "Set render settings"),
    )


def set_camera_settings(context, args):
    return advanced_helpers.set_camera_settings(
        context,
        camera_name=str(args.get("camera_name") or ""),
        lens=args.get("lens"),
        sensor_width=args.get("sensor_width"),
        dof_enabled=args.get("dof_enabled"),
        focus_object_name=str(args.get("focus_object_name") or ""),
        aperture_fstop=args.get("aperture_fstop"),
        label=args.get("label", "Set camera settings"),
    )


def set_world_background(context, args):
    return advanced_helpers.set_world_background(
        context,
        color=_float_list(args.get("color"), 3, (0.05, 0.05, 0.07)),
        label=args.get("label", "Set world background"),
    )


def create_empty(context, args):
    return advanced_helpers.create_empty(
        context,
        name=str(args.get("name") or "Claude Empty"),
        location=_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        rotation=_float_list(args.get("rotation"), 3, (0.0, 0.0, 0.0)),
        scale=_float_list(args.get("scale"), 3, (1.0, 1.0, 1.0)),
        empty_display_type=str(args.get("empty_display_type") or "PLAIN_AXES"),
        empty_display_size=float(args.get("empty_display_size", 1.0)),
        select_new=bool(args.get("select_new", True)),
        label=args.get("label", "Create empty"),
    )


def set_object_visibility(context, args):
    return advanced_helpers.set_object_visibility(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        hide_viewport=args.get("hide_viewport"),
        hide_render=args.get("hide_render"),
        hide_select=args.get("hide_select"),
        label=args.get("label", "Set object visibility"),
    )


def set_object_display(context, args):
    return advanced_helpers.set_object_display(
        context,
        object_names=_name_list(args.get("object_names")),
        selected_only=bool(args.get("selected_only", True)),
        display_type=str(args.get("display_type") or ""),
        show_name=args.get("show_name"),
        show_wire=args.get("show_wire"),
        show_in_front=args.get("show_in_front"),
        color=_optional_float_list(args.get("color"), 4, (1.0, 1.0, 1.0, 1.0)),
        empty_display_type=str(args.get("empty_display_type") or ""),
        empty_display_size=args.get("empty_display_size"),
        label=args.get("label", "Set object display"),
    )


def duplicate_selected_objects(context, args):
    return advanced_helpers.duplicate_selected_objects(
        context,
        name_prefix=str(args.get("name_prefix") or "Claude Copy "),
        offset=_float_list(args.get("offset"), 3, (0.0, 0.0, 0.0)),
        linked_data=bool(args.get("linked_data", False)),
        copy_animation=bool(args.get("copy_animation", False)),
        select_new=bool(args.get("select_new", True)),
        label=args.get("label", "Duplicate selected objects"),
    )


def parent_selected_to_empty(context, args):
    return advanced_helpers.parent_selected_to_empty(
        context,
        name=str(args.get("name") or "Claude Parent"),
        location=_optional_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        empty_display_type=str(args.get("empty_display_type") or "PLAIN_AXES"),
        keep_transform=bool(args.get("keep_transform", True)),
        label=args.get("label", "Parent selected to empty"),
    )


def align_selected_objects(context, args):
    return advanced_helpers.align_selected_objects(
        context,
        axis=str(args.get("axis") or "Z"),
        mode=str(args.get("mode") or "ACTIVE"),
        value=args.get("value"),
        label=args.get("label", "Align selected objects"),
    )


def distribute_selected_objects(context, args):
    return advanced_helpers.distribute_selected_objects(
        context,
        axis=str(args.get("axis") or "X"),
        start=args.get("start"),
        end=args.get("end"),
        label=args.get("label", "Distribute selected objects"),
    )


def shade_smooth_selected(context, args):
    return advanced_helpers.shade_smooth_selected(
        context,
        add_weighted_normals=bool(args.get("add_weighted_normals", True)),
        label=args.get("label", "Shade smooth selected"),
    )


def add_bevel_and_subsurf(context, args):
    return advanced_helpers.add_bevel_and_subsurf(
        context,
        bevel_width=float(args.get("bevel_width", 0.06)),
        bevel_segments=_bounded_int(args.get("bevel_segments"), 3, maximum=16),
        subsurf_levels=_bounded_int(args.get("subsurf_levels"), 1, minimum=0, maximum=3),
        weighted_normals=bool(args.get("weighted_normals", True)),
        label=args.get("label", "Add bevel and subdivision"),
    )


def create_wheel_assembly(context, args):
    return advanced_helpers.create_wheel_assembly(
        context,
        name=str(args.get("name") or "Claude Wheel"),
        location=_float_list(args.get("location"), 3, (0.0, 0.0, 0.0)),
        radius=float(args.get("radius", 0.45)),
        tire_thickness=float(args.get("tire_thickness", 0.12)),
        axis=str(args.get("axis") or "Y"),
        tire_material_name=str(args.get("tire_material_name") or "Claude Tire Rubber"),
        rim_material_name=str(args.get("rim_material_name") or "Claude Wheel Rim"),
        label=args.get("label", "Create wheel assembly"),
    )


def add_panel_seams(context, args):
    return advanced_helpers.add_panel_seams(
        context,
        target_name=str(args.get("target_name") or ""),
        seam_material_name=str(args.get("seam_material_name") or "Claude Panel Seams"),
        bevel_depth=float(args.get("bevel_depth", 0.015)),
        label=args.get("label", "Add panel seams"),
    )


def add_window_materials(context, args):
    return advanced_helpers.add_window_materials(
        context,
        target_name=str(args.get("target_name") or ""),
        material_name=str(args.get("material_name") or "Claude Blue Glass"),
        color=_float_list(args.get("color"), 4, (0.08, 0.35, 0.65, 0.42)),
        create_panels=bool(args.get("create_panels", True)),
        label=args.get("label", "Add window materials"),
    )


def apply_vehicle_refinement_template(context, args):
    return advanced_helpers.apply_vehicle_refinement_template(
        context,
        target_name=str(args.get("target_name") or ""),
        detail_level=str(args.get("detail_level") or "medium"),
        label=args.get("label", "Apply vehicle refinement template"),
    )


def apply_product_refinement_template(context, args):
    return advanced_helpers.apply_product_refinement_template(
        context,
        target_name=str(args.get("target_name") or ""),
        style=str(args.get("style") or "studio"),
        include_stage=bool(args.get("include_stage", True)),
        include_callouts=bool(args.get("include_callouts", True)),
        include_turntable=bool(args.get("include_turntable", False)),
        label=args.get("label", "Apply product refinement template"),
    )


def apply_character_refinement_template(context, args):
    return advanced_helpers.apply_character_refinement_template(
        context,
        target_name=str(args.get("target_name") or ""),
        character_style=str(args.get("character_style") or "neutral"),
        detail_level=str(args.get("detail_level") or "medium"),
        create_guides=bool(args.get("create_guides", True)),
        label=args.get("label", "Apply character refinement template"),
    )


def create_studio_product_stage(context, args):
    return advanced_helpers.create_studio_product_stage(
        context,
        target_name=str(args.get("target_name") or ""),
        stage_name=str(args.get("stage_name") or "Claude Product Stage"),
        floor=bool(args.get("floor", True)),
        backdrop=bool(args.get("backdrop", True)),
        lighting=bool(args.get("lighting", True)),
        camera=bool(args.get("camera", True)),
        label=args.get("label", "Create studio product stage"),
    )


def add_dimension_callouts(context, args):
    return advanced_helpers.add_dimension_callouts(
        context,
        target_name=str(args.get("target_name") or ""),
        unit_label=str(args.get("unit_label") or "bu"),
        include_width=bool(args.get("include_width", True)),
        include_depth=bool(args.get("include_depth", True)),
        include_height=bool(args.get("include_height", True)),
        label=args.get("label", "Add dimension callouts"),
    )


def apply_lighting_preset(context, args):
    return advanced_helpers.apply_lighting_preset(
        context,
        target_name=str(args.get("target_name") or ""),
        preset=str(args.get("preset") or "product_softbox"),
        rig_name=str(args.get("rig_name") or "Claude Lighting"),
        label=args.get("label", "Apply lighting preset"),
    )


def create_material_palette(context, args):
    return advanced_helpers.create_material_palette(
        context,
        palette_name=str(args.get("palette_name") or "Claude Material Palette"),
        palette=str(args.get("palette") or "product_neutral"),
        create_swatches=bool(args.get("create_swatches", True)),
        assign_to_selected=bool(args.get("assign_to_selected", False)),
        label=args.get("label", "Create material palette"),
    )


def create_product_turntable_setup(context, args):
    return advanced_helpers.create_product_turntable_setup(
        context,
        target_name=str(args.get("target_name") or ""),
        frame_start=int(args.get("frame_start", 1)),
        frame_end=int(args.get("frame_end", 120)),
        revolutions=float(args.get("revolutions", 1.0)),
        radius=float(args.get("radius", 0.0)),
        height=float(args.get("height", 0.0)),
        setup_name=str(args.get("setup_name") or "Claude Product Turntable"),
        create_stage=bool(args.get("create_stage", True)),
        label=args.get("label", "Create product turntable setup"),
    )


def organize_scene_for_production(context, args):
    return advanced_helpers.organize_scene_for_production(
        context,
        collection_prefix=str(args.get("collection_prefix") or "Claude Production"),
        selected_only=bool(args.get("selected_only", False)),
        label=args.get("label", "Organize scene for production"),
    )


def add_track_to_constraint(context, args):
    return live_preview.add_track_to_constraint(
        context,
        target_name=str(args.get("target_name") or ""),
        name=str(args.get("name") or "Claude Track To"),
        track_axis=str(args.get("track_axis") or "TRACK_NEGATIVE_Z"),
        up_axis=str(args.get("up_axis") or "UP_Y"),
        influence=float(args.get("influence", 1.0)),
        label=args.get("label", "Add Track To constraint"),
    )


def add_light(context, args):
    light_type = str(args.get("light_type") or "POINT").upper()
    if light_type not in {"POINT", "SUN", "SPOT", "AREA"}:
        light_type = "POINT"
    return live_preview.add_light(
        context,
        light_type=light_type,
        name=str(args.get("name") or "Claude Light"),
        location=_float_list(args.get("location"), 3, (3.0, -4.0, 4.0)),
        energy=float(args.get("energy", 500.0)),
        color=_float_list(args.get("color"), 3, (1.0, 0.92, 0.82)),
        label=args.get("label", "Add light"),
    )


def add_camera(context, args):
    return live_preview.add_camera(
        context,
        name=str(args.get("name") or "Claude Camera"),
        location=_float_list(args.get("location"), 3, (4.0, -6.0, 4.0)),
        rotation=_float_list(args.get("rotation"), 3, (1.1, 0.0, 0.65)),
        lens=float(args.get("lens", 50.0)),
        label=args.get("label", "Add camera"),
    )


def set_scene_frame_range(context, args):
    return live_preview.set_scene_frame_range(
        context,
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        current_frame=args.get("current_frame"),
        fps=args.get("fps"),
        label=args.get("label", "Set timeline"),
    )


def set_active_camera(context, args):
    return live_preview.set_active_camera(
        context,
        camera_name=str(args.get("camera_name") or ""),
        label=args.get("label", "Set active camera"),
    )


def animate_selected_transform(context, args):
    return live_preview.animate_selected_transform(
        context,
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        location_start=_optional_float_list(args.get("location_start"), 3, (0.0, 0.0, 0.0)),
        location_end=_optional_float_list(args.get("location_end"), 3, (0.0, 0.0, 0.0)),
        rotation_start=_optional_float_list(args.get("rotation_start"), 3, (0.0, 0.0, 0.0)),
        rotation_end=_optional_float_list(args.get("rotation_end"), 3, (0.0, 0.0, 0.0)),
        scale_start=_optional_float_list(args.get("scale_start"), 3, (1.0, 1.0, 1.0)),
        scale_end=_optional_float_list(args.get("scale_end"), 3, (1.0, 1.0, 1.0)),
        label=args.get("label", "Animate selected transform"),
    )


def create_camera_orbit(context, args):
    active = context.active_object.name if context.active_object else ""
    return live_preview.create_camera_orbit(
        context,
        target_name=str(args.get("target_name") or active),
        frame_start=int(args.get("frame_start", context.scene.frame_start)),
        frame_end=int(args.get("frame_end", context.scene.frame_end)),
        radius=float(args.get("radius", 5.0)),
        height=float(args.get("height", 2.5)),
        name=str(args.get("name") or "Claude Orbit Camera"),
        lens=float(args.get("lens", 35.0)),
        label=args.get("label", "Create camera orbit"),
    )


def capture_viewport(context, args):
    prefs = preferences.get_preferences(context)
    max_bytes = args.get("max_bytes")
    if max_bytes is None:
        max_bytes = getattr(prefs, "max_screenshot_bytes", viewport_capture.DEFAULT_MAX_BYTES)
    metadata, attachments = viewport_capture.capture_viewport(
        context,
        capture_dir=getattr(prefs, "capture_cache_dir", None),
        max_bytes=_bounded_int(max_bytes, viewport_capture.DEFAULT_MAX_BYTES, minimum=262144, maximum=20 * 1024 * 1024),
    )
    return {
        "ok": bool(metadata.get("available")),
        "message": metadata.get("note") or "Viewport screenshot capture complete",
        "visual_context": metadata,
        "attachment_available": bool(attachments),
        "attachment_keys": sorted(attachments.keys()),
    }


def capture_animation_playblast(context, args):
    prefs = preferences.get_preferences(context)
    max_bytes = args.get("max_bytes")
    if max_bytes is None:
        max_bytes = getattr(prefs, "max_screenshot_bytes", viewport_capture.DEFAULT_MAX_BYTES)
    metadata = playblast_capture.capture_animation_playblast(
        context,
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        max_frames=_bounded_int(
            args.get("max_frames"),
            playblast_capture.DEFAULT_MAX_FRAMES,
            minimum=1,
            maximum=playblast_capture.MAX_PLAYBLAST_FRAMES,
        ),
        max_bytes=_bounded_int(max_bytes, viewport_capture.DEFAULT_MAX_BYTES, minimum=262144, maximum=20 * 1024 * 1024),
        brief=str(args.get("brief") or ""),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
    )
    return {
        "ok": bool(metadata.get("available")),
        "message": metadata.get("note") or "Animation playblast capture complete",
        "playblast": metadata,
    }


def capture_object_inspection_renders(context, args):
    prefs = preferences.get_preferences(context)
    metadata_result = inspection_render.capture_object_inspection_renders(
        context,
        object_names=_name_list(args.get("object_names")),
        views=_name_list(args.get("views")),
        frame=args.get("frame"),
        resolution_x=_bounded_int(args.get("resolution_x"), 800, minimum=64, maximum=4096),
        resolution_y=_bounded_int(args.get("resolution_y"), 600, minimum=64, maximum=4096),
        lens=_bounded_float(args.get("lens"), 50.0, minimum=1.0, maximum=300.0),
        distance_factor=_bounded_float(args.get("distance_factor"), 3.0, minimum=0.5, maximum=20.0),
        camera_name=str(args.get("camera_name") or "Claude Inspection Camera"),
        note=str(args.get("note") or args.get("brief") or ""),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
    )
    return metadata_result


def get_blend_file_diagnostics(context, args):
    return lab_parity.get_blend_file_diagnostics(
        context,
        max_items=_bounded_int(args.get("max_items"), 50, minimum=1, maximum=200),
    )


def get_workspace_layout(context, args):
    return lab_parity.get_workspace_layout(
        context,
        max_workspaces=_bounded_int(args.get("max_workspaces"), 20, minimum=1, maximum=100),
        max_areas=_bounded_int(args.get("max_areas"), 80, minimum=1, maximum=300),
    )


def jump_to_workspace(context, args):
    return lab_parity.jump_to_workspace(
        context,
        workspace_name=str(args.get("workspace_name") or args.get("name") or ""),
    )


def focus_object_in_viewport(context, args):
    return lab_parity.focus_object_in_viewport(
        context,
        object_name=str(args.get("object_name") or ""),
        select=bool(args.get("select", True)),
    )


def render_scene_thumbnail(context, args):
    prefs = preferences.get_preferences(context)
    return lab_parity.render_scene_thumbnail(
        context,
        filepath=str(args.get("filepath") or ""),
        frame=args.get("frame"),
        resolution_x=_bounded_int(args.get("resolution_x"), 512, minimum=32, maximum=4096),
        resolution_y=_bounded_int(args.get("resolution_y"), 512, minimum=32, maximum=4096),
        camera_name=str(args.get("camera_name") or ""),
        note=str(args.get("note") or ""),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
    )


def start_render_job(context, args):
    prefs = preferences.get_preferences(context)
    return render_jobs.start_render_job(
        context,
        frame_start=args.get("frame_start"),
        frame_end=args.get("frame_end"),
        resolution_x=_bounded_int(args.get("resolution_x"), 1920, minimum=16, maximum=8192),
        resolution_y=_bounded_int(args.get("resolution_y"), 1080, minimum=16, maximum=8192),
        resolution_percentage=_bounded_int(args.get("resolution_percentage"), 100, minimum=1, maximum=100),
        samples=_bounded_int(args.get("samples"), 64, minimum=1, maximum=4096),
        fps=args.get("fps"),
        camera_name=str(args.get("camera_name") or ""),
        output_kind=str(args.get("output_kind") or "frames"),
        job_name=str(args.get("job_name") or ""),
        note=str(args.get("note") or ""),
        capture_dir=getattr(prefs, "capture_cache_dir", None),
    )


def get_render_job_status(context, args):
    prefs = preferences.get_preferences(context)
    job_id = str(args.get("job_id") or "")
    job = render_jobs.render_job_status(
        job_id,
        context=context,
        preferred_dir=getattr(prefs, "capture_cache_dir", None),
    )
    return {
        "ok": bool(job.get("available", False)),
        "message": "Render job status collected" if job.get("available") else job.get("message", "Render job was not found"),
        "render_job": job,
    }


def cancel_render_job(context, args):
    prefs = preferences.get_preferences(context)
    return render_jobs.cancel_render_job(
        str(args.get("job_id") or ""),
        context=context,
        preferred_dir=getattr(prefs, "capture_cache_dir", None),
    )


def search_blender_docs(context, args):
    prefs = preferences.get_preferences(context)
    return docs_index.search_blender_docs(
        str(args.get("query") or ""),
        cache_dir=getattr(prefs, "docs_cache_dir", None),
        local_first=bool(getattr(prefs, "local_docs_first", True)),
    )


def draft_script(context, args):
    script_text = _extract_script_code(args)
    intent_text = "\n".join(
        str(args.get(key) or "")
        for key in ("intent", "expected_changes", "brief", "prompt")
    )
    guard_text = "\n".join([intent_text, script_text[:4000]])
    if _looks_like_render_job_intent(guard_text) and not _has_explicit_animation_helper_gap(guard_text):
        return {
            "ok": False,
            "blocked": True,
            "message": (
                "This looks like a long render or playblast job. Use start_render_job first, then poll "
                "get_render_job_status, unless the render job helper cannot express the request."
            ),
            "recommended_tool": "start_render_job",
            "requires_user_approval": False,
        }
    if (
        _looks_like_animation_intent(guard_text)
        and not _animation_script_fallback_recently_allowed(context)
        and not _has_explicit_animation_helper_gap(guard_text)
    ):
        workflow_seen = _animation_workflow_recently_seen(context)
        return {
            "ok": False,
            "code": "animation_workflow_required",
            "message": (
                "The recent animation workflow did not allow script fallback; use run_animation_workflow again "
                "or state the helper gap explicitly."
                if workflow_seen
                else "Use run_animation_workflow first unless helpers cannot express this."
            ),
            "requires_user_approval": False,
            "animation_workflow_seen": workflow_seen,
            "explicit_helper_gap_required": True,
            "recommended_tools": [
                "plan_animation_workflow",
                "run_animation_workflow",
                "run_animation_task",
            ],
        }
    staged = script_runner.stage_script(
        context,
        code=script_text,
        intent=str(args.get("intent") or ""),
        expected_changes=str(args.get("expected_changes") or ""),
        risk_level=str(args.get("risk_level") or "medium"),
        target_objects=args.get("target_objects") or [],
    )
    if not staged.get("ok") or staged.get("analysis", {}).get("blocked"):
        return staged
    if not script_runner.external_script_trust_active(context):
        return staged
    prefs = preferences.get_preferences(context)
    run_result = script_runner.run_externally_approved_script(
        context,
        "",
        checkpoint_enabled=bool(getattr(prefs, "checkpoints_enabled", True)),
        checkpoint_dir=getattr(prefs, "checkpoint_dir", None),
    )
    return {
        "ok": bool(run_result.get("ok")),
        "message": (
            "Script staged and auto-ran under active external script trust"
            if run_result.get("ok")
            else "Script staged but auto-run failed under active external script trust"
        ),
        "auto_ran": bool(run_result.get("ok")),
        "auto_run_attempted": True,
        "auto_run_reason": "external_script_trust_active",
        "staged": staged,
        "run_result": run_result,
        "requires_user_approval": False,
    }


def run_approved_script(context, args):
    prefs = preferences.get_preferences(context)
    return script_runner.run_externally_approved_script(
        context,
        str(args.get("approval_token") or ""),
        checkpoint_enabled=bool(getattr(prefs, "checkpoints_enabled", True)),
        checkpoint_dir=getattr(prefs, "checkpoint_dir", None),
    )


def commit_preview(context, args):
    return live_preview.commit(context)


def revert_preview(context, args):
    return live_preview.revert(context)


def _compact_targets(step):
    for key in (
        "objects",
        "selected_objects",
        "actions",
        "materials",
        "created",
        "created_objects",
        "duplicates",
        "collections",
        "lights",
        "cameras",
    ):
        value = step.get(key)
        if not value:
            continue
        if isinstance(value, list):
            names = []
            for item in value[:8]:
                if isinstance(item, dict):
                    names.append(str(item.get("object") or item.get("action") or item.get("name") or item))
                else:
                    names.append(str(item))
            return names
        return [str(value)]
    for key in ("object", "target", "camera", "material", "collection", "action", "world"):
        value = step.get(key)
        if value:
            return [str(value)]
    return []


def _format_count(noun, count):
    count = int(count or 0)
    suffix = "" if count == 1 else "s"
    return f"{count} {noun}{suffix}"


def _preview_expected_changes(step, label, kind, target_text):
    custom = str(step.get("expected_changes") or "").strip()
    if custom:
        return custom
    if kind == "create_studio_product_stage":
        return (
            f"{label}: creates a studio stage for {step.get('target') or target_text} with "
            f"{_format_count('object', len(step.get('created_objects') or []))}, "
            f"{_format_count('light', len(step.get('lights') or []))}, "
            f"and {'a camera' if step.get('camera') else 'no camera'}."
        )
    if kind == "add_dimension_callouts":
        axes = ", ".join(sorted((step.get("measurements") or {}).keys())) or "bounds"
        return f"{label}: adds dimension callouts for {step.get('target') or target_text} covering {axes}."
    if kind == "apply_lighting_preset":
        return (
            f"{label}: adds the {step.get('preset', 'production')} lighting preset around "
            f"{step.get('target') or target_text} with {_format_count('light', len(step.get('lights') or []))}."
        )
    if kind == "create_material_palette":
        return (
            f"{label}: creates the {step.get('palette', 'production')} palette with "
            f"{_format_count('material', len(step.get('materials') or []))} and "
            f"{_format_count('swatch', len(step.get('swatches') or []))}."
        )
    if kind == "create_product_turntable_setup":
        return (
            f"{label}: sets up {step.get('target') or target_text} for a turntable from frame "
            f"{step.get('frame_start')} to {step.get('frame_end')}, with "
            f"{'stage, ' if step.get('stage_created') else ''}"
            f"camera {step.get('camera') or 'none'} and action {step.get('action') or 'none'}."
        )
    if kind == "organize_scene_for_production":
        return (
            f"{label}: links {_format_count('object', len(step.get('linked') or []))} into "
            f"{_format_count('production collection', len(step.get('collections') or []))} without deleting original links."
        )
    if kind == "apply_vehicle_refinement_template":
        return (
            f"{label}: adds a vehicle detail kit around {step.get('target') or target_text} with "
            f"{_format_count('created object', len(step.get('created_objects') or []))}."
        )
    if kind in {"apply_product_refinement_template", "apply_character_refinement_template"}:
        features = ", ".join(step.get("features") or []) or "bounded production details"
        return f"{label}: applies {features} around {step.get('target') or target_text}."
    return f"{label}: {kind} affects {target_text}."


def _preview_change_report(transaction):
    steps = list((transaction or {}).get("applied_steps") or [])
    if not steps:
        return {}
    step = steps[-1]
    label = str(step.get("label") or step.get("type") or "Live preview change")
    kind = str(step.get("type") or "preview_change")
    targets = _compact_targets(step)
    target_text = ", ".join(targets[:5]) if targets else "current scene"
    if len(targets) > 5:
        target_text += f", +{len(targets) - 5} more"
    manifest = live_preview.transaction_manifest(transaction)
    rollback_scopes = manifest.get("rollback_scopes") or []
    rollback_text = ", ".join(rollback_scopes[:5]) if rollback_scopes else "none"
    expected_changes = _preview_expected_changes(step, label, kind, target_text)
    expected_with_rollback = f"{expected_changes} Rollback snapshots: {rollback_text}."
    return {
        "label": label,
        "type": kind,
        "targets": targets,
        "expected_changes": expected_with_rollback,
        "rollback_snapshot_count": int(manifest.get("snapshot_count", 0) or 0),
        "rollback_scopes": rollback_scopes,
    }


def _attach_preview_change_report(result):
    if not isinstance(result, dict) or not result.get("ok") or not result.get("transaction_id"):
        return result
    transaction = live_preview.current_transaction()
    if not transaction or transaction.get("id") != result.get("transaction_id"):
        return result
    report = _preview_change_report(transaction)
    if not report:
        return result
    enriched = dict(result)
    enriched.setdefault("expected_changes", report["expected_changes"])
    enriched.setdefault("preview_change_report", report)
    return enriched


TOOL_FUNCTIONS = {
    "inspect_scene": inspect_scene,
    "list_scene_objects": list_scene_objects,
    "get_object_details": get_object_details,
    "get_animation_details": get_animation_details,
    "get_animation_scene_context": get_animation_scene_context,
    "create_animation_brief": create_animation_brief,
    "create_timing_chart": create_timing_chart,
    "plan_animation_workflow": plan_animation_workflow,
    "run_animation_workflow": run_animation_workflow,
    "run_animation_task": run_animation_task,
    "analyze_motion_arcs": analyze_motion_arcs,
    "analyze_fcurve_spacing": analyze_fcurve_spacing,
    "analyze_pose_clarity": analyze_pose_clarity,
    "analyze_animation_principles": analyze_animation_principles,
    "sample_animation_state": sample_animation_state,
    "analyze_contact_sliding": analyze_contact_sliding,
    "analyze_collision_penetration": analyze_collision_penetration,
    "analyze_center_of_mass": analyze_center_of_mass,
    "analyze_camera_framing": analyze_camera_framing,
    "analyze_motion_physics": analyze_motion_physics,
    "compare_animation_to_brief": compare_animation_to_brief,
    "review_playblast_against_brief": review_playblast_against_brief,
    "review_inspection_renders_against_brief": review_inspection_renders_against_brief,
    "repair_animation_from_findings": repair_animation_from_findings,
    "run_animation_repair_loop": run_animation_repair_loop,
    "get_material_node_details": get_material_node_details,
    "get_geometry_nodes_details": get_geometry_nodes_details,
    "get_shader_nodes_details": get_shader_nodes_details,
    "get_rigging_details": get_rigging_details,
    "get_shape_key_details": get_shape_key_details,
    "get_curve_text_details": get_curve_text_details,
    "get_simulation_details": get_simulation_details,
    "get_collection_layer_details": get_collection_layer_details,
    "get_render_camera_compositor_details": get_render_camera_compositor_details,
    "select_objects": select_objects,
    "set_current_frame": set_current_frame,
    "set_selected_location_delta": set_selected_location_delta,
    "set_selected_transform": set_selected_transform,
    "create_primitive": create_primitive,
    "assign_material_to_selected": assign_material_to_selected,
    "assign_emission_material_to_selected": assign_emission_material_to_selected,
    "create_collection": create_collection,
    "link_selected_to_collection": link_selected_to_collection,
    "add_modifier_to_selected": add_modifier_to_selected,
    "create_shader_material": create_shader_material,
    "add_geometry_nodes_modifier": add_geometry_nodes_modifier,
    "create_shape_key": create_shape_key,
    "animate_shape_key": animate_shape_key,
    "animate_object_bounce": animate_object_bounce,
    "create_progressive_bounce_animation": create_progressive_bounce_animation,
    "animate_material_property": animate_material_property,
    "animate_light_property": animate_light_property,
    "create_follow_path_animation": create_follow_path_animation,
    "set_action_interpolation": set_action_interpolation,
    "retime_actions": retime_actions,
    "add_action_cycles": add_action_cycles,
    "clear_animation": clear_animation,
    "set_animation_preview_range": set_animation_preview_range,
    "create_turntable_animation": create_turntable_animation,
    "create_pulse_animation": create_pulse_animation,
    "create_reveal_animation": create_reveal_animation,
    "create_staggered_motion": create_staggered_motion,
    "block_key_poses": block_key_poses,
    "add_breakdown_pose": add_breakdown_pose,
    "set_pose_hold": set_pose_hold,
    "set_rig_pose_hold": set_rig_pose_hold,
    "create_motion_arc": create_motion_arc,
    "create_text_object": create_text_object,
    "create_curve_path": create_curve_path,
    "add_particle_system_to_selected": add_particle_system_to_selected,
    "create_basic_armature": create_basic_armature,
    "add_copy_transform_constraint": add_copy_transform_constraint,
    "set_render_settings": set_render_settings,
    "set_camera_settings": set_camera_settings,
    "set_world_background": set_world_background,
    "create_empty": create_empty,
    "set_object_visibility": set_object_visibility,
    "set_object_display": set_object_display,
    "duplicate_selected_objects": duplicate_selected_objects,
    "parent_selected_to_empty": parent_selected_to_empty,
    "align_selected_objects": align_selected_objects,
    "distribute_selected_objects": distribute_selected_objects,
    "shade_smooth_selected": shade_smooth_selected,
    "add_bevel_and_subsurf": add_bevel_and_subsurf,
    "create_wheel_assembly": create_wheel_assembly,
    "add_panel_seams": add_panel_seams,
    "add_window_materials": add_window_materials,
    "apply_vehicle_refinement_template": apply_vehicle_refinement_template,
    "apply_product_refinement_template": apply_product_refinement_template,
    "apply_character_refinement_template": apply_character_refinement_template,
    "create_studio_product_stage": create_studio_product_stage,
    "add_dimension_callouts": add_dimension_callouts,
    "apply_lighting_preset": apply_lighting_preset,
    "create_material_palette": create_material_palette,
    "create_product_turntable_setup": create_product_turntable_setup,
    "organize_scene_for_production": organize_scene_for_production,
    "add_track_to_constraint": add_track_to_constraint,
    "add_light": add_light,
    "add_camera": add_camera,
    "set_scene_frame_range": set_scene_frame_range,
    "set_active_camera": set_active_camera,
    "animate_selected_transform": animate_selected_transform,
    "create_camera_orbit": create_camera_orbit,
    "capture_viewport": capture_viewport,
    "capture_animation_playblast": capture_animation_playblast,
    "capture_object_inspection_renders": capture_object_inspection_renders,
    "get_blend_file_diagnostics": get_blend_file_diagnostics,
    "get_workspace_layout": get_workspace_layout,
    "jump_to_workspace": jump_to_workspace,
    "focus_object_in_viewport": focus_object_in_viewport,
    "render_scene_thumbnail": render_scene_thumbnail,
    "start_render_job": start_render_job,
    "get_render_job_status": get_render_job_status,
    "cancel_render_job": cancel_render_job,
    "search_blender_docs": search_blender_docs,
    "draft_script": draft_script,
    "run_approved_script": run_approved_script,
    "commit_preview": commit_preview,
    "revert_preview": revert_preview,
}


def execute_tool(context, name, args):
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return _json_result({"ok": False, "message": f"Unknown Blender tool: {name}"})
    try:
        result = fn(context, args or {})
    except Exception as exc:
        result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    if isinstance(result, str):
        return result
    result = _attach_preview_change_report(result)
    return _json_result(result)


def register():
    pass


def unregister():
    pass
