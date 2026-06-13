"""Safer advanced live-preview helpers for deeper Blender systems."""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from . import live_preview


def _coerce_vector(value, fallback):
    return live_preview._coerce_vector(value, fallback)


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
    transaction = live_preview.begin(label)
    material = bpy.data.materials.get(name)
    created = material is None
    if material is None:
        material = bpy.data.materials.new(name or "Claude Shader Material")
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
    transaction = live_preview.begin(label)
    group = bpy.data.node_groups.get(node_group_name)
    created_group = group is None
    if group is None:
        group = bpy.data.node_groups.new(node_group_name or "Claude Geometry Nodes", "GeometryNodeTree")
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
        modifier = obj.modifiers.new(name or "Claude Geometry Nodes", "NODES")
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


def create_shape_key(context, *, object_name="", key_name="Claude Shape", value=0.0, label="Create shape key"):
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
        key = obj.shape_key_add(name=key_name or "Claude Shape")
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
        key = obj.shape_key_add(name=key_name or "Claude Shape")
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
    obj = bpy.data.objects.new(name or "Claude Text", curve)
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
    obj = bpy.data.objects.new(name or "Claude Curve", curve)
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
        modifier = obj.modifiers.new(name or "Claude Particles", "PARTICLE_SYSTEM")
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
    obj.name = name or "Claude Armature"
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
    name="Claude Copy Transform",
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
        constraint.name = name or f"Claude {constraint_type.title()}"
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
    world = context.scene.world or bpy.data.worlds.new("Claude World")
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
        if add_weighted_normals and obj.modifiers.get("Claude Weighted Normals") is None:
            modifier = obj.modifiers.new("Claude Weighted Normals", "WEIGHTED_NORMAL")
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
        bevel = obj.modifiers.new("Claude Detail Bevel", "BEVEL")
        bevel.width = max(0.0, min(10.0, float(bevel_width)))
        bevel.segments = max(1, min(16, int(bevel_segments)))
        live_preview._record_created_modifier(obj, bevel)
        if int(subsurf_levels) > 0:
            subsurf = obj.modifiers.new("Claude Detail Subdivision", "SUBSURF")
            subsurf.levels = max(0, min(3, int(subsurf_levels)))
            subsurf.render_levels = max(0, min(3, int(subsurf_levels)))
            live_preview._record_created_modifier(obj, subsurf)
        if weighted_normals:
            normals = obj.modifiers.new("Claude Weighted Normals", "WEIGHTED_NORMAL")
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
    tire_material_name="Claude Tire Rubber",
    rim_material_name="Claude Wheel Rim",
    label="Create wheel assembly",
):
    transaction = live_preview.begin(label)
    tire_material = _material_for_color(tire_material_name, (0.005, 0.005, 0.006, 1.0))
    rim_material = _material_for_color(rim_material_name, (0.72, 0.72, 0.68, 1.0))
    objects = _create_wheel_parts(
        context,
        name=name or "Claude Wheel",
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
    seam_material_name="Claude Panel Seams",
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
    material_name="Claude Blue Glass",
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
    transaction = live_preview.begin(label)
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

    original_selection = list(context.selected_objects)
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

    tire_material = _material_for_color("Claude Tire Rubber", (0.005, 0.005, 0.006, 1.0))
    rim_material = _material_for_color("Claude Wheel Rim", (0.72, 0.72, 0.68, 1.0))
    created = []
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

    headlight_material = _material_for_color("Claude Headlight White", (1.0, 0.95, 0.82, 1.0))
    tail_material = _material_for_color("Claude Tail Light Red", (1.0, 0.02, 0.0, 1.0))
    light_z = min_z + sz * 0.36
    light_scale = (sx * 0.035, sy * 0.035, sz * 0.09)
    for y in (min_y + sy * 0.28, max_y - sy * 0.28):
        created.append(_create_cube_object(context, f"{target.name} Front Headlight", (min_x - sx * 0.01, y, light_z), light_scale, headlight_material).name)
        created.append(_create_cube_object(context, f"{target.name} Rear Taillight", (max_x + sx * 0.01, y, light_z), light_scale, tail_material).name)

    bpy.ops.object.select_all(action="DESELECT")
    for obj in original_selection:
        if obj.name in bpy.data.objects:
            obj.select_set(True)
    if target.name in bpy.data.objects:
        context.view_layer.objects.active = target

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


def register():
    pass


def unregister():
    pass
