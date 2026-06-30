"""Shared helper-first routing metadata for script fallback decisions."""

from __future__ import annotations

import re


SCRIPT_REQUEST_KEYWORDS = {
    "script",
    "python",
    "draft_script",
    "draft script",
    "approved script",
}

EXPLICIT_SCRIPT_FALLBACK_KEYWORDS = {
    "custom code",
    "custom python",
    "custom blender python",
    "custom script",
    "custom node",
    "custom nodes",
    "custom node network",
    "custom material",
    "custom shader",
    "custom rig",
    "custom geometry node",
    "custom geometry nodes",
    "custom procedural",
    "procedural script",
    "procedural material",
    "procedural shader",
    "procedural geometry",
    "helper gap",
    "helper tools cannot express",
    "helpers cannot express",
    "no helper can express",
    "no helper tool can express",
    "requires custom python",
    "requires custom blender python",
}

SCRIPT_FALLBACK_KEYWORDS = SCRIPT_REQUEST_KEYWORDS | EXPLICIT_SCRIPT_FALLBACK_KEYWORDS

ANIMATION_HELPER_GAP_TERMS = {
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

HELPER_GAP_TERMS = ANIMATION_HELPER_GAP_TERMS | {
    "custom code",
    "custom script",
    "custom node",
    "custom nodes",
    "custom node network",
    "custom material",
    "custom shader",
    "custom rig",
    "custom geometry node",
    "custom geometry nodes",
    "custom procedural",
    "procedural script",
    "procedural material",
    "procedural shader",
    "procedural geometry",
    "no direct helper",
    "helper fallback approved",
}

HELPER_FIRST_SCRIPT_GROUPS = {
    "project_files",
    "selection",
    "basic_edit",
    "materials",
    "animation",
    "camera_render",
    "external_assets",
    "advanced_create",
    "refinement",
    "vehicle",
    "product",
    "character",
    "rigging",
    "curves_text",
    "particles",
    "geometry_nodes",
    "advanced_workflow",
    "two_d_storyboard",
    "procedural_3d",
    "simulation_setup",
    "preview_control",
}

STRICT_HELPER_FIRST_SCRIPT_GROUPS = {
    "external_assets",
    "project_files",
}

STRICT_HELPER_FIRST_SCRIPT_CODES = {
    "external_asset_workflow_required",
    "project_file_helper_required",
    "simulation_helper_required",
}

HELPER_FIRST_SCRIPT_RULES = (
    {
        "code": "advanced_workflow_helper_required",
        "terms": {
            "advanced workflow",
            "advanced 3d",
            "advanced 2d",
            "advanced animation",
            "which tools",
            "what tools",
            "helper path",
            "workflow plan",
            "director workflow",
        },
        "message": (
            "Use the advanced workflow planner and domain helpers before drafting Python for broad advanced "
            "3D, 2D, animation, simulation, or compositor/render work."
        ),
        "recommended_tools": [
            "plan_director_workflow",
            "plan_advanced_scene_workflow",
            "get_2d_animation_details",
            "get_geometry_nodes_details",
            "get_simulation_details",
            "get_render_camera_compositor_details",
        ],
    },
    {
        "code": "two_d_storyboard_helper_required",
        "terms": {
            "storyboard",
            "animatic",
            "2d animation",
            "2d scene",
            "cutout",
            "cut-out",
            "motion graphic",
            "motion graphics",
            "grease pencil",
            "grease-pencil",
        },
        "message": (
            "Use the 2D/storyboard inspection and creation helpers before drafting Python for common "
            "storyboard, animatic, cutout, or motion-graphics setup."
        ),
        "recommended_tools": [
            "get_2d_animation_details",
            "create_storyboard_panels",
            "create_2d_cutout_layer",
            "create_camera_dolly_animation",
            "capture_animation_playblast",
        ],
    },
    {
        "code": "procedural_3d_helper_required",
        "terms": {
            "array stack",
            "modifier stack",
            "procedural array",
            "object kit",
            "kitbash",
            "scatter grid",
            "radial array",
            "modular wall panel",
            "wall panel",
            "mechanical part",
            "pipe run",
            "hard surface",
            "hard-surface",
            "non destructive",
            "non-destructive",
        },
        "message": (
            "Use procedural modeling helpers and geometry-node inspection before drafting Python for common "
            "non-destructive array/bevel/weighted-normal stacks."
        ),
        "recommended_tools": [
            "plan_advanced_scene_workflow",
            "get_geometry_nodes_details",
            "create_procedural_object_kit",
            "apply_procedural_array_stack",
            "add_geometry_nodes_modifier",
            "add_bevel_and_subsurf",
        ],
    },
    {
        "code": "camera_animation_helper_required",
        "terms": {
            "camera dolly",
            "dolly shot",
            "camera move",
            "camera animation",
            "lens keyframe",
            "animate camera",
            "directed shot",
            "shot template",
        },
        "message": "Use the directed shot or camera dolly animation helper before drafting Python for common camera moves.",
        "recommended_tools": [
            "create_directed_animation_shot",
            "create_camera_dolly_animation",
            "set_camera_settings",
            "capture_animation_playblast",
        ],
    },
    {
        "code": "simulation_setup_helper_required",
        "terms": {
            "cloth simulation",
            "cloth sim",
            "add cloth",
            "physics setup",
            "simulation setup",
            "add particle system",
            "particle system",
        },
        "message": (
            "Use bounded simulation setup helpers before drafting Python for common cloth or particle "
            "simulation setup; inspect cache state before any persistent bake."
        ),
        "recommended_tools": [
            "get_simulation_details",
            "add_cloth_simulation_to_selected",
            "add_particle_system_to_selected",
            "inspect_simulation_bake",
        ],
    },
    {
        "code": "external_asset_workflow_required",
        "terms": {
            "poly haven",
            "polyhaven",
            "sketchfab",
            "external asset",
            "asset download",
            "download asset",
            "download model",
            "import asset",
            "import model",
            "import hdri",
            "import texture",
            "environment map",
        },
        "message": (
            "Use the external asset discovery, async download/cache job, and queued import helpers before "
            "drafting Python for asset download or import."
        ),
        "recommended_tools": [
            "plan_asset_import_workflow",
            "search_poly_haven_assets",
            "search_sketchfab_models",
            "start_external_asset_download",
            "get_external_asset_job_status",
            "start_external_asset_import_job",
            "get_external_asset_import_job_status",
        ],
    },
    {
        "code": "project_file_helper_required",
        "terms": {
            "save blend",
            "save as",
            "save-as",
            "save copy",
            "open blend",
            "open file",
            "new project",
            "create project",
            "bpy.ops.wm.save_as_mainfile",
            "bpy.ops.wm.open_mainfile",
            "bpy.ops.wm.read_homefile",
        },
        "message": (
            "Use blend-file lifecycle helpers for save, open, and new-project work so user-confirmed paths, "
            "discard confirmation, and checkpoint policy stay enforced."
        ),
        "recommended_tools": [
            "get_blend_file_diagnostics",
            "save_blend_file",
            "open_blend_file",
            "create_new_blender_project",
            "autosave_current_blend_file",
        ],
    },
    {
        "code": "simulation_helper_required",
        "terms": {
            "persistent bake",
            "point cache",
            "bpy.ops.ptcache",
            "bpy.ops.fluid",
            "bake_all",
            "free_bake",
            "free_bake_all",
        },
        "message": (
            "Use simulation inspection and the fixed persistent-bake staging helper before drafting custom "
            "simulation bake Python."
        ),
        "recommended_tools": [
            "get_simulation_details",
            "inspect_simulation_bake",
            "add_cloth_simulation_to_selected",
            "stage_persistent_simulation_bake",
        ],
    },
    {
        "code": "creation_helper_required",
        "terms": {
            "add cube",
            "create cube",
            "add sphere",
            "create sphere",
            "add primitive",
            "create primitive",
            "add empty",
            "create empty",
            "add light",
            "create light",
            "add camera",
            "create camera",
            "add text",
            "create text",
            "create curve",
            "primitive_cube_add",
            "primitive_uv_sphere_add",
            "primitive_cone_add",
            "primitive_cylinder_add",
            "bpy.ops.object.empty_add",
            "bpy.ops.object.light_add",
            "bpy.ops.object.camera_add",
            "bpy.ops.object.text_add",
            "bpy.data.objects.new",
        },
        "message": (
            "Use creation helpers for bounded primitives, empties, lights, cameras, text, and curves before "
            "drafting Python."
        ),
        "recommended_tools": [
            "create_primitive",
            "create_empty",
            "add_light",
            "add_camera",
            "create_text_object",
            "create_curve_path",
        ],
    },
    {
        "code": "material_helper_required",
        "terms": {
            "material",
            "shader",
            "make it red",
            "make it blue",
            "make it green",
            "base color",
            "emission",
            "roughness",
            "metallic",
            "diffuse_color",
            "active_material",
            "bpy.data.materials",
            "principled bsdf",
        },
        "message": (
            "Use material and shader helpers before drafting Python for common color, emission, metallic, "
            "roughness, alpha, or material-assignment changes."
        ),
        "recommended_tools": [
            "assign_material_to_selected",
            "assign_emission_material_to_selected",
            "create_shader_material",
            "get_material_node_details",
            "get_shader_nodes_details",
        ],
    },
    {
        "code": "transform_helper_required",
        "terms": {
            "move selected",
            "move cube",
            "move object",
            "set location",
            "change location",
            "rotate selected",
            "scale selected",
            "set transform",
            ".location",
            ".rotation_euler",
            ".scale",
            "bpy.ops.transform",
        },
        "message": (
            "Use selection and transform helpers before drafting Python for common object location, rotation, "
            "or scale changes."
        ),
        "recommended_tools": [
            "list_scene_objects",
            "select_objects",
            "set_selected_location_delta",
            "set_selected_transform",
        ],
    },
    {
        "code": "scene_setting_helper_required",
        "terms": {
            "render settings",
            "set resolution",
            "frame range",
            "world background",
            "camera lens",
            "depth of field",
            "scene.render",
            "scene.frame_start",
            "scene.frame_end",
            "scene.world",
            "camera.data.lens",
            "light.data.energy",
        },
        "message": (
            "Use render, camera, light, and world helpers before drafting Python for common scene setting changes."
        ),
        "recommended_tools": [
            "set_render_settings",
            "set_camera_settings",
            "set_world_background",
            "add_light",
            "add_camera",
            "apply_lighting_preset",
        ],
    },
)


def contains_keyword(text, keywords):
    normalized = str(text or "").lower()
    return any(str(keyword or "").lower() in normalized for keyword in keywords)


def contains_guard_term(text, term):
    normalized = str(text or "").lower()
    term_text = str(term or "").strip().lower()
    if not term_text:
        return False
    pattern = re.escape(term_text).replace(r"\ ", r"\s+")
    prefix = r"(?<![a-z0-9_])" if term_text[0].isalnum() else ""
    suffix = r"(?![a-z0-9_])" if term_text[-1].isalnum() else ""
    return bool(re.search(f"{prefix}{pattern}{suffix}", normalized))


def contains_any_guard_term(text, terms):
    return any(contains_guard_term(text, term) for term in terms)


def has_explicit_animation_helper_gap(text):
    return contains_any_guard_term(text, ANIMATION_HELPER_GAP_TERMS)


def has_explicit_helper_gap(text):
    return contains_any_guard_term(text, HELPER_GAP_TERMS)


def should_include_draft_script(text, matched_groups):
    if not contains_keyword(text, SCRIPT_FALLBACK_KEYWORDS):
        return False
    matched = set(matched_groups or [])
    if matched.intersection(STRICT_HELPER_FIRST_SCRIPT_GROUPS):
        return False
    if contains_keyword(text, EXPLICIT_SCRIPT_FALLBACK_KEYWORDS):
        return True
    return True


def should_include_privileged_script(text, matched_groups):
    if not contains_keyword(text, SCRIPT_FALLBACK_KEYWORDS):
        return False
    matched = set(matched_groups or [])
    return bool(matched.intersection(STRICT_HELPER_FIRST_SCRIPT_GROUPS))


def iter_helper_first_script_rules():
    return iter(HELPER_FIRST_SCRIPT_RULES)


def _matching_helper_first_rule(text, *, ignore_helper_gap=False):
    if not ignore_helper_gap and has_explicit_helper_gap(text):
        return None
    for rule in HELPER_FIRST_SCRIPT_RULES:
        if not contains_any_guard_term(text, rule["terms"]):
            continue
        return rule
    return None


def _result_for_rule(rule):
    if not rule:
        return None
    recommended_tools = list(rule["recommended_tools"])
    return {
        "ok": True,
        "blocked": False,
        "code": rule["code"],
        "message": rule["message"],
        "requires_user_approval": False,
        "explicit_helper_gap_required": False,
        "recommended_tools": recommended_tools,
        "recommended_next_step": f"Consider {recommended_tools[0]} or another listed helper if it covers the edit.",
    }


def helper_first_script_advisory(text):
    return _result_for_rule(_matching_helper_first_rule(text))


def helper_first_script_guard(text):
    for rule in HELPER_FIRST_SCRIPT_RULES:
        if rule["code"] not in STRICT_HELPER_FIRST_SCRIPT_CODES:
            continue
        if not contains_any_guard_term(text, rule["terms"]):
            continue
        result = _result_for_rule(rule)
        result.update(
            {
                "ok": False,
                "blocked": True,
                "explicit_helper_gap_required": True,
                "recommended_next_step": f"Call {result['recommended_tools'][0]} or another listed helper before retrying draft_script.",
            }
        )
        return result
    return None


def register():
    pass


def unregister():
    pass
