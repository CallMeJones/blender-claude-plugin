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


def _animation_owner_summary(data_block):
    animation_data = getattr(data_block, "animation_data", None)
    if animation_data is None:
        return {"has_animation_data": False, "action": None, "driver_count": 0, "nla_track_count": 0}
    action = animation_data.action
    drivers = list(getattr(animation_data, "drivers", []) or [])
    nla_tracks = list(getattr(animation_data, "nla_tracks", []) or [])
    return {
        "has_animation_data": True,
        "action": _safe_name(action),
        "fcurve_count": len(_iter_action_fcurves(action)),
        "driver_count": len(drivers),
        "nla_track_count": len(nla_tracks),
        "nla_tracks": [{"name": track.name, "strip_count": len(getattr(track, "strips", []) or [])} for track in nla_tracks[:8]],
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
                "custom_shape": _safe_name(getattr(pose_bone, "custom_shape", None)),
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
    z_min, z_max = _bbox_z_range(obj)
    dimensions = _xyz(obj.dimensions)
    tools = {"get_animation_details"}
    cautions = []
    if rig["likely_rig_driven"] or obj.type == "ARMATURE" or pose_bone_count:
        tools.add("get_rigging_details")
        cautions.append("Inspect rig controls before keyframing mesh/object transforms.")
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
        "physics": physics,
        "suggested_primary_animation_target": primary_target,
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
                "rig_control_candidate_count": own_control_count or target_control_count,
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
    for obj in context.scene.objects:
        if names and obj.name not in names:
            continue
        modifiers = [
            _modifier_summary(modifier)
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
            }
            for psys in list(getattr(obj, "particle_systems", []))[:12]
        ]
        if modifiers or particle_systems:
            result.append({"name": obj.name, "type": obj.type, "modifiers": modifiers, "particle_systems": particle_systems})
        if len(result) >= int(max_objects):
            break
    return {"ok": True, "objects": result}


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
