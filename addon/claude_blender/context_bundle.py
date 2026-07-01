"""Build compact, progressive-disclosure context bundles from Blender state."""

from __future__ import annotations

import platform
import sys
from collections import Counter

import bpy

from . import viewport_capture, world_model


def _safe_name(data_block):
    return getattr(data_block, "name", None) if data_block else None


def _vec(value):
    return [round(float(component), 5) for component in value]


def _xyz(value):
    return {
        "x": round(float(value[0]), 5),
        "y": round(float(value[1]), 5),
        "z": round(float(value[2]), 5),
    }


def _rgba(value):
    return {
        "r": round(float(value[0]), 5),
        "g": round(float(value[1]), 5),
        "b": round(float(value[2]), 5),
        "a": round(float(value[3]), 5),
    }


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


def _mesh_summary(obj):
    if obj.type != "MESH" or obj.data is None:
        return None
    mesh = obj.data
    return {
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "polygons": len(mesh.polygons),
    }


def _object_summary(obj):
    animation_data = getattr(obj, "animation_data", None)
    action = animation_data.action if animation_data else None
    return {
        "name": obj.name,
        "type": obj.type,
        "mode": getattr(obj, "mode", None),
        "location": _xyz(obj.location),
        "rotation_euler_radians": _xyz(obj.rotation_euler),
        "scale": _xyz(obj.scale),
        "dimensions_blender_units": _xyz(obj.dimensions),
        "data": _safe_name(obj.data),
        "mesh_summary": _mesh_summary(obj),
        "collection_users": len(obj.users_collection),
        "hidden_viewport": bool(obj.hide_viewport),
        "hidden_render": bool(obj.hide_render),
        "material_slots": [_safe_name(slot.material) for slot in obj.material_slots],
        "modifiers": [{"name": mod.name, "type": mod.type, "show_viewport": bool(mod.show_viewport)} for mod in obj.modifiers],
        "constraints": [{"name": con.name, "type": con.type, "influence": round(float(con.influence), 5)} for con in obj.constraints],
        "animation": {
            "has_animation_data": animation_data is not None,
            "action": _safe_name(action),
            "fcurves": len(_iter_action_fcurves(action)),
        },
    }


def _material_summary(material):
    if material is None:
        return None
    node_names = []
    if material.use_nodes and material.node_tree:
        node_names = [node.name for node in list(material.node_tree.nodes)[:20]]
    return {
        "name": material.name,
        "use_nodes": bool(material.use_nodes),
        "diffuse_color_rgba": _rgba(material.diffuse_color),
        "node_count": len(material.node_tree.nodes) if material.node_tree else 0,
        "nodes": node_names,
    }


def _scene_summary(scene):
    object_counts = Counter(obj.type for obj in scene.objects)
    return {
        "name": scene.name,
        "frame_current": int(scene.frame_current),
        "frame_start": int(scene.frame_start),
        "frame_end": int(scene.frame_end),
        "fps": int(scene.render.fps),
        "unit_system": scene.unit_settings.system,
        "unit_scale_length": round(float(scene.unit_settings.scale_length), 5),
        "length_unit": scene.unit_settings.length_unit,
        "dimension_note": "Object dimensions are reported as named x/y/z values in Blender units",
        "render_engine": scene.render.engine,
        "resolution": [int(scene.render.resolution_x), int(scene.render.resolution_y)],
        "camera": _safe_name(scene.camera),
        "world": _safe_name(scene.world),
        "object_count": len(scene.objects),
        "object_counts_by_type": dict(sorted(object_counts.items())),
        "collection_count": len(bpy.data.collections),
        "material_count": len(bpy.data.materials),
        "action_count": len(bpy.data.actions),
    }


def _selection_summary(context):
    return {
        "active_object": _safe_name(context.active_object),
        "selected_objects": [_object_summary(obj) for obj in context.selected_objects[:25]],
        "selected_count": len(context.selected_objects),
    }


def _animation_summary(scene):
    actions = []
    for action in list(bpy.data.actions)[:25]:
        keyframe_count = 0
        fcurves = _iter_action_fcurves(action)
        for fcurve in fcurves:
            keyframe_count += len(fcurve.keyframe_points)
        actions.append(
            {
                "name": action.name,
                "fcurves": len(fcurves),
                "keyframes": keyframe_count,
            }
        )
    return {
        "frame_current": int(scene.frame_current),
        "frame_range": [int(scene.frame_start), int(scene.frame_end)],
        "actions": actions,
    }


def _material_context(context):
    materials = []
    seen = set()
    for obj in context.selected_objects:
        for slot in obj.material_slots:
            material = slot.material
            if material and material.name not in seen:
                seen.add(material.name)
                materials.append(_material_summary(material))
    return materials


def _environment(context):
    workspace = context.workspace.name if context.workspace else None
    return {
        "blender_version": ".".join(str(part) for part in bpy.app.version),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "mode": context.mode,
        "workspace": workspace,
        "online_access": bool(getattr(bpy.app, "online_access", True)),
    }


def build_context_bundle(context, *, include_visual=False, capture_dir=None, max_screenshot_bytes=None):
    """Return a compact context bundle suitable for sending to an LLM."""

    scene = context.scene
    active = context.active_object
    attachments = {}
    if include_visual:
        visual_context, attachments = viewport_capture.capture_viewport(
            context,
            capture_dir=capture_dir,
            max_bytes=max_screenshot_bytes or viewport_capture.DEFAULT_MAX_BYTES,
        )
    else:
        visual_context = {
            "requested": False,
            "available": False,
            "note": "Viewport screenshot toggle is off",
        }
    bundle = {
        "environment": _environment(context),
        "scene_summary": _scene_summary(scene),
        "selection_summary": _selection_summary(context),
        "active_object_detail": _object_summary(active) if active else None,
        "world_model_summary": world_model.world_model_summary(context),
        "animation_summary": _animation_summary(scene),
        "material_summary": _material_context(context),
        "visual_context": visual_context,
        "available_tools": [
            "inspect_scene",
            "list_scene_objects",
            "get_object_details",
            "get_animation_details",
            "get_animation_scene_context",
            "create_animation_brief",
            "create_timing_chart",
            "plan_animation_workflow",
            "run_animation_workflow",
            "run_animation_task",
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
            "repair_animation_from_findings",
            "run_animation_repair_loop",
            "get_material_node_details",
            "get_geometry_nodes_details",
            "get_shader_nodes_details",
            "get_rigging_details",
            "get_shape_key_details",
            "get_curve_text_details",
            "get_simulation_details",
            "inspect_simulation_bake",
            "stage_persistent_simulation_bake",
            "get_collection_layer_details",
            "get_render_camera_compositor_details",
            "get_blend_file_diagnostics",
            "save_blend_file",
            "open_blend_file",
            "create_new_blender_project",
            "autosave_current_blend_file",
            "get_workspace_layout",
            "get_visual_evidence_resources",
            "capture_viewport",
            "capture_animation_playblast",
            "capture_object_inspection_renders",
            "render_scene_thumbnail",
            "start_render_job",
            "get_render_job_status",
            "cancel_render_job",
            "assemble_render_job_video",
            "validate_render_job_output",
            "search_blender_docs",
            "list_poly_haven_categories",
            "search_poly_haven_assets",
            "inspect_poly_haven_asset_files",
            "download_poly_haven_asset",
            "import_poly_haven_asset",
            "search_sketchfab_models",
            "download_sketchfab_model",
            "import_sketchfab_model",
            "start_external_asset_download",
            "get_external_asset_job_status",
            "cancel_external_asset_job",
            "import_external_asset_job_result",
            "start_external_asset_import_job",
            "get_external_asset_import_job_status",
            "prepare_imported_asset_presentation",
            "cancel_external_asset_import_job",
            "delete_external_asset_job",
            "get_external_asset_cache_diagnostics",
            "prune_external_asset_cache",
            "select_objects",
            "jump_to_workspace",
            "set_viewport_view",
            "focus_object_in_viewport",
            "set_current_frame",
            "set_selected_location_delta",
            "set_selected_transform",
            "create_primitive",
            "create_empty",
            "set_object_visibility",
            "set_object_display",
            "assign_material_to_selected",
            "assign_emission_material_to_selected",
            "create_collection",
            "link_selected_to_collection",
            "add_modifier_to_selected",
            "create_shader_material",
            "add_geometry_nodes_modifier",
            "create_shape_key",
            "animate_shape_key",
            "animate_object_bounce",
            "create_progressive_bounce_animation",
            "animate_material_property",
            "animate_light_property",
            "create_follow_path_animation",
            "set_action_interpolation",
            "retime_actions",
            "add_action_cycles",
            "clear_animation",
            "set_animation_preview_range",
            "create_turntable_animation",
            "create_pulse_animation",
            "create_reveal_animation",
            "create_staggered_motion",
            "create_directed_animation_shot",
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
            "create_text_object",
            "create_curve_path",
            "add_particle_system_to_selected",
            "create_basic_armature",
            "add_copy_transform_constraint",
            "set_render_settings",
            "set_camera_settings",
            "set_world_background",
            "plan_director_workflow",
            "plan_advanced_scene_workflow",
            "plan_asset_import_workflow",
            "get_2d_animation_details",
            "create_storyboard_panels",
            "create_2d_cutout_layer",
            "apply_procedural_array_stack",
            "edit_mesh",
            "curve_to_mesh",
            "boolean_op",
            "mirror_model",
            "symmetrize_model",
            "solidify_model",
            "create_procedural_object_kit",
            "create_camera_dolly_animation",
            "create_directed_animation_shot",
            "add_cloth_simulation_to_selected",
            "duplicate_selected_objects",
            "parent_selected_to_empty",
            "align_selected_objects",
            "distribute_selected_objects",
            "shade_smooth_selected",
            "add_bevel_and_subsurf",
            "create_wheel_assembly",
            "add_panel_seams",
            "add_window_materials",
            "apply_vehicle_refinement_template",
            "apply_product_refinement_template",
            "apply_character_refinement_template",
            "create_studio_product_stage",
            "add_dimension_callouts",
            "apply_lighting_preset",
            "create_material_palette",
            "create_product_turntable_setup",
            "prepare_imported_asset_presentation",
            "organize_scene_for_production",
            "add_track_to_constraint",
            "add_light",
            "add_camera",
            "set_scene_frame_range",
            "set_active_camera",
            "animate_selected_transform",
            "create_camera_orbit",
            "commit_preview",
            "revert_preview",
            "draft_script",
            "run_approved_script",
        ],
        "privacy_redactions": {
            "raw_mesh_data": "omitted",
            "file_paths": "omitted",
            "screenshots": "controlled_by_toggle",
        },
    }
    if attachments:
        bundle["_attachments"] = attachments
    return bundle


def public_bundle(bundle):
    """Return a copy of a bundle without API-only attachment payloads."""

    return {key: value for key, value in bundle.items() if key != "_attachments"}


def attachment_blocks(bundle):
    attachments = bundle.get("_attachments") or {}
    return [value for value in attachments.values() if value.get("type") == "image"]


def summarize_for_status(bundle):
    scene = bundle["scene_summary"]
    selection = bundle["selection_summary"]
    visual = bundle.get("visual_context") or {}
    visual_note = ", viewport image" if visual.get("available") else ""
    return (
        f"{scene['object_count']} objects, "
        f"{selection['selected_count']} selected, "
        f"frame {scene['frame_current']}, "
        f"{scene['render_engine']}"
        f"{visual_note}"
    )


def register():
    pass


def unregister():
    pass
