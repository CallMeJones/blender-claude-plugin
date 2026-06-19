"""Safer advanced live-preview helpers for deeper Blender systems."""

from __future__ import annotations

from contextlib import contextmanager
import math

import bpy
from mathutils import Vector

from . import live_preview


KEYFRAME_INTERPOLATIONS = {
    "CONSTANT",
    "LINEAR",
    "BEZIER",
    "SINE",
    "QUAD",
    "CUBIC",
    "QUART",
    "QUINT",
    "EXPO",
    "CIRC",
    "BACK",
    "BOUNCE",
    "ELASTIC",
}

EMPTY_DISPLAY_TYPES = {"PLAIN_AXES", "ARROWS", "SINGLE_ARROW", "CIRCLE", "CUBE", "SPHERE", "CONE", "IMAGE"}
OBJECT_DISPLAY_TYPES = {"TEXTURED", "SOLID", "WIRE", "BOUNDS"}

LIGHTING_PRESETS = {
    "product_softbox": [
        ("Key", (-1.2, -1.4, 1.5), 650.0, 1.15, (1.0, 0.93, 0.84)),
        ("Fill", (1.3, -0.9, 0.8), 180.0, 1.7, (0.78, 0.86, 1.0)),
        ("Rim", (0.0, 1.35, 1.15), 360.0, 0.75, (1.0, 1.0, 0.94)),
    ],
    "dramatic_rim": [
        ("Key", (-1.4, -1.1, 1.1), 430.0, 0.75, (1.0, 0.86, 0.7)),
        ("Rim", (1.15, 1.35, 1.55), 850.0, 0.6, (0.68, 0.82, 1.0)),
        ("Top", (0.0, -0.1, 2.0), 150.0, 1.2, (1.0, 0.96, 0.9)),
    ],
    "gallery_even": [
        ("Left Softbox", (-1.35, -0.55, 1.25), 320.0, 1.45, (1.0, 0.95, 0.9)),
        ("Right Softbox", (1.35, -0.55, 1.25), 320.0, 1.45, (0.9, 0.95, 1.0)),
        ("Top Wash", (0.0, 0.0, 2.0), 220.0, 1.8, (1.0, 1.0, 0.96)),
    ],
}

MATERIAL_PALETTES = {
    "product_neutral": [
        ("Graphite", (0.04, 0.045, 0.05, 1.0)),
        ("Warm Silver", (0.62, 0.6, 0.56, 1.0)),
        ("Porcelain", (0.92, 0.9, 0.84, 1.0)),
        ("Signal Blue", (0.02, 0.24, 0.72, 1.0)),
        ("Safety Amber", (1.0, 0.56, 0.08, 1.0)),
    ],
    "automotive": [
        ("Paint Red", (0.8, 0.02, 0.015, 1.0)),
        ("Deep Blue", (0.02, 0.08, 0.28, 1.0)),
        ("Rubber Black", (0.005, 0.005, 0.006, 1.0)),
        ("Chrome", (0.72, 0.72, 0.68, 1.0)),
        ("Glass Blue", (0.08, 0.35, 0.65, 0.42)),
    ],
    "cinematic": [
        ("Key Warm", (1.0, 0.74, 0.42, 1.0)),
        ("Cool Fill", (0.15, 0.32, 0.82, 1.0)),
        ("Deep Shadow", (0.015, 0.014, 0.02, 1.0)),
        ("Practical Glow", (1.0, 0.85, 0.2, 1.0)),
        ("Muted Skin", (0.72, 0.48, 0.36, 1.0)),
    ],
}

PRODUCT_REFINEMENT_STYLES = {
    "studio": {
        "material": ("Agent Bridge Product Satin White", (0.82, 0.84, 0.8, 1.0)),
        "bevel_factor": 0.018,
        "segments": 3,
    },
    "catalog": {
        "material": ("Agent Bridge Product Catalog Blue", (0.05, 0.22, 0.72, 1.0)),
        "bevel_factor": 0.014,
        "segments": 2,
    },
    "premium": {
        "material": ("Agent Bridge Product Premium Graphite", (0.035, 0.038, 0.042, 1.0)),
        "bevel_factor": 0.02,
        "segments": 4,
    },
}

CHARACTER_PALETTES = {
    "neutral": {
        "skin": ("Agent Bridge Character Skin", (0.72, 0.48, 0.36, 1.0)),
        "hair": ("Agent Bridge Character Hair", (0.09, 0.065, 0.045, 1.0)),
        "eye": ("Agent Bridge Character Eye", (0.02, 0.025, 0.03, 1.0)),
        "accent": ("Agent Bridge Character Accent", (0.18, 0.32, 0.72, 1.0)),
        "guide": ("Agent Bridge Character Guide Lines", (0.04, 0.04, 0.045, 1.0)),
    },
    "toon": {
        "skin": ("Agent Bridge Toon Skin", (0.95, 0.68, 0.48, 1.0)),
        "hair": ("Agent Bridge Toon Hair", (0.03, 0.025, 0.055, 1.0)),
        "eye": ("Agent Bridge Toon Eye", (0.0, 0.0, 0.0, 1.0)),
        "accent": ("Agent Bridge Toon Accent", (0.95, 0.22, 0.16, 1.0)),
        "guide": ("Agent Bridge Toon Guide Lines", (0.02, 0.02, 0.025, 1.0)),
    },
}


def _coerce_vector(value, fallback):
    return live_preview._coerce_vector(value, fallback)


def _coerce_color(value, fallback=(1.0, 1.0, 1.0, 1.0)):
    values = list(value) if value is not None else list(fallback)
    result = values[:4]
    while len(result) < 4:
        result.append(fallback[len(result)])
    return tuple(float(component) for component in result)


def _record_shape_keys(obj):
    transaction = live_preview.begin()
    key = f"object:{obj.name}:shape_keys"
    if key in transaction["before_state"]:
        return
    keys = obj.data.shape_keys if obj.type == "MESH" and obj.data else None
    animation_data = getattr(keys, "animation_data", None) if keys else None
    action = animation_data.action if animation_data else None
    transaction["before_state"][key] = {
        "kind": "shape_keys",
        "object_name": obj.name,
        "had_shape_keys": keys is not None,
        "key_blocks": [
            {
                "name": block.name,
                "value": float(block.value),
                "slider_min": float(block.slider_min),
                "slider_max": float(block.slider_max),
            }
            for block in list(keys.key_blocks)
        ]
        if keys
        else [],
        "had_animation_data": animation_data is not None,
        "action_name": action.name if action else None,
    }
    transaction["changed_data_blocks"].append(obj.name)


def _record_shader_material(material):
    transaction = live_preview.begin()
    key = f"material:{material.name}:shader"
    if key in transaction["before_state"]:
        return
    principled = _find_node(material, "BSDF_PRINCIPLED")
    sockets = {}
    if principled:
        for socket_name in ("Base Color", "Metallic", "Roughness", "Alpha", "Emission Color", "Emission Strength"):
            socket = principled.inputs.get(socket_name)
            if socket and hasattr(socket, "default_value"):
                sockets[socket_name] = _socket_value(socket.default_value)
    node_names = []
    links = []
    if material.use_nodes and material.node_tree:
        node_names = [node.name for node in material.node_tree.nodes]
        links = [
            {
                "from_node": link.from_node.name,
                "from_socket": {
                    "name": link.from_socket.name,
                    "identifier": getattr(link.from_socket, "identifier", link.from_socket.name),
                },
                "to_node": link.to_node.name,
                "to_socket": {
                    "name": link.to_socket.name,
                    "identifier": getattr(link.to_socket, "identifier", link.to_socket.name),
                },
            }
            for link in material.node_tree.links
        ]
    transaction["before_state"][key] = {
        "kind": "shader_material",
        "material_name": material.name,
        "use_nodes": bool(material.use_nodes),
        "diffuse_color": tuple(float(component) for component in material.diffuse_color),
        "blend_method": getattr(material, "blend_method", None),
        "surface_render_method": getattr(material, "surface_render_method", None),
        "principled_socket_values": sockets,
        "node_names": node_names,
        "links": links,
    }
    transaction["changed_data_blocks"].append(material.name)


def _record_scene_render(scene):
    transaction = live_preview.begin()
    key = f"scene:{scene.name}:render_settings"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "scene_render_settings",
        "scene_name": scene.name,
        "engine": scene.render.engine,
        "resolution_x": int(scene.render.resolution_x),
        "resolution_y": int(scene.render.resolution_y),
        "fps": int(scene.render.fps),
        "frame_start": int(scene.frame_start),
        "frame_end": int(scene.frame_end),
        "frame_current": int(scene.frame_current),
        "film_transparent": bool(scene.render.film_transparent),
    }


def _record_world_background(world):
    transaction = live_preview.begin()
    key = f"world:{world.name}:background"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "world_background",
        "world_name": world.name,
        "color": tuple(float(component) for component in world.color),
    }
    transaction["changed_data_blocks"].append(world.name)


def _record_scene_world(scene):
    transaction = live_preview.begin()
    key = f"scene:{scene.name}:world"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "scene_world",
        "scene_name": scene.name,
        "world_name": scene.world.name if scene.world else None,
    }


def _record_camera_settings(camera_obj):
    transaction = live_preview.begin()
    data = camera_obj.data if camera_obj and camera_obj.type == "CAMERA" else None
    if data is None:
        return
    key = f"camera:{data.name}:settings"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "camera_settings",
        "camera_name": data.name,
        "lens": float(data.lens),
        "sensor_width": float(data.sensor_width),
        "use_dof": bool(data.dof.use_dof),
        "focus_object": data.dof.focus_object.name if data.dof.focus_object else None,
        "aperture_fstop": float(data.dof.aperture_fstop),
    }
    transaction["changed_data_blocks"].append(camera_obj.name)


def _record_mesh_smoothing(mesh):
    transaction = live_preview.begin()
    key = f"mesh:{mesh.name}:smoothing"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "mesh_smoothing",
        "mesh_name": mesh.name,
        "polygon_smooth": [bool(poly.use_smooth) for poly in mesh.polygons],
    }
    transaction["changed_data_blocks"].append(mesh.name)


def _socket_value(value):
    if isinstance(value, (int, float, bool, str)) or value is None:
        return value
    try:
        return tuple(float(component) for component in value)
    except TypeError:
        return value


def _set_socket_value(socket, value):
    if not socket or not hasattr(socket, "default_value"):
        return False
    current = socket.default_value
    if hasattr(current, "__len__") and not isinstance(current, str):
        values = list(value)
        for index in range(min(len(current), len(values))):
            current[index] = float(values[index])
    else:
        socket.default_value = value
    return True


def _normalize_frame_range(frame_start, frame_end, label):
    frame_start = int(frame_start)
    frame_end = int(frame_end)
    if frame_start == frame_end:
        return None, None, {"ok": False, "message": f"{label} needs two different frames"}
    if frame_start > frame_end:
        frame_start, frame_end = frame_end, frame_start
    return frame_start, frame_end, None


def _set_action_interpolation(action, interpolation="LINEAR"):
    interpolation = str(interpolation or "LINEAR").upper()
    if interpolation not in KEYFRAME_INTERPOLATIONS:
        interpolation = "LINEAR"
    for fcurve in live_preview._iter_action_fcurves(action):
        for point in fcurve.keyframe_points:
            point.interpolation = interpolation


def _axis_index(axis):
    axis = str(axis or "Z").upper()
    return {"X": 0, "Y": 1, "Z": 2}.get(axis, 2), axis if axis in {"X", "Y", "Z"} else "Z"


def _find_node(material, node_type):
    if not material or not material.use_nodes or not material.node_tree:
        return None
    return next((node for node in material.node_tree.nodes if node.type == node_type), None)


def _ensure_principled_material(material):
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = _find_node(material, "BSDF_PRINCIPLED")
    if principled is None:
        principled = nodes.new(type="ShaderNodeBsdfPrincipled")
        principled.location = (0, 0)
    output = _find_node(material, "OUTPUT_MATERIAL")
    if output is None:
        output = nodes.new(type="ShaderNodeOutputMaterial")
        output.location = (260, 0)
    if principled.outputs and output.inputs.get("Surface") and not output.inputs["Surface"].is_linked:
        links.new(principled.outputs[0], output.inputs["Surface"])
    return principled


def _record_material_node_tree_animation(material):
    node_tree = material.node_tree if material and material.use_nodes else None
    if node_tree is None:
        return
    transaction = live_preview.begin()
    key = f"material:{material.name}:node_tree_animation"
    if key in transaction["before_state"]:
        return
    animation_data = node_tree.animation_data
    action = animation_data.action if animation_data else None
    transaction["before_state"][key] = {
        "kind": "material_node_tree_animation",
        "material_name": material.name,
        "had_animation_data": animation_data is not None,
        "action_name": action.name if action else None,
    }
    transaction["changed_data_blocks"].append(material.name)


def _assign_material_node_tree_preview_action(material):
    _record_material_node_tree_animation(material)
    action = bpy.data.actions.new(name=f"{material.name} Agent Bridge Material Preview Action")
    material.node_tree.animation_data_create().action = action
    live_preview._record_created_id("action", action.name)
    return action


def _material_for_color(name, color):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
        live_preview._record_created_id("material", material.name)
    else:
        live_preview._record_material(material)
    rgba = (
        float(color[0]),
        float(color[1]),
        float(color[2]),
        float(color[3]) if len(color) > 3 else 1.0,
    )
    material.diffuse_color = rgba
    return material


def _selection_snapshot(context):
    active = context.view_layer.objects.active if context.view_layer else None
    return {
        "selected_names": [obj.name for obj in context.selected_objects],
        "active_name": active.name if active else "",
    }


def _restore_selection_snapshot(context, snapshot):
    bpy.ops.object.select_all(action="DESELECT")
    for name in snapshot.get("selected_names", []):
        obj = bpy.data.objects.get(name)
        if obj:
            obj.select_set(True)
    if context.view_layer:
        context.view_layer.objects.active = bpy.data.objects.get(snapshot.get("active_name", ""))


@contextmanager
def _preserve_selection(context):
    snapshot = _selection_snapshot(context)
    try:
        yield
    finally:
        _restore_selection_snapshot(context, snapshot)


def _bounds_world(obj):
    coords = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_x = min(vec.x for vec in coords)
    max_x = max(vec.x for vec in coords)
    min_y = min(vec.y for vec in coords)
    max_y = max(vec.y for vec in coords)
    min_z = min(vec.z for vec in coords)
    max_z = max(vec.z for vec in coords)
    return {
        "center": ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, (min_z + max_z) / 2.0),
        "min": (min_x, min_y, min_z),
        "max": (max_x, max_y, max_z),
        "size": (max_x - min_x, max_y - min_y, max_z - min_z),
    }


def _axis_rotation(axis):
    axis = str(axis or "Y").upper()
    if axis == "X":
        return (0.0, math.radians(90.0), 0.0)
    if axis == "Y":
        return (math.radians(90.0), 0.0, 0.0)
    return (0.0, 0.0, 0.0)


def _create_cube_object(context, name, location, scale, material=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = context.object
    obj.name = name
    obj.data.name = f"{name} Mesh"
    obj.scale = scale
    if material:
        obj.data.materials.append(material)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("mesh", obj.data.name)
    return obj


def _create_uv_sphere_object(context, name, location, radius, material=None, *, segments=32, ring_count=16):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=max(8, int(segments)),
        ring_count=max(4, int(ring_count)),
        radius=max(0.01, float(radius)),
        location=location,
    )
    obj = context.object
    obj.name = name
    obj.data.name = f"{name} Mesh"
    if material:
        obj.data.materials.append(material)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("mesh", obj.data.name)
    return obj


def _create_cylinder_object(context, name, location, radius, depth, material=None, *, vertices=32, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=max(8, int(vertices)),
        radius=max(0.01, float(radius)),
        depth=max(0.01, float(depth)),
        location=location,
        rotation=rotation,
    )
    obj = context.object
    obj.name = name
    obj.data.name = f"{name} Mesh"
    if material:
        obj.data.materials.append(material)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("mesh", obj.data.name)
    return obj


def _create_curve_line(context, name, points, bevel_depth, material=None):
    curve = bpy.data.curves.new(f"{name} Data", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = max(0.0, float(bevel_depth))
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, values in zip(spline.points, points):
        point.co = (float(values[0]), float(values[1]), float(values[2]), 1.0)
    obj = bpy.data.objects.new(name, curve)
    context.scene.collection.objects.link(obj)
    if material:
        curve.materials.append(material)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("curve", curve.name)
    return obj


def _create_text_label(context, name, text, location, *, size=0.2, rotation=(0.0, 0.0, 0.0), material=None):
    curve = bpy.data.curves.new(f"{name} Data", "FONT")
    curve.body = str(text)
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = max(0.01, float(size))
    obj = bpy.data.objects.new(name, curve)
    obj.location = _coerce_vector(location, (0.0, 0.0, 0.0))
    obj.rotation_euler = _coerce_vector(rotation, (0.0, 0.0, 0.0))
    context.scene.collection.objects.link(obj)
    if material:
        curve.materials.append(material)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("curve", curve.name)
    return obj


def _create_empty_target(context, name, location, *, display_size=0.4):
    empty = bpy.data.objects.new(name, object_data=None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = max(0.01, float(display_size))
    empty.location = _coerce_vector(location, (0.0, 0.0, 0.0))
    context.scene.collection.objects.link(empty)
    live_preview._record_created_id("object", empty.name)
    return empty


def _track_to_target(obj, target):
    constraint = obj.constraints.new(type="TRACK_TO")
    constraint.name = "Agent Bridge Look At Target"
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    live_preview._record_created_constraint(obj, constraint)
    return constraint


def _create_area_light(context, name, location, *, energy, size, color, target=None):
    data = bpy.data.lights.new(name=name, type="AREA")
    data.energy = max(0.0, float(energy))
    data.size = max(0.01, float(size))
    data.color = (float(color[0]), float(color[1]), float(color[2]))
    obj = bpy.data.objects.new(name=name, object_data=data)
    obj.location = _coerce_vector(location, (0.0, 0.0, 0.0))
    context.scene.collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("light", data.name)
    if target is not None:
        _track_to_target(obj, target)
    return obj


def _create_wheel_parts(context, *, name, location, radius, thickness, axis, tire_material, rim_material):
    rotation = _axis_rotation(axis)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=max(0.01, float(radius)),
        minor_radius=max(0.005, float(thickness)),
        major_segments=64,
        minor_segments=16,
        location=location,
        rotation=rotation,
    )
    tire = context.object
    tire.name = f"{name} Tire"
    tire.data.name = f"{tire.name} Mesh"
    tire.data.materials.append(tire_material)
    live_preview._record_created_id("object", tire.name)
    live_preview._record_created_id("mesh", tire.data.name)

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48,
        radius=max(0.01, float(radius) * 0.62),
        depth=max(0.01, float(thickness) * 2.2),
        location=location,
        rotation=rotation,
    )
    rim = context.object
    rim.name = f"{name} Rim"
    rim.data.name = f"{rim.name} Mesh"
    rim.data.materials.append(rim_material)
    live_preview._record_created_id("object", rim.name)
    live_preview._record_created_id("mesh", rim.data.name)

    return [tire, rim]


def create_shader_material(
    context,
    *,
    name,
    base_color,
    metallic=0.0,
    roughness=0.5,
    alpha=1.0,
    emission_color=None,
    emission_strength=0.0,
    assign_to_selected=True,
    label="Create shader material",
):
    transaction = live_preview.begin(label, context)
    material = bpy.data.materials.get(name)
    created = material is None
    if material is None:
        material = bpy.data.materials.new(name or "Agent Bridge Shader Material")
        live_preview._record_created_id("material", material.name)
    else:
        _record_shader_material(material)

    rgba = (
        float(base_color[0]),
        float(base_color[1]),
        float(base_color[2]),
        float(base_color[3]) if len(base_color) > 3 else float(alpha),
    )
    material.diffuse_color = rgba
    principled = _ensure_principled_material(material)
    _set_socket_value(principled.inputs.get("Base Color"), rgba)
    _set_socket_value(principled.inputs.get("Metallic"), max(0.0, min(1.0, float(metallic))))
    _set_socket_value(principled.inputs.get("Roughness"), max(0.0, min(1.0, float(roughness))))
    _set_socket_value(principled.inputs.get("Alpha"), max(0.0, min(1.0, float(alpha))))
    if emission_color is not None:
        emission = (
            float(emission_color[0]),
            float(emission_color[1]),
            float(emission_color[2]),
            float(emission_color[3]) if len(emission_color) > 3 else 1.0,
        )
        _set_socket_value(principled.inputs.get("Emission Color"), emission)
    _set_socket_value(principled.inputs.get("Emission Strength"), max(0.0, float(emission_strength)))
    if alpha < 1.0:
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "BLENDED"
        elif hasattr(material, "blend_method"):
            material.blend_method = "BLEND"

    assigned = []
    if assign_to_selected:
        for obj in context.selected_objects:
            if obj.type != "MESH" or obj.data is None:
                continue
            live_preview._record_object_materials(obj)
            if obj.material_slots:
                obj.material_slots[0].material = material
            else:
                obj.data.materials.append(material)
            assigned.append(obj.name)

    transaction["applied_steps"].append(
        {
            "type": "create_shader_material",
            "label": label,
            "material": material.name,
            "created": created,
            "assigned_objects": assigned,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"{'Created' if created else 'Updated'} shader material {material.name}",
        "material": material.name,
        "assigned_objects": assigned,
        "transaction_id": transaction["id"],
    }


def add_geometry_nodes_modifier(
    context,
    *,
    name,
    node_group_name,
    selected_only=True,
    label="Add Geometry Nodes modifier",
):
    targets = [obj for obj in (context.selected_objects if selected_only else context.scene.objects) if obj.type == "MESH"]
    if not targets:
        return {"ok": False, "message": "No mesh objects available for Geometry Nodes modifier"}
    transaction = live_preview.begin(label, context)
    group = bpy.data.node_groups.get(node_group_name)
    created_group = group is None
    if group is None:
        group = bpy.data.node_groups.new(node_group_name or "Agent Bridge Geometry Nodes", "GeometryNodeTree")
        live_preview._record_created_id("node_group", group.name)
        group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        group_input = group.nodes.new("NodeGroupInput")
        group_output = group.nodes.new("NodeGroupOutput")
        group_input.location = (-220, 0)
        group_output.location = (220, 0)
        group.links.new(group_input.outputs["Geometry"], group_output.inputs["Geometry"])
    changed = []
    for obj in targets:
        modifier = obj.modifiers.new(name or "Agent Bridge Geometry Nodes", "NODES")
        modifier.node_group = group
        live_preview._record_created_modifier(obj, modifier)
        changed.append(obj.name)
    transaction["applied_steps"].append(
        {
            "type": "add_geometry_nodes_modifier",
            "label": label,
            "objects": changed,
            "node_group": group.name,
            "created_group": created_group,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added Geometry Nodes modifier to {len(changed)} mesh object(s)",
        "objects": changed,
        "node_group": group.name,
        "transaction_id": transaction["id"],
    }


def create_shape_key(context, *, object_name="", key_name="Agent Bridge Shape", value=0.0, label="Create shape key"):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None or obj.type != "MESH":
        return {"ok": False, "message": "A mesh object is required for shape keys"}
    transaction = live_preview.begin(label)
    _record_shape_keys(obj)
    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis")
    key = obj.data.shape_keys.key_blocks.get(key_name)
    created = key is None
    if key is None:
        key = obj.shape_key_add(name=key_name or "Agent Bridge Shape")
    key.value = max(float(key.slider_min), min(float(key.slider_max), float(value)))
    transaction["applied_steps"].append(
        {
            "type": "create_shape_key",
            "label": label,
            "object": obj.name,
            "shape_key": key.name,
            "created": created,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"{'Created' if created else 'Updated'} shape key {key.name} on {obj.name}",
        "object": obj.name,
        "shape_key": key.name,
        "transaction_id": transaction["id"],
    }


def animate_shape_key(
    context,
    *,
    object_name="",
    key_name,
    frame_start,
    frame_end,
    value_start=0.0,
    value_end=1.0,
    create_if_missing=True,
    label="Animate shape key",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None or obj.type != "MESH":
        return {"ok": False, "message": "A mesh object is required for shape key animation"}
    transaction = live_preview.begin(label)
    live_preview._record_scene_timeline(context.scene)
    _record_shape_keys(obj)
    if obj.data.shape_keys is None:
        if not create_if_missing:
            return {"ok": False, "message": f"Object has no shape keys: {obj.name}"}
        obj.shape_key_add(name="Basis")
    key = obj.data.shape_keys.key_blocks.get(key_name)
    if key is None:
        if not create_if_missing:
            return {"ok": False, "message": f"Shape key not found: {key_name}"}
        key = obj.shape_key_add(name=key_name or "Agent Bridge Shape")
    frame_start = int(frame_start)
    frame_end = int(frame_end)
    if frame_start == frame_end:
        return {"ok": False, "message": "Shape key animation needs two different frames"}
    if frame_start > frame_end:
        frame_start, frame_end = frame_end, frame_start
    context.scene.frame_start = min(context.scene.frame_start, frame_start)
    context.scene.frame_end = max(context.scene.frame_end, frame_end)
    key.value = max(float(key.slider_min), min(float(key.slider_max), float(value_start)))
    key.keyframe_insert(data_path="value", frame=frame_start)
    key.value = max(float(key.slider_min), min(float(key.slider_max), float(value_end)))
    key.keyframe_insert(data_path="value", frame=frame_end)
    keys = obj.data.shape_keys
    action = keys.animation_data.action if keys.animation_data else None
    if action:
        live_preview._record_created_id("action", action.name)
        live_preview._set_linear_interpolation(action)
    context.scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "animate_shape_key",
            "label": label,
            "object": obj.name,
            "shape_key": key.name,
            "frame_start": frame_start,
            "frame_end": frame_end,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Animated shape key {key.name} on {obj.name}",
        "object": obj.name,
        "shape_key": key.name,
        "transaction_id": transaction["id"],
    }


def animate_object_bounce(
    context,
    *,
    object_name="",
    frame_start,
    frame_end,
    axis="Z",
    distance=2.0,
    cycles=1,
    interpolation="BEZIER",
    label="Animate object bounce",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None:
        return {"ok": False, "message": "Object not found for bounce animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Bounce animation")
    if error:
        return error
    cycles = max(1, min(24, int(cycles)))
    axis_index, axis = _axis_index(axis)
    distance = float(distance)

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)

    live_preview._record_object_transform(obj)
    action = live_preview._assign_preview_action(obj)
    base_location = [float(value) for value in obj.location]
    span = frame_end - frame_start
    keyed_frames = []
    for step in range(cycles * 2 + 1):
        frame = round(frame_start + (span * step / (cycles * 2)))
        location = list(base_location)
        location[axis_index] += distance if step % 2 else 0.0
        obj.location = location
        obj.keyframe_insert(data_path="location", frame=frame)
        keyed_frames.append(int(frame))
    _set_action_interpolation(action, interpolation)
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "animate_object_bounce",
            "label": label,
            "object": obj.name,
            "axis": axis,
            "distance": distance,
            "cycles": cycles,
            "frames": keyed_frames,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Animated bounce on {obj.name} over {cycles} cycle(s)",
        "object": obj.name,
        "frame_start": frame_start,
        "frame_end": frame_end,
        "frames": keyed_frames,
        "action": action.name,
        "transaction_id": transaction["id"],
    }


def create_progressive_bounce_animation(
    context,
    *,
    object_name="",
    frame_start,
    frame_end,
    axis="Z",
    distance=2.0,
    cycles=2,
    scale_end_factor=0.6,
    interpolation="BEZIER",
    label="Create progressive bounce animation",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None:
        return {"ok": False, "message": "Object not found for progressive bounce animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Progressive bounce animation")
    if error:
        return error
    cycles = max(1, min(24, int(cycles)))
    axis_index, axis = _axis_index(axis)
    distance = float(distance)
    scale_end_factor = max(0.01, float(scale_end_factor))

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)

    live_preview._record_object_transform(obj)
    action = live_preview._assign_preview_action(obj)
    base_location = [float(value) for value in obj.location]
    base_scale = [float(value) for value in obj.scale]
    span = frame_end - frame_start
    step_count = cycles * 2
    keyed_frames = []
    scale_keys = []
    for step in range(step_count + 1):
        progress = step / step_count if step_count else 1.0
        frame = round(frame_start + (span * progress))
        factor = 1.0 + ((scale_end_factor - 1.0) * progress)
        location = list(base_location)
        location[axis_index] += distance if step % 2 else 0.0
        obj.location = location
        obj.scale = [component * factor for component in base_scale]
        obj.keyframe_insert(data_path="location", frame=frame)
        obj.keyframe_insert(data_path="scale", frame=frame)
        keyed_frames.append(int(frame))
        scale_keys.append({"frame": int(frame), "factor": round(float(factor), 6)})
    _set_action_interpolation(action, interpolation)
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "create_progressive_bounce_animation",
            "label": label,
            "object": obj.name,
            "axis": axis,
            "distance": distance,
            "cycles": cycles,
            "frames": keyed_frames,
            "scale_end_factor": scale_end_factor,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Animated progressive bounce on {obj.name} over {cycles} cycle(s)",
        "object": obj.name,
        "frame_start": frame_start,
        "frame_end": frame_end,
        "frames": keyed_frames,
        "scale_keys": scale_keys,
        "scale_end_factor": scale_end_factor,
        "action": action.name,
        "transaction_id": transaction["id"],
    }


def _resolve_animation_material(context, material_name="", object_name="", create_if_missing=True):
    material = bpy.data.materials.get(str(material_name or "")) if material_name else None
    obj = bpy.data.objects.get(str(object_name or "")) if object_name else context.active_object
    has_material_slots = obj is not None and getattr(obj, "data", None) is not None and hasattr(obj.data, "materials")
    if material is None and has_material_slots:
        material = obj.active_material or (obj.data.materials[0] if len(obj.data.materials) else None)
    if material is None and create_if_missing:
        material = bpy.data.materials.new(str(material_name or "Agent Bridge Animated Material"))
        live_preview._record_created_id("material", material.name)
        if has_material_slots:
            live_preview._record_object_materials(obj)
            obj.data.materials.append(material)
    return material, obj


def _socket_animation_value(socket, value, fallback):
    current = socket.default_value
    if hasattr(current, "__len__") and not isinstance(current, str):
        fallback_values = list(fallback) if fallback is not None else list(current)
        if isinstance(value, (int, float)):
            values = [float(value)] * len(current)
        else:
            values = list(value if value is not None else fallback_values)
        if len(values) == 3 and len(current) >= 4:
            values.append(fallback_values[3] if len(fallback_values) > 3 else 1.0)
        while len(values) < len(current):
            index = len(values)
            values.append(fallback_values[index] if index < len(fallback_values) else 0.0)
        return tuple(float(component) for component in values[: len(current)])
    if isinstance(value, (list, tuple)):
        return float(value[0]) if value else float(fallback or 0.0)
    return float(value if value is not None else fallback)


def animate_material_property(
    context,
    *,
    material_name="",
    object_name="",
    property_name="base_color",
    frame_start,
    frame_end,
    value_start=None,
    value_end=None,
    create_if_missing=True,
    interpolation="LINEAR",
    label="Animate material property",
):
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Material animation")
    if error:
        return error
    property_key = str(property_name or "base_color").strip().lower().replace(" ", "_")
    socket_names = {
        "base_color": "Base Color",
        "diffuse_color": "Base Color",
        "color": "Base Color",
        "emission_color": "Emission Color",
        "emission": "Emission Color",
        "emission_strength": "Emission Strength",
        "glow": "Emission Strength",
        "roughness": "Roughness",
        "metallic": "Metallic",
        "alpha": "Alpha",
    }
    socket_name = socket_names.get(property_key)
    if socket_name is None:
        return {"ok": False, "message": f"Unsupported material animation property: {property_name}"}

    transaction = live_preview.begin(label, context)
    material, obj = _resolve_animation_material(context, material_name, object_name, create_if_missing)
    if material is None:
        return {"ok": False, "message": "Material not found for animation"}
    live_preview._record_scene_timeline(context.scene)
    context.scene.frame_start = min(context.scene.frame_start, frame_start)
    context.scene.frame_end = max(context.scene.frame_end, frame_end)
    _record_shader_material(material)
    principled = _ensure_principled_material(material)
    socket = principled.inputs.get(socket_name)
    if socket is None or not hasattr(socket, "default_value"):
        return {"ok": False, "message": f"Material socket not found: {socket_name}"}

    current_value = _socket_value(socket.default_value)
    start = _socket_animation_value(socket, value_start, current_value)
    end = _socket_animation_value(socket, value_end, start)
    action = _assign_material_node_tree_preview_action(material)
    _set_socket_value(socket, start)
    socket.keyframe_insert(data_path="default_value", frame=frame_start)
    _set_socket_value(socket, end)
    socket.keyframe_insert(data_path="default_value", frame=frame_end)
    if socket_name == "Base Color":
        material.diffuse_color = end
    elif socket_name == "Alpha":
        rgba = list(material.diffuse_color)
        while len(rgba) < 4:
            rgba.append(1.0)
        rgba[3] = float(end)
        material.diffuse_color = tuple(rgba)
        if hasattr(material, "blend_method"):
            material.blend_method = "BLEND"
    _set_action_interpolation(action, interpolation)
    context.scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "animate_material_property",
            "label": label,
            "material": material.name,
            "object": obj.name if obj else None,
            "property": property_key,
            "frame_start": frame_start,
            "frame_end": frame_end,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Animated {property_key} on material {material.name}",
        "material": material.name,
        "property": property_key,
        "socket": socket_name,
        "action": action.name,
        "transaction_id": transaction["id"],
    }


def _record_light_settings(light_obj):
    data = light_obj.data if light_obj and light_obj.type == "LIGHT" else None
    if data is None:
        return
    transaction = live_preview.begin()
    key = f"light:{data.name}:settings"
    if key in transaction["before_state"]:
        return
    transaction["before_state"][key] = {
        "kind": "light_settings",
        "light_data_name": data.name,
        "energy": float(data.energy),
        "color": tuple(float(component) for component in data.color),
        "shadow_soft_size": float(getattr(data, "shadow_soft_size", 0.0)),
        "spot_size": float(getattr(data, "spot_size", 0.0)),
        "spot_blend": float(getattr(data, "spot_blend", 0.0)),
    }
    transaction["changed_data_blocks"].append(data.name)


def _record_light_data_animation(light_obj):
    data = light_obj.data if light_obj and light_obj.type == "LIGHT" else None
    if data is None:
        return
    transaction = live_preview.begin()
    key = f"light:{data.name}:animation"
    if key in transaction["before_state"]:
        return
    animation_data = data.animation_data
    action = animation_data.action if animation_data else None
    transaction["before_state"][key] = {
        "kind": "light_data_animation",
        "light_data_name": data.name,
        "had_animation_data": animation_data is not None,
        "action_name": action.name if action else None,
    }
    transaction["changed_data_blocks"].append(data.name)


def _assign_light_preview_action(light_obj):
    _record_light_data_animation(light_obj)
    action = bpy.data.actions.new(name=f"{light_obj.name} Agent Bridge Light Preview Action")
    light_obj.data.animation_data_create().action = action
    live_preview._record_created_id("action", action.name)
    return action


def _light_animation_value(current, value):
    if hasattr(current, "__len__") and not isinstance(current, str):
        values = list(value if value is not None else current)
        while len(values) < len(current):
            values.append(current[len(values)])
        return tuple(float(component) for component in values[: len(current)])
    if isinstance(value, (list, tuple)):
        return float(value[0]) if value else float(current)
    return float(value if value is not None else current)


def animate_light_property(
    context,
    *,
    light_name="",
    property_name="energy",
    frame_start,
    frame_end,
    value_start=None,
    value_end=None,
    interpolation="LINEAR",
    label="Animate light property",
):
    light_obj = bpy.data.objects.get(light_name) if light_name else context.active_object
    if light_obj is None or light_obj.type != "LIGHT":
        light_obj = next((obj for obj in context.scene.objects if obj.type == "LIGHT"), None)
    if light_obj is None or light_obj.type != "LIGHT":
        return {"ok": False, "message": "A light object is required for light animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Light animation")
    if error:
        return error
    property_key = str(property_name or "energy").strip().lower()
    data_path_map = {
        "energy": "energy",
        "intensity": "energy",
        "color": "color",
        "colour": "color",
        "shadow_soft_size": "shadow_soft_size",
        "spot_size": "spot_size",
        "spot_blend": "spot_blend",
    }
    data_path = data_path_map.get(property_key)
    if data_path is None or not hasattr(light_obj.data, data_path):
        return {"ok": False, "message": f"Unsupported light animation property: {property_name}"}
    if value_start is None and value_end is None:
        return {"ok": False, "message": "Light animation needs at least value_end or value_start"}

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)
    _record_light_settings(light_obj)
    action = _assign_light_preview_action(light_obj)
    current = getattr(light_obj.data, data_path)
    start = _light_animation_value(current, value_start)
    end = _light_animation_value(start, value_end)
    setattr(light_obj.data, data_path, start)
    light_obj.data.keyframe_insert(data_path=data_path, frame=frame_start)
    setattr(light_obj.data, data_path, end)
    light_obj.data.keyframe_insert(data_path=data_path, frame=frame_end)
    _set_action_interpolation(action, interpolation)
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "animate_light_property",
            "label": label,
            "light": light_obj.name,
            "property": data_path,
            "frame_start": frame_start,
            "frame_end": frame_end,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Animated {data_path} on light {light_obj.name}",
        "light": light_obj.name,
        "property": data_path,
        "action": action.name,
        "transaction_id": transaction["id"],
    }


def create_follow_path_animation(
    context,
    *,
    object_name="",
    path_name="",
    path_points=None,
    frame_start,
    frame_end,
    constraint_name="Agent Bridge Follow Path",
    follow_curve=True,
    interpolation="LINEAR",
    label="Create follow path animation",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None:
        return {"ok": False, "message": "Object not found for follow-path animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Follow-path animation")
    if error:
        return error

    transaction = live_preview.begin(label, context)
    path_obj = bpy.data.objects.get(str(path_name or "")) if path_name else None
    if path_obj is None:
        if len(path_points or []) < 2:
            return {"ok": False, "message": "Provide an existing curve path or at least two path points"}
        path_obj = _create_curve_line(context, path_name or f"{obj.name} Follow Path", path_points, 0.02)
    if path_obj.type != "CURVE":
        return {"ok": False, "message": f"Follow path target is not a curve: {path_obj.name}"}

    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)
    live_preview._record_object_transform(obj)
    action = live_preview._assign_preview_action(obj)
    constraint = obj.constraints.new(type="FOLLOW_PATH")
    constraint.name = constraint_name or "Agent Bridge Follow Path"
    constraint.target = path_obj
    constraint.use_curve_follow = bool(follow_curve)
    constraint.use_fixed_location = True
    live_preview._record_created_constraint(obj, constraint)
    constraint.offset_factor = 0.0
    constraint.keyframe_insert(data_path="offset_factor", frame=frame_start)
    constraint.offset_factor = 1.0
    constraint.keyframe_insert(data_path="offset_factor", frame=frame_end)
    _set_action_interpolation(action, interpolation)
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "create_follow_path_animation",
            "label": label,
            "object": obj.name,
            "path": path_obj.name,
            "constraint": constraint.name,
            "frame_start": frame_start,
            "frame_end": frame_end,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Animated {obj.name} along path {path_obj.name}",
        "object": obj.name,
        "path": path_obj.name,
        "constraint": constraint.name,
        "action": action.name,
        "transaction_id": transaction["id"],
    }


def _animation_action_from(data_block):
    animation_data = getattr(data_block, "animation_data", None)
    return animation_data.action if animation_data else None


def _object_animation_actions(obj):
    actions = [_animation_action_from(obj)]
    data = getattr(obj, "data", None)
    if data:
        actions.append(_animation_action_from(data))
    if obj.type == "MESH" and data and getattr(data, "shape_keys", None):
        actions.append(_animation_action_from(data.shape_keys))
    for slot in getattr(obj, "material_slots", []):
        material = slot.material
        if material:
            actions.append(_animation_action_from(material))
            if material.use_nodes and material.node_tree:
                actions.append(_animation_action_from(material.node_tree))
    return [action for action in actions if action]


def _resolve_animation_actions(context, *, action_names=None, object_names=None, selected_only=False, max_actions=32):
    actions = []
    missing_actions = []
    missing_objects = []
    seen = set()

    def add_action(action):
        if action and action.name not in seen:
            seen.add(action.name)
            actions.append(action)

    for name in action_names or []:
        action = bpy.data.actions.get(str(name))
        if action:
            add_action(action)
        else:
            missing_actions.append(str(name))

    objects = []
    if object_names:
        for name in object_names:
            obj = bpy.data.objects.get(str(name))
            if obj:
                objects.append(obj)
            else:
                missing_objects.append(str(name))
    elif selected_only:
        objects = list(context.selected_objects)
    elif context.active_object and not actions:
        objects = [context.active_object]

    for obj in objects:
        for action in _object_animation_actions(obj):
            add_action(action)

    return actions[: max(1, int(max_actions or 1))], missing_actions, missing_objects


def _valid_interpolation(value):
    interpolation = str(value or "LINEAR").upper()
    return interpolation if interpolation in KEYFRAME_INTERPOLATIONS else "LINEAR"


def _valid_easing(value):
    easing = str(value or "").upper()
    return easing if easing in {"AUTO", "EASE_IN", "EASE_OUT", "EASE_IN_OUT"} else ""


def set_action_interpolation(
    context,
    *,
    action_names=None,
    object_names=None,
    selected_only=False,
    interpolation="LINEAR",
    easing="",
    label="Set action interpolation",
):
    actions, missing_actions, missing_objects = _resolve_animation_actions(
        context,
        action_names=action_names or [],
        object_names=object_names or [],
        selected_only=selected_only,
    )
    if not actions:
        return {"ok": False, "message": "No actions found for interpolation update", "missing_action_names": missing_actions, "missing_object_names": missing_objects}
    interpolation = _valid_interpolation(interpolation)
    easing = _valid_easing(easing)
    transaction = live_preview.begin(label, context)
    changed = []
    for action in actions:
        live_preview._record_action_edit(action)
        for fcurve in live_preview._iter_action_fcurves(action):
            for point in fcurve.keyframe_points:
                point.interpolation = interpolation
                if easing and hasattr(point, "easing"):
                    point.easing = easing
            fcurve.update()
        changed.append(action.name)
    transaction["applied_steps"].append(
        {"type": "set_action_interpolation", "label": label, "actions": changed, "interpolation": interpolation, "easing": easing}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Updated interpolation on {len(changed)} action(s)",
        "actions": changed,
        "missing_action_names": missing_actions,
        "missing_object_names": missing_objects,
        "transaction_id": transaction["id"],
    }


def _action_frame_span(action):
    frames = [
        float(point.co.x)
        for fcurve in live_preview._iter_action_fcurves(action)
        for point in fcurve.keyframe_points
    ]
    if not frames:
        return None
    return min(frames), max(frames)


def retime_actions(
    context,
    *,
    action_names=None,
    object_names=None,
    selected_only=False,
    frame_start,
    frame_end,
    snap_to_integer=True,
    label="Retime actions",
):
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Action retime")
    if error:
        return error
    actions, missing_actions, missing_objects = _resolve_animation_actions(
        context,
        action_names=action_names or [],
        object_names=object_names or [],
        selected_only=selected_only,
    )
    if not actions:
        return {"ok": False, "message": "No actions found for retiming", "missing_action_names": missing_actions, "missing_object_names": missing_objects}
    retime_plan = []
    skipped = []
    for action in actions:
        span = _action_frame_span(action)
        if span is None or span[0] == span[1]:
            skipped.append(action.name)
            continue
        retime_plan.append((action, span))
    if not retime_plan:
        return {
            "ok": False,
            "message": "No retimeable actions found",
            "actions": [],
            "skipped_actions": skipped,
            "missing_action_names": missing_actions,
            "missing_object_names": missing_objects,
        }
    transaction = live_preview.begin(label, context)
    live_preview._record_scene_timeline(context.scene)
    context.scene.frame_start = min(context.scene.frame_start, frame_start)
    context.scene.frame_end = max(context.scene.frame_end, frame_end)
    changed = []
    for action, span in retime_plan:
        old_start, old_end = span
        scale = (frame_end - frame_start) / (old_end - old_start)
        live_preview._record_action_edit(action)
        for fcurve in live_preview._iter_action_fcurves(action):
            for point in fcurve.keyframe_points:
                old_x = float(point.co.x)
                new_x = frame_start + (old_x - old_start) * scale
                if snap_to_integer:
                    new_x = round(new_x)
                handle_left_dx = float(point.handle_left.x) - old_x
                handle_right_dx = float(point.handle_right.x) - old_x
                point.co.x = new_x
                point.handle_left.x = new_x + handle_left_dx * scale
                point.handle_right.x = new_x + handle_right_dx * scale
            fcurve.update()
        changed.append(action.name)
    context.scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "retime_actions",
            "label": label,
            "actions": changed,
            "frame_start": frame_start,
            "frame_end": frame_end,
            "skipped_actions": skipped,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": bool(changed),
        "message": f"Retimed {len(changed)} action(s)",
        "actions": changed,
        "skipped_actions": skipped,
        "missing_action_names": missing_actions,
        "missing_object_names": missing_objects,
        "transaction_id": transaction["id"],
    }


def add_action_cycles(
    context,
    *,
    action_names=None,
    object_names=None,
    selected_only=False,
    mode_before="NONE",
    mode_after="REPEAT",
    replace_existing=False,
    label="Add action cycles",
):
    actions, missing_actions, missing_objects = _resolve_animation_actions(
        context,
        action_names=action_names or [],
        object_names=object_names or [],
        selected_only=selected_only,
    )
    if not actions:
        return {"ok": False, "message": "No actions found for cycles", "missing_action_names": missing_actions, "missing_object_names": missing_objects}
    valid_modes = {"NONE", "REPEAT", "REPEAT_OFFSET", "MIRROR"}
    mode_before = str(mode_before or "NONE").upper()
    mode_after = str(mode_after or "REPEAT").upper()
    if mode_before not in valid_modes:
        mode_before = "NONE"
    if mode_after not in valid_modes:
        mode_after = "REPEAT"
    cycles_plan = []
    for action in actions:
        fcurves_to_change = []
        for fcurve in live_preview._iter_action_fcurves(action):
            existing = [modifier for modifier in list(fcurve.modifiers) if modifier.type == "CYCLES"]
            if existing and not replace_existing:
                continue
            fcurves_to_change.append((fcurve, existing))
        if fcurves_to_change:
            cycles_plan.append((action, fcurves_to_change))
    if not cycles_plan:
        return {
            "ok": False,
            "message": "No f-curves available for cycles update",
            "actions": [],
            "missing_action_names": missing_actions,
            "missing_object_names": missing_objects,
        }
    transaction = live_preview.begin(label, context)
    changed = []
    for action, fcurves_to_change in cycles_plan:
        live_preview._record_action_edit(action)
        fcurve_count = 0
        for fcurve, existing in fcurves_to_change:
            for modifier in existing:
                fcurve.modifiers.remove(modifier)
            modifier = fcurve.modifiers.new(type="CYCLES")
            modifier.mode_before = mode_before
            modifier.mode_after = mode_after
            fcurve_count += 1
        if fcurve_count:
            changed.append({"action": action.name, "fcurves": fcurve_count})
    transaction["applied_steps"].append(
        {"type": "add_action_cycles", "label": label, "actions": changed, "mode_before": mode_before, "mode_after": mode_after}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": bool(changed),
        "message": f"Added cycles to {len(changed)} action(s)",
        "actions": changed,
        "missing_action_names": missing_actions,
        "missing_object_names": missing_objects,
        "transaction_id": transaction["id"],
    }


def _data_collection_for_object(obj):
    if obj.type == "CAMERA":
        return "cameras"
    if obj.type == "LIGHT":
        return "lights"
    if obj.type == "MESH":
        return "meshes"
    if obj.type in {"CURVE", "FONT"}:
        return "curves"
    if obj.type == "ARMATURE":
        return "armatures"
    return ""


def clear_animation(
    context,
    *,
    object_names=None,
    selected_only=True,
    include_object_animation=True,
    include_data_animation=True,
    include_shape_key_animation=True,
    include_material_animation=False,
    label="Clear animation",
):
    names = [str(name) for name in object_names or [] if str(name).strip()]
    if names:
        objects = [bpy.data.objects.get(name) for name in names]
        missing = [name for name, obj in zip(names, objects) if obj is None]
        objects = [obj for obj in objects if obj]
    elif selected_only:
        objects = list(context.selected_objects)
        missing = []
    elif context.active_object:
        objects = [context.active_object]
        missing = []
    else:
        objects = []
        missing = []
    if not objects:
        return {"ok": False, "message": "No objects found for animation clearing", "missing_object_names": missing}
    has_clearable_animation = False
    for obj in objects:
        if include_object_animation and obj.animation_data:
            has_clearable_animation = True
            break
        if include_data_animation and getattr(obj, "data", None) and obj.data.animation_data:
            has_clearable_animation = True
            break
        if include_shape_key_animation and obj.type == "MESH" and obj.data and obj.data.shape_keys and obj.data.shape_keys.animation_data:
            has_clearable_animation = True
            break
        if include_material_animation:
            for slot in obj.material_slots:
                material = slot.material
                if not material:
                    continue
                if material.animation_data or (material.use_nodes and material.node_tree and material.node_tree.animation_data):
                    has_clearable_animation = True
                    break
        if has_clearable_animation:
            break
    if not has_clearable_animation:
        return {"ok": False, "message": "No animation found to clear", "cleared": [], "missing_object_names": missing}

    transaction = live_preview.begin(label, context)
    cleared = []
    for obj in objects:
        if include_object_animation and obj.animation_data:
            live_preview._record_object_animation(obj)
            obj.animation_data_clear()
            cleared.append({"object": obj.name, "target": "object"})
        if include_data_animation and getattr(obj, "data", None) and obj.data.animation_data:
            collection = _data_collection_for_object(obj)
            if collection:
                live_preview._record_id_animation(obj.data, collection)
                obj.data.animation_data_clear()
                cleared.append({"object": obj.name, "target": "data"})
        if include_shape_key_animation and obj.type == "MESH" and obj.data and obj.data.shape_keys and obj.data.shape_keys.animation_data:
            _record_shape_keys(obj)
            obj.data.shape_keys.animation_data_clear()
            cleared.append({"object": obj.name, "target": "shape_keys"})
        if include_material_animation:
            for slot in obj.material_slots:
                material = slot.material
                if not material:
                    continue
                if material.animation_data:
                    live_preview._record_id_animation(material, "materials")
                    material.animation_data_clear()
                    cleared.append({"object": obj.name, "target": f"material:{material.name}"})
                if material.use_nodes and material.node_tree and material.node_tree.animation_data:
                    _record_material_node_tree_animation(material)
                    material.node_tree.animation_data_clear()
                    cleared.append({"object": obj.name, "target": f"material_node_tree:{material.name}"})
    transaction["applied_steps"].append({"type": "clear_animation", "label": label, "cleared": cleared})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Cleared {len(cleared)} animation target(s)",
        "cleared": cleared,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }


def set_animation_preview_range(
    context,
    *,
    frame_start,
    frame_end,
    current_frame=None,
    use_preview_range=True,
    label="Set animation preview range",
):
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Preview range")
    if error:
        return error
    scene = context.scene
    transaction = live_preview.begin(label, context)
    live_preview._record_scene_playback(scene)
    scene.use_preview_range = bool(use_preview_range)
    scene.frame_preview_start = frame_start
    scene.frame_preview_end = frame_end
    if current_frame is not None:
        scene.frame_set(int(current_frame))
    transaction["applied_steps"].append(
        {"type": "set_animation_preview_range", "label": label, "frame_start": frame_start, "frame_end": frame_end, "use_preview_range": bool(use_preview_range)}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Set preview range to {frame_start}-{frame_end}", "transaction_id": transaction["id"]}


def create_turntable_animation(
    context,
    *,
    object_name="",
    frame_start,
    frame_end,
    axis="Z",
    revolutions=1.0,
    add_cycles=False,
    label="Create turntable animation",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None:
        return {"ok": False, "message": "Object not found for turntable animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Turntable animation")
    if error:
        return error
    axis_index, axis = _axis_index(axis)
    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)
    live_preview._record_object_transform(obj)
    action = live_preview._assign_preview_action(obj)
    base_rotation = [float(value) for value in obj.rotation_euler]
    obj.rotation_euler = base_rotation
    obj.keyframe_insert(data_path="rotation_euler", frame=frame_start)
    end_rotation = list(base_rotation)
    end_rotation[axis_index] += math.tau * float(revolutions)
    obj.rotation_euler = end_rotation
    obj.keyframe_insert(data_path="rotation_euler", frame=frame_end)
    _set_action_interpolation(action, "LINEAR")
    if add_cycles:
        live_preview._record_action_edit(action)
        for fcurve in live_preview._iter_action_fcurves(action):
            modifier = fcurve.modifiers.new(type="CYCLES")
            modifier.mode_before = "NONE"
            modifier.mode_after = "REPEAT"
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {"type": "create_turntable_animation", "label": label, "object": obj.name, "axis": axis, "revolutions": float(revolutions)}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created turntable animation for {obj.name}", "object": obj.name, "action": action.name, "transaction_id": transaction["id"]}


def create_pulse_animation(
    context,
    *,
    object_name="",
    frame_start,
    frame_end,
    scale_factor=1.15,
    emission_strength_end=None,
    label="Create pulse animation",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None:
        return {"ok": False, "message": "Object not found for pulse animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Pulse animation")
    if error:
        return error
    frame_mid = int(round((frame_start + frame_end) / 2))
    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)
    live_preview._record_object_transform(obj)
    action = live_preview._assign_preview_action(obj)
    base_scale = [float(value) for value in obj.scale]
    obj.scale = base_scale
    obj.keyframe_insert(data_path="scale", frame=frame_start)
    obj.scale = [value * float(scale_factor) for value in base_scale]
    obj.keyframe_insert(data_path="scale", frame=frame_mid)
    obj.scale = base_scale
    obj.keyframe_insert(data_path="scale", frame=frame_end)
    _set_action_interpolation(action, "SINE")
    material_action = None
    if emission_strength_end is not None:
        material_result = animate_material_property(
            context,
            object_name=obj.name,
            property_name="emission_strength",
            frame_start=frame_start,
            frame_end=frame_mid,
            value_start=0.0,
            value_end=float(emission_strength_end),
            label=label,
        )
        material_action = material_result.get("action") if material_result.get("ok") else None
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {"type": "create_pulse_animation", "label": label, "object": obj.name, "scale_factor": float(scale_factor), "material_action": material_action}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created pulse animation for {obj.name}", "object": obj.name, "action": action.name, "material_action": material_action, "transaction_id": transaction["id"]}


def create_reveal_animation(
    context,
    *,
    object_name="",
    frame_start,
    frame_end,
    scale_start=0.01,
    scale_end=1.0,
    fade_material=True,
    label="Create reveal animation",
):
    obj = bpy.data.objects.get(object_name) if object_name else context.active_object
    if obj is None:
        return {"ok": False, "message": "Object not found for reveal animation"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Reveal animation")
    if error:
        return error
    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)
    live_preview._record_object_transform(obj)
    action = live_preview._assign_preview_action(obj)
    base_scale = [float(value) for value in obj.scale]
    obj.scale = [value * float(scale_start) for value in base_scale]
    obj.keyframe_insert(data_path="scale", frame=frame_start)
    obj.scale = [value * float(scale_end) for value in base_scale]
    obj.keyframe_insert(data_path="scale", frame=frame_end)
    _set_action_interpolation(action, "BEZIER")
    material_action = None
    if fade_material and obj.type == "MESH":
        material_result = animate_material_property(
            context,
            object_name=obj.name,
            property_name="alpha",
            frame_start=frame_start,
            frame_end=frame_end,
            value_start=0.0,
            value_end=1.0,
            label=label,
        )
        material_action = material_result.get("action") if material_result.get("ok") else None
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {"type": "create_reveal_animation", "label": label, "object": obj.name, "material_action": material_action}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created reveal animation for {obj.name}", "object": obj.name, "action": action.name, "material_action": material_action, "transaction_id": transaction["id"]}


def create_staggered_motion(
    context,
    *,
    object_names=None,
    frame_start,
    duration=24,
    frame_step=6,
    location_delta=(0.0, 0.0, 1.0),
    interpolation="BEZIER",
    label="Create staggered motion",
):
    names = [str(name) for name in object_names or [] if str(name).strip()]
    if names:
        objects = [bpy.data.objects.get(name) for name in names]
        missing = [name for name, obj in zip(names, objects) if obj is None]
        objects = [obj for obj in objects if obj]
    else:
        objects = list(context.selected_objects)
        missing = []
    if not objects:
        return {"ok": False, "message": "No objects found for staggered motion", "missing_object_names": missing}
    frame_start = int(frame_start)
    duration = max(1, int(duration))
    frame_step = max(0, int(frame_step))
    delta = _coerce_vector(location_delta, (0.0, 0.0, 1.0))
    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    end_frame = frame_start + (len(objects) - 1) * frame_step + duration
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, end_frame)
    animated = []
    for index, obj in enumerate(objects):
        start = frame_start + index * frame_step
        end = start + duration
        live_preview._record_object_transform(obj)
        action = live_preview._assign_preview_action(obj)
        start_location = [float(value) for value in obj.location]
        end_location = [start_location[0] + delta[0], start_location[1] + delta[1], start_location[2] + delta[2]]
        obj.location = start_location
        obj.keyframe_insert(data_path="location", frame=start)
        obj.location = end_location
        obj.keyframe_insert(data_path="location", frame=end)
        _set_action_interpolation(action, interpolation)
        animated.append({"object": obj.name, "action": action.name, "frame_start": start, "frame_end": end})
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {"type": "create_staggered_motion", "label": label, "objects": animated, "location_delta": list(delta)}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created staggered motion for {len(animated)} object(s)", "objects": animated, "missing_object_names": missing, "transaction_id": transaction["id"]}


TRANSFORM_PATHS = ("location", "rotation_euler", "scale")
TRANSFORM_PATH_ALIASES = {
    "location": "location",
    "position": "location",
    "translation": "location",
    "rotation": "rotation_euler",
    "rotation_euler": "rotation_euler",
    "scale": "scale",
}


def _resolve_named_or_selected_objects(context, object_names=None, *, selected_only=False, fallback_active=True):
    names = [str(name) for name in object_names or [] if str(name).strip()]
    missing = []
    if names:
        objects = [bpy.data.objects.get(name) for name in names]
        missing = [name for name, obj in zip(names, objects) if obj is None]
        objects = [obj for obj in objects if obj]
    elif selected_only or context.selected_objects:
        objects = list(context.selected_objects)
    elif fallback_active and context.active_object:
        objects = [context.active_object]
    else:
        objects = []
    return [obj for obj in objects if obj], missing


def _normalize_transform_paths(paths=None, *, action=None):
    normalized = []
    for path in paths or []:
        key = TRANSFORM_PATH_ALIASES.get(str(path).strip().lower())
        if key and key not in normalized:
            normalized.append(key)
    if normalized:
        return normalized
    if action:
        for fcurve in live_preview._iter_action_fcurves(action):
            if fcurve.data_path in TRANSFORM_PATHS and fcurve.data_path not in normalized:
                normalized.append(fcurve.data_path)
    return normalized


def _fcurves_for_path(action, path):
    result = {}
    if not action:
        return result
    for fcurve in live_preview._iter_action_fcurves(action):
        if fcurve.data_path == path:
            result[int(fcurve.array_index)] = fcurve
    return result


def _evaluate_transform_path(action, path, frame, fallback):
    fallback_values = _coerce_vector(fallback, fallback)
    fcurves = _fcurves_for_path(action, path)
    values = []
    for index, fallback_value in enumerate(fallback_values):
        fcurve = fcurves.get(index)
        values.append(float(fcurve.evaluate(frame)) if fcurve else float(fallback_value))
    return tuple(values)


def _action_keyframes_for_paths(action, paths):
    frames = set()
    for fcurve in live_preview._iter_action_fcurves(action) if action else []:
        if fcurve.data_path not in paths:
            continue
        frames.update(int(round(point.co.x)) for point in fcurve.keyframe_points)
    return sorted(frames)


def _surrounding_frames(action, frame, paths):
    frames = _action_keyframes_for_paths(action, paths)
    previous = [item for item in frames if item < frame]
    following = [item for item in frames if item > frame]
    return (max(previous) if previous else None, min(following) if following else None)


def _prepare_transform_action_for_edit(obj):
    action = obj.animation_data.action if obj.animation_data and obj.animation_data.action else None
    if action:
        transaction = live_preview.current_transaction()
        if transaction and f"created:action:{action.name}" in transaction.get("before_state", {}):
            return action, False
        live_preview._record_object_animation(obj)
        live_preview._record_action_edit(action)
        return action, False
    return live_preview._assign_preview_action(obj), True


def _set_transform_path(obj, path, values):
    if path == "location":
        obj.location = values
    elif path == "rotation_euler":
        obj.rotation_euler = values
    elif path == "scale":
        obj.scale = values


def _transform_fallback(obj, path):
    if path == "location":
        return obj.location
    if path == "rotation_euler":
        return obj.rotation_euler
    return obj.scale


def add_breakdown_pose(
    context,
    *,
    object_names=None,
    frame=None,
    previous_frame=None,
    next_frame=None,
    factor=0.5,
    location=None,
    rotation=None,
    scale=None,
    paths=None,
    selected_only=False,
    interpolation="CONSTANT",
    label="Add breakdown pose",
):
    frame = int(frame if frame is not None else context.scene.frame_current)
    factor = max(0.0, min(1.0, float(factor)))
    objects, missing = _resolve_named_or_selected_objects(context, object_names, selected_only=selected_only)
    if not objects:
        return {"ok": False, "message": "No objects found for breakdown pose", "missing_object_names": missing}

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame)
    scene.frame_end = max(scene.frame_end, frame)
    interpolation = str(interpolation or "CONSTANT").upper()
    keyed = []
    for obj in objects:
        live_preview._record_object_transform(obj)
        action, created_action = _prepare_transform_action_for_edit(obj)
        explicit = {}
        if location is not None:
            explicit["location"] = _coerce_vector(location, obj.location)
        if rotation is not None:
            explicit["rotation_euler"] = _coerce_vector(rotation, obj.rotation_euler)
        if scale is not None:
            explicit["scale"] = _coerce_vector(scale, obj.scale)
        active_paths = _normalize_transform_paths(paths, action=action)
        if explicit:
            active_paths = [path for path in TRANSFORM_PATHS if path in explicit or path in active_paths]
        if not active_paths:
            active_paths = list(explicit)
        if not active_paths:
            return {"ok": False, "message": "Breakdown pose needs existing transform animation or explicit location, rotation, or scale values"}
        prev_frame = int(previous_frame) if previous_frame is not None else None
        next_item = int(next_frame) if next_frame is not None else None
        if prev_frame is None or next_item is None:
            inferred_prev, inferred_next = _surrounding_frames(action, frame, active_paths)
            prev_frame = prev_frame if prev_frame is not None else inferred_prev
            next_item = next_item if next_item is not None else inferred_next
        keyed_paths = []
        values_by_path = {}
        for path in active_paths:
            fallback = _transform_fallback(obj, path)
            if path in explicit:
                values = explicit[path]
            elif prev_frame is not None and next_item is not None and next_item != prev_frame:
                before = _evaluate_transform_path(action, path, prev_frame, fallback)
                after = _evaluate_transform_path(action, path, next_item, fallback)
                values = tuple(before[index] + (after[index] - before[index]) * factor for index in range(3))
            else:
                values = _evaluate_transform_path(action, path, frame, fallback)
            _set_transform_path(obj, path, values)
            obj.keyframe_insert(data_path=path, frame=frame)
            keyed_paths.append(path)
            values_by_path[path] = [round(float(value), 6) for value in values]
        _set_action_interpolation(action, interpolation)
        keyed.append(
            {
                "object": obj.name,
                "action": action.name,
                "created_action": created_action,
                "frame": frame,
                "paths": keyed_paths,
                "previous_frame": prev_frame,
                "next_frame": next_item,
                "factor": factor,
                "values": values_by_path,
            }
        )
    scene.frame_set(frame)
    transaction["applied_steps"].append({"type": "add_breakdown_pose", "label": label, "objects": keyed, "frame": frame})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added breakdown pose at frame {frame} for {len(keyed)} object(s)",
        "objects": keyed,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }


def set_pose_hold(
    context,
    *,
    object_names=None,
    frame=None,
    hold_frames=4,
    paths=None,
    selected_only=False,
    interpolation="CONSTANT",
    label="Set pose hold",
):
    frame = int(frame if frame is not None else context.scene.frame_current)
    hold_frames = max(1, int(hold_frames or 1))
    hold_frame = frame + hold_frames
    objects, missing = _resolve_named_or_selected_objects(context, object_names, selected_only=selected_only)
    if not objects:
        return {"ok": False, "message": "No objects found for pose hold", "missing_object_names": missing}

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame)
    scene.frame_end = max(scene.frame_end, hold_frame)
    interpolation = str(interpolation or "CONSTANT").upper()
    held = []
    for obj in objects:
        live_preview._record_object_transform(obj)
        action, created_action = _prepare_transform_action_for_edit(obj)
        active_paths = _normalize_transform_paths(paths, action=action) or list(TRANSFORM_PATHS)
        keyed_paths = []
        values_by_path = {}
        for path in active_paths:
            values = _evaluate_transform_path(action, path, frame, _transform_fallback(obj, path))
            for key_frame in (frame, hold_frame):
                _set_transform_path(obj, path, values)
                obj.keyframe_insert(data_path=path, frame=key_frame)
            keyed_paths.append(path)
            values_by_path[path] = [round(float(value), 6) for value in values]
        _set_action_interpolation(action, interpolation)
        held.append(
            {
                "object": obj.name,
                "action": action.name,
                "created_action": created_action,
                "frame": frame,
                "hold_frame": hold_frame,
                "hold_frames": hold_frames,
                "paths": keyed_paths,
                "values": values_by_path,
            }
        )
    scene.frame_set(frame)
    transaction["applied_steps"].append({"type": "set_pose_hold", "label": label, "objects": held, "frame": frame, "hold_frame": hold_frame})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Set {hold_frames}-frame hold from frame {frame} for {len(held)} object(s)",
        "objects": held,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }


RIG_POSE_PATHS = ("location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale")
RIG_POSE_PATH_ALIASES = {
    **TRANSFORM_PATH_ALIASES,
    "quaternion": "rotation_quaternion",
    "rotation_quaternion": "rotation_quaternion",
    "axis_angle": "rotation_axis_angle",
    "rotation_axis_angle": "rotation_axis_angle",
}


def _pose_bone_rotation_path(pose_bone):
    mode = str(getattr(pose_bone, "rotation_mode", "") or "").upper()
    if mode == "QUATERNION":
        return "rotation_quaternion"
    if mode == "AXIS_ANGLE":
        return "rotation_axis_angle"
    return "rotation_euler"


def _normalize_rig_pose_paths(paths=None, *, pose_bone=None):
    normalized = []
    for path in paths or []:
        key = RIG_POSE_PATH_ALIASES.get(str(path).strip().lower())
        if key in RIG_POSE_PATHS and key not in normalized:
            normalized.append(key)
    return normalized or ["location", _pose_bone_rotation_path(pose_bone)]


def _pose_path_values(pose_bone, path):
    return tuple(float(value) for value in getattr(pose_bone, path))


def _resolve_armature_for_pose_hold(context, armature_name=""):
    if armature_name:
        armature = bpy.data.objects.get(str(armature_name))
        return armature if armature and armature.type == "ARMATURE" else None
    active = context.active_object
    if active and active.type == "ARMATURE":
        return active
    for obj in context.selected_objects:
        if obj and obj.type == "ARMATURE":
            return obj
    return None


def _default_control_bone_names(armature, *, maximum=8):
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


def set_rig_pose_hold(
    context,
    *,
    armature_name="",
    bone_names=None,
    frame=None,
    hold_frames=4,
    paths=None,
    interpolation="CONSTANT",
    label="Set rig pose hold",
):
    armature = _resolve_armature_for_pose_hold(context, armature_name)
    if armature is None:
        return {"ok": False, "message": "An armature object is required for rig pose hold"}
    if armature.pose is None:
        return {"ok": False, "message": f"Armature has no pose bones: {armature.name}"}
    requested_bones = [str(name) for name in bone_names or [] if str(name).strip()]
    if not requested_bones:
        requested_bones = _default_control_bone_names(armature)
    pose_bones = []
    missing_bones = []
    for name in requested_bones:
        pose_bone = armature.pose.bones.get(name)
        if pose_bone:
            pose_bones.append(pose_bone)
        else:
            missing_bones.append(name)
    if not pose_bones:
        return {
            "ok": False,
            "message": "No matching pose bones found for rig pose hold",
            "armature": armature.name,
            "missing_bone_names": missing_bones,
        }

    frame = int(frame if frame is not None else context.scene.frame_current)
    hold_frames = max(1, int(hold_frames or 1))
    hold_frame = frame + hold_frames
    interpolation = str(interpolation or "CONSTANT").upper()

    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame)
    scene.frame_end = max(scene.frame_end, hold_frame)
    scene.frame_set(frame)
    action, created_action = _prepare_transform_action_for_edit(armature)
    keyed = []
    for pose_bone in pose_bones:
        live_preview._record_pose_bone_transform(armature, pose_bone)
        keyed_paths = []
        values_by_path = {}
        active_paths = _normalize_rig_pose_paths(paths, pose_bone=pose_bone)
        for path in active_paths:
            values = _pose_path_values(pose_bone, path)
            for key_frame in (frame, hold_frame):
                setattr(pose_bone, path, values)
                pose_bone.keyframe_insert(data_path=path, frame=key_frame)
            keyed_paths.append(path)
            values_by_path[path] = [round(float(value), 6) for value in values]
        keyed.append(
            {
                "armature": armature.name,
                "bone": pose_bone.name,
                "action": action.name,
                "created_action": created_action,
                "frame": frame,
                "hold_frame": hold_frame,
                "hold_frames": hold_frames,
                "paths": keyed_paths,
                "values": values_by_path,
            }
        )
    _set_action_interpolation(action, interpolation)
    scene.frame_set(frame)
    transaction["applied_steps"].append(
        {
            "type": "set_rig_pose_hold",
            "label": label,
            "armature": armature.name,
            "bones": [item["bone"] for item in keyed],
            "frame": frame,
            "hold_frame": hold_frame,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Set {hold_frames}-frame rig hold from frame {frame} for {len(keyed)} control bone(s)",
        "armature": armature.name,
        "bones": keyed,
        "missing_bone_names": missing_bones,
        "transaction_id": transaction["id"],
    }


def create_motion_arc(
    context,
    *,
    object_names=None,
    frame_start=None,
    frame_end=None,
    sample_step=4,
    selected_only=False,
    name_prefix="Agent Bridge Motion Arc",
    bevel_depth=0.015,
    color=(0.08, 0.45, 1.0, 1.0),
    label="Create motion arc",
):
    objects, missing = _resolve_named_or_selected_objects(context, object_names, selected_only=selected_only)
    if not objects:
        return {"ok": False, "message": "No objects found for motion arc", "missing_object_names": missing}
    scene = context.scene
    frame_start = int(frame_start if frame_start is not None else scene.frame_start)
    frame_end = int(frame_end if frame_end is not None else scene.frame_end)
    if frame_end < frame_start:
        frame_start, frame_end = frame_end, frame_start
    sample_step = max(1, int(sample_step or 1))
    frames = list(range(frame_start, frame_end + 1, sample_step))
    if frames[-1] != frame_end:
        frames.append(frame_end)
    if len(frames) < 2:
        frames = [frame_start, frame_start + 1]

    transaction = live_preview.begin(label, context)
    material = _material_for_color(f"{name_prefix} Material", _coerce_color(color, (0.08, 0.45, 1.0, 1.0)))
    arcs = []
    for obj in objects:
        action = obj.animation_data.action if obj.animation_data and obj.animation_data.action else None
        points = [
            _evaluate_transform_path(action, "location", frame, obj.location)
            for frame in frames
        ]
        curve = bpy.data.curves.new(f"{name_prefix} {obj.name} Data", "CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 2
        curve.bevel_depth = max(0.0, float(bevel_depth))
        spline = curve.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for point, coords in zip(spline.points, points):
            point.co = (float(coords[0]), float(coords[1]), float(coords[2]), 1.0)
        arc_obj = bpy.data.objects.new(f"{name_prefix} {obj.name}", curve)
        context.scene.collection.objects.link(arc_obj)
        curve.materials.append(material)
        live_preview._record_created_id("curve", curve.name)
        live_preview._record_created_id("object", arc_obj.name)
        arcs.append(
            {
                "source_object": obj.name,
                "arc_object": arc_obj.name,
                "curve": curve.name,
                "frame_start": frame_start,
                "frame_end": frame_end,
                "sample_step": sample_step,
                "sample_count": len(points),
                "points": [[round(float(component), 6) for component in coords] for coords in points],
            }
        )
    transaction["applied_steps"].append({"type": "create_motion_arc", "label": label, "arcs": arcs})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Created {len(arcs)} motion arc(s)",
        "arcs": arcs,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }


def block_key_poses(
    context,
    *,
    object_names=None,
    poses=None,
    selected_only=False,
    interpolation="CONSTANT",
    label="Block key poses",
):
    names = [str(name) for name in object_names or [] if str(name).strip()]
    if names:
        objects = [bpy.data.objects.get(name) for name in names]
        missing = [name for name, obj in zip(names, objects) if obj is None]
        objects = [obj for obj in objects if obj]
    elif selected_only or context.selected_objects:
        objects = list(context.selected_objects)
        missing = []
    else:
        objects = [context.active_object] if context.active_object else []
        missing = []
    objects = [obj for obj in objects if obj]
    if not objects:
        return {"ok": False, "message": "No objects found for blocking key poses", "missing_object_names": missing}
    pose_items = [pose for pose in poses or [] if isinstance(pose, dict)]
    if not pose_items:
        return {"ok": False, "message": "At least one key pose is required for blocking"}
    transform_paths = set()
    for pose in pose_items:
        if pose.get("location") is not None:
            transform_paths.add("location")
        if pose.get("rotation") is not None or pose.get("rotation_euler") is not None:
            transform_paths.add("rotation_euler")
        if pose.get("scale") is not None:
            transform_paths.add("scale")
    if not transform_paths:
        return {"ok": False, "message": "Each blocking pass needs at least one location, rotation, or scale pose value"}
    frames = []
    for pose in pose_items:
        frame = int(pose.get("frame", context.scene.frame_current))
        frames.append(frame)
        hold_frames = max(0, int(pose.get("hold_frames", 0) or 0))
        if hold_frames:
            frames.append(frame + hold_frames)
    frame_start = min(frames)
    frame_end = max(frames)
    interpolation = str(interpolation or "CONSTANT").upper()
    transaction = live_preview.begin(label, context)
    scene = context.scene
    live_preview._record_scene_timeline(scene)
    scene.frame_start = min(scene.frame_start, frame_start)
    scene.frame_end = max(scene.frame_end, frame_end)
    blocked = []
    for obj in objects:
        live_preview._record_object_transform(obj)
        action = live_preview._assign_preview_action(obj)
        base_location = [float(value) for value in obj.location]
        base_rotation = [float(value) for value in obj.rotation_euler]
        base_scale = [float(value) for value in obj.scale]
        keyed_frames = []
        for pose in sorted(pose_items, key=lambda item: int(item.get("frame", frame_start))):
            frame = int(pose.get("frame", frame_start))
            hold_frames = max(0, int(pose.get("hold_frames", 0) or 0))
            location = _coerce_vector(pose.get("location"), base_location) if pose.get("location") is not None else None
            rotation_value = pose.get("rotation_euler", pose.get("rotation"))
            rotation = _coerce_vector(rotation_value, base_rotation) if rotation_value is not None else None
            scale = _coerce_vector(pose.get("scale"), base_scale) if pose.get("scale") is not None else None
            for key_frame in (frame, frame + hold_frames) if hold_frames else (frame,):
                if location is not None:
                    obj.location = location
                    obj.keyframe_insert(data_path="location", frame=key_frame)
                if rotation is not None:
                    obj.rotation_euler = rotation
                    obj.keyframe_insert(data_path="rotation_euler", frame=key_frame)
                if scale is not None:
                    obj.scale = scale
                    obj.keyframe_insert(data_path="scale", frame=key_frame)
                keyed_frames.append(int(key_frame))
        _set_action_interpolation(action, interpolation)
        blocked.append(
            {
                "object": obj.name,
                "action": action.name,
                "frames": sorted(set(keyed_frames)),
                "paths": sorted(transform_paths),
            }
        )
    scene.frame_set(frame_start)
    transaction["applied_steps"].append(
        {
            "type": "block_key_poses",
            "label": label,
            "objects": blocked,
            "frame_start": frame_start,
            "frame_end": frame_end,
            "pose_count": len(pose_items),
            "interpolation": interpolation,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Blocked {len(pose_items)} key pose(s) for {len(blocked)} object(s)",
        "objects": blocked,
        "missing_object_names": missing,
        "transaction_id": transaction["id"],
    }


def create_text_object(
    context,
    *,
    name,
    body,
    location,
    rotation,
    scale,
    size=1.0,
    align_x="CENTER",
    align_y="CENTER",
    material_name="",
    color=None,
    label="Create text object",
):
    transaction = live_preview.begin(label)
    curve = bpy.data.curves.new(f"{name} Data", "FONT")
    curve.body = str(body)
    curve.size = max(0.01, float(size))
    curve.align_x = align_x if align_x in {"LEFT", "CENTER", "RIGHT", "JUSTIFY", "FLUSH"} else "CENTER"
    curve.align_y = align_y if align_y in {"CENTER", "TOP", "BOTTOM"} else "CENTER"
    obj = bpy.data.objects.new(name or "Agent Bridge Text", curve)
    obj.location = _coerce_vector(location, (0.0, 0.0, 0.0))
    obj.rotation_euler = _coerce_vector(rotation, (0.0, 0.0, 0.0))
    obj.scale = _coerce_vector(scale, (1.0, 1.0, 1.0))
    context.scene.collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("curve", curve.name)
    if color is not None:
        material = _material_for_color(material_name or f"{obj.name} Material", color)
        curve.materials.append(material)
    transaction["applied_steps"].append({"type": "create_text_object", "label": label, "object": obj.name})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created text object {obj.name}", "object": obj.name, "transaction_id": transaction["id"]}


def create_curve_path(
    context,
    *,
    name,
    points,
    bevel_depth=0.02,
    cyclic=False,
    material_name="",
    color=None,
    label="Create curve path",
):
    if len(points or []) < 2:
        return {"ok": False, "message": "Curve path needs at least two points"}
    transaction = live_preview.begin(label)
    curve = bpy.data.curves.new(f"{name} Data", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = max(0.0, float(bevel_depth))
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, values in zip(spline.points, points):
        xyz = _coerce_vector(values, (0.0, 0.0, 0.0))
        point.co = (xyz[0], xyz[1], xyz[2], 1.0)
    spline.use_cyclic_u = bool(cyclic)
    obj = bpy.data.objects.new(name or "Agent Bridge Curve", curve)
    context.scene.collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("curve", curve.name)
    if color is not None:
        material = _material_for_color(material_name or f"{obj.name} Material", color)
        curve.materials.append(material)
    transaction["applied_steps"].append({"type": "create_curve_path", "label": label, "object": obj.name})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created curve path {obj.name}", "object": obj.name, "transaction_id": transaction["id"]}


def add_particle_system_to_selected(
    context,
    *,
    name,
    count=200,
    frame_start=1,
    frame_end=80,
    lifetime=80,
    particle_size=0.05,
    label="Add particle system",
):
    selected = [obj for obj in context.selected_objects if obj.type == "MESH"]
    if not selected:
        return {"ok": False, "message": "No selected mesh objects for particle system"}
    transaction = live_preview.begin(label)
    changed = []
    for obj in selected:
        modifier = obj.modifiers.new(name or "Agent Bridge Particles", "PARTICLE_SYSTEM")
        live_preview._record_created_modifier(obj, modifier)
        settings = modifier.particle_system.settings
        settings.name = f"{modifier.name} Settings"
        live_preview._record_created_id("particle_settings", settings.name)
        settings.count = max(1, min(20000, int(count)))
        settings.frame_start = float(frame_start)
        settings.frame_end = float(frame_end)
        settings.lifetime = max(1.0, float(lifetime))
        settings.particle_size = max(0.001, float(particle_size))
        changed.append(obj.name)
    transaction["applied_steps"].append({"type": "add_particle_system", "label": label, "objects": changed})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added particle system to {len(changed)} mesh object(s)",
        "objects": changed,
        "transaction_id": transaction["id"],
    }


def create_basic_armature(
    context,
    *,
    name,
    location,
    rotation,
    show_in_front=True,
    label="Create basic armature",
):
    transaction = live_preview.begin(label)
    bpy.ops.object.armature_add(enter_editmode=False, location=_coerce_vector(location, (0.0, 0.0, 0.0)), rotation=_coerce_vector(rotation, (0.0, 0.0, 0.0)))
    obj = context.object
    if obj is None:
        return {"ok": False, "message": "Armature was not created"}
    obj.name = name or "Agent Bridge Armature"
    obj.data.name = f"{obj.name} Data"
    obj.show_in_front = bool(show_in_front)
    live_preview._record_created_id("object", obj.name)
    live_preview._record_created_id("armature", obj.data.name)
    transaction["applied_steps"].append({"type": "create_basic_armature", "label": label, "object": obj.name})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created armature {obj.name}", "object": obj.name, "transaction_id": transaction["id"]}


def add_copy_transform_constraint(
    context,
    *,
    target_name,
    constraint_type="COPY_LOCATION",
    name="Agent Bridge Copy Transform",
    influence=1.0,
    label="Add copy transform constraint",
):
    target = bpy.data.objects.get(str(target_name or ""))
    if target is None:
        return {"ok": False, "message": f"Target object not found: {target_name}"}
    constraint_type = str(constraint_type or "COPY_LOCATION").upper()
    if constraint_type not in {"COPY_LOCATION", "COPY_ROTATION", "COPY_SCALE", "COPY_TRANSFORMS"}:
        return {"ok": False, "message": f"Unsupported copy constraint type: {constraint_type}"}
    selected = [obj for obj in context.selected_objects if obj.name != target.name]
    if not selected:
        return {"ok": False, "message": "Select at least one constrained object other than the target"}
    transaction = live_preview.begin(label)
    changed = []
    for obj in selected:
        constraint = obj.constraints.new(type=constraint_type)
        constraint.name = name or f"Agent Bridge {constraint_type.title()}"
        constraint.target = target
        constraint.influence = max(0.0, min(1.0, float(influence)))
        live_preview._record_created_constraint(obj, constraint)
        changed.append(obj.name)
    transaction["applied_steps"].append(
        {"type": "add_copy_transform_constraint", "label": label, "target": target.name, "objects": changed}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Added {constraint_type} constraint to {len(changed)} object(s)", "transaction_id": transaction["id"]}


def set_render_settings(
    context,
    *,
    engine="",
    resolution=None,
    fps=None,
    frame_start=None,
    frame_end=None,
    film_transparent=None,
    label="Set render settings",
):
    scene = context.scene
    transaction = live_preview.begin(label)
    _record_scene_render(scene)
    if engine:
        scene.render.engine = str(engine)
    if resolution is not None:
        scene.render.resolution_x = max(16, min(16384, int(resolution[0])))
        scene.render.resolution_y = max(16, min(16384, int(resolution[1])))
    if fps is not None:
        scene.render.fps = max(1, min(240, int(fps)))
    if frame_start is not None:
        scene.frame_start = int(frame_start)
    if frame_end is not None:
        scene.frame_end = int(frame_end)
    if scene.frame_start > scene.frame_end:
        scene.frame_start, scene.frame_end = scene.frame_end, scene.frame_start
    if film_transparent is not None:
        scene.render.film_transparent = bool(film_transparent)
    transaction["applied_steps"].append({"type": "set_render_settings", "label": label, "scene": scene.name})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": "Updated render settings", "transaction_id": transaction["id"]}


def set_camera_settings(
    context,
    *,
    camera_name="",
    lens=None,
    sensor_width=None,
    dof_enabled=None,
    focus_object_name="",
    aperture_fstop=None,
    label="Set camera settings",
):
    camera = bpy.data.objects.get(camera_name) if camera_name else context.scene.camera
    if camera is None or camera.type != "CAMERA":
        return {"ok": False, "message": "A camera object is required"}
    transaction = live_preview.begin(label)
    _record_camera_settings(camera)
    data = camera.data
    if lens is not None:
        data.lens = max(1.0, min(1000.0, float(lens)))
    if sensor_width is not None:
        data.sensor_width = max(1.0, min(200.0, float(sensor_width)))
    if dof_enabled is not None:
        data.dof.use_dof = bool(dof_enabled)
    if focus_object_name:
        focus = bpy.data.objects.get(focus_object_name)
        if focus is None:
            return {"ok": False, "message": f"Focus object not found: {focus_object_name}"}
        data.dof.focus_object = focus
    if aperture_fstop is not None:
        data.dof.aperture_fstop = max(0.1, min(128.0, float(aperture_fstop)))
    transaction["applied_steps"].append({"type": "set_camera_settings", "label": label, "camera": camera.name})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Updated camera settings for {camera.name}", "camera": camera.name, "transaction_id": transaction["id"]}


def set_world_background(context, *, color, label="Set world background"):
    _record_scene_world(context.scene)
    world = context.scene.world or bpy.data.worlds.new("Agent Bridge World")
    if context.scene.world is None:
        context.scene.world = world
        live_preview._record_created_id("world", world.name)
    transaction = live_preview.begin(label)
    _record_world_background(world)
    values = list(color)
    world.color = (
        float(values[0]),
        float(values[1]),
        float(values[2]),
    )
    transaction["applied_steps"].append({"type": "set_world_background", "label": label, "world": world.name})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Updated world background {world.name}", "transaction_id": transaction["id"]}


def _created_data_kind(obj):
    if obj.type == "MESH":
        return "mesh"
    if obj.type in {"CURVE", "FONT"}:
        return "curve"
    if obj.type == "CAMERA":
        return "camera"
    if obj.type == "LIGHT":
        return "light"
    if obj.type == "ARMATURE":
        return "armature"
    return ""


def _link_object_like_source(context, source, duplicate):
    collections = list(source.users_collection)
    if not collections:
        collections = [context.collection or context.scene.collection]
    for collection in collections:
        collection.objects.link(duplicate)


def _resolve_edit_objects(context, *, object_names=None, selected_only=True, include_active=False, max_objects=64):
    names = [str(name) for name in object_names or [] if str(name).strip()]
    missing = []
    if names:
        objects = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj:
                objects.append(obj)
            else:
                missing.append(name)
        return objects[: max(1, int(max_objects or 1))], missing
    if selected_only:
        return list(context.selected_objects)[: max(1, int(max_objects or 1))], missing
    if include_active and context.active_object:
        return [context.active_object], missing
    return [], missing


def create_empty(
    context,
    *,
    name="Agent Bridge Empty",
    location=(0.0, 0.0, 0.0),
    rotation=(0.0, 0.0, 0.0),
    scale=(1.0, 1.0, 1.0),
    empty_display_type="PLAIN_AXES",
    empty_display_size=1.0,
    select_new=True,
    label="Create empty",
):
    transaction = live_preview.begin(label, context)
    obj = bpy.data.objects.new(name or "Agent Bridge Empty", object_data=None)
    display_type = str(empty_display_type or "PLAIN_AXES").upper()
    obj.empty_display_type = display_type if display_type in EMPTY_DISPLAY_TYPES else "PLAIN_AXES"
    obj.empty_display_size = max(0.01, float(empty_display_size))
    obj.location = _coerce_vector(location, (0.0, 0.0, 0.0))
    obj.rotation_euler = _coerce_vector(rotation, (0.0, 0.0, 0.0))
    obj.scale = _coerce_vector(scale, (1.0, 1.0, 1.0))
    context.scene.collection.objects.link(obj)
    live_preview._record_created_id("object", obj.name)
    if select_new:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        context.view_layer.objects.active = obj
    transaction["applied_steps"].append({"type": "create_empty", "label": label, "object": obj.name})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created empty {obj.name}", "object": obj.name, "transaction_id": transaction["id"]}


def set_object_visibility(
    context,
    *,
    object_names=None,
    selected_only=True,
    hide_viewport=None,
    hide_render=None,
    hide_select=None,
    label="Set object visibility",
):
    if hide_viewport is None and hide_render is None and hide_select is None:
        return {"ok": False, "message": "At least one visibility flag is required"}
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
    if not objects:
        return {"ok": False, "message": "No objects found for visibility update", "missing_object_names": missing}
    transaction = live_preview.begin(label, context)
    changed = []
    warnings = []
    for obj in objects:
        live_preview._record_object_visibility(obj)
        if hide_viewport is not None:
            value = bool(hide_viewport)
            obj.hide_viewport = value
            try:
                obj.hide_set(value)
            except Exception as exc:
                warnings.append(f"Could not set viewport hide state for {obj.name}: {type(exc).__name__}: {exc}")
        if hide_render is not None:
            obj.hide_render = bool(hide_render)
        if hide_select is not None:
            obj.hide_select = bool(hide_select)
        changed.append(obj.name)
    transaction["applied_steps"].append({"type": "set_object_visibility", "label": label, "objects": changed})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Updated visibility for {len(changed)} object(s)",
        "objects": changed,
        "missing_object_names": missing,
        "warnings": warnings,
        "transaction_id": transaction["id"],
    }


def set_object_display(
    context,
    *,
    object_names=None,
    selected_only=True,
    display_type="",
    show_name=None,
    show_wire=None,
    show_in_front=None,
    color=None,
    empty_display_type="",
    empty_display_size=None,
    label="Set object display",
):
    has_change = any(
        value is not None and value != ""
        for value in (display_type, show_name, show_wire, show_in_front, color, empty_display_type, empty_display_size)
    )
    if not has_change:
        return {"ok": False, "message": "At least one display setting is required"}
    objects, missing = _resolve_edit_objects(context, object_names=object_names, selected_only=selected_only)
    if not objects:
        return {"ok": False, "message": "No objects found for display update", "missing_object_names": missing}
    display_type = str(display_type or "").upper()
    empty_display_type = str(empty_display_type or "").upper()
    display_color = _coerce_color(color) if color is not None else None
    transaction = live_preview.begin(label, context)
    changed = []
    for obj in objects:
        live_preview._record_object_display(obj)
        if display_type:
            obj.display_type = display_type if display_type in OBJECT_DISPLAY_TYPES else "TEXTURED"
        if show_name is not None:
            obj.show_name = bool(show_name)
        if show_wire is not None and hasattr(obj, "show_wire"):
            obj.show_wire = bool(show_wire)
        if show_in_front is not None:
            obj.show_in_front = bool(show_in_front)
        if display_color is not None:
            obj.color = display_color
        if obj.type == "EMPTY":
            if empty_display_type:
                obj.empty_display_type = empty_display_type if empty_display_type in EMPTY_DISPLAY_TYPES else "PLAIN_AXES"
            if empty_display_size is not None:
                obj.empty_display_size = max(0.01, float(empty_display_size))
        changed.append(obj.name)
    transaction["applied_steps"].append({"type": "set_object_display", "label": label, "objects": changed})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Updated display settings for {len(changed)} object(s)", "objects": changed, "missing_object_names": missing, "transaction_id": transaction["id"]}


def duplicate_selected_objects(
    context,
    *,
    name_prefix="Agent Bridge Copy ",
    offset=(0.0, 0.0, 0.0),
    linked_data=False,
    copy_animation=False,
    select_new=True,
    label="Duplicate selected objects",
):
    selected = [obj for obj in context.selected_objects if obj]
    if not selected:
        return {"ok": False, "message": "No selected objects to duplicate"}
    transaction = live_preview.begin(label, context)
    offset = _coerce_vector(offset, (0.0, 0.0, 0.0))
    created = []
    if select_new:
        bpy.ops.object.select_all(action="DESELECT")
    for obj in selected:
        duplicate = obj.copy()
        duplicate.name = f"{name_prefix}{obj.name}" if name_prefix else f"{obj.name} Copy"
        if obj.data and not linked_data:
            duplicate.data = obj.data.copy()
            duplicate.data.name = f"{duplicate.name} Data"
        if duplicate.animation_data and not copy_animation:
            duplicate.animation_data_clear()
        duplicate.location.x += float(offset[0])
        duplicate.location.y += float(offset[1])
        duplicate.location.z += float(offset[2])
        _link_object_like_source(context, obj, duplicate)
        live_preview._record_created_id("object", duplicate.name)
        data_kind = _created_data_kind(duplicate)
        if data_kind and duplicate.data and duplicate.data is not obj.data:
            live_preview._record_created_id(data_kind, duplicate.data.name)
        if select_new:
            duplicate.select_set(True)
            context.view_layer.objects.active = duplicate
        created.append(duplicate.name)
    transaction["applied_steps"].append(
        {
            "type": "duplicate_selected_objects",
            "label": label,
            "source_objects": [obj.name for obj in selected],
            "created_objects": created,
            "linked_data": bool(linked_data),
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Duplicated {len(created)} object(s)",
        "objects": created,
        "transaction_id": transaction["id"],
    }


def parent_selected_to_empty(
    context,
    *,
    name="Agent Bridge Parent",
    location=None,
    empty_display_type="PLAIN_AXES",
    keep_transform=True,
    label="Parent selected to empty",
):
    selected = [obj for obj in context.selected_objects if obj]
    if not selected:
        return {"ok": False, "message": "No selected objects to parent"}
    transaction = live_preview.begin(label, context)
    if location is None:
        center = Vector((0.0, 0.0, 0.0))
        for obj in selected:
            center += obj.matrix_world.translation
        center /= len(selected)
        location = center
    location = _coerce_vector(location, (0.0, 0.0, 0.0))
    empty = bpy.data.objects.new(name or "Agent Bridge Parent", object_data=None)
    empty.empty_display_type = empty_display_type if empty_display_type in {"PLAIN_AXES", "ARROWS", "CUBE", "SPHERE"} else "PLAIN_AXES"
    empty.empty_display_size = 1.0
    empty.location = location
    context.scene.collection.objects.link(empty)
    live_preview._record_created_id("object", empty.name)
    for obj in selected:
        live_preview._record_object_parent(obj)
        live_preview._record_object_transform(obj)
        world_matrix = obj.matrix_world.copy()
        obj.parent = empty
        if keep_transform:
            obj.matrix_parent_inverse = empty.matrix_world.inverted()
            obj.matrix_world = world_matrix
    bpy.ops.object.select_all(action="DESELECT")
    empty.select_set(True)
    context.view_layer.objects.active = empty
    transaction["applied_steps"].append(
        {
            "type": "parent_selected_to_empty",
            "label": label,
            "empty": empty.name,
            "children": [obj.name for obj in selected],
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Parented {len(selected)} object(s) to {empty.name}",
        "empty": empty.name,
        "children": [obj.name for obj in selected],
        "transaction_id": transaction["id"],
    }


def align_selected_objects(context, *, axis="Z", mode="ACTIVE", value=None, label="Align selected objects"):
    selected = [obj for obj in context.selected_objects if obj]
    if len(selected) < 2:
        return {"ok": False, "message": "Select at least two objects to align"}
    axis_index, axis = _axis_index(axis)
    mode = str(mode or "ACTIVE").upper()
    if mode == "VALUE":
        if value is None:
            return {"ok": False, "message": "Alignment mode VALUE requires a numeric value"}
        target = float(value)
    elif mode == "MIN":
        target = min(float(obj.location[axis_index]) for obj in selected)
    elif mode == "MAX":
        target = max(float(obj.location[axis_index]) for obj in selected)
    elif mode == "CENTER":
        target = sum(float(obj.location[axis_index]) for obj in selected) / len(selected)
    else:
        active = context.view_layer.objects.active if context.view_layer else None
        if active is None:
            return {"ok": False, "message": "Alignment mode ACTIVE requires an active object"}
        target = float(active.location[axis_index])
        mode = "ACTIVE"

    transaction = live_preview.begin(label, context)
    for obj in selected:
        live_preview._record_object_transform(obj)
        obj.location[axis_index] = target
    transaction["applied_steps"].append(
        {
            "type": "align_selected_objects",
            "label": label,
            "objects": [obj.name for obj in selected],
            "axis": axis,
            "mode": mode,
            "value": target,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Aligned {len(selected)} object(s) on {axis}",
        "objects": [obj.name for obj in selected],
        "axis": axis,
        "value": target,
        "transaction_id": transaction["id"],
    }


def distribute_selected_objects(
    context,
    *,
    axis="X",
    start=None,
    end=None,
    label="Distribute selected objects",
):
    selected = [obj for obj in context.selected_objects if obj]
    if len(selected) < 2:
        return {"ok": False, "message": "Select at least two objects to distribute"}
    axis_index, axis = _axis_index(axis)
    ordered = sorted(selected, key=lambda obj: (float(obj.location[axis_index]), obj.name))
    if start is None:
        start = float(ordered[0].location[axis_index])
    if end is None:
        end = float(ordered[-1].location[axis_index])
    start = float(start)
    end = float(end)
    transaction = live_preview.begin(label, context)
    positions = {}
    for index, obj in enumerate(ordered):
        factor = index / max(1, len(ordered) - 1)
        position = start + (end - start) * factor
        live_preview._record_object_transform(obj)
        obj.location[axis_index] = position
        positions[obj.name] = position
    transaction["applied_steps"].append(
        {
            "type": "distribute_selected_objects",
            "label": label,
            "objects": [obj.name for obj in ordered],
            "axis": axis,
            "start": start,
            "end": end,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Distributed {len(ordered)} object(s) on {axis}",
        "objects": [obj.name for obj in ordered],
        "positions": positions,
        "transaction_id": transaction["id"],
    }


def shade_smooth_selected(context, *, add_weighted_normals=True, label="Shade smooth selected"):
    selected = [obj for obj in context.selected_objects if obj.type == "MESH" and obj.data]
    if not selected:
        return {"ok": False, "message": "No selected mesh objects to shade smooth"}
    transaction = live_preview.begin(label)
    changed = []
    for obj in selected:
        _record_mesh_smoothing(obj.data)
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        if add_weighted_normals and obj.modifiers.get("Agent Bridge Weighted Normals") is None:
            modifier = obj.modifiers.new("Agent Bridge Weighted Normals", "WEIGHTED_NORMAL")
            live_preview._record_created_modifier(obj, modifier)
        changed.append(obj.name)
    transaction["applied_steps"].append({"type": "shade_smooth_selected", "label": label, "objects": changed})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Smoothed {len(changed)} mesh object(s)", "objects": changed, "transaction_id": transaction["id"]}


def add_bevel_and_subsurf(
    context,
    *,
    bevel_width=0.06,
    bevel_segments=3,
    subsurf_levels=1,
    weighted_normals=True,
    label="Add bevel and subdivision",
):
    selected = [obj for obj in context.selected_objects if obj.type == "MESH" and obj.data]
    if not selected:
        return {"ok": False, "message": "No selected mesh objects for bevel/subdivision"}
    transaction = live_preview.begin(label)
    changed = []
    for obj in selected:
        bevel = obj.modifiers.new("Agent Bridge Detail Bevel", "BEVEL")
        bevel.width = max(0.0, min(10.0, float(bevel_width)))
        bevel.segments = max(1, min(16, int(bevel_segments)))
        live_preview._record_created_modifier(obj, bevel)
        if int(subsurf_levels) > 0:
            subsurf = obj.modifiers.new("Agent Bridge Detail Subdivision", "SUBSURF")
            subsurf.levels = max(0, min(3, int(subsurf_levels)))
            subsurf.render_levels = max(0, min(3, int(subsurf_levels)))
            live_preview._record_created_modifier(obj, subsurf)
        if weighted_normals:
            normals = obj.modifiers.new("Agent Bridge Weighted Normals", "WEIGHTED_NORMAL")
            live_preview._record_created_modifier(obj, normals)
        changed.append(obj.name)
    transaction["applied_steps"].append({"type": "add_bevel_and_subsurf", "label": label, "objects": changed})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Added bevel/detail modifiers to {len(changed)} mesh object(s)", "objects": changed, "transaction_id": transaction["id"]}


def create_wheel_assembly(
    context,
    *,
    name,
    location,
    radius=0.45,
    tire_thickness=0.12,
    axis="Y",
    tire_material_name="Agent Bridge Tire Rubber",
    rim_material_name="Agent Bridge Wheel Rim",
    label="Create wheel assembly",
):
    transaction = live_preview.begin(label)
    tire_material = _material_for_color(tire_material_name, (0.005, 0.005, 0.006, 1.0))
    rim_material = _material_for_color(rim_material_name, (0.72, 0.72, 0.68, 1.0))
    objects = _create_wheel_parts(
        context,
        name=name or "Agent Bridge Wheel",
        location=_coerce_vector(location, (0.0, 0.0, 0.0)),
        radius=radius,
        thickness=tire_thickness,
        axis=axis,
        tire_material=tire_material,
        rim_material=rim_material,
    )
    transaction["applied_steps"].append(
        {"type": "create_wheel_assembly", "label": label, "objects": [obj.name for obj in objects]}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Created wheel assembly {name}", "objects": [obj.name for obj in objects], "transaction_id": transaction["id"]}


def add_panel_seams(
    context,
    *,
    target_name="",
    seam_material_name="Agent Bridge Panel Seams",
    bevel_depth=0.015,
    label="Add panel seams",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or target.type != "MESH":
        return {"ok": False, "message": "A mesh target object is required for panel seams"}
    transaction = live_preview.begin(label)
    bounds = _bounds_world(target)
    min_x, min_y, min_z = bounds["min"]
    max_x, max_y, max_z = bounds["max"]
    sx, sy, sz = bounds["size"]
    seam_material = _material_for_color(seam_material_name, (0.01, 0.008, 0.006, 1.0))
    z_top = max_z + max(0.01, sz * 0.01)
    y_left = min_y - max(0.01, sy * 0.01)
    y_right = max_y + max(0.01, sy * 0.01)
    x_front = min_x + sx * 0.28
    x_mid = min_x + sx * 0.52
    x_rear = min_x + sx * 0.76
    created = []
    for index, x in enumerate((x_front, x_mid, x_rear), start=1):
        created.append(
            _create_curve_line(
                context,
                f"{target.name} Panel Seam Top {index}",
                [(x, min_y, z_top), (x, max_y, z_top)],
                bevel_depth,
                seam_material,
            ).name
        )
    for side_name, y in (("L", y_left), ("R", y_right)):
        z_side = min_z + sz * 0.48
        created.append(
            _create_curve_line(
                context,
                f"{target.name} Door Seam {side_name}",
                [(x_mid, y, min_z + sz * 0.12), (x_mid, y, z_side)],
                bevel_depth,
                seam_material,
            ).name
        )
        created.append(
            _create_curve_line(
                context,
                f"{target.name} Belt Line {side_name}",
                [(min_x + sx * 0.18, y, z_side), (max_x - sx * 0.12, y, z_side)],
                bevel_depth,
                seam_material,
            ).name
        )
    transaction["applied_steps"].append({"type": "add_panel_seams", "label": label, "target": target.name, "objects": created})
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {"ok": True, "message": f"Added panel seams around {target.name}", "objects": created, "transaction_id": transaction["id"]}


def add_window_materials(
    context,
    *,
    target_name="",
    material_name="Agent Bridge Blue Glass",
    color=(0.08, 0.35, 0.65, 0.42),
    create_panels=True,
    label="Add window materials",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    transaction = live_preview.begin(label)
    material = bpy.data.materials.get(material_name)
    if material is None:
        material = bpy.data.materials.new(material_name)
        live_preview._record_created_id("material", material.name)
    else:
        _record_shader_material(material)
    rgba = (
        float(color[0]),
        float(color[1]),
        float(color[2]),
        float(color[3]) if len(color) > 3 else 0.45,
    )
    material.diffuse_color = rgba
    material.use_nodes = True
    principled = _ensure_principled_material(material)
    _set_socket_value(principled.inputs.get("Base Color"), rgba)
    _set_socket_value(principled.inputs.get("Alpha"), rgba[3])
    _set_socket_value(principled.inputs.get("Roughness"), 0.08)
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "BLENDED"
    elif hasattr(material, "blend_method"):
        material.blend_method = "BLEND"

    assigned = []
    for obj in context.scene.objects:
        lowered = obj.name.lower()
        if obj.type == "MESH" and any(word in lowered for word in ("window", "glass", "windshield")):
            live_preview._record_object_materials(obj)
            if obj.material_slots:
                obj.material_slots[0].material = material
            else:
                obj.data.materials.append(material)
            assigned.append(obj.name)

    created = []
    if create_panels and target and target.type == "MESH":
        bounds = _bounds_world(target)
        min_x, min_y, min_z = bounds["min"]
        max_x, max_y, max_z = bounds["max"]
        sx, sy, sz = bounds["size"]
        thickness = max(0.015, min(sx, sy, sz) * 0.025)
        z = min_z + sz * 0.72
        panel_height = max(0.05, sz * 0.22)
        created.append(
            _create_cube_object(
                context,
                f"{target.name} Windshield Glass",
                (min_x + sx * 0.3, min_y - thickness, z),
                (sx * 0.18, thickness, panel_height),
                material,
            ).name
        )
        created.append(
            _create_cube_object(
                context,
                f"{target.name} Rear Glass",
                (max_x - sx * 0.28, min_y - thickness, z),
                (sx * 0.16, thickness, panel_height),
                material,
            ).name
        )
        for side_name, y in (("Left", min_y - thickness), ("Right", max_y + thickness)):
            created.append(
                _create_cube_object(
                    context,
                    f"{target.name} {side_name} Side Glass",
                    (min_x + sx * 0.52, y, z),
                    (sx * 0.24, thickness, panel_height),
                    material,
                ).name
            )
    transaction["applied_steps"].append(
        {"type": "add_window_materials", "label": label, "material": material.name, "assigned": assigned, "created": created}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Prepared window material {material.name}",
        "material": material.name,
        "assigned_objects": assigned,
        "created_objects": created,
        "transaction_id": transaction["id"],
    }


def create_studio_product_stage(
    context,
    *,
    target_name="",
    stage_name="Agent Bridge Product Stage",
    floor=True,
    backdrop=True,
    lighting=True,
    camera=True,
    label="Create studio product stage",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or not hasattr(target, "bound_box"):
        return {"ok": False, "message": "A target object with bounds is required for a studio stage"}
    transaction = live_preview.begin(label, context)
    bounds = _bounds_world(target)
    min_x, min_y, min_z = bounds["min"]
    max_x, max_y, max_z = bounds["max"]
    center_x, center_y, center_z = bounds["center"]
    sx, sy, sz = bounds["size"]
    max_dim = max(1.0, sx, sy, sz)
    stage_name = str(stage_name or "Agent Bridge Product Stage")
    floor_material = _material_for_color(f"{stage_name} Warm Gray", (0.58, 0.57, 0.54, 1.0))
    backdrop_material = _material_for_color(f"{stage_name} Soft Backdrop", (0.72, 0.71, 0.68, 1.0))

    created = []
    floor_thickness = max(0.02, max_dim * 0.025)
    if floor:
        created.append(
            _create_cube_object(
                context,
                f"{stage_name} Floor",
                (center_x, center_y, min_z - floor_thickness / 2.0),
                (max_dim * 2.8, max_dim * 2.2, floor_thickness),
                floor_material,
            ).name
        )
    if backdrop:
        created.append(
            _create_cube_object(
                context,
                f"{stage_name} Backdrop",
                (center_x, max_y + max_dim * 0.72, min_z + max_dim * 0.7),
                (max_dim * 2.8, floor_thickness, max_dim * 1.45),
                backdrop_material,
            ).name
        )

    target_empty = _create_empty_target(
        context,
        f"{stage_name} Target",
        (center_x, center_y, center_z),
        display_size=max_dim * 0.12,
    )
    created.append(target_empty.name)

    lights = []
    if lighting:
        key = _create_area_light(
            context,
            f"{stage_name} Key Light",
            (min_x - max_dim * 1.2, min_y - max_dim * 1.35, max_z + max_dim * 1.3),
            energy=650.0,
            size=max_dim * 1.15,
            color=(1.0, 0.93, 0.84),
            target=target_empty,
        )
        fill = _create_area_light(
            context,
            f"{stage_name} Fill Light",
            (max_x + max_dim * 1.3, min_y - max_dim * 0.9, max_z + max_dim * 0.75),
            energy=180.0,
            size=max_dim * 1.7,
            color=(0.78, 0.86, 1.0),
            target=target_empty,
        )
        rim = _create_area_light(
            context,
            f"{stage_name} Rim Light",
            (center_x, max_y + max_dim * 1.25, max_z + max_dim * 1.1),
            energy=360.0,
            size=max_dim * 0.75,
            color=(1.0, 1.0, 0.94),
            target=target_empty,
        )
        lights = [key.name, fill.name, rim.name]
        created.extend(lights)

    camera_name = ""
    if camera:
        live_preview._record_scene_camera(context.scene)
        data = bpy.data.cameras.new(name=f"{stage_name} Camera")
        data.lens = 70.0
        data.dof.use_dof = True
        data.dof.focus_object = target_empty
        data.dof.aperture_fstop = 5.6
        camera_obj = bpy.data.objects.new(name=f"{stage_name} Camera", object_data=data)
        camera_obj.location = (center_x - max_dim * 1.8, min_y - max_dim * 2.2, center_z + max_dim * 1.0)
        context.scene.collection.objects.link(camera_obj)
        live_preview._record_created_id("object", camera_obj.name)
        live_preview._record_created_id("camera", data.name)
        _track_to_target(camera_obj, target_empty)
        context.scene.camera = camera_obj
        camera_name = camera_obj.name
        created.append(camera_obj.name)

    transaction["applied_steps"].append(
        {
            "type": "create_studio_product_stage",
            "label": label,
            "target": target.name,
            "created_objects": created,
            "lights": lights,
            "camera": camera_name,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Created product stage around {target.name}",
        "target": target.name,
        "created_objects": created,
        "lights": lights,
        "camera": camera_name,
        "transaction_id": transaction["id"],
    }


def add_dimension_callouts(
    context,
    *,
    target_name="",
    unit_label="bu",
    include_width=True,
    include_depth=True,
    include_height=True,
    label="Add dimension callouts",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or not hasattr(target, "bound_box"):
        return {"ok": False, "message": "A target object with bounds is required for dimension callouts"}
    if not any((include_width, include_depth, include_height)):
        return {"ok": False, "message": "Enable at least one dimension callout"}
    transaction = live_preview.begin(label, context)
    bounds = _bounds_world(target)
    min_x, min_y, min_z = bounds["min"]
    max_x, max_y, max_z = bounds["max"]
    center_x, center_y, center_z = bounds["center"]
    sx, sy, sz = bounds["size"]
    max_dim = max(1.0, sx, sy, sz)
    offset = max_dim * 0.18
    line_material = _material_for_color(f"{target.name} Dimension Lines", (0.02, 0.02, 0.02, 1.0))
    text_material = _material_for_color(f"{target.name} Dimension Text", (0.95, 0.95, 0.88, 1.0))
    bevel = max(0.004, max_dim * 0.006)
    text_size = max(0.08, max_dim * 0.075)
    unit_label = str(unit_label or "bu")
    created = []
    measurements = {}

    def add_line(name, points, text, text_location, rotation=(math.radians(60.0), 0.0, 0.0)):
        line = _create_curve_line(context, name, points, bevel, line_material)
        label_obj = _create_text_label(
            context,
            f"{name} Label",
            text,
            text_location,
            size=text_size,
            rotation=rotation,
            material=text_material,
        )
        created.extend([line.name, label_obj.name])

    if include_width:
        y = min_y - offset
        z = min_z + offset * 0.35
        value = float(sx)
        measurements["width"] = value
        add_line(
            f"{target.name} Width Callout",
            [(min_x, y, z), (max_x, y, z)],
            f"W {value:.2f} {unit_label}",
            (center_x, y, z + offset * 0.22),
        )
    if include_depth:
        x = max_x + offset
        z = min_z + offset * 0.35
        value = float(sy)
        measurements["depth"] = value
        add_line(
            f"{target.name} Depth Callout",
            [(x, min_y, z), (x, max_y, z)],
            f"D {value:.2f} {unit_label}",
            (x, center_y, z + offset * 0.22),
            rotation=(math.radians(60.0), 0.0, math.radians(90.0)),
        )
    if include_height:
        x = max_x + offset
        y = max_y + offset
        value = float(sz)
        measurements["height"] = value
        add_line(
            f"{target.name} Height Callout",
            [(x, y, min_z), (x, y, max_z)],
            f"H {value:.2f} {unit_label}",
            (x, y, center_z),
            rotation=(math.radians(70.0), 0.0, math.radians(90.0)),
        )

    transaction["applied_steps"].append(
        {
            "type": "add_dimension_callouts",
            "label": label,
            "target": target.name,
            "created_objects": created,
            "measurements": measurements,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Added dimension callouts for {target.name}",
        "target": target.name,
        "created_objects": created,
        "measurements": measurements,
        "transaction_id": transaction["id"],
    }


def apply_lighting_preset(
    context,
    *,
    target_name="",
    preset="product_softbox",
    rig_name="Agent Bridge Lighting",
    label="Apply lighting preset",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or not hasattr(target, "bound_box"):
        return {"ok": False, "message": "A target object with bounds is required for a lighting preset"}
    preset_key = str(preset or "product_softbox").lower()
    lights_spec = LIGHTING_PRESETS.get(preset_key) or LIGHTING_PRESETS["product_softbox"]
    transaction = live_preview.begin(label, context)
    bounds = _bounds_world(target)
    center_x, center_y, center_z = bounds["center"]
    sx, sy, sz = bounds["size"]
    max_dim = max(1.0, sx, sy, sz)
    rig_name = str(rig_name or "Agent Bridge Lighting")
    target_empty = _create_empty_target(
        context,
        f"{rig_name} Target",
        (center_x, center_y, center_z),
        display_size=max_dim * 0.12,
    )
    created = [target_empty.name]
    lights = []
    for suffix, factors, energy, size, color in lights_spec:
        location = (
            center_x + factors[0] * max_dim,
            center_y + factors[1] * max_dim,
            center_z + factors[2] * max_dim,
        )
        light = _create_area_light(
            context,
            f"{rig_name} {suffix}",
            location,
            energy=energy,
            size=max_dim * size,
            color=color,
            target=target_empty,
        )
        lights.append(light.name)
        created.append(light.name)
    transaction["applied_steps"].append(
        {
            "type": "apply_lighting_preset",
            "label": label,
            "target": target.name,
            "preset": preset_key if preset_key in LIGHTING_PRESETS else "product_softbox",
            "created_objects": created,
            "lights": lights,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Applied {preset_key if preset_key in LIGHTING_PRESETS else 'product_softbox'} lighting around {target.name}",
        "target": target.name,
        "preset": preset_key if preset_key in LIGHTING_PRESETS else "product_softbox",
        "created_objects": created,
        "lights": lights,
        "transaction_id": transaction["id"],
    }


def create_material_palette(
    context,
    *,
    palette_name="Agent Bridge Material Palette",
    palette="product_neutral",
    create_swatches=True,
    assign_to_selected=False,
    label="Create material palette",
):
    palette_key = str(palette or "product_neutral").lower()
    entries = MATERIAL_PALETTES.get(palette_key) or MATERIAL_PALETTES["product_neutral"]
    transaction = live_preview.begin(label, context)
    palette_name = str(palette_name or "Agent Bridge Material Palette")
    selected_for_assignment = [obj for obj in context.selected_objects if obj.type == "MESH" and obj.data]
    materials = []
    for suffix, color in entries:
        material = _material_for_color(f"{palette_name} {suffix}", color)
        materials.append(material)

    swatches = []
    if create_swatches:
        active = context.active_object
        if active is not None and hasattr(active, "bound_box"):
            bounds = _bounds_world(active)
            min_x, min_y, min_z = bounds["min"]
            sx, sy, sz = bounds["size"]
            max_dim = max(1.0, sx, sy, sz)
            start = (min_x, min_y - max_dim * 0.35, min_z + max_dim * 0.05)
            size = max_dim * 0.08
            gap = size * 1.35
        else:
            start = (0.0, -2.0, 0.05)
            size = 0.12
            gap = 0.18
        for index, material in enumerate(materials):
            swatch = _create_cube_object(
                context,
                f"{palette_name} Swatch {index + 1}",
                (start[0] + gap * index, start[1], start[2]),
                (size, size, size),
                material,
            )
            swatches.append(swatch.name)

    assigned = []
    if assign_to_selected:
        for index, obj in enumerate(selected_for_assignment):
            material = materials[index % len(materials)]
            live_preview._record_object_materials(obj)
            obj.data.materials.clear()
            obj.data.materials.append(material)
            assigned.append({"object": obj.name, "material": material.name})

    transaction["applied_steps"].append(
        {
            "type": "create_material_palette",
            "label": label,
            "palette": palette_key if palette_key in MATERIAL_PALETTES else "product_neutral",
            "materials": [material.name for material in materials],
            "swatches": swatches,
            "assigned": assigned,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Created {len(materials)} material palette entries",
        "palette": palette_key if palette_key in MATERIAL_PALETTES else "product_neutral",
        "materials": [material.name for material in materials],
        "swatches": swatches,
        "assigned": assigned,
        "transaction_id": transaction["id"],
    }


def create_product_turntable_setup(
    context,
    *,
    target_name="",
    frame_start=1,
    frame_end=120,
    revolutions=1.0,
    radius=0.0,
    height=0.0,
    setup_name="Agent Bridge Product Turntable",
    create_stage=True,
    label="Create product turntable setup",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or not hasattr(target, "bound_box"):
        return {"ok": False, "message": "A target object with bounds is required for a turntable setup"}
    frame_start, frame_end, error = _normalize_frame_range(frame_start, frame_end, "Product turntable setup")
    if error:
        return error
    transaction = live_preview.begin(label, context)
    bounds = _bounds_world(target)
    sx, sy, sz = bounds["size"]
    max_dim = max(1.0, sx, sy, sz)
    stage_result = {}
    if create_stage:
        stage_result = create_studio_product_stage(
            context,
            target_name=target.name,
            stage_name=f"{setup_name} Stage",
            floor=True,
            backdrop=True,
            lighting=True,
            camera=False,
            label=label,
        )
    animation_result = create_turntable_animation(
        context,
        object_name=target.name,
        frame_start=frame_start,
        frame_end=frame_end,
        axis="Z",
        revolutions=revolutions,
        add_cycles=True,
        label=label,
    )
    orbit_result = live_preview.create_camera_orbit(
        context,
        target_name=target.name,
        frame_start=frame_start,
        frame_end=frame_end,
        radius=float(radius) if float(radius or 0.0) > 0.0 else max_dim * 2.6,
        height=float(height) if float(height or 0.0) > 0.0 else max_dim * 0.9,
        name=f"{setup_name} Camera",
        lens=70.0,
        label=label,
    )
    transaction["applied_steps"].append(
        {
            "type": "create_product_turntable_setup",
            "label": label,
            "target": target.name,
            "frame_start": frame_start,
            "frame_end": frame_end,
            "stage_created": bool(stage_result.get("ok")),
            "camera": orbit_result.get("camera", ""),
            "action": animation_result.get("action", ""),
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": bool(animation_result.get("ok") and orbit_result.get("ok") and (not create_stage or stage_result.get("ok"))),
        "message": f"Created product turntable setup for {target.name}",
        "target": target.name,
        "stage": stage_result,
        "animation": animation_result,
        "camera_orbit": orbit_result,
        "transaction_id": transaction["id"],
    }


def organize_scene_for_production(
    context,
    *,
    collection_prefix="Agent Bridge Production",
    selected_only=False,
    label="Organize scene for production",
):
    collection_prefix = str(collection_prefix or "Agent Bridge Production")
    objects = list(context.selected_objects) if selected_only else list(context.scene.objects)
    objects = [obj for obj in objects if obj and not obj.name.startswith(collection_prefix)]
    if not objects:
        return {"ok": False, "message": "No objects available to organize"}
    transaction = live_preview.begin(label, context)
    buckets = {
        "Meshes": {"MESH"},
        "Cameras": {"CAMERA"},
        "Lights": {"LIGHT"},
        "Curves Text": {"CURVE", "FONT"},
        "Helpers": {"EMPTY", "ARMATURE"},
    }
    collections = {}
    linked = []
    for obj in objects:
        bucket_name = "Other"
        for name, types in buckets.items():
            if obj.type in types:
                bucket_name = name
                break
        collection_name = f"{collection_prefix} - {bucket_name}"
        collection = collections.get(collection_name) or bpy.data.collections.get(collection_name)
        if collection is None:
            collection = bpy.data.collections.new(collection_name)
            context.scene.collection.children.link(collection)
            live_preview._record_created_id("collection", collection.name)
        collections[collection_name] = collection
        live_preview._record_object_collections(obj)
        if collection.objects.get(obj.name) is None:
            collection.objects.link(obj)
        linked.append({"object": obj.name, "collection": collection.name})
    transaction["applied_steps"].append(
        {
            "type": "organize_scene_for_production",
            "label": label,
            "collections": sorted(collections),
            "linked": linked,
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Linked {len(linked)} object(s) into production collections",
        "collections": sorted(collections),
        "linked": linked,
        "transaction_id": transaction["id"],
    }


def apply_vehicle_refinement_template(
    context,
    *,
    target_name="",
    detail_level="medium",
    label="Apply vehicle refinement template",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or target.type != "MESH":
        return {"ok": False, "message": "A mesh target object is required for vehicle refinement"}
    transaction = live_preview.begin(label, context)
    bounds = _bounds_world(target)
    min_x, min_y, min_z = bounds["min"]
    max_x, max_y, max_z = bounds["max"]
    sx, sy, sz = bounds["size"]
    radius = max(0.12, min(sx, sy, sz) * 0.22)
    thickness = radius * 0.28
    y_offset = max(0.06, sy * 0.55)
    z_wheel = min_z + radius * 0.95
    x_front = min_x + sx * 0.18
    x_rear = max_x - sx * 0.18

    created = []
    with _preserve_selection(context):
        bpy.ops.object.select_all(action="DESELECT")
        target.select_set(True)
        context.view_layer.objects.active = target
        add_bevel_and_subsurf(
            context,
            bevel_width=max(0.01, min(sx, sy, sz) * 0.018),
            bevel_segments=3 if detail_level != "low" else 2,
            subsurf_levels=1 if detail_level in {"medium", "high"} else 0,
            weighted_normals=True,
            label=label,
        )
        shade_smooth_selected(context, add_weighted_normals=True, label=label)

        tire_material = _material_for_color("Agent Bridge Tire Rubber", (0.005, 0.005, 0.006, 1.0))
        rim_material = _material_for_color("Agent Bridge Wheel Rim", (0.72, 0.72, 0.68, 1.0))
        for side_name, y in (("Left", min_y - y_offset * 0.08), ("Right", max_y + y_offset * 0.08)):
            for axle_name, x in (("Front", x_front), ("Rear", x_rear)):
                created.extend(
                    obj.name
                    for obj in _create_wheel_parts(
                        context,
                        name=f"{target.name} {side_name} {axle_name} Wheel",
                        location=(x, y, z_wheel),
                        radius=radius,
                        thickness=thickness,
                        axis="Y",
                        tire_material=tire_material,
                        rim_material=rim_material,
                    )
                )

        glass = add_window_materials(context, target_name=target.name, create_panels=True, label=label)
        seams = add_panel_seams(context, target_name=target.name, bevel_depth=max(0.008, min(sx, sy, sz) * 0.006), label=label)
        created.extend(glass.get("created_objects") or [])
        created.extend(seams.get("objects") or [])

        headlight_material = _material_for_color("Agent Bridge Headlight White", (1.0, 0.95, 0.82, 1.0))
        tail_material = _material_for_color("Agent Bridge Tail Light Red", (1.0, 0.02, 0.0, 1.0))
        light_z = min_z + sz * 0.36
        light_scale = (sx * 0.035, sy * 0.035, sz * 0.09)
        for y in (min_y + sy * 0.28, max_y - sy * 0.28):
            created.append(
                _create_cube_object(
                    context,
                    f"{target.name} Front Headlight",
                    (min_x - sx * 0.01, y, light_z),
                    light_scale,
                    headlight_material,
                ).name
            )
            created.append(
                _create_cube_object(
                    context,
                    f"{target.name} Rear Taillight",
                    (max_x + sx * 0.01, y, light_z),
                    light_scale,
                    tail_material,
                ).name
            )

    transaction["applied_steps"].append(
        {"type": "apply_vehicle_refinement_template", "label": label, "target": target.name, "created_objects": created}
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Applied vehicle refinement template around {target.name}",
        "target": target.name,
        "created_objects": created,
        "transaction_id": transaction["id"],
    }


def apply_product_refinement_template(
    context,
    *,
    target_name="",
    style="studio",
    include_stage=True,
    include_callouts=True,
    include_turntable=False,
    label="Apply product refinement template",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or not hasattr(target, "bound_box"):
        return {"ok": False, "message": "A target object with bounds is required for product refinement"}
    transaction = live_preview.begin(label, context)
    bounds = _bounds_world(target)
    sx, sy, sz = bounds["size"]
    min_dim = max(0.05, min(sx, sy, sz))
    style_key = str(style or "studio").lower()
    style_spec = PRODUCT_REFINEMENT_STYLES.get(style_key) or PRODUCT_REFINEMENT_STYLES["studio"]
    material_name, material_color = style_spec["material"]
    material = _material_for_color(material_name, material_color)

    stage_result = {}
    callout_result = {}
    turntable_result = {}
    with _preserve_selection(context):
        bpy.ops.object.select_all(action="DESELECT")
        target.select_set(True)
        context.view_layer.objects.active = target
        if target.type == "MESH" and target.data:
            live_preview._record_object_materials(target)
            if target.material_slots:
                target.material_slots[0].material = material
            else:
                target.data.materials.append(material)
            add_bevel_and_subsurf(
                context,
                bevel_width=max(0.006, min_dim * float(style_spec["bevel_factor"])),
                bevel_segments=int(style_spec["segments"]),
                subsurf_levels=1,
                weighted_normals=True,
                label=label,
            )
            shade_smooth_selected(context, add_weighted_normals=True, label=label)

        if include_stage:
            stage_result = create_studio_product_stage(
                context,
                target_name=target.name,
                stage_name=f"{target.name} Product Stage",
                floor=True,
                backdrop=True,
                lighting=True,
                camera=True,
                label=label,
            )

        if include_callouts:
            callout_result = add_dimension_callouts(
                context,
                target_name=target.name,
                unit_label="bu",
                include_width=True,
                include_depth=True,
                include_height=True,
                label=label,
            )

        if include_turntable:
            turntable_result = create_product_turntable_setup(
                context,
                target_name=target.name,
                frame_start=context.scene.frame_start,
                frame_end=max(context.scene.frame_end, context.scene.frame_start + 96),
                revolutions=1.0,
                setup_name=f"{target.name} Product Review",
                create_stage=False,
                label=label,
            )

    created = []
    created.extend(stage_result.get("created_objects") or [])
    created.extend(callout_result.get("created_objects") or [])
    if turntable_result.get("camera_orbit", {}).get("camera"):
        created.append(turntable_result["camera_orbit"]["camera"])
    features = ["material polish"]
    if target.type == "MESH":
        features.append("smooth bevel stack")
    if stage_result.get("ok"):
        features.append("studio stage")
    if callout_result.get("ok"):
        features.append("dimension callouts")
    if turntable_result.get("ok"):
        features.append("turntable review")

    transaction["applied_steps"].append(
        {
            "type": "apply_product_refinement_template",
            "label": label,
            "target": target.name,
            "style": style_key if style_key in PRODUCT_REFINEMENT_STYLES else "studio",
            "material": material.name,
            "created_objects": created,
            "features": features,
            "expected_changes": f"Polishes {target.name} for product presentation with {', '.join(features)}.",
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Applied product refinement template around {target.name}",
        "target": target.name,
        "style": style_key if style_key in PRODUCT_REFINEMENT_STYLES else "studio",
        "material": material.name,
        "stage": stage_result,
        "callouts": callout_result,
        "turntable": turntable_result,
        "created_objects": created,
        "features": features,
        "transaction_id": transaction["id"],
    }


def apply_character_refinement_template(
    context,
    *,
    target_name="",
    character_style="neutral",
    detail_level="medium",
    create_guides=True,
    label="Apply character refinement template",
):
    target = bpy.data.objects.get(target_name) if target_name else context.active_object
    if target is None or target.type != "MESH":
        return {"ok": False, "message": "A mesh target object is required for character refinement"}
    transaction = live_preview.begin(label, context)
    bounds = _bounds_world(target)
    min_x, min_y, min_z = bounds["min"]
    max_x, max_y, max_z = bounds["max"]
    center_x, center_y, center_z = bounds["center"]
    sx, sy, sz = bounds["size"]
    min_dim = max(0.05, min(sx, sy, sz))
    max_dim = max(1.0, sx, sy, sz)
    style_key = str(character_style or "neutral").lower()
    palette = CHARACTER_PALETTES.get(style_key) or CHARACTER_PALETTES["neutral"]
    skin_material = _material_for_color(*palette["skin"])
    hair_material = _material_for_color(*palette["hair"])
    eye_material = _material_for_color(*palette["eye"])
    accent_material = _material_for_color(*palette["accent"])
    guide_material = _material_for_color(*palette["guide"])

    head_radius = max(0.12, min_dim * 0.32)
    neck_height = head_radius * 0.65
    head_z = max_z + neck_height + head_radius * 0.95
    created = []
    with _preserve_selection(context):
        bpy.ops.object.select_all(action="DESELECT")
        target.select_set(True)
        context.view_layer.objects.active = target
        live_preview._record_object_materials(target)
        if target.material_slots:
            target.material_slots[0].material = accent_material
        else:
            target.data.materials.append(accent_material)
        add_bevel_and_subsurf(
            context,
            bevel_width=max(0.005, min_dim * 0.012),
            bevel_segments=3 if detail_level != "low" else 2,
            subsurf_levels=1 if detail_level in {"medium", "high"} else 0,
            weighted_normals=True,
            label=label,
        )
        shade_smooth_selected(context, add_weighted_normals=True, label=label)

        neck = _create_cylinder_object(
            context,
            f"{target.name} Character Neck",
            (center_x, center_y, max_z + neck_height * 0.42),
            head_radius * 0.28,
            neck_height,
            skin_material,
            vertices=24,
        )
        head = _create_uv_sphere_object(
            context,
            f"{target.name} Character Head",
            (center_x, center_y, head_z),
            head_radius,
            skin_material,
            segments=32,
            ring_count=16,
        )
        hair = _create_uv_sphere_object(
            context,
            f"{target.name} Character Hair Cap",
            (center_x, center_y + head_radius * 0.04, head_z + head_radius * 0.22),
            head_radius * 0.92,
            hair_material,
            segments=32,
            ring_count=8,
        )
        hair.scale.z = 0.42
        shoulder = _create_cube_object(
            context,
            f"{target.name} Character Shoulder Line",
            (center_x, center_y, max_z - sz * 0.08),
            (max(0.1, sx * 0.62), max(0.02, sy * 0.05), max(0.02, sz * 0.035)),
            accent_material,
        )
        created.extend([neck.name, head.name, hair.name, shoulder.name])

        eye_z = head_z + head_radius * 0.12
        eye_y = center_y - max(0.04, head_radius * 0.82)
        eye_radius = head_radius * 0.095
        for side, x in (("Left", center_x - head_radius * 0.32), ("Right", center_x + head_radius * 0.32)):
            eye = _create_uv_sphere_object(
                context,
                f"{target.name} Character {side} Eye",
                (x, eye_y, eye_z),
                eye_radius,
                eye_material,
                segments=16,
                ring_count=8,
            )
            created.append(eye.name)

        guide_objects = []
        if create_guides:
            vertical = _create_curve_line(
                context,
                f"{target.name} Character Gesture Line",
                [(center_x, center_y - sy * 0.08, min_z), (center_x, center_y - sy * 0.08, head_z + head_radius)],
                max(0.004, max_dim * 0.004),
                guide_material,
            )
            shoulder_line = _create_curve_line(
                context,
                f"{target.name} Character Shoulder Guide",
                [(min_x, center_y - sy * 0.09, max_z - sz * 0.08), (max_x, center_y - sy * 0.09, max_z - sz * 0.08)],
                max(0.004, max_dim * 0.004),
                guide_material,
            )
            guide_objects.extend([vertical.name, shoulder_line.name])
            created.extend(guide_objects)

    features = ["body polish", "head blockout", "eyes", "shoulder marker"]
    if create_guides:
        features.append("gesture guides")
    transaction["applied_steps"].append(
        {
            "type": "apply_character_refinement_template",
            "label": label,
            "target": target.name,
            "style": style_key if style_key in CHARACTER_PALETTES else "neutral",
            "detail_level": str(detail_level or "medium"),
            "created_objects": created,
            "features": features,
            "expected_changes": f"Adds a bounded character presentation kit around {target.name}: {', '.join(features)}.",
        }
    )
    live_preview.redraw(context)
    live_preview._mark_pending(context, label)
    return {
        "ok": True,
        "message": f"Applied character refinement template around {target.name}",
        "target": target.name,
        "style": style_key if style_key in CHARACTER_PALETTES else "neutral",
        "detail_level": str(detail_level or "medium"),
        "created_objects": created,
        "features": features,
        "transaction_id": transaction["id"],
    }


def register():
    pass


def unregister():
    pass
