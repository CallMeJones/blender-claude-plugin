"""Read-only deep Blender world-model summaries."""

from __future__ import annotations

from collections import Counter

import bpy
import mathutils


def _safe_name(data_block):
    return getattr(data_block, "name", None) if data_block else None


def _xyz(value):
    return {
        "x": round(float(value[0]), 5),
        "y": round(float(value[1]), 5),
        "z": round(float(value[2]), 5),
    }


def _rgba(value):
    channels = list(value)
    while len(channels) < 4:
        channels.append(1.0)
    return {
        "r": round(float(channels[0]), 5),
        "g": round(float(channels[1]), 5),
        "b": round(float(channels[2]), 5),
        "a": round(float(channels[3]), 5),
    }


def _limit(items, maximum):
    return list(items)[: max(1, int(maximum or 1))]


def _idprops_summary(data_block, maximum=16):
    result = {}
    if data_block is None:
        return result
    for key in list(data_block.keys())[:maximum]:
        value = data_block.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            result[str(key)] = value
        else:
            result[str(key)] = repr(value)[:160]
    return result


def _node_tree_summary(node_tree, *, max_nodes=24, max_links=48):
    if node_tree is None:
        return None
    nodes = list(getattr(node_tree, "nodes", []))
    links = list(getattr(node_tree, "links", []))
    return {
        "name": node_tree.name,
        "type": getattr(node_tree, "type", None),
        "bl_idname": getattr(node_tree, "bl_idname", None),
        "node_count": len(nodes),
        "link_count": len(links),
        "nodes": [
            {
                "name": node.name,
                "label": node.label,
                "type": node.type,
                "bl_idname": getattr(node, "bl_idname", None),
                "location": _xyz((node.location.x, node.location.y, 0.0)),
            }
            for node in nodes[:max_nodes]
        ],
        "links": [
            {
                "from_node": link.from_node.name,
                "from_socket": link.from_socket.name,
                "to_node": link.to_node.name,
                "to_socket": link.to_socket.name,
            }
            for link in links[:max_links]
        ],
        "truncated_nodes": max(0, len(nodes) - max_nodes),
        "truncated_links": max(0, len(links) - max_links),
    }


def _scene_compositor_tree(scene):
    return getattr(scene, "node_tree", None) or getattr(scene, "compositing_node_group", None)


def _scene_uses_compositor(scene):
    return bool(getattr(scene, "use_nodes", False) or _scene_compositor_tree(scene))


def _drivers_summary(data_block, *, max_drivers=24):
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
                            "id": _safe_name(target.id),
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


def _modifier_summary(modifier):
    item = {
        "name": modifier.name,
        "type": modifier.type,
        "show_viewport": bool(modifier.show_viewport),
        "show_render": bool(getattr(modifier, "show_render", False)),
    }
    node_group = getattr(modifier, "node_group", None)
    if node_group:
        item["node_group"] = {
            "name": node_group.name,
            "type": getattr(node_group, "type", None),
            "bl_idname": getattr(node_group, "bl_idname", None),
            "node_count": len(getattr(node_group, "nodes", [])),
        }
    return item


def _iter_action_fcurves(action):
    if action is None:
        return []
    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None:
        return list(fcurves)
    result = []
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                result.extend(list(getattr(channelbag, "fcurves", [])))
    return result


def _action_channel_summary(action, *, max_paths=18):
    fcurves = _iter_action_fcurves(action)
    frames = sorted({int(round(point.co.x)) for fcurve in fcurves for point in fcurve.keyframe_points})
    keyed_paths = sorted({fcurve.data_path for fcurve in fcurves})
    property_groups = Counter()
    for path in keyed_paths:
        if path.startswith("pose.bones"):
            property_groups["pose_bones"] += 1
        elif path.startswith("key_blocks"):
            property_groups["shape_keys"] += 1
        else:
            property_groups[path.split("[", 1)[0].split(".", 1)[0]] += 1
    return {
        "keyframe_count": sum(len(fcurve.keyframe_points) for fcurve in fcurves),
        "keyframe_range": [frames[0], frames[-1]] if frames else [],
        "keyed_paths": keyed_paths[:max_paths],
        "truncated_keyed_paths": max(0, len(keyed_paths) - max_paths),
        "keyed_property_groups": dict(sorted(property_groups.items())),
        "has_location_keys": any(path == "location" for path in keyed_paths),
        "has_rotation_keys": any(path in {"rotation_euler", "rotation_quaternion"} for path in keyed_paths),
        "has_scale_keys": any(path == "scale" for path in keyed_paths),
        "has_pose_bone_keys": any(path.startswith("pose.bones") for path in keyed_paths),
        "has_shape_key_keys": any(path.startswith("key_blocks") for path in keyed_paths),
    }


def _animation_owner_summary(data_block):
    animation_data = getattr(data_block, "animation_data", None)
    if animation_data is None:
        return {"has_animation_data": False, "action": None, "driver_count": 0, "nla_track_count": 0}
    action = animation_data.action
    drivers = list(getattr(animation_data, "drivers", []) or [])
    nla_tracks = list(getattr(animation_data, "nla_tracks", []) or [])
    action_slot = getattr(animation_data, "action_slot", None)
    action_slots = list(getattr(action, "slots", []) or []) if action else []
    pose_markers = list(getattr(action, "pose_markers", []) or []) if action else []
    return {
        "has_animation_data": True,
        "action": _safe_name(action),
        "action_slot": _safe_name(action_slot),
        "action_slot_count": len(action_slots),
        "action_slots": [
            {
                "name": _safe_name(slot),
                "identifier": getattr(slot, "identifier", ""),
                "target_id_type": getattr(slot, "target_id_type", ""),
            }
            for slot in action_slots[:8]
        ],
        "fcurve_count": len(_iter_action_fcurves(action)),
        "channel_summary": _action_channel_summary(action),
        "driver_count": len(drivers),
        "nla_track_count": len(nla_tracks),
        "nla_tracks": [{"name": track.name, "strip_count": len(getattr(track, "strips", []) or [])} for track in nla_tracks[:8]],
        "pose_marker_count": len(pose_markers),
        "pose_markers": [{"name": marker.name, "frame": int(marker.frame)} for marker in pose_markers[:12]],
    }


def _bbox_z_range(obj):
    corners = getattr(obj, "bound_box", None)
    if not corners:
        z = float(obj.matrix_world.translation.z)
        return z, z
    points = [obj.matrix_world @ mathutils.Vector(corner) for corner in corners]
    values = [float(point.z) for point in points]
    return min(values), max(values)


_RIG_CONTROL_NAME_TOKENS = (
    "ctrl",
    "control",
    "ctl",
    "ik",
    "fk",
    "target",
    "pole",
    "root",
    "master",
    "cog",
    "hips",
    "hand",
    "foot",
)


def _pose_bone_control_hints(obj, *, max_candidates=16):
    pose_bones = list(getattr(getattr(obj, "pose", None), "bones", []) or []) if obj.type == "ARMATURE" else []
    candidates = []
    for pose_bone in pose_bones:
        data_bone = obj.data.bones.get(pose_bone.name) if obj.data else None
        constraints = list(getattr(pose_bone, "constraints", []) or [])
        name_lower = pose_bone.name.lower()
        reasons = []
        if any(token in name_lower for token in _RIG_CONTROL_NAME_TOKENS):
            reasons.append("control_name")
        if data_bone and not data_bone.use_deform:
            reasons.append("non_deforming_bone")
        if constraints:
            reasons.append("pose_constraints")
        if getattr(pose_bone, "custom_shape", None):
            reasons.append("custom_shape")
        if not reasons:
            continue
        candidates.append(
            {
                "name": pose_bone.name,
                "parent": _safe_name(pose_bone.parent),
                "use_deform": bool(data_bone.use_deform) if data_bone else None,
                "constraint_types": sorted({con.type for con in constraints}),
                "constraint_targets": [
                    {
                        "constraint": con.name,
                        "type": con.type,
                        "target": _safe_name(getattr(con, "target", None)),
                        "subtarget": getattr(con, "subtarget", ""),
                    }
                    for con in constraints[:8]
                    if getattr(con, "target", None) or getattr(con, "subtarget", "")
                ],
                "custom_shape": _safe_name(getattr(pose_bone, "custom_shape", None)),
                "lock_location": [bool(value) for value in getattr(pose_bone, "lock_location", (False, False, False))],
                "lock_rotation": [bool(value) for value in getattr(pose_bone, "lock_rotation", (False, False, False))],
                "lock_scale": [bool(value) for value in getattr(pose_bone, "lock_scale", (False, False, False))],
                "custom_properties": _idprops_summary(pose_bone, maximum=8),
                "likely_control": True,
                "reasons": reasons,
            }
        )
    return {
        "pose_bone_count": len(pose_bones),
        "control_candidate_count": len(candidates),
        "control_candidates": candidates[: max(1, int(max_candidates or 1))],
        "truncated": len(candidates) > max(1, int(max_candidates or 1)),
    }


def _pose_library_candidates(obj, *, max_actions=8):
    if obj.type != "ARMATURE":
        return []
    candidates = []
    armature_name = obj.name.lower()
    for action in bpy.data.actions:
        fcurves = _iter_action_fcurves(action)
        if not any(fcurve.data_path.startswith("pose.bones") for fcurve in fcurves):
            continue
        marker_count = len(getattr(action, "pose_markers", []) or [])
        reasons = []
        if marker_count:
            reasons.append("pose_markers")
        if getattr(action, "asset_data", None):
            reasons.append("asset_action")
        if "pose" in action.name.lower() or armature_name in action.name.lower():
            reasons.append("name_hint")
        if not reasons:
            reasons.append("pose_bone_fcurves")
        candidates.append(
            {
                "name": action.name,
                "fcurve_count": len(fcurves),
                "pose_marker_count": marker_count,
                "keyframe_range": _action_channel_summary(action).get("keyframe_range", []),
                "reasons": reasons,
            }
        )
    return candidates[: max(1, int(max_actions or 1))]


def _rig_target_armatures(obj):
    armatures = []
    seen = set()
    if getattr(obj.parent, "type", None) == "ARMATURE":
        armatures.append(obj.parent)
        seen.add(obj.parent.name)
    for modifier in obj.modifiers:
        if modifier.type != "ARMATURE":
            continue
        armature = getattr(modifier, "object", None)
        if armature and armature.name not in seen:
            armatures.append(armature)
            seen.add(armature.name)
    return armatures


def _rig_target_summary(obj):
    parent_armature = obj.parent if getattr(obj.parent, "type", None) == "ARMATURE" else None
    armature_modifiers = []
    for modifier in obj.modifiers:
        if modifier.type != "ARMATURE":
            continue
        armature_modifiers.append(
            {
                "name": modifier.name,
                "object": _safe_name(getattr(modifier, "object", None)),
                "show_viewport": bool(modifier.show_viewport),
            }
        )
    control_targets = []
    for armature in _rig_target_armatures(obj):
        hints = _pose_bone_control_hints(armature, max_candidates=8)
        control_targets.append(
            {
                "name": armature.name,
                "pose_bone_count": hints["pose_bone_count"],
                "control_candidate_count": hints["control_candidate_count"],
                "control_candidates": hints["control_candidates"],
            }
        )
    return {
        "parent_armature": _safe_name(parent_armature),
        "armature_modifiers": armature_modifiers,
        "control_targets": control_targets,
        "likely_rig_driven": bool(parent_armature or armature_modifiers),
    }


def _physics_summary(obj):
    rigid_body = getattr(obj, "rigid_body", None)
    rigid_body_constraint = getattr(obj, "rigid_body_constraint", None)
    simulation_types = {"PARTICLE_SYSTEM", "FLUID", "CLOTH", "SOFT_BODY", "DYNAMIC_PAINT"}
    return {
        "rigid_body": {
            "type": getattr(rigid_body, "type", None),
            "mass": round(float(getattr(rigid_body, "mass", 0.0)), 5) if rigid_body else 0.0,
            "collision_shape": getattr(rigid_body, "collision_shape", None),
        } if rigid_body else None,
        "rigid_body_constraint": {
            "type": getattr(rigid_body_constraint, "type", None),
            "object1": _safe_name(getattr(rigid_body_constraint, "object1", None)),
            "object2": _safe_name(getattr(rigid_body_constraint, "object2", None)),
        } if rigid_body_constraint else None,
        "simulation_modifiers": [_modifier_summary(modifier) for modifier in obj.modifiers if modifier.type in simulation_types],
        "particle_system_count": len(getattr(obj, "particle_systems", []) or []),
    }


def _point_cache_summary(point_cache):
    if point_cache is None:
        return None
    return {
        "name": getattr(point_cache, "name", ""),
        "index": int(getattr(point_cache, "index", 0)),
        "frame_start": int(getattr(point_cache, "frame_start", 0)),
        "frame_end": int(getattr(point_cache, "frame_end", 0)),
        "frame_step": int(getattr(point_cache, "frame_step", 1)),
        "is_baked": bool(getattr(point_cache, "is_baked", False)),
        "use_disk_cache": bool(getattr(point_cache, "use_disk_cache", False)),
        "use_external": bool(getattr(point_cache, "use_external", False)),
        "filepath": getattr(point_cache, "filepath", ""),
        "info": str(getattr(point_cache, "info", "") or "")[:240],
    }


def _rigid_body_world_summary(scene):
    world = getattr(scene, "rigidbody_world", None)
    if world is None:
        return None
    return {
        "enabled": bool(getattr(world, "enabled", True)),
        "collection": _safe_name(getattr(world, "collection", None)),
        "constraints": _safe_name(getattr(world, "constraints", None)),
        "time_scale": round(float(getattr(world, "time_scale", 1.0)), 5),
        "substeps_per_frame": int(getattr(world, "substeps_per_frame", 0)),
        "solver_iterations": int(getattr(world, "solver_iterations", 0)),
        "point_cache": _point_cache_summary(getattr(world, "point_cache", None)),
    }


def _rigid_body_detail(obj):
    rigid_body = getattr(obj, "rigid_body", None)
    if rigid_body is None:
        return None
    return {
        "type": getattr(rigid_body, "type", None),
        "enabled": bool(getattr(rigid_body, "enabled", True)),
        "kinematic": bool(getattr(rigid_body, "kinematic", False)),
        "mass": round(float(getattr(rigid_body, "mass", 0.0)), 5),
        "collision_shape": getattr(rigid_body, "collision_shape", None),
        "mesh_source": getattr(rigid_body, "mesh_source", None),
        "friction": round(float(getattr(rigid_body, "friction", 0.0)), 5),
        "restitution": round(float(getattr(rigid_body, "restitution", 0.0)), 5),
        "linear_damping": round(float(getattr(rigid_body, "linear_damping", 0.0)), 5),
        "angular_damping": round(float(getattr(rigid_body, "angular_damping", 0.0)), 5),
        "use_margin": bool(getattr(rigid_body, "use_margin", False)),
        "collision_margin": round(float(getattr(rigid_body, "collision_margin", 0.0)), 5),
    }


def _rigid_body_constraint_detail(obj):
    constraint = getattr(obj, "rigid_body_constraint", None)
    if constraint is None:
        return None
    return {
        "type": getattr(constraint, "type", None),
        "enabled": bool(getattr(constraint, "enabled", True)),
        "disable_collisions": bool(getattr(constraint, "disable_collisions", False)),
        "object1": _safe_name(getattr(constraint, "object1", None)),
        "object2": _safe_name(getattr(constraint, "object2", None)),
        "breaking_threshold": round(float(getattr(constraint, "breaking_threshold", 0.0)), 5),
        "use_breaking": bool(getattr(constraint, "use_breaking", False)),
    }


def _simulation_modifier_detail(modifier):
    item = _modifier_summary(modifier)
    point_cache = getattr(modifier, "point_cache", None)
    if point_cache is not None:
        item["point_cache"] = _point_cache_summary(point_cache)
    if modifier.type == "FLUID":
        domain = getattr(modifier, "domain_settings", None)
        flow = getattr(modifier, "flow_settings", None)
        effector = getattr(modifier, "effector_settings", None)
        if domain:
            item["fluid_domain"] = {
                "domain_type": getattr(domain, "domain_type", None),
                "resolution_max": int(getattr(domain, "resolution_max", 0)),
                "cache_type": getattr(domain, "cache_type", None),
                "cache_frame_start": int(getattr(domain, "cache_frame_start", 0)),
                "cache_frame_end": int(getattr(domain, "cache_frame_end", 0)),
                "cache_directory": getattr(domain, "cache_directory", ""),
                "has_cache_baked_data": bool(getattr(domain, "has_cache_baked_data", False)),
                "has_cache_baked_mesh": bool(getattr(domain, "has_cache_baked_mesh", False)),
            }
        if flow:
            item["fluid_flow"] = {
                "flow_type": getattr(flow, "flow_type", None),
                "flow_behavior": getattr(flow, "flow_behavior", None),
                "surface_distance": round(float(getattr(flow, "surface_distance", 0.0)), 5),
            }
        if effector:
            item["fluid_effector"] = {
                "effector_type": getattr(effector, "effector_type", None),
                "surface_distance": round(float(getattr(effector, "surface_distance", 0.0)), 5),
            }
    elif modifier.type == "CLOTH":
        settings = getattr(modifier, "settings", None)
        collision = getattr(modifier, "collision_settings", None)
        if settings:
            item["cloth_settings"] = {
                "quality": int(getattr(settings, "quality", 0)),
                "mass": round(float(getattr(settings, "mass", 0.0)), 5),
                "tension_stiffness": round(float(getattr(settings, "tension_stiffness", 0.0)), 5),
                "compression_stiffness": round(float(getattr(settings, "compression_stiffness", 0.0)), 5),
                "shear_stiffness": round(float(getattr(settings, "shear_stiffness", 0.0)), 5),
            }
        if collision:
            item["cloth_collision"] = {
                "use_collision": bool(getattr(collision, "use_collision", False)),
                "use_self_collision": bool(getattr(collision, "use_self_collision", False)),
                "distance_min": round(float(getattr(collision, "distance_min", 0.0)), 5),
            }
    elif modifier.type == "SOFT_BODY":
        settings = getattr(modifier, "settings", None)
        if settings:
            item["soft_body_settings"] = {
                "mass": round(float(getattr(settings, "mass", 0.0)), 5),
                "friction": round(float(getattr(settings, "friction", 0.0)), 5),
                "speed": round(float(getattr(settings, "speed", 0.0)), 5),
                "use_goal": bool(getattr(settings, "use_goal", False)),
                "use_edges": bool(getattr(settings, "use_edges", False)),
            }
    return item


def _material_animation_summaries(obj):
    result = []
    for slot in obj.material_slots:
        material = slot.material
        if not material:
            continue
        material_item = {
            "material": material.name,
            "material_animation": _animation_owner_summary(material),
            "node_tree_animation": _animation_owner_summary(material.node_tree) if material.use_nodes and material.node_tree else None,
        }
        if material_item["material_animation"]["has_animation_data"] or (
            material_item["node_tree_animation"] and material_item["node_tree_animation"]["has_animation_data"]
        ):
            result.append(material_item)
    return result


def _animation_scene_object_context(obj):
    object_animation = _animation_owner_summary(obj)
    data_animation = _animation_owner_summary(obj.data) if getattr(obj, "data", None) else None
    shape_key_animation = (
        _animation_owner_summary(obj.data.shape_keys)
        if obj.type == "MESH" and obj.data and obj.data.shape_keys
        else None
    )
    rig = _rig_target_summary(obj)
    physics = _physics_summary(obj)
    material_animation = _material_animation_summaries(obj)
    constraints = [{"name": con.name, "type": con.type, "influence": round(float(con.influence), 5)} for con in list(obj.constraints)[:16]]
    drivers = _drivers_summary(obj, max_drivers=12)
    shape_key_count = len(obj.data.shape_keys.key_blocks) if obj.type == "MESH" and obj.data and obj.data.shape_keys else 0
    pose_bone_count = len(getattr(getattr(obj, "pose", None), "bones", []) or []) if obj.type == "ARMATURE" else 0
    rig_control_hints = _pose_bone_control_hints(obj) if obj.type == "ARMATURE" else None
    pose_library_candidates = _pose_library_candidates(obj) if obj.type == "ARMATURE" else []
    z_min, z_max = _bbox_z_range(obj)
    dimensions = _xyz(obj.dimensions)
    tools = {"get_animation_details"}
    cautions = []
    routing_confidence = "medium"
    if rig["likely_rig_driven"] or obj.type == "ARMATURE" or pose_bone_count:
        tools.add("get_rigging_details")
        cautions.append("Inspect rig controls before keyframing mesh/object transforms.")
        routing_confidence = "high" if (rig_control_hints and rig_control_hints["control_candidate_count"]) or any(target["control_candidate_count"] for target in rig["control_targets"]) else "low"
    if obj.type == "ARMATURE" and pose_bone_count and rig_control_hints and not rig_control_hints["control_candidate_count"]:
        cautions.append("No obvious rig control bones were detected; inspect rigging details before posing.")
    if rig["likely_rig_driven"] and not any(target["control_candidate_count"] for target in rig["control_targets"]):
        cautions.append("Rig-driven mesh has no obvious control target hints; inspect the armature before repair.")
    if shape_key_count or (shape_key_animation and shape_key_animation["has_animation_data"]):
        tools.add("get_shape_key_details")
        cautions.append("Shape keys may be the intended animation target for deformation.")
    if physics["rigid_body"] or physics["rigid_body_constraint"] or physics["simulation_modifiers"] or physics["particle_system_count"]:
        tools.add("get_simulation_details")
        cautions.append("Physics or simulation state may need baking/validation before repair.")
    if material_animation:
        tools.add("get_material_node_details")
    if constraints or drivers or object_animation["driver_count"]:
        tools.add("get_rigging_details")
    if object_animation["has_animation_data"] and (object_animation.get("channel_summary") or {}).get("has_pose_bone_keys"):
        tools.add("get_rigging_details")
    if data_animation and data_animation["has_animation_data"]:
        routing_confidence = max(routing_confidence, "medium", key={"low": 0, "medium": 1, "high": 2}.get)
    if rig["likely_rig_driven"]:
        primary_target = "rig_controls"
    elif shape_key_count:
        primary_target = "shape_keys"
    elif material_animation:
        primary_target = "material_or_shader"
    elif obj.type == "CAMERA":
        primary_target = "camera_transform_or_settings"
    elif obj.type == "LIGHT":
        primary_target = "light_data_or_transform"
    else:
        primary_target = "object_transform"
    return {
        "name": obj.name,
        "type": obj.type,
        "data": _safe_name(obj.data),
        "parent": _safe_name(obj.parent),
        "dimensions_blender_units": dimensions,
        "scale": _xyz(obj.scale),
        "world_z_range": [round(z_min, 5), round(z_max, 5)],
        "likely_contact_surface": bool(obj.type == "MESH" and dimensions["z"] <= 0.1 and dimensions["x"] >= 1.0 and dimensions["y"] >= 1.0),
        "object_animation": object_animation,
        "data_animation": data_animation,
        "shape_key_animation": shape_key_animation,
        "shape_key_count": shape_key_count,
        "material_animation": material_animation,
        "constraints": constraints,
        "drivers": drivers,
        "rig": rig,
        "rig_control_hints": rig_control_hints,
        "pose_bone_count": pose_bone_count,
        "pose_library_candidates": pose_library_candidates,
        "physics": physics,
        "suggested_primary_animation_target": primary_target,
        "animation_routing_confidence": routing_confidence,
        "recommended_animation_owner": primary_target,
        "recommended_detail_tools": sorted(tools),
        "cautions": cautions,
    }


def animation_scene_context(context, *, object_names=None, selected_only=False, max_objects=20):
    names = set(object_names or [])
    if names:
        candidates = [obj for obj in (bpy.data.objects.get(name) for name in names) if obj is not None]
        missing = [name for name in names if bpy.data.objects.get(name) is None]
    elif selected_only and context.selected_objects:
        candidates = list(context.selected_objects)
        missing = []
    else:
        candidates = list(context.scene.objects)
        missing = []
    objects = [_animation_scene_object_context(obj) for obj in candidates[: max(1, int(max_objects or 1))]]
    recommended = []
    cautions = []
    for item in objects:
        recommended.extend(item["recommended_detail_tools"])
        cautions.extend({"object": item["name"], "message": caution} for caution in item["cautions"])
    contact_surface_candidates = sorted(
        [
            {
                "name": item["name"],
                "world_z_range": item["world_z_range"],
                "dimensions_blender_units": item["dimensions_blender_units"],
                "suggested_use": "floor_or_contact_surface",
            }
            for item in objects
            if item["likely_contact_surface"]
        ],
        key=lambda item: (
            item["world_z_range"][0],
            -item["dimensions_blender_units"]["x"] * item["dimensions_blender_units"]["y"],
        ),
    )[:12]
    subject_routing = []
    for item in objects:
        target_control_count = sum(target["control_candidate_count"] for target in item["rig"].get("control_targets", []))
        own_control_count = (item["rig_control_hints"] or {}).get("control_candidate_count", 0)
        subject_routing.append(
            {
                "object": item["name"],
                "type": item["type"],
                "suggested_primary_animation_target": item["suggested_primary_animation_target"],
                "recommended_animation_owner": item["recommended_animation_owner"],
                "animation_routing_confidence": item["animation_routing_confidence"],
                "rig_control_candidate_count": own_control_count or target_control_count,
                "pose_library_candidate_count": len(item.get("pose_library_candidates") or []),
                "likely_contact_surface": item["likely_contact_surface"],
                "recommended_detail_tools": item["recommended_detail_tools"],
                "cautions": item["cautions"][:4],
            }
        )
    counted_control_sources = set()
    rig_control_candidate_count = 0
    for item in objects:
        if item["rig_control_hints"] is not None and item["name"] not in counted_control_sources:
            counted_control_sources.add(item["name"])
            rig_control_candidate_count += item["rig_control_hints"]["control_candidate_count"]
        for target in item["rig"].get("control_targets", []):
            if target["name"] in counted_control_sources:
                continue
            counted_control_sources.add(target["name"])
            rig_control_candidate_count += target["control_candidate_count"]
    if context.scene.camera:
        recommended.append("get_render_camera_compositor_details")
    else:
        cautions.append({"object": "", "message": "No active camera is set for shot/framing review."})
    summary = {
        "object_count": len(objects),
        "animated_object_count": sum(1 for item in objects if item["object_animation"]["has_animation_data"]),
        "rig_driven_object_count": sum(1 for item in objects if item["rig"]["likely_rig_driven"] or item["type"] == "ARMATURE"),
        "shape_key_object_count": sum(1 for item in objects if item["shape_key_count"]),
        "physics_object_count": sum(
            1
            for item in objects
            if item["physics"]["rigid_body"] or item["physics"]["simulation_modifiers"] or item["physics"]["particle_system_count"]
        ),
        "pose_library_candidate_count": sum(len(item.get("pose_library_candidates") or []) for item in objects),
        "contact_surface_candidate_count": sum(1 for item in objects if item["likely_contact_surface"]),
        "rig_control_candidate_count": rig_control_candidate_count,
        "active_camera": _safe_name(context.scene.camera),
        "camera_count": len([obj for obj in context.scene.objects if obj.type == "CAMERA"]),
    }
    return {
        "ok": True,
        "message": f"Built animation-aware scene context for {len(objects)} object(s)",
        "summary": summary,
        "objects": objects,
        "subject_routing": subject_routing,
        "contact_surface_candidates": contact_surface_candidates,
        "recommended_next_tools": sorted(set(recommended)),
        "cautions": cautions,
        "missing_object_names": missing,
        "note": "Use recommended detail tools before choosing whether to animate object transforms, rig controls, shape keys, materials, physics, or camera settings.",
    }


def world_model_summary(context):
    scene = context.scene
    object_counts = Counter(obj.type for obj in scene.objects)
    modifier_counts = Counter()
    constraint_counts = Counter()
    geometry_nodes = 0
    drivers = 0
    shape_key_meshes = 0
    simulation_modifiers = 0
    rigid_body_objects = 0
    particle_systems = 0
    curve_objects = 0
    text_objects = 0
    armatures = 0
    for obj in scene.objects:
        if obj.type == "ARMATURE":
            armatures += 1
        if obj.type == "CURVE":
            curve_objects += 1
        if obj.type == "FONT":
            text_objects += 1
        for modifier in obj.modifiers:
            modifier_counts[modifier.type] += 1
            if modifier.type == "NODES":
                geometry_nodes += 1
            if modifier.type in {"PARTICLE_SYSTEM", "FLUID", "CLOTH", "SOFT_BODY", "DYNAMIC_PAINT"}:
                simulation_modifiers += 1
        if getattr(obj, "rigid_body", None) or getattr(obj, "rigid_body_constraint", None):
            rigid_body_objects += 1
        particle_systems += len(getattr(obj, "particle_systems", []) or [])
        for constraint in obj.constraints:
            constraint_counts[constraint.type] += 1
        animation_data = getattr(obj, "animation_data", None)
        drivers += len(getattr(animation_data, "drivers", []) or []) if animation_data else 0
        if obj.type == "MESH" and obj.data and obj.data.shape_keys:
            shape_key_meshes += 1
            drivers += len(getattr(obj.data.shape_keys.animation_data, "drivers", []) or []) if obj.data.shape_keys.animation_data else 0
    material_node_count = 0
    for material in bpy.data.materials:
        if material.use_nodes and material.node_tree:
            material_node_count += len(material.node_tree.nodes)
    compositor_tree = _scene_compositor_tree(scene)
    compositor_nodes = len(compositor_tree.nodes) if compositor_tree else 0
    return {
        "object_counts_by_type": dict(sorted(object_counts.items())),
        "modifier_counts_by_type": dict(sorted(modifier_counts.items())),
        "constraint_counts_by_type": dict(sorted(constraint_counts.items())),
        "geometry_node_modifier_count": geometry_nodes,
        "material_node_count": material_node_count,
        "armature_count": armatures,
        "driver_count": drivers,
        "shape_key_mesh_count": shape_key_meshes,
        "curve_object_count": curve_objects,
        "text_object_count": text_objects,
        "simulation_modifier_count": simulation_modifiers,
        "rigid_body_object_count": rigid_body_objects,
        "particle_system_count": particle_systems,
        "collection_count": len(bpy.data.collections),
        "view_layer_count": len(scene.view_layers),
        "compositor_node_count": compositor_nodes,
        "camera_count": len([obj for obj in scene.objects if obj.type == "CAMERA"]),
        "active_camera": _safe_name(scene.camera),
    }


def geometry_nodes_details(context, *, object_names=None, max_objects=12):
    names = set(object_names or [])
    objects = []
    for obj in context.scene.objects:
        if names and obj.name not in names:
            continue
        modifiers = []
        for modifier in obj.modifiers:
            if modifier.type != "NODES":
                continue
            item = _modifier_summary(modifier)
            item["node_tree"] = _node_tree_summary(getattr(modifier, "node_group", None), max_nodes=28, max_links=60)
            modifiers.append(item)
        if modifiers:
            objects.append({"name": obj.name, "type": obj.type, "geometry_node_modifiers": modifiers})
        if len(objects) >= int(max_objects):
            break
    return {"ok": True, "objects": objects}


def shader_nodes_details(context, *, material_names=None, selected_only=True, max_materials=12):
    names = set(material_names or [])
    materials = []
    if names:
        candidates = [bpy.data.materials.get(name) for name in names]
    elif selected_only:
        seen = set()
        candidates = []
        for obj in context.selected_objects:
            for slot in obj.material_slots:
                material = slot.material
                if material and material.name not in seen:
                    seen.add(material.name)
                    candidates.append(material)
    else:
        candidates = list(bpy.data.materials)
    for material in candidates:
        if material is None:
            continue
        materials.append(
            {
                "name": material.name,
                "use_nodes": bool(material.use_nodes),
                "diffuse_color_rgba": _rgba(material.diffuse_color),
                "node_tree": _node_tree_summary(material.node_tree, max_nodes=32, max_links=64)
                if material.use_nodes
                else None,
                "drivers": _drivers_summary(material),
            }
        )
        if len(materials) >= int(max_materials):
            break
    return {"ok": True, "materials": materials}


def rigging_details(context, *, object_names=None, max_objects=12):
    names = set(object_names or [])
    result = []
    for obj in context.scene.objects:
        if names and obj.name not in names:
            continue
        if obj.type != "ARMATURE" and not obj.constraints and not _drivers_summary(obj):
            continue
        armature = None
        if obj.type == "ARMATURE" and obj.data:
            armature = {
                "data": obj.data.name,
                "bone_count": len(obj.data.bones),
                "bones": [
                    {
                        "name": bone.name,
                        "parent": _safe_name(bone.parent),
                        "use_deform": bool(bone.use_deform),
                        "head_local": _xyz(bone.head_local),
                        "tail_local": _xyz(bone.tail_local),
                    }
                    for bone in list(obj.data.bones)[:48]
                ],
                "pose_bones": [
                    {
                        "name": bone.name,
                        "constraints": [
                            {"name": con.name, "type": con.type, "influence": round(float(con.influence), 5)}
                            for con in list(bone.constraints)[:12]
                        ],
                    }
                    for bone in list(getattr(obj.pose, "bones", []))[:48]
                ]
                if obj.pose
                else [],
                "control_hints": _pose_bone_control_hints(obj, max_candidates=24),
                "pose_library_candidates": _pose_library_candidates(obj, max_actions=12),
            }
        result.append(
            {
                "name": obj.name,
                "type": obj.type,
                "armature": armature,
                "constraints": [
                    {"name": con.name, "type": con.type, "influence": round(float(con.influence), 5)}
                    for con in list(obj.constraints)[:24]
                ],
                "drivers": _drivers_summary(obj),
            }
        )
        if len(result) >= int(max_objects):
            break
    return {"ok": True, "objects": result}


def shape_key_details(context, *, object_names=None, max_objects=12):
    names = set(object_names or [])
    result = []
    for obj in context.scene.objects:
        if names and obj.name not in names:
            continue
        if obj.type != "MESH" or not obj.data or not obj.data.shape_keys:
            continue
        keys = obj.data.shape_keys
        result.append(
            {
                "object": obj.name,
                "mesh": obj.data.name,
                "shape_key_data": keys.name,
                "key_blocks": [
                    {
                        "name": key.name,
                        "value": round(float(key.value), 5),
                        "slider_min": round(float(key.slider_min), 5),
                        "slider_max": round(float(key.slider_max), 5),
                        "relative_key": _safe_name(key.relative_key),
                    }
                    for key in list(keys.key_blocks)[:48]
                ],
                "drivers": _drivers_summary(keys),
            }
        )
        if len(result) >= int(max_objects):
            break
    return {"ok": True, "objects": result}


def curve_text_details(context, *, object_names=None, max_objects=20):
    names = set(object_names or [])
    result = []
    for obj in context.scene.objects:
        if names and obj.name not in names:
            continue
        if obj.type not in {"CURVE", "FONT"} or obj.data is None:
            continue
        data = obj.data
        item = {
            "name": obj.name,
            "type": obj.type,
            "data": data.name,
            "dimensions": getattr(data, "dimensions", None),
            "bevel_depth": round(float(getattr(data, "bevel_depth", 0.0)), 5),
            "resolution_u": int(getattr(data, "resolution_u", 0)),
            "material_slots": [_safe_name(slot.material) for slot in obj.material_slots],
        }
        if obj.type == "CURVE":
            item["splines"] = [
                {
                    "type": spline.type,
                    "point_count": len(getattr(spline, "points", [])),
                    "bezier_point_count": len(getattr(spline, "bezier_points", [])),
                    "use_cyclic_u": bool(getattr(spline, "use_cyclic_u", False)),
                }
                for spline in list(data.splines)[:24]
            ]
        if obj.type == "FONT":
            item["body_preview"] = data.body[:500]
            item["align_x"] = data.align_x
            item["align_y"] = data.align_y
            item["size"] = round(float(data.size), 5)
        result.append(item)
        if len(result) >= int(max_objects):
            break
    return {"ok": True, "objects": result}


def simulation_details(context, *, object_names=None, max_objects=20):
    names = set(object_names or [])
    result = []
    simulation_types = {"PARTICLE_SYSTEM", "FLUID", "CLOTH", "SOFT_BODY", "DYNAMIC_PAINT"}
    scene = context.scene
    scene_frame_range = [int(scene.frame_start), int(scene.frame_end)]
    rigid_body_world = _rigid_body_world_summary(scene)
    summary = {
        "rigid_body_object_count": 0,
        "rigid_body_constraint_count": 0,
        "simulation_modifier_count": 0,
        "particle_system_count": 0,
        "baked_cache_count": 0,
        "unbaked_cache_count": 0,
    }
    recommended_next_tools = set()
    cautions = []
    for obj in context.scene.objects:
        if names and obj.name not in names:
            continue
        modifiers = [
            _simulation_modifier_detail(modifier)
            for modifier in obj.modifiers
            if modifier.type in simulation_types
        ]
        particle_systems = [
            {
                "name": psys.name,
                "settings": _safe_name(psys.settings),
                "count": int(getattr(psys.settings, "count", 0)) if psys.settings else 0,
                "frame_start": round(float(getattr(psys.settings, "frame_start", 0)), 4) if psys.settings else 0,
                "frame_end": round(float(getattr(psys.settings, "frame_end", 0)), 4) if psys.settings else 0,
                "physics_type": getattr(psys.settings, "physics_type", None) if psys.settings else None,
                "emit_from": getattr(psys.settings, "emit_from", None) if psys.settings else None,
                "render_type": getattr(psys.settings, "render_type", None) if psys.settings else None,
                "point_cache": _point_cache_summary(getattr(psys, "point_cache", None)),
            }
            for psys in list(getattr(obj, "particle_systems", []))[:12]
        ]
        rigid_body = _rigid_body_detail(obj)
        rigid_body_constraint = _rigid_body_constraint_detail(obj)
        if not (rigid_body or rigid_body_constraint or modifiers or particle_systems):
            continue
        object_cautions = []
        if rigid_body and rigid_body_world is None:
            object_cautions.append("Rigid body object exists but the scene has no rigid-body world.")
        if rigid_body and rigid_body.get("type") == "ACTIVE" and rigid_body.get("mass", 0.0) <= 0:
            object_cautions.append("Active rigid body has non-positive mass.")
        for modifier in modifiers:
            cache = modifier.get("point_cache")
            if cache:
                if cache.get("is_baked"):
                    summary["baked_cache_count"] += 1
                else:
                    summary["unbaked_cache_count"] += 1
                    object_cautions.append(f"{modifier['name']} cache is not baked.")
                if cache.get("frame_start") and cache.get("frame_end"):
                    if cache["frame_start"] > scene_frame_range[0] or cache["frame_end"] < scene_frame_range[1]:
                        object_cautions.append(f"{modifier['name']} cache range does not cover the scene frame range.")
        for psys in particle_systems:
            cache = psys.get("point_cache")
            if cache:
                if cache.get("is_baked"):
                    summary["baked_cache_count"] += 1
                else:
                    summary["unbaked_cache_count"] += 1
                    object_cautions.append(f"{psys['name']} particle cache is not baked.")
        if modifiers or particle_systems or rigid_body:
            recommended_next_tools.update({"sample_animation_state", "compare_animation_to_brief"})
        if object_cautions:
            cautions.extend({"object": obj.name, "message": message} for message in object_cautions[:6])
        summary["rigid_body_object_count"] += 1 if rigid_body else 0
        summary["rigid_body_constraint_count"] += 1 if rigid_body_constraint else 0
        summary["simulation_modifier_count"] += len(modifiers)
        summary["particle_system_count"] += len(particle_systems)
        result.append(
            {
                "name": obj.name,
                "type": obj.type,
                "rigid_body": rigid_body,
                "rigid_body_constraint": rigid_body_constraint,
                "modifiers": modifiers,
                "particle_systems": particle_systems,
                "cautions": object_cautions[:8],
            }
        )
        if len(result) >= int(max_objects):
            break
    world_cache = rigid_body_world.get("point_cache") if rigid_body_world else None
    if world_cache:
        if world_cache.get("is_baked"):
            summary["baked_cache_count"] += 1
        else:
            summary["unbaked_cache_count"] += 1
            cautions.append({"object": "", "message": "Rigid body world cache is not baked."})
        if world_cache.get("frame_start") and world_cache.get("frame_end"):
            if world_cache["frame_start"] > scene_frame_range[0] or world_cache["frame_end"] < scene_frame_range[1]:
                cautions.append({"object": "", "message": "Rigid body world cache range does not cover the scene frame range."})
    if summary["unbaked_cache_count"]:
        recommended_next_tools.add("compare_animation_to_brief")
    return {
        "ok": True,
        "message": f"Found simulation state on {len(result)} object(s)",
        "scene": {
            "frame_current": int(scene.frame_current),
            "frame_range": scene_frame_range,
            "rigid_body_world": rigid_body_world,
        },
        "summary": summary,
        "objects": result,
        "recommended_next_tools": sorted(recommended_next_tools),
        "cautions": cautions[:24],
        "note": "Read-only simulation inspection; bake or run simulation intentionally before treating physics-heavy validation as final.",
    }


def _collection_tree(collection, *, depth=0, max_depth=4):
    item = {
        "name": collection.name,
        "object_count": len(collection.objects),
        "objects": [obj.name for obj in list(collection.objects)[:30]],
        "children": [],
    }
    if depth < max_depth:
        item["children"] = [_collection_tree(child, depth=depth + 1, max_depth=max_depth) for child in collection.children]
    return item


def collection_layer_details(context, *, max_depth=4):
    scene = context.scene
    return {
        "ok": True,
        "scene_collection": _collection_tree(scene.collection, max_depth=max_depth),
        "collections": [
            {
                "name": collection.name,
                "object_count": len(collection.objects),
                "child_count": len(collection.children),
                "hide_select": bool(getattr(collection, "hide_select", False)),
                "hide_viewport": bool(getattr(collection, "hide_viewport", False)),
                "hide_render": bool(getattr(collection, "hide_render", False)),
            }
            for collection in list(bpy.data.collections)[:80]
        ],
        "view_layers": [
            {
                "name": layer.name,
                "use_pass_combined": bool(getattr(layer, "use_pass_combined", False)),
                "use_pass_z": bool(getattr(layer, "use_pass_z", False)),
                "use_pass_normal": bool(getattr(layer, "use_pass_normal", False)),
            }
            for layer in scene.view_layers
        ],
    }


def render_camera_compositor_details(context):
    scene = context.scene
    camera = scene.camera
    camera_data = camera.data if camera and camera.type == "CAMERA" else None
    compositor_tree = _scene_compositor_tree(scene)
    return {
        "ok": True,
        "render": {
            "engine": scene.render.engine,
            "resolution": [int(scene.render.resolution_x), int(scene.render.resolution_y)],
            "fps": int(scene.render.fps),
            "frame_range": [int(scene.frame_start), int(scene.frame_end)],
            "film_transparent": bool(scene.render.film_transparent),
            "filepath_set": bool(scene.render.filepath),
        },
        "eevee": {
            "available": hasattr(scene, "eevee"),
            "settings": {
                "taa_render_samples": getattr(getattr(scene, "eevee", None), "taa_render_samples", None),
                "use_gtao": getattr(getattr(scene, "eevee", None), "use_gtao", None),
            },
        },
        "camera": {
            "name": _safe_name(camera),
            "location": _xyz(camera.location) if camera else None,
            "rotation_euler_radians": _xyz(camera.rotation_euler) if camera else None,
            "lens": round(float(camera_data.lens), 5) if camera_data else None,
            "sensor_width": round(float(camera_data.sensor_width), 5) if camera_data else None,
            "dof_enabled": bool(camera_data.dof.use_dof) if camera_data else None,
            "dof_focus_object": _safe_name(camera_data.dof.focus_object) if camera_data else None,
        },
        "world": {
            "name": _safe_name(scene.world),
            "color": _rgba(scene.world.color) if scene.world else None,
            "use_nodes": bool(scene.world.use_nodes) if scene.world else False,
            "node_tree": _node_tree_summary(scene.world.node_tree, max_nodes=20, max_links=40)
            if scene.world and scene.world.use_nodes
            else None,
        },
        "compositor": {
            "use_nodes": _scene_uses_compositor(scene),
            "node_tree": _node_tree_summary(compositor_tree, max_nodes=32, max_links=64),
        },
    }


def register():
    pass


def unregister():
    pass
