"""Reversible live preview transactions for low-risk helper changes."""

from __future__ import annotations

import copy
import math
import time
import uuid

import bpy
from mathutils import Matrix

_current_transaction = None


def _serialize_vector(value):
    return tuple(float(component) for component in value)


def _serialize_matrix(value):
    return tuple(tuple(float(component) for component in row) for row in value)


def _serialize_quaternion(value):
    return tuple(float(component) for component in value)


def _snapshot_id_property_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return copy.deepcopy(value)
    except Exception:
        try:
            return list(value)
        except Exception:
            return value


def _set_sequence(target, value):
    for index in range(min(len(target), len(value))):
        target[index] = value[index]


def _set_vector(target, value):
    target[0] = value[0]
    target[1] = value[1]
    target[2] = value[2]


def _coerce_vector(value, fallback):
    if value is None:
        return tuple(float(component) for component in fallback)
    result = list(value)[:3]
    while len(result) < 3:
        result.append(fallback[len(result)])
    return tuple(float(component) for component in result)


def _snapshot_kind(before):
    if before.get("created"):
        return f"created_{before.get('kind', 'datablock')}"
    if before.get("kind"):
        return str(before["kind"])
    if before.get("object_name") and "location" in before:
        return "object_transform"
    if before.get("object_name") and "materials" in before:
        return "object_material_slots"
    if before.get("object_name") and "collections" in before:
        return "object_collections"
    if before.get("kind") == "object_parent":
        return "object_parent"
    if before.get("material_name") and "diffuse_color" in before:
        return "material_diffuse"
    if before.get("scene_name") and "camera_name" in before:
        return "scene_camera"
    if before.get("scene_name") and "frame_start" in before:
        return "scene_timeline"
    if before.get("object_name") and "had_animation_data" in before:
        return "object_animation"
    return "unknown"


def transaction_manifest(transaction=None):
    """Return a compact manifest of rollback coverage for UI/logging."""

    transaction = transaction or current_transaction()
    if not transaction:
        return {
            "transaction_id": "",
            "status": "none",
            "applied_step_count": 0,
            "snapshot_count": 0,
            "created": {},
            "modified": {},
            "rollback_scopes": [],
            "changed_data_blocks": [],
        }

    created = {}
    modified = {}
    scopes = set()
    for before in transaction.get("before_state", {}).values():
        kind = _snapshot_kind(before)
        scopes.add(kind)
        name = (
            before.get("name")
            or before.get("object_name")
            or before.get("material_name")
            or before.get("mesh_name")
            or before.get("scene_name")
            or before.get("world_name")
            or before.get("camera_name")
            or "unnamed"
        )
        bucket = created if before.get("created") else modified
        bucket.setdefault(kind, [])
        if name not in bucket[kind]:
            bucket[kind].append(name)

    return {
        "transaction_id": transaction.get("id", ""),
        "status": transaction.get("status", "unknown"),
        "user_request": transaction.get("user_request", ""),
        "applied_step_count": len(transaction.get("applied_steps", [])),
        "snapshot_count": len(transaction.get("before_state", {})),
        "created": created,
        "modified": modified,
        "rollback_scopes": sorted(scopes),
        "changed_data_blocks": sorted(set(transaction.get("changed_data_blocks", []))),
    }


def _count_manifest_items(items):
    return sum(len(values) for values in (items or {}).values())


def _preview_manifest_summary(manifest=None, *, warnings=None):
    manifest = manifest or transaction_manifest()
    status = manifest.get("status", "unknown")
    if status == "none":
        return "No preview transaction"
    scopes = ", ".join((manifest.get("rollback_scopes") or [])[:8]) or "none"
    changed = ", ".join((manifest.get("changed_data_blocks") or [])[:8]) or "none"
    summary = (
        f"{status}: {manifest.get('applied_step_count', 0)} step(s), "
        f"{manifest.get('snapshot_count', 0)} rollback snapshot(s), "
        f"{_count_manifest_items(manifest.get('created'))} created, "
        f"{_count_manifest_items(manifest.get('modified'))} modified. "
        f"Scopes: {scopes}. Changed: {changed}."
    )
    if warnings:
        summary += f" Rollback warnings: {len(warnings)}."
    return summary[:1200]


def _rollback_warning_summary(warnings):
    warnings = [str(warning) for warning in (warnings or []) if str(warning)]
    if not warnings:
        return ""
    lines = [f"- {warning}" for warning in warnings[:6]]
    if len(warnings) > len(lines):
        lines.append(f"- ... {len(warnings) - len(lines)} more")
    return "\n".join(lines)[:1200]


def _clear_pending_preview_state(state):
    state.pending_preview = False
    state.pending_preview_label = ""
    state.pending_preview_summary = ""
    state.pending_preview_warnings = ""


def _socket_by_saved_name(sockets, saved):
    identifier = saved.get("identifier")
    name = saved.get("name")
    if identifier and sockets.get(identifier):
        return sockets.get(identifier)
    if name and sockets.get(name):
        return sockets.get(name)
    return None


def _restore_node_tree_links(material, before):
    if not material.use_nodes or not material.node_tree:
        return []
    warnings = []
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    original_names = set(before.get("node_names") or [])
    for link in list(links):
        links.remove(link)
    for node in list(nodes):
        if node.name not in original_names:
            nodes.remove(node)
    for saved in before.get("links", []):
        from_node = nodes.get(saved.get("from_node", ""))
        to_node = nodes.get(saved.get("to_node", ""))
        if not from_node or not to_node:
            warnings.append(f"Skipped missing node link {saved}")
            continue
        from_socket = _socket_by_saved_name(from_node.outputs, saved.get("from_socket", {}))
        to_socket = _socket_by_saved_name(to_node.inputs, saved.get("to_socket", {}))
        if not from_socket or not to_socket:
            warnings.append(f"Skipped missing socket link {saved}")
            continue
        try:
            links.new(from_socket, to_socket)
        except Exception as exc:
            warnings.append(f"Could not restore material link: {type(exc).__name__}: {exc}")
    return warnings


def _record_created_id(kind, name):
    transaction = begin()
    key = f"created:{kind}:{name}"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "kind": kind,
            "name": name,
            "created": True,
        }
        transaction["changed_data_blocks"].append(name)


def _record_created_modifier(obj, modifier):
    transaction = begin()
    key = f"object:{obj.name}:modifier:{modifier.name}"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "kind": "object_modifier",
            "object_name": obj.name,
            "name": modifier.name,
            "created": True,
        }
        transaction["changed_data_blocks"].append(obj.name)


def _record_created_constraint(obj, constraint):
    transaction = begin()
    key = f"object:{obj.name}:constraint:{constraint.name}"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "kind": "object_constraint",
            "object_name": obj.name,
            "name": constraint.name,
            "created": True,
        }
        transaction["changed_data_blocks"].append(obj.name)


def _record_selection_state(transaction, context):
    scene = getattr(context, "scene", None)
    view_layer = getattr(context, "view_layer", None)
    if scene is None or view_layer is None:
        return
    key = f"scene:{scene.name}:selection"
    if key in transaction["before_state"]:
        return
    selected = []
    for obj in getattr(context, "selected_objects", []) or []:
        if obj and obj.name not in selected:
            selected.append(obj.name)
    active = getattr(getattr(view_layer, "objects", None), "active", None)
    transaction["before_state"][key] = {
        "kind": "selection_state",
        "scene_name": scene.name,
        "selected_object_names": selected,
        "active_object_name": active.name if active else None,
    }
    transaction["changed_data_blocks"].append(scene.name)


def _view_layer_object(view_layer, name):
    if not name or view_layer is None:
        return None
    objects = getattr(view_layer, "objects", None)
    if objects is not None and hasattr(objects, "get"):
        return objects.get(name)
    return bpy.data.objects.get(name)


def _restore_selection_state(context, before, warnings):
    view_layer = getattr(context, "view_layer", None)
    if view_layer is None:
        warnings.append("Could not restore selection: missing view layer")
        return
    try:
        for obj in list(getattr(view_layer, "objects", [])):
            if obj:
                obj.select_set(False)
        for name in before.get("selected_object_names", []):
            obj = _view_layer_object(view_layer, name)
            if obj:
                obj.select_set(True)
            else:
                warnings.append(f"Missing selected object for selection restore: {name}")
        active_name = before.get("active_object_name")
        if active_name:
            active = _view_layer_object(view_layer, active_name)
            if active:
                view_layer.objects.active = active
            else:
                warnings.append(f"Missing active object for selection restore: {active_name}")
        else:
            view_layer.objects.active = None
    except Exception as exc:
        warnings.append(f"Could not restore selection: {type(exc).__name__}: {exc}")


def _mark_pending(context, label):
    scene = getattr(context, "scene", None)
    if scene and hasattr(scene, "claude_blender"):
        manifest = transaction_manifest()
        scene.claude_blender.pending_preview = True
        scene.claude_blender.pending_preview_label = label
        scene.claude_blender.pending_preview_summary = _preview_manifest_summary(manifest)
        scene.claude_blender.pending_preview_warnings = ""
        scene.claude_blender.status = label


def current_transaction():
    return _current_transaction


def begin(user_request="", context=None):
    global _current_transaction
    context = context or bpy.context
    if _current_transaction and _current_transaction["status"] == "pending":
        _record_selection_state(_current_transaction, context)
        return _current_transaction
    _current_transaction = {
        "id": str(uuid.uuid4()),
        "user_request": user_request,
        "started_at": time.time(),
        "changed_data_blocks": [],
        "before_state": {},
        "applied_steps": [],
        "status": "pending",
    }
    _record_selection_state(_current_transaction, context)
    return _current_transaction


def _record_object_transform(obj):
    transaction = begin()
    key = f"object:{obj.name}:transform"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "object_name": obj.name,
            "location": _serialize_vector(obj.location),
            "rotation_euler": _serialize_vector(obj.rotation_euler),
            "scale": _serialize_vector(obj.scale),
        }
        transaction["changed_data_blocks"].append(obj.name)


def _record_pose_bone_transform(armature, pose_bone):
    transaction = begin()
    key = f"pose_bone:{armature.name}:{pose_bone.name}:transform"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "kind": "pose_bone_transform",
            "armature_name": armature.name,
            "bone_name": pose_bone.name,
            "location": _serialize_vector(pose_bone.location),
            "rotation_mode": pose_bone.rotation_mode,
            "rotation_euler": _serialize_vector(pose_bone.rotation_euler),
            "rotation_quaternion": _serialize_quaternion(pose_bone.rotation_quaternion),
            "rotation_axis_angle": _serialize_quaternion(pose_bone.rotation_axis_angle),
            "scale": _serialize_vector(pose_bone.scale),
        }
        transaction["changed_data_blocks"].append(f"{armature.name}:{pose_bone.name}")


def _record_id_property(owner_kind, owner_name, property_name, *, armature_name=""):
    transaction = begin()
    key = f"id_property:{owner_kind}:{armature_name}:{owner_name}:{property_name}"
    if key in transaction["before_state"]:
        return
    owner = None
    if owner_kind == "object":
        owner = bpy.data.objects.get(owner_name)
    elif owner_kind == "armature_data":
        owner = bpy.data.armatures.get(owner_name)
    elif owner_kind == "pose_bone":
        armature = bpy.data.objects.get(armature_name)
        owner = armature.pose.bones.get(owner_name) if armature and armature.pose else None
    if owner is None:
        return
    exists = property_name in owner
    transaction["before_state"][key] = {
        "kind": "id_property",
        "owner_kind": owner_kind,
        "owner_name": owner_name,
        "armature_name": armature_name,
        "property_name": property_name,
        "exists": bool(exists),
        "value": _snapshot_id_property_value(owner.get(property_name)) if exists else None,
    }
    label = f"{armature_name}:{owner_name}" if armature_name else owner_name
    transaction["changed_data_blocks"].append(label)


def _record_object_visibility(obj):
    transaction = begin()
    key = f"object:{obj.name}:visibility"
    if key not in transaction["before_state"]:
        try:
            hide_get = bool(obj.hide_get())
        except Exception:
            hide_get = False
        transaction["before_state"][key] = {
            "kind": "object_visibility",
            "object_name": obj.name,
            "hide_get": hide_get,
            "hide_viewport": bool(getattr(obj, "hide_viewport", False)),
            "hide_render": bool(getattr(obj, "hide_render", False)),
            "hide_select": bool(getattr(obj, "hide_select", False)),
        }
        transaction["changed_data_blocks"].append(obj.name)


def _record_object_display(obj):
    transaction = begin()
    key = f"object:{obj.name}:display"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "kind": "object_display",
            "object_name": obj.name,
            "display_type": getattr(obj, "display_type", None),
            "show_name": getattr(obj, "show_name", None),
            "show_wire": getattr(obj, "show_wire", None),
            "show_in_front": getattr(obj, "show_in_front", None),
            "color": _serialize_vector(getattr(obj, "color", (1.0, 1.0, 1.0, 1.0))),
            "empty_display_type": getattr(obj, "empty_display_type", None),
            "empty_display_size": getattr(obj, "empty_display_size", None),
        }
        transaction["changed_data_blocks"].append(obj.name)


def _record_object_materials(obj):
    transaction = begin()
    key = f"object:{obj.name}:materials"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "object_name": obj.name,
            "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
        }
        transaction["changed_data_blocks"].append(obj.name)


def _record_object_collections(obj):
    transaction = begin()
    key = f"object:{obj.name}:collections"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "object_name": obj.name,
            "collections": [collection.name for collection in obj.users_collection],
        }
        transaction["changed_data_blocks"].append(obj.name)


def _record_object_parent(obj):
    transaction = begin()
    key = f"object:{obj.name}:parent"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "kind": "object_parent",
            "object_name": obj.name,
            "parent_name": obj.parent.name if obj.parent else None,
            "matrix_parent_inverse": _serialize_matrix(obj.matrix_parent_inverse),
            "matrix_world": _serialize_matrix(obj.matrix_world),
        }
        transaction["changed_data_blocks"].append(obj.name)


def _record_material(material):
    transaction = begin()
    key = f"material:{material.name}:diffuse"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "material_name": material.name,
            "diffuse_color": tuple(float(component) for component in material.diffuse_color),
        }
        transaction["changed_data_blocks"].append(material.name)


def _record_scene_camera(scene):
    transaction = begin()
    key = f"scene:{scene.name}:camera"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "scene_name": scene.name,
            "camera_name": scene.camera.name if scene.camera else None,
        }


def _record_scene_timeline(scene):
    transaction = begin()
    key = f"scene:{scene.name}:timeline"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "scene_name": scene.name,
            "frame_start": int(scene.frame_start),
            "frame_end": int(scene.frame_end),
            "frame_current": int(scene.frame_current),
            "fps": int(scene.render.fps),
        }


def _record_scene_playback(scene):
    transaction = begin()
    key = f"scene:{scene.name}:playback"
    if key not in transaction["before_state"]:
        transaction["before_state"][key] = {
            "kind": "scene_playback",
            "scene_name": scene.name,
            "use_preview_range": bool(scene.use_preview_range),
            "frame_preview_start": int(scene.frame_preview_start),
            "frame_preview_end": int(scene.frame_preview_end),
            "frame_current": int(scene.frame_current),
        }


def _record_object_animation(obj):
    transaction = begin()
    key = f"object:{obj.name}:animation"
    if key not in transaction["before_state"]:
        animation_data = obj.animation_data
        action = animation_data.action if animation_data else None
        transaction["before_state"][key] = {
            "object_name": obj.name,
            "had_animation_data": animation_data is not None,
            "action_name": action.name if action else None,
        }
        transaction["changed_data_blocks"].append(obj.name)


def _record_id_animation(data_block, collection_name):
    if data_block is None or not collection_name:
        return
    transaction = begin()
    key = f"id:{collection_name}:{data_block.name}:animation"
    if key in transaction["before_state"]:
        return
    animation_data = data_block.animation_data
    action = animation_data.action if animation_data else None
    transaction["before_state"][key] = {
        "kind": "id_animation",
        "collection_name": str(collection_name),
        "data_block_name": data_block.name,
        "had_animation_data": animation_data is not None,
        "action_name": action.name if action else None,
    }
    transaction["changed_data_blocks"].append(data_block.name)


def _assign_preview_action(obj):
    _record_object_animation(obj)
    action = bpy.data.actions.new(name=f"{obj.name} Agent Bridge Preview Action")
    obj.animation_data_create().action = action
    _record_created_id("action", action.name)
    return action


def _fcurve_modifier_snapshot(modifier):
    item = {
        "type": modifier.type,
        "mute": bool(getattr(modifier, "mute", False)),
        "show_expanded": bool(getattr(modifier, "show_expanded", False)),
    }
    for attr in ("mode_before", "mode_after", "cycles_before", "cycles_after"):
        if hasattr(modifier, attr):
            value = getattr(modifier, attr)
            item[attr] = int(value) if isinstance(value, int) else value
    return item


def _keyframe_point_snapshot(point):
    return {
        "co": _serialize_vector((point.co.x, point.co.y, 0.0))[:2],
        "interpolation": getattr(point, "interpolation", None),
        "easing": getattr(point, "easing", None),
        "handle_left_type": getattr(point, "handle_left_type", None),
        "handle_right_type": getattr(point, "handle_right_type", None),
        "handle_left": _serialize_vector((point.handle_left.x, point.handle_left.y, 0.0))[:2],
        "handle_right": _serialize_vector((point.handle_right.x, point.handle_right.y, 0.0))[:2],
    }


def _record_action_edit(action):
    if action is None:
        return
    transaction = begin()
    key = f"action:{action.name}:edit"
    if key in transaction["before_state"]:
        return
    fcurves = _iter_action_fcurves(action)
    transaction["before_state"][key] = {
        "kind": "action_edit",
        "action_name": action.name,
        "fcurves": [
            {
                "data_path": fcurve.data_path,
                "array_index": int(fcurve.array_index),
                "extrapolation": getattr(fcurve, "extrapolation", None),
                "mute": bool(getattr(fcurve, "mute", False)),
                "keyframes": [_keyframe_point_snapshot(point) for point in fcurve.keyframe_points],
                "modifiers": [_fcurve_modifier_snapshot(modifier) for modifier in list(getattr(fcurve, "modifiers", []) or [])],
            }
            for fcurve in fcurves
        ],
    }
    transaction["changed_data_blocks"].append(action.name)


def _iter_action_fcurves(action):
    fcurves = getattr(action, "fcurves", None)
    if fcurves is not None:
        return list(fcurves)
    result = []
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                result.extend(list(getattr(channelbag, "fcurves", [])))
    return result


def _set_linear_interpolation(action):
    if not action:
        return
    for fcurve in _iter_action_fcurves(action):
        for point in fcurve.keyframe_points:
            point.interpolation = "LINEAR"


def apply_location_delta(context, delta, *, label="Move selected objects"):
    selected = list(context.selected_objects)
    if not selected:
        return {
            "ok": False,
            "message": "No selected objects to move",
        }
    transaction = begin(label, context)
    for obj in selected:
        _record_object_transform(obj)
        obj.location.x += float(delta[0])
        obj.location.y += float(delta[1])
        obj.location.z += float(delta[2])
    transaction["applied_steps"].append(
        {
            "type": "set_transform_delta",
            "label": label,
            "objects": [obj.name for obj in selected],
            "delta": [float(delta[0]), float(delta[1]), float(delta[2])],
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Moved {len(selected)} selected object(s)",
        "transaction_id": transaction["id"],
    }


def set_selected_transform(context, *, location=None, rotation=None, scale=None, label="Set selected transform"):
    selected = list(context.selected_objects)
    if not selected:
        return {"ok": False, "message": "No selected objects to transform"}
    if location is None and rotation is None and scale is None:
        return {"ok": False, "message": "No transform values were provided"}

    transaction = begin(label, context)
    changed = []
    for obj in selected:
        _record_object_transform(obj)
        if location is not None:
            _set_vector(obj.location, _coerce_vector(location, obj.location))
        if rotation is not None:
            _set_vector(obj.rotation_euler, _coerce_vector(rotation, obj.rotation_euler))
        if scale is not None:
            _set_vector(obj.scale, _coerce_vector(scale, obj.scale))
        changed.append(obj.name)

    transaction["applied_steps"].append(
        {
            "type": "set_selected_transform",
            "label": label,
            "objects": changed,
            "location": list(location) if location is not None else None,
            "rotation": list(rotation) if rotation is not None else None,
            "scale": list(scale) if scale is not None else None,
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Set transform on {len(selected)} selected object(s)",
        "transaction_id": transaction["id"],
    }


def create_primitive(
    context,
    *,
    primitive_type,
    name,
    location,
    rotation,
    scale,
    label="Create primitive",
):
    primitive_type = str(primitive_type or "CUBE").upper()
    if primitive_type not in {"CUBE", "UV_SPHERE", "ICO_SPHERE", "CYLINDER", "CONE", "PLANE", "TORUS"}:
        return {"ok": False, "message": f"Unsupported primitive type: {primitive_type}"}

    transaction = begin(label, context)
    loc = _coerce_vector(location, (0.0, 0.0, 0.0))
    rot = _coerce_vector(rotation, (0.0, 0.0, 0.0))

    if primitive_type == "CUBE":
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=loc, rotation=rot)
    elif primitive_type == "UV_SPHERE":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.0, location=loc, rotation=rot)
    elif primitive_type == "ICO_SPHERE":
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0, location=loc, rotation=rot)
    elif primitive_type == "CYLINDER":
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=1.0, depth=2.0, location=loc, rotation=rot)
    elif primitive_type == "CONE":
        bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=1.0, depth=2.0, location=loc, rotation=rot)
    elif primitive_type == "PLANE":
        bpy.ops.mesh.primitive_plane_add(size=2.0, location=loc, rotation=rot)
    elif primitive_type == "TORUS":
        bpy.ops.mesh.primitive_torus_add(major_radius=0.75, minor_radius=0.25, location=loc, rotation=rot)

    obj = context.object
    if obj is None:
        return {"ok": False, "message": "Primitive was not created"}
    if name:
        obj.name = str(name)
        if obj.data:
            obj.data.name = f"{obj.name} Mesh"
    obj.scale = _coerce_vector(scale, (1.0, 1.0, 1.0))
    _record_created_id("object", obj.name)
    if obj.data:
        _record_created_id("mesh", obj.data.name)

    transaction["applied_steps"].append(
        {
            "type": "create_primitive",
            "label": label,
            "object": obj.name,
            "primitive_type": primitive_type,
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Created {primitive_type} object {obj.name}",
        "object": obj.name,
        "transaction_id": transaction["id"],
    }


def assign_material_to_selected(context, *, name, color, label="Assign material"):
    selected = [obj for obj in context.selected_objects if obj.type == "MESH"]
    if not selected:
        return {"ok": False, "message": "No selected mesh objects for material assignment"}

    transaction = begin(label, context)
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
        _record_created_id("material", material.name)
    else:
        _record_material(material)
    material.diffuse_color = (
        float(color[0]),
        float(color[1]),
        float(color[2]),
        float(color[3]) if len(color) > 3 else 1.0,
    )
    for obj in selected:
        _record_object_materials(obj)
        if obj.material_slots:
            obj.material_slots[0].material = material
        else:
            obj.data.materials.append(material)
    transaction["applied_steps"].append(
        {
            "type": "assign_material",
            "label": label,
            "objects": [obj.name for obj in selected],
            "material": material.name,
            "color": list(material.diffuse_color),
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Assigned material {material.name} to {len(selected)} mesh object(s)",
        "transaction_id": transaction["id"],
    }


def assign_emission_material_to_selected(context, *, name, color, strength, label="Assign emission material"):
    selected = [obj for obj in context.selected_objects if obj.type == "MESH"]
    if not selected:
        return {"ok": False, "message": "No selected mesh objects for emission material assignment"}

    transaction = begin(label, context)
    material = bpy.data.materials.new(name=name or "Agent Bridge Emission Material")
    _record_created_id("material", material.name)
    material.diffuse_color = (
        float(color[0]),
        float(color[1]),
        float(color[2]),
        float(color[3]) if len(color) > 3 else 1.0,
    )
    material.use_nodes = True
    nodes = material.node_tree.nodes
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (260, 0)
    emission = nodes.new(type="ShaderNodeEmission")
    emission.location = (0, 0)
    emission.inputs["Color"].default_value = material.diffuse_color
    emission.inputs["Strength"].default_value = max(0.0, float(strength))
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])

    for obj in selected:
        _record_object_materials(obj)
        if obj.material_slots:
            obj.material_slots[0].material = material
        else:
            obj.data.materials.append(material)
    transaction["applied_steps"].append(
        {
            "type": "assign_emission_material",
            "label": label,
            "objects": [obj.name for obj in selected],
            "material": material.name,
            "strength": float(strength),
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Assigned emission material {material.name} to {len(selected)} mesh object(s)",
        "transaction_id": transaction["id"],
    }


def create_collection(context, *, name, label="Create collection"):
    name = str(name or "Agent Bridge Collection")
    transaction = begin(label, context)
    collection = bpy.data.collections.get(name)
    created = collection is None
    if collection is None:
        collection = bpy.data.collections.new(name)
        context.scene.collection.children.link(collection)
        _record_created_id("collection", collection.name)
    transaction["applied_steps"].append(
        {
            "type": "create_collection",
            "label": label,
            "collection": collection.name,
            "created": created,
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {
        "ok": True,
        "message": f"{'Created' if created else 'Found'} collection {collection.name}",
        "collection": collection.name,
        "transaction_id": transaction["id"],
    }


def link_selected_to_collection(context, *, collection_name, label="Link selected to collection"):
    selected = list(context.selected_objects)
    if not selected:
        return {"ok": False, "message": "No selected objects to link to a collection"}
    transaction = begin(label, context)
    collection = bpy.data.collections.get(collection_name)
    created = collection is None
    if collection is None:
        collection = bpy.data.collections.new(collection_name or "Agent Bridge Collection")
        context.scene.collection.children.link(collection)
        _record_created_id("collection", collection.name)
    linked = []
    for obj in selected:
        _record_object_collections(obj)
        if collection.objects.get(obj.name) is None:
            collection.objects.link(obj)
        linked.append(obj.name)
    transaction["applied_steps"].append(
        {
            "type": "link_selected_to_collection",
            "label": label,
            "collection": collection.name,
            "objects": linked,
            "collection_created": created,
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Linked {len(linked)} selected object(s) to {collection.name}",
        "collection": collection.name,
        "transaction_id": transaction["id"],
    }


def add_modifier_to_selected(
    context,
    *,
    modifier_type,
    name,
    amount=0.1,
    segments=2,
    levels=1,
    count=3,
    relative_offset=(1.2, 0.0, 0.0),
    label="Add modifier",
):
    modifier_type = str(modifier_type or "").upper()
    if modifier_type not in {"BEVEL", "SUBSURF", "SOLIDIFY", "ARRAY"}:
        return {"ok": False, "message": f"Unsupported modifier type: {modifier_type}"}
    selected = [obj for obj in context.selected_objects if obj.type == "MESH"]
    if not selected:
        return {"ok": False, "message": "No selected mesh objects for modifier"}

    transaction = begin(label, context)
    changed = []
    for obj in selected:
        modifier = obj.modifiers.new(name=name or f"Agent Bridge {modifier_type.title()}", type=modifier_type)
        _record_created_modifier(obj, modifier)
        if modifier_type == "BEVEL":
            modifier.width = max(0.0, float(amount))
            modifier.segments = max(1, int(segments))
        elif modifier_type == "SUBSURF":
            modifier.levels = max(0, int(levels))
            modifier.render_levels = max(0, int(levels))
        elif modifier_type == "SOLIDIFY":
            modifier.thickness = float(amount)
        elif modifier_type == "ARRAY":
            modifier.count = max(1, int(count))
            modifier.relative_offset_displace = _coerce_vector(relative_offset, (1.2, 0.0, 0.0))
        changed.append(obj.name)

    transaction["applied_steps"].append(
        {
            "type": "add_modifier",
            "label": label,
            "modifier_type": modifier_type,
            "objects": changed,
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added {modifier_type} modifier to {len(changed)} mesh object(s)",
        "transaction_id": transaction["id"],
    }


def add_track_to_constraint(
    context,
    *,
    target_name,
    name="Agent Bridge Track To",
    track_axis="TRACK_NEGATIVE_Z",
    up_axis="UP_Y",
    influence=1.0,
    label="Add Track To constraint",
):
    target = bpy.data.objects.get(str(target_name or ""))
    if target is None:
        return {"ok": False, "message": f"Target object not found: {target_name}"}
    selected = [obj for obj in context.selected_objects if obj.name != target.name]
    if not selected:
        return {"ok": False, "message": "Select at least one constrained object other than the target"}
    valid_track = {"TRACK_X", "TRACK_Y", "TRACK_Z", "TRACK_NEGATIVE_X", "TRACK_NEGATIVE_Y", "TRACK_NEGATIVE_Z"}
    valid_up = {"UP_X", "UP_Y", "UP_Z"}
    track_axis = track_axis if track_axis in valid_track else "TRACK_NEGATIVE_Z"
    up_axis = up_axis if up_axis in valid_up else "UP_Y"

    transaction = begin(label, context)
    changed = []
    for obj in selected:
        constraint = obj.constraints.new(type="TRACK_TO")
        constraint.name = name or "Agent Bridge Track To"
        constraint.target = target
        constraint.track_axis = track_axis
        constraint.up_axis = up_axis
        constraint.influence = max(0.0, min(1.0, float(influence)))
        _record_created_constraint(obj, constraint)
        changed.append(obj.name)
    transaction["applied_steps"].append(
        {
            "type": "add_track_to_constraint",
            "label": label,
            "target": target.name,
            "objects": changed,
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added Track To constraint to {len(changed)} object(s)",
        "transaction_id": transaction["id"],
    }


def add_light(context, *, light_type, name, location, energy, color, label="Add light"):
    transaction = begin(label, context)
    data = bpy.data.lights.new(name=name, type=light_type)
    data.energy = float(energy)
    data.color = (float(color[0]), float(color[1]), float(color[2]))
    obj = bpy.data.objects.new(name=name, object_data=data)
    obj.location = (float(location[0]), float(location[1]), float(location[2]))
    context.scene.collection.objects.link(obj)
    _record_created_id("object", obj.name)
    _record_created_id("light", data.name)
    transaction["applied_steps"].append(
        {
            "type": "add_light",
            "label": label,
            "object": obj.name,
            "light_type": light_type,
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {"ok": True, "message": f"Added {light_type} light {obj.name}", "transaction_id": transaction["id"]}


def add_camera(context, *, name, location, rotation, lens, label="Add camera"):
    transaction = begin(label, context)
    _record_scene_camera(context.scene)
    data = bpy.data.cameras.new(name=name)
    data.lens = float(lens)
    obj = bpy.data.objects.new(name=name, object_data=data)
    obj.location = (float(location[0]), float(location[1]), float(location[2]))
    obj.rotation_euler = (float(rotation[0]), float(rotation[1]), float(rotation[2]))
    context.scene.collection.objects.link(obj)
    context.scene.camera = obj
    _record_created_id("object", obj.name)
    _record_created_id("camera", data.name)
    transaction["applied_steps"].append(
        {
            "type": "add_camera",
            "label": label,
            "object": obj.name,
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {"ok": True, "message": f"Added camera {obj.name}", "transaction_id": transaction["id"]}


def set_scene_frame_range(context, *, frame_start, frame_end, current_frame=None, fps=None, label="Set timeline"):
    frame_start = int(frame_start)
    frame_end = int(frame_end)
    if frame_start > frame_end:
        return {"ok": False, "message": "frame_start must be less than or equal to frame_end"}
    transaction = begin(label, context)
    scene = context.scene
    _record_scene_timeline(scene)
    scene.frame_start = frame_start
    scene.frame_end = frame_end
    if current_frame is not None:
        scene.frame_set(int(current_frame))
    if fps is not None:
        scene.render.fps = max(1, int(fps))
    transaction["applied_steps"].append(
        {
            "type": "set_scene_frame_range",
            "label": label,
            "frame_start": scene.frame_start,
            "frame_end": scene.frame_end,
            "frame_current": scene.frame_current,
            "fps": scene.render.fps,
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Set timeline to frames {scene.frame_start}-{scene.frame_end}",
        "transaction_id": transaction["id"],
    }


def set_active_camera(context, *, camera_name, label="Set active camera"):
    camera = bpy.data.objects.get(str(camera_name or ""))
    if camera is None:
        return {"ok": False, "message": f"Camera object not found: {camera_name}"}
    if camera.type != "CAMERA":
        return {"ok": False, "message": f"Object is not a camera: {camera.name}"}
    transaction = begin(label, context)
    _record_scene_camera(context.scene)
    context.scene.camera = camera
    transaction["applied_steps"].append(
        {
            "type": "set_active_camera",
            "label": label,
            "camera": camera.name,
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Set active camera to {camera.name}",
        "camera": camera.name,
        "transaction_id": transaction["id"],
    }


def animate_selected_transform(
    context,
    *,
    frame_start,
    frame_end,
    location_start=None,
    location_end=None,
    rotation_start=None,
    rotation_end=None,
    scale_start=None,
    scale_end=None,
    label="Animate selected transform",
):
    selected = list(context.selected_objects)
    if not selected:
        return {"ok": False, "message": "No selected objects to animate"}
    frame_start = int(frame_start)
    frame_end = int(frame_end)
    if frame_start == frame_end:
        return {"ok": False, "message": "Animation needs two different frames"}
    if frame_start > frame_end:
        frame_start, frame_end = frame_end, frame_start
    animated_paths = []
    if location_start is not None or location_end is not None:
        animated_paths.append("location")
    if rotation_start is not None or rotation_end is not None:
        animated_paths.append("rotation_euler")
    if scale_start is not None or scale_end is not None:
        animated_paths.append("scale")
    if not animated_paths:
        return {"ok": False, "message": "No animated transform values were provided"}

    transaction = begin(label, context)
    scene = context.scene
    _record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)

    for obj in selected:
        _record_object_transform(obj)
        action = _assign_preview_action(obj)

        if "location" in animated_paths:
            start = _coerce_vector(location_start, obj.location)
            end = _coerce_vector(location_end, start)
            _set_vector(obj.location, start)
            obj.keyframe_insert(data_path="location", frame=frame_start)
            _set_vector(obj.location, end)
            obj.keyframe_insert(data_path="location", frame=frame_end)

        if "rotation_euler" in animated_paths:
            start = _coerce_vector(rotation_start, obj.rotation_euler)
            end = _coerce_vector(rotation_end, start)
            _set_vector(obj.rotation_euler, start)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame_start)
            _set_vector(obj.rotation_euler, end)
            obj.keyframe_insert(data_path="rotation_euler", frame=frame_end)

        if "scale" in animated_paths:
            start = _coerce_vector(scale_start, obj.scale)
            end = _coerce_vector(scale_end, start)
            _set_vector(obj.scale, start)
            obj.keyframe_insert(data_path="scale", frame=frame_start)
            _set_vector(obj.scale, end)
            obj.keyframe_insert(data_path="scale", frame=frame_end)

        _set_linear_interpolation(action)

    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "animate_selected_transform",
            "label": label,
            "objects": [obj.name for obj in selected],
            "frame_start": frame_start,
            "frame_end": frame_end,
            "paths": animated_paths,
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Animated {len(selected)} selected object(s) from frame {frame_start} to {frame_end}",
        "transaction_id": transaction["id"],
    }


def create_camera_orbit(
    context,
    *,
    target_name,
    frame_start,
    frame_end,
    radius,
    height,
    name,
    lens=35.0,
    label="Create camera orbit",
):
    target = bpy.data.objects.get(str(target_name)) if target_name else context.active_object
    if target is None:
        return {"ok": False, "message": "Target object not found for camera orbit"}
    frame_start = int(frame_start)
    frame_end = int(frame_end)
    if frame_start == frame_end:
        return {"ok": False, "message": "Camera orbit needs two different frames"}
    if frame_start > frame_end:
        frame_start, frame_end = frame_end, frame_start

    transaction = begin(label, context)
    scene = context.scene
    _record_scene_camera(scene)
    _record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)

    target_empty = bpy.data.objects.new(name=f"{name} Look Target", object_data=None)
    target_empty.empty_display_type = "PLAIN_AXES"
    target_empty.empty_display_size = 0.75
    target_empty.location = _serialize_vector(target.location)
    scene.collection.objects.link(target_empty)
    _record_created_id("object", target_empty.name)

    orbit_root = bpy.data.objects.new(name=f"{name} Orbit Root", object_data=None)
    orbit_root.empty_display_type = "PLAIN_AXES"
    orbit_root.empty_display_size = 1.0
    orbit_root.location = _serialize_vector(target.location)
    scene.collection.objects.link(orbit_root)
    _record_created_id("object", orbit_root.name)

    camera_data = bpy.data.cameras.new(name=name)
    camera_data.lens = float(lens)
    camera = bpy.data.objects.new(name=name, object_data=camera_data)
    camera.parent = orbit_root
    camera.location = (float(radius), 0.0, float(height))
    camera.rotation_euler = (0.0, 0.0, 0.0)
    track = camera.constraints.new(type="TRACK_TO")
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    track.target = target_empty
    scene.collection.objects.link(camera)
    scene.camera = camera
    _record_created_id("object", camera.name)
    _record_created_id("camera", camera_data.name)

    _record_object_animation(orbit_root)
    orbit_root.rotation_euler = (0.0, 0.0, 0.0)
    orbit_root.keyframe_insert(data_path="rotation_euler", frame=frame_start)
    orbit_root.rotation_euler = (0.0, 0.0, math.tau)
    orbit_root.keyframe_insert(data_path="rotation_euler", frame=frame_end)
    if orbit_root.animation_data and orbit_root.animation_data.action:
        _record_created_id("action", orbit_root.animation_data.action.name)
        _set_linear_interpolation(orbit_root.animation_data.action)

    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "create_camera_orbit",
            "label": label,
            "target": target.name,
            "camera": camera.name,
            "frame_start": frame_start,
            "frame_end": frame_end,
        }
    )
    redraw(context)
    _mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Created camera orbit {camera.name} around {target.name}",
        "camera": camera.name,
        "target": target.name,
        "transaction_id": transaction["id"],
    }


def commit(context):
    transaction = current_transaction()
    if not transaction or transaction["status"] != "pending":
        return {"ok": False, "message": "No pending preview transaction"}
    transaction["status"] = "committed"
    manifest = transaction_manifest(transaction)
    summary = _preview_manifest_summary(manifest)
    if hasattr(context.scene, "claude_blender"):
        state = context.scene.claude_blender
        _clear_pending_preview_state(state)
        state.last_preview_summary = summary
        state.last_preview_warnings = ""
    redraw(context)
    return {
        "ok": True,
        "message": "Preview committed",
        "manifest": manifest,
        "manifest_summary": summary,
    }


def revert(context):
    transaction = current_transaction()
    if not transaction or transaction["status"] != "pending":
        return {"ok": False, "message": "No pending preview transaction"}
    rollback_warnings = []
    before_values = list(transaction["before_state"].values())
    timeline_scene_names = {
        before["scene_name"]
        for before in before_values
        if before.get("scene_name") and "frame_start" in before
    }
    for before in before_values:
        if before.get("object_name") and "location" in before:
            obj = bpy.data.objects.get(before["object_name"])
            if obj is None:
                rollback_warnings.append(f"Missing object for transform restore: {before['object_name']}")
                continue
            _set_vector(obj.location, before["location"])
            _set_vector(obj.rotation_euler, before["rotation_euler"])
            _set_vector(obj.scale, before["scale"])
        elif before.get("object_name") and "materials" in before:
            obj = bpy.data.objects.get(before["object_name"])
            if obj is None or obj.type != "MESH":
                rollback_warnings.append(f"Missing mesh object for material restore: {before['object_name']}")
                continue
            obj.data.materials.clear()
            for material_name in before["materials"]:
                if material_name:
                    material = bpy.data.materials.get(material_name)
                    if material:
                        obj.data.materials.append(material)
                    else:
                        rollback_warnings.append(f"Missing material for slot restore: {material_name}")
        elif before.get("object_name") and "collections" in before:
            obj = bpy.data.objects.get(before["object_name"])
            if obj is None:
                rollback_warnings.append(f"Missing object for collection restore: {before['object_name']}")
                continue
            original_names = set(before["collections"])
            for collection_name in original_names:
                collection = bpy.data.collections.get(collection_name)
                if collection and collection.objects.get(obj.name) is None:
                    collection.objects.link(obj)
                elif collection is None:
                    rollback_warnings.append(f"Missing collection for link restore: {collection_name}")
            for collection in list(obj.users_collection):
                if collection.name not in original_names and len(obj.users_collection) > 1:
                    collection.objects.unlink(obj)
        elif before.get("kind") == "object_parent":
            obj = bpy.data.objects.get(before["object_name"])
            if obj is None:
                rollback_warnings.append(f"Missing object for parent restore: {before['object_name']}")
                continue
            obj.parent = bpy.data.objects.get(before["parent_name"]) if before["parent_name"] else None
            obj.matrix_parent_inverse = Matrix(before["matrix_parent_inverse"])
            obj.matrix_world = Matrix(before["matrix_world"])
        elif before.get("kind") == "pose_bone_transform":
            armature = bpy.data.objects.get(before["armature_name"])
            pose_bone = armature.pose.bones.get(before["bone_name"]) if armature and armature.pose else None
            if not pose_bone:
                rollback_warnings.append(
                    f"Missing pose bone for transform restore: {before['armature_name']}:{before['bone_name']}"
                )
                continue
            _set_vector(pose_bone.location, before["location"])
            pose_bone.rotation_mode = before["rotation_mode"]
            _set_vector(pose_bone.rotation_euler, before["rotation_euler"])
            _set_sequence(pose_bone.rotation_quaternion, before.get("rotation_quaternion") or ())
            _set_sequence(pose_bone.rotation_axis_angle, before.get("rotation_axis_angle") or ())
            _set_vector(pose_bone.scale, before["scale"])
        elif before.get("kind") == "id_property":
            owner_kind = before.get("owner_kind")
            owner = None
            if owner_kind == "object":
                owner = bpy.data.objects.get(before["owner_name"])
            elif owner_kind == "armature_data":
                owner = bpy.data.armatures.get(before["owner_name"])
            elif owner_kind == "pose_bone":
                armature = bpy.data.objects.get(before.get("armature_name", ""))
                owner = armature.pose.bones.get(before["owner_name"]) if armature and armature.pose else None
            if owner is None:
                rollback_warnings.append(
                    f"Missing data-block for custom property restore: {owner_kind}:{before.get('owner_name')}"
                )
                continue
            property_name = before.get("property_name")
            if before.get("exists"):
                owner[property_name] = before.get("value")
            elif property_name in owner:
                del owner[property_name]
        elif before.get("kind") == "object_modifier":
            obj = bpy.data.objects.get(before["object_name"])
            if obj:
                modifier = obj.modifiers.get(before["name"])
                if modifier:
                    obj.modifiers.remove(modifier)
        elif before.get("kind") == "object_constraint":
            obj = bpy.data.objects.get(before["object_name"])
            if obj:
                constraint = obj.constraints.get(before["name"])
                if constraint:
                    obj.constraints.remove(constraint)
        elif before.get("kind") == "object_visibility":
            obj = bpy.data.objects.get(before["object_name"])
            if obj:
                obj.hide_viewport = bool(before["hide_viewport"])
                obj.hide_render = bool(before["hide_render"])
                obj.hide_select = bool(before["hide_select"])
                try:
                    obj.hide_set(bool(before["hide_get"]))
                except Exception as exc:
                    rollback_warnings.append(f"Could not restore viewport hide state for {obj.name}: {type(exc).__name__}: {exc}")
            else:
                rollback_warnings.append(f"Missing object for visibility restore: {before['object_name']}")
        elif before.get("kind") == "object_display":
            obj = bpy.data.objects.get(before["object_name"])
            if obj:
                for attr in ("display_type", "show_name", "show_wire", "show_in_front", "empty_display_type", "empty_display_size"):
                    value = before.get(attr)
                    if value is not None and hasattr(obj, attr):
                        setattr(obj, attr, value)
                if before.get("color") is not None and hasattr(obj, "color"):
                    obj.color = before["color"]
            else:
                rollback_warnings.append(f"Missing object for display restore: {before['object_name']}")
        elif before.get("material_name") and "diffuse_color" in before:
            material = bpy.data.materials.get(before["material_name"])
            if material:
                material.diffuse_color = before["diffuse_color"]
        elif before.get("scene_name") and "camera_name" in before:
            scene = bpy.data.scenes.get(before["scene_name"])
            if scene:
                scene.camera = bpy.data.objects.get(before["camera_name"]) if before["camera_name"] else None
        elif before.get("kind") == "scene_render_settings":
            scene = bpy.data.scenes.get(before["scene_name"])
            if scene:
                scene.render.engine = before["engine"]
                scene.render.resolution_x = before["resolution_x"]
                scene.render.resolution_y = before["resolution_y"]
                scene.render.fps = before["fps"]
                scene.frame_start = before["frame_start"]
                scene.frame_end = before["frame_end"]
                scene.render.film_transparent = before["film_transparent"]
                scene.frame_set(before["frame_current"])
        elif before.get("scene_name") and "frame_start" in before:
            scene = bpy.data.scenes.get(before["scene_name"])
            if scene:
                scene.frame_start = before["frame_start"]
                scene.frame_end = before["frame_end"]
                scene.render.fps = before["fps"]
                scene.frame_set(before["frame_current"])
        elif before.get("kind") == "scene_playback":
            scene = bpy.data.scenes.get(before["scene_name"])
            if scene:
                scene.use_preview_range = before["use_preview_range"]
                scene.frame_preview_start = before["frame_preview_start"]
                scene.frame_preview_end = before["frame_preview_end"]
                if before["scene_name"] not in timeline_scene_names:
                    scene.frame_set(before["frame_current"])
        elif before.get("kind") == "scene_world":
            scene = bpy.data.scenes.get(before["scene_name"])
            if scene:
                scene.world = bpy.data.worlds.get(before["world_name"]) if before["world_name"] else None
        elif before.get("kind") == "world_background":
            world = bpy.data.worlds.get(before["world_name"])
            if world:
                world.color = before["color"]
        elif before.get("kind") == "camera_settings":
            camera = bpy.data.cameras.get(before["camera_name"])
            if camera:
                camera.lens = before["lens"]
                camera.sensor_width = before["sensor_width"]
                camera.dof.use_dof = before["use_dof"]
                camera.dof.focus_object = bpy.data.objects.get(before["focus_object"]) if before["focus_object"] else None
                camera.dof.aperture_fstop = before["aperture_fstop"]
        elif before.get("kind") == "selection_state":
            continue
        elif before.get("kind") == "mesh_smoothing":
            mesh = bpy.data.meshes.get(before["mesh_name"])
            if mesh:
                for polygon, use_smooth in zip(mesh.polygons, before["polygon_smooth"]):
                    polygon.use_smooth = bool(use_smooth)
        elif before.get("kind") == "shader_material":
            material = bpy.data.materials.get(before["material_name"])
            if material:
                material.use_nodes = before["use_nodes"]
                material.diffuse_color = before["diffuse_color"]
                if before["blend_method"] is not None and hasattr(material, "blend_method"):
                    material.blend_method = before["blend_method"]
                if before["surface_render_method"] is not None and hasattr(material, "surface_render_method"):
                    material.surface_render_method = before["surface_render_method"]
                if material.use_nodes and material.node_tree:
                    principled = next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
                    if principled:
                        for socket_name, value in before["principled_socket_values"].items():
                            socket = principled.inputs.get(socket_name)
                            if not socket or not hasattr(socket, "default_value"):
                                continue
                            current = socket.default_value
                            if hasattr(current, "__len__") and not isinstance(current, str):
                                for index in range(min(len(current), len(value))):
                                    current[index] = value[index]
                            else:
                                socket.default_value = value
            else:
                rollback_warnings.append(f"Missing material for shader restore: {before['material_name']}")
        elif before.get("kind") == "material_node_tree_animation":
            material = bpy.data.materials.get(before["material_name"])
            node_tree = material.node_tree if material and material.use_nodes else None
            if node_tree:
                if before["had_animation_data"]:
                    animation_data = node_tree.animation_data_create()
                    animation_data.action = bpy.data.actions.get(before["action_name"]) if before["action_name"] else None
                elif node_tree.animation_data:
                    node_tree.animation_data_clear()
        elif before.get("kind") == "light_settings":
            light = bpy.data.lights.get(before["light_data_name"])
            if light:
                light.energy = before["energy"]
                light.color = before["color"]
                if hasattr(light, "shadow_soft_size"):
                    light.shadow_soft_size = before["shadow_soft_size"]
                if hasattr(light, "spot_size"):
                    light.spot_size = before["spot_size"]
                if hasattr(light, "spot_blend"):
                    light.spot_blend = before["spot_blend"]
            else:
                rollback_warnings.append(f"Missing light data for settings restore: {before['light_data_name']}")
        elif before.get("kind") == "light_data_animation":
            light = bpy.data.lights.get(before["light_data_name"])
            if light:
                if before["had_animation_data"]:
                    animation_data = light.animation_data_create()
                    animation_data.action = bpy.data.actions.get(before["action_name"]) if before["action_name"] else None
                elif light.animation_data:
                    light.animation_data_clear()
            else:
                rollback_warnings.append(f"Missing light data for animation restore: {before['light_data_name']}")
        elif before.get("kind") == "action_edit":
            action = bpy.data.actions.get(before["action_name"])
            if action:
                current_fcurves = _iter_action_fcurves(action)
                saved_keys = {
                    (saved["data_path"], int(saved["array_index"]))
                    for saved in before.get("fcurves", [])
                }
                if hasattr(action, "fcurves"):
                    for fcurve in list(current_fcurves):
                        key = (fcurve.data_path, int(fcurve.array_index))
                        if key not in saved_keys:
                            try:
                                action.fcurves.remove(fcurve)
                            except Exception as exc:
                                rollback_warnings.append(f"Could not remove added f-curve during restore: {type(exc).__name__}: {exc}")
                    current_fcurves = _iter_action_fcurves(action)
                for saved in before.get("fcurves", []):
                    fcurve = next(
                        (
                            item
                            for item in current_fcurves
                            if item.data_path == saved["data_path"] and int(item.array_index) == int(saved["array_index"])
                        ),
                        None,
                    )
                    if fcurve is None:
                        if hasattr(action, "fcurves"):
                            try:
                                fcurve = action.fcurves.new(data_path=saved["data_path"], index=int(saved["array_index"]))
                                current_fcurves.append(fcurve)
                            except Exception as exc:
                                rollback_warnings.append(f"Missing f-curve for action restore: {action.name} {saved['data_path']}[{saved['array_index']}]: {type(exc).__name__}: {exc}")
                                continue
                        else:
                            rollback_warnings.append(f"Missing f-curve for action restore: {action.name} {saved['data_path']}[{saved['array_index']}]")
                            continue
                    if saved.get("extrapolation") is not None:
                        fcurve.extrapolation = saved["extrapolation"]
                    fcurve.mute = bool(saved.get("mute", False))
                    while len(fcurve.modifiers) > 0:
                        fcurve.modifiers.remove(fcurve.modifiers[-1])
                    for modifier_state in saved.get("modifiers", []):
                        try:
                            modifier = fcurve.modifiers.new(type=modifier_state["type"])
                        except Exception as exc:
                            rollback_warnings.append(f"Could not restore f-curve modifier: {type(exc).__name__}: {exc}")
                            continue
                        for attr, value in modifier_state.items():
                            if attr == "type" or not hasattr(modifier, attr):
                                continue
                            setattr(modifier, attr, value)
                    saved_points = saved.get("keyframes", [])
                    try:
                        while len(fcurve.keyframe_points) > 0:
                            fcurve.keyframe_points.remove(fcurve.keyframe_points[-1], fast=True)
                    except Exception as exc:
                        rollback_warnings.append(f"Could not clear f-curve keyframes during restore: {action.name} {saved['data_path']}[{saved['array_index']}]: {type(exc).__name__}: {exc}")
                        continue
                    for point_state in saved_points:
                        point = fcurve.keyframe_points.insert(point_state["co"][0], point_state["co"][1], options={"FAST"})
                        if point_state.get("interpolation") is not None:
                            point.interpolation = point_state["interpolation"]
                        if point_state.get("easing") is not None and hasattr(point, "easing"):
                            point.easing = point_state["easing"]
                        if point_state.get("handle_left_type") is not None:
                            point.handle_left_type = point_state["handle_left_type"]
                        if point_state.get("handle_right_type") is not None:
                            point.handle_right_type = point_state["handle_right_type"]
                        point.handle_left = point_state["handle_left"]
                        point.handle_right = point_state["handle_right"]
                    fcurve.update()
            else:
                rollback_warnings.append(f"Missing action for action restore: {before['action_name']}")
        elif before.get("kind") == "id_animation":
            collection = getattr(bpy.data, before["collection_name"], None)
            data_block = collection.get(before["data_block_name"]) if collection and hasattr(collection, "get") else None
            if data_block:
                if before["had_animation_data"]:
                    animation_data = data_block.animation_data_create()
                    animation_data.action = bpy.data.actions.get(before["action_name"]) if before["action_name"] else None
                elif data_block.animation_data:
                    data_block.animation_data_clear()
            else:
                rollback_warnings.append(f"Missing data-block for animation restore: {before['collection_name']}:{before['data_block_name']}")
        elif before.get("kind") == "shape_keys":
            obj = bpy.data.objects.get(before["object_name"])
            if obj is None or obj.type != "MESH" or obj.data is None:
                continue
            keys = obj.data.shape_keys
            if keys:
                original_names = [item["name"] for item in before["key_blocks"]]
                for key in list(keys.key_blocks):
                    if key.name not in original_names:
                        obj.shape_key_remove(key)
                if before["had_shape_keys"]:
                    for item in before["key_blocks"]:
                        key = keys.key_blocks.get(item["name"]) if obj.data.shape_keys else None
                        if key:
                            key.value = item["value"]
                            key.slider_min = item["slider_min"]
                            key.slider_max = item["slider_max"]
                else:
                    for key in list(obj.data.shape_keys.key_blocks) if obj.data.shape_keys else []:
                        obj.shape_key_remove(key)
            keys = obj.data.shape_keys
            if keys:
                if before["had_animation_data"]:
                    animation_data = keys.animation_data_create()
                    animation_data.action = bpy.data.actions.get(before["action_name"]) if before["action_name"] else None
                elif keys.animation_data:
                    keys.animation_data_clear()
        elif before.get("object_name") and "had_animation_data" in before:
            obj = bpy.data.objects.get(before["object_name"])
            if obj is None:
                continue
            if before["had_animation_data"]:
                animation_data = obj.animation_data_create()
                animation_data.action = bpy.data.actions.get(before["action_name"]) if before["action_name"] else None
            else:
                obj.animation_data_clear()
    for before in list(transaction["before_state"].values()):
        if not before.get("created"):
            continue
        if before.get("kind") == "object":
            obj = bpy.data.objects.get(before["name"])
            if obj:
                bpy.data.objects.remove(obj, do_unlink=True)
        elif before.get("kind") == "material":
            material = bpy.data.materials.get(before["name"])
            if material:
                bpy.data.materials.remove(material, do_unlink=True)
        elif before.get("kind") == "light":
            light = bpy.data.lights.get(before["name"])
            if light and light.users == 0:
                bpy.data.lights.remove(light)
        elif before.get("kind") == "camera":
            camera = bpy.data.cameras.get(before["name"])
            if camera and camera.users == 0:
                bpy.data.cameras.remove(camera)
        elif before.get("kind") == "mesh":
            mesh = bpy.data.meshes.get(before["name"])
            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        elif before.get("kind") == "action":
            action = bpy.data.actions.get(before["name"])
            if action and action.users == 0:
                bpy.data.actions.remove(action)
        elif before.get("kind") == "curve":
            curve = bpy.data.curves.get(before["name"])
            if curve and curve.users == 0:
                bpy.data.curves.remove(curve)
        elif before.get("kind") == "armature":
            armature = bpy.data.armatures.get(before["name"])
            if armature and armature.users == 0:
                bpy.data.armatures.remove(armature)
        elif before.get("kind") == "node_group":
            group = bpy.data.node_groups.get(before["name"])
            if group and group.users == 0:
                bpy.data.node_groups.remove(group)
        elif before.get("kind") == "particle_settings":
            settings = bpy.data.particles.get(before["name"])
            if settings and settings.users == 0:
                bpy.data.particles.remove(settings)
        elif before.get("kind") == "world":
            world = bpy.data.worlds.get(before["name"])
            if world and world.users == 0:
                bpy.data.worlds.remove(world)
        elif before.get("kind") == "collection":
            collection = bpy.data.collections.get(before["name"])
            if collection:
                for parent in list(bpy.data.collections):
                    if parent.children.get(collection.name):
                        parent.children.unlink(collection)
                for scene in bpy.data.scenes:
                    if scene.collection.children.get(collection.name):
                        scene.collection.children.unlink(collection)
                bpy.data.collections.remove(collection)
    for before in list(transaction["before_state"].values()):
        if not before.get("created"):
            continue
        if before.get("kind") == "material":
            material = bpy.data.materials.get(before["name"])
            if material and material.users == 0:
                bpy.data.materials.remove(material)
        elif before.get("kind") == "curve":
            curve = bpy.data.curves.get(before["name"])
            if curve and curve.users == 0:
                bpy.data.curves.remove(curve)
        elif before.get("kind") == "mesh":
            mesh = bpy.data.meshes.get(before["name"])
            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        elif before.get("kind") == "action":
            action = bpy.data.actions.get(before["name"])
            if action and action.users == 0:
                bpy.data.actions.remove(action)
    for before in list(transaction["before_state"].values()):
        if before.get("kind") != "shader_material":
            continue
        material = bpy.data.materials.get(before["material_name"])
        if material:
            rollback_warnings.extend(_restore_node_tree_links(material, before))
    for before in list(transaction["before_state"].values()):
        if before.get("kind") == "selection_state":
            _restore_selection_state(context, before, rollback_warnings)
    transaction["status"] = "reverted"
    transaction["rollback_warnings"] = rollback_warnings
    manifest = transaction_manifest(transaction)
    summary = _preview_manifest_summary(manifest, warnings=rollback_warnings)
    warning_summary = _rollback_warning_summary(rollback_warnings)
    if hasattr(context.scene, "claude_blender"):
        state = context.scene.claude_blender
        _clear_pending_preview_state(state)
        state.last_preview_summary = summary
        state.last_preview_warnings = warning_summary
    redraw(context)
    return {
        "ok": True,
        "message": "Preview reverted",
        "manifest": manifest,
        "manifest_summary": summary,
        "rollback_warnings": rollback_warnings,
        "rollback_warning_summary": warning_summary,
    }


def redraw(context):
    view_layer = getattr(context, "view_layer", None)
    if view_layer:
        view_layer.update()
    screen = getattr(context, "screen", None)
    if screen:
        for area in screen.areas:
            if area.type in {"VIEW_3D", "DOPESHEET_EDITOR", "GRAPH_EDITOR", "TIMELINE", "PROPERTIES"}:
                area.tag_redraw()


def register():
    pass


def unregister():
    global _current_transaction
    _current_transaction = None
