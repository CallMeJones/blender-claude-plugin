"""Semantic bridge contract for JSON bridge and MCP access.

The Blender extension owns real scene reads/writes through bpy. A local
companion process exposes these tool names over MCP without changing the core
tool semantics.
"""

from __future__ import annotations

try:
    from . import build_info
except ImportError:  # Allows direct imports from addon/claude_blender.
    import build_info


BRIDGE_VERSION = build_info.BRIDGE_VERSION
CONTRACT_SCHEMA_VERSION = "1.0"
DEFAULT_TOOL_TIMEOUT_SECONDS = 60


DEFAULT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean", "description": "Whether the tool completed successfully"},
        "message": {"type": "string", "description": "Human-readable status or error message"},
    },
    "additionalProperties": True,
}


TOOL_CONTRACTS = {
    "inspect_scene": {
        "description": "Return a compact context bundle for the active Blender scene",
        "mutates_scene": False,
    },
    "list_scene_objects": {
        "description": "Return object names, types, selection, visibility, collections, and locations",
        "mutates_scene": False,
    },
    "get_object_details": {
        "description": "Return deeper details for a named Blender object",
        "mutates_scene": False,
    },
    "get_animation_details": {
        "description": "Return scene timeline, action, f-curve, and keyframe details",
        "mutates_scene": False,
    },
    "get_animation_scene_context": {
        "description": "Return animation-aware routing context for rigs, control candidates, shape keys, physics, materials, cameras, contact surfaces, and likely edit targets",
        "mutates_scene": False,
    },
    "create_animation_brief": {
        "description": "Create a structured animation prompt contract from the user brief and scene context",
        "mutates_scene": False,
    },
    "create_timing_chart": {
        "description": "Create a structured timing/blocking chart from an animation brief",
        "mutates_scene": False,
    },
    "plan_animation_workflow": {
        "description": "Plan the Milestone 7 animation workflow with brief, scene routing, timing chart, helper calls, evaluator calls, repair calls, and script fallback rules",
        "mutates_scene": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "subject_names": {"type": "array", "items": {"type": "string"}},
                "frame_start": {"type": "integer"},
                "frame_end": {"type": "integer"},
                "mode": {"type": "string", "enum": ["generate", "review", "repair", "full"]},
                "selected_only": {"type": "boolean"},
                "max_objects": {"type": "integer"},
                "brief": {"type": "object"},
                "timing_chart": {"type": "object"},
                "playblast": {"type": "object"},
                "findings": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
    "run_animation_workflow": {
        "description": "Execute a helper-backed Milestone 7 animation workflow, run structured review, and optionally apply bounded repair operations while leaving changes in preview",
        "mutates_scene": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "subject_names": {"type": "array", "items": {"type": "string"}},
                "frame_start": {"type": "integer"},
                "frame_end": {"type": "integer"},
                "mode": {"type": "string", "enum": ["generate", "review", "repair", "full"]},
                "selected_only": {"type": "boolean"},
                "max_objects": {"type": "integer"},
                "brief": {"type": "object"},
                "timing_chart": {"type": "object"},
                "playblast": {"type": "object"},
                "findings": {"type": "array", "items": {"type": "object"}},
                "apply_generation": {"type": "boolean"},
                "run_review": {"type": "boolean"},
                "capture_playblast": {"type": "boolean"},
                "apply_repairs": {"type": "boolean"},
                "max_generation_steps": {"type": "integer"},
                "max_repair_iterations": {"type": "integer"},
                "max_repair_operations": {"type": "integer"},
                "recapture_after_repair": {"type": "boolean"},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
    "run_animation_task": {
        "description": "One-input animation task wrapper that routes the prompt through the Milestone 7 planner/runner workflow before any script fallback",
        "mutates_scene": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
            },
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
    "analyze_motion_arcs": {
        "description": "Analyze sampled location motion arcs for selected or named objects",
        "mutates_scene": False,
    },
    "analyze_fcurve_spacing": {
        "description": "Analyze transform key spacing and interpolation for selected or named objects",
        "mutates_scene": False,
    },
    "analyze_pose_clarity": {
        "description": "Analyze keyed pose count, holds, and transform readability",
        "mutates_scene": False,
    },
    "analyze_animation_principles": {
        "description": "Evaluate animation data against animator principles and the prompt contract",
        "mutates_scene": False,
    },
    "sample_animation_state": {
        "description": "Sample object transform state across an animation range",
        "mutates_scene": False,
    },
    "analyze_contact_sliding": {
        "description": "Detect object sliding while sampled bounding boxes are near a contact plane",
        "mutates_scene": False,
    },
    "analyze_collision_penetration": {
        "description": "Detect sampled world bounding-box intersections between animated objects",
        "mutates_scene": False,
    },
    "analyze_center_of_mass": {
        "description": "Check sampled subject centers against support-surface footprints for balance and weight",
        "mutates_scene": False,
    },
    "analyze_camera_framing": {
        "description": "Check whether animated subjects remain framed by the active or named camera",
        "mutates_scene": False,
    },
    "analyze_motion_physics": {
        "description": "Check sampled speed and acceleration for physically implausible spikes",
        "mutates_scene": False,
    },
    "compare_animation_to_brief": {
        "description": "Compare current animation state against a structured animation brief",
        "mutates_scene": False,
    },
    "review_playblast_against_brief": {
        "description": "Review playblast metadata, compact pixel motion evidence, and current animation state against a prompt contract",
        "mutates_scene": False,
    },
    "review_inspection_renders_against_brief": {
        "description": "Review diagnostic object render metadata and image evidence against a prompt contract",
        "mutates_scene": False,
    },
    "repair_animation_from_findings": {
        "description": "Create targeted non-mutating repair operations with executable helper tool-call payloads",
        "mutates_scene": False,
    },
    "run_animation_repair_loop": {
        "description": "Apply bounded animation repair operations and re-run playblast/brief review",
        "mutates_scene": True,
    },
    "create_progressive_bounce_animation": {
        "description": "Create repeated bounce keyframes plus decreasing scale keys for one object",
        "mutates_scene": True,
    },
    "get_material_node_details": {
        "description": "Return material node, socket, and link details",
        "mutates_scene": False,
    },
    "get_geometry_nodes_details": {
        "description": "Return Geometry Nodes modifier and node-group summaries",
        "mutates_scene": False,
    },
    "get_shader_nodes_details": {
        "description": "Return shader node tree, node, link, and driver summaries",
        "mutates_scene": False,
    },
    "get_rigging_details": {
        "description": "Return armature, bone, pose, constraint, and driver summaries",
        "mutates_scene": False,
    },
    "get_shape_key_details": {
        "description": "Return mesh shape key block, value, range, and driver summaries",
        "mutates_scene": False,
    },
    "get_curve_text_details": {
        "description": "Return curve spline and text object summaries",
        "mutates_scene": False,
    },
    "get_simulation_details": {
        "description": "Return rigid-body, particle, point-cache, and simulation bake summaries",
        "mutates_scene": False,
    },
    "inspect_simulation_bake": {
        "description": "Sample evaluated simulation state across frames and report cache/bake readiness without mutating persistent caches",
        "mutates_scene": False,
    },
    "stage_persistent_simulation_bake": {
        "description": "Stage a fixed-template scene-wide persistent simulation point-cache bake script for explicit approval or active script trust",
        "mutates_scene": True,
        "has_side_effects": True,
        "requires_approval": True,
    },
    "get_collection_layer_details": {
        "description": "Return collection tree, membership, visibility, and view-layer summaries",
        "mutates_scene": False,
    },
    "get_render_camera_compositor_details": {
        "description": "Return render, camera, world, and compositor summaries",
        "mutates_scene": False,
    },
    "search_blender_docs": {
        "description": "Search local cached official Blender docs before online docs",
        "mutates_scene": False,
    },
    "capture_viewport": {
        "description": "Capture the current viewport/window and return visual metadata plus a local artifact path",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["scene:read", "files:write"],
        "supports_headless": False,
        "timeout_seconds": 30,
    },
    "capture_animation_playblast": {
        "description": "Capture sampled viewport frames across an animation range for visual review",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["scene:read", "files:write"],
        "supports_headless": False,
        "timeout_seconds": 120,
    },
    "capture_object_inspection_renders": {
        "description": "Render diagnostic close-up PNGs of named objects from bounded inspection views and expose them as MCP resources",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["scene:read", "files:write"],
        "supports_headless": True,
        "timeout_seconds": 180,
    },
    "get_blend_file_diagnostics": {
        "description": "Return blend-file diagnostics for save path, backups, missing external files, linked libraries, and data-block usage summaries",
        "mutates_scene": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "max_items": {"type": "integer", "description": "Maximum external file/library entries to return"},
            },
            "additionalProperties": False,
        },
    },
    "get_workspace_layout": {
        "description": "Return workspace, window, screen, and area layout JSON for the current Blender UI",
        "mutates_scene": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "max_workspaces": {"type": "integer"},
                "max_areas": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    },
    "jump_to_workspace": {
        "description": "Switch the active interactive Blender window to a named workspace",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["ui:navigate"],
        "supports_headless": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "workspace_name": {"type": "string"},
            },
            "required": ["workspace_name"],
            "additionalProperties": False,
        },
    },
    "focus_object_in_viewport": {
        "description": "Frame a named object in the first 3D viewport and optionally select it",
        "mutates_scene": True,
        "has_side_effects": True,
        "permissions": ["ui:navigate", "scene:mutate"],
        "supports_headless": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string"},
                "select": {"type": "boolean", "description": "Select and activate the object before focusing. Defaults to true."},
            },
            "required": ["object_name"],
            "additionalProperties": False,
        },
    },
    "render_scene_thumbnail": {
        "description": "Render a small PNG from the scene camera or named camera and expose it as an MCP image resource",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["scene:read", "files:write"],
        "supports_headless": True,
        "timeout_seconds": 180,
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Optional PNG output path. Defaults to the project/session capture cache."},
                "frame": {"type": "integer", "description": "Frame to render. Defaults to current frame."},
                "resolution_x": {"type": "integer", "description": "PNG width. Defaults to 512."},
                "resolution_y": {"type": "integer", "description": "PNG height. Defaults to 512."},
                "camera_name": {"type": "string", "description": "Optional camera object name. Defaults to the active scene camera."},
                "note": {"type": "string", "description": "Short reason stored in thumbnail metadata."},
            },
            "additionalProperties": False,
        },
    },
    "start_render_job": {
        "description": "Start a long-running background Blender render job and return immediately with a job id for status polling",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["scene:read", "files:write", "process:start"],
        "supports_headless": True,
        "timeout_seconds": 30,
        "input_schema": {
            "type": "object",
            "properties": {
                "frame_start": {"type": "integer"},
                "frame_end": {"type": "integer"},
                "resolution_x": {"type": "integer"},
                "resolution_y": {"type": "integer"},
                "resolution_percentage": {"type": "integer"},
                "samples": {"type": "integer"},
                "fps": {"type": "integer"},
                "camera_name": {"type": "string"},
                "output_kind": {"type": "string", "enum": ["frames", "video", "mp4"]},
                "job_name": {"type": "string"},
                "note": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    "get_render_job_status": {
        "description": "Poll an async render job for progress, output paths, frame resources, logs, and completion state",
        "mutates_scene": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    "cancel_render_job": {
        "description": "Cancel a tracked async render job started by this Blender bridge session",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["process:terminate"],
        "supports_headless": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    "assemble_render_job_video": {
        "description": "Assemble a completed PNG frame-sequence render job into an MP4 using a background Blender process",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["files:read", "files:write", "process:start"],
        "supports_headless": True,
        "timeout_seconds": 30,
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "fps": {"type": "integer"},
                "output_path": {"type": "string"},
                "quality": {"type": "string", "enum": ["LOWEST", "LOW", "MEDIUM", "HIGH", "PERC_LOSSLESS", "LOSSLESS"]},
                "overwrite": {"type": "boolean"},
                "allow_partial": {"type": "boolean"},
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    "validate_render_job_output": {
        "description": "Validate render job frame sequence and MP4 output paths, sizes, resource URIs, and completion health",
        "mutates_scene": False,
        "has_side_effects": False,
        "permissions": ["files:read"],
        "supports_headless": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "require_video": {"type": "boolean"},
                "min_video_size_bytes": {"type": "integer"},
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    "set_selected_location_delta": {
        "description": "Move selected Blender objects by a delta with rollback state",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_selected_transform": {
        "description": "Set absolute location, rotation, and/or scale for selected objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "select_objects": {
        "description": "Select named objects and optionally set the active object",
        "mutates_scene": True,
    },
    "set_current_frame": {
        "description": "Set the current scene frame/playhead",
        "mutates_scene": True,
    },
    "create_primitive": {
        "description": "Create a mesh primitive with transform values",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_empty": {
        "description": "Create an empty helper object with transform and display settings",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_object_visibility": {
        "description": "Set viewport, render, or selection visibility flags for named or selected objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_object_display": {
        "description": "Set object viewport display type, name/wire/in-front flags, display color, and empty display settings",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "assign_material_to_selected": {
        "description": "Create or update a material and assign it to selected mesh objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "assign_emission_material_to_selected": {
        "description": "Create a new emission material node setup and assign it to selected mesh objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_collection": {
        "description": "Create or find a collection in the current scene",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "link_selected_to_collection": {
        "description": "Link selected objects to a named collection without deleting existing links",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_modifier_to_selected": {
        "description": "Add a bounded common modifier to selected mesh objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_shader_material": {
        "description": "Create or update a Principled BSDF material and optionally assign it",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_geometry_nodes_modifier": {
        "description": "Add a valid passthrough Geometry Nodes modifier and node group",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_shape_key": {
        "description": "Create or update a mesh shape key value",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "animate_shape_key": {
        "description": "Keyframe a mesh shape key value over a frame range",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "animate_object_bounce": {
        "description": "Create repeated location keyframes that bounce one object along an axis",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "animate_material_property": {
        "description": "Keyframe a Principled material socket such as base color, emission strength, roughness, metallic, or alpha",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "animate_light_property": {
        "description": "Keyframe a light data property such as energy, color, shadow softness, spot size, or spot blend",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_follow_path_animation": {
        "description": "Animate an object along an existing curve or a new curve built from path points",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_action_interpolation": {
        "description": "Set interpolation and optional easing on action keyframes",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "retime_actions": {
        "description": "Scale existing action keyframes into a new frame range",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_action_cycles": {
        "description": "Add cycles modifiers to action f-curves for looping animation",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "clear_animation": {
        "description": "Clear object, data, shape-key, and optional material animation",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_animation_preview_range": {
        "description": "Set scene preview playback range and optional current frame",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_turntable_animation": {
        "description": "Create a rotating product/object turntable animation",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_pulse_animation": {
        "description": "Create a scale pulse and optional emission-strength pulse",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_reveal_animation": {
        "description": "Create a scale reveal and optional material alpha fade",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_staggered_motion": {
        "description": "Create staggered location animation across selected or named objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "block_key_poses": {
        "description": "Block keyed transform poses for selected or named objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_breakdown_pose": {
        "description": "Add a keyed breakdown pose between existing key poses",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_pose_hold": {
        "description": "Duplicate a keyed pose to create a readable hold",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_rig_pose_hold": {
        "description": "Duplicate pose-bone transforms on named rig control bones for a readable hold",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_motion_arc": {
        "description": "Create preview curve objects that visualize sampled object motion arcs",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_text_object": {
        "description": "Create a text object with transform and optional material",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_curve_path": {
        "description": "Create a 3D curve path from points",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_particle_system_to_selected": {
        "description": "Add a bounded particle system to selected mesh objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_basic_armature": {
        "description": "Create a simple one-bone armature object",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_copy_transform_constraint": {
        "description": "Add a copy transform-style constraint to selected objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_render_settings": {
        "description": "Set render engine, resolution, FPS, frame range, and transparency",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_camera_settings": {
        "description": "Set active or named camera lens and depth-of-field settings",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_world_background": {
        "description": "Set scene world background color",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "duplicate_selected_objects": {
        "description": "Duplicate selected objects with optional unique data, offset, animation copy, and selecting the duplicates",
        "mutates_scene": True,
        "requires_live_preview": True,
        "requires_selection": True,
    },
    "parent_selected_to_empty": {
        "description": "Create an empty and parent selected objects to it while preserving world transforms",
        "mutates_scene": True,
        "requires_live_preview": True,
        "requires_selection": True,
    },
    "align_selected_objects": {
        "description": "Align selected object locations on one axis using active, min, max, center, or explicit value",
        "mutates_scene": True,
        "requires_live_preview": True,
        "requires_selection": True,
    },
    "distribute_selected_objects": {
        "description": "Evenly distribute selected object locations along one axis",
        "mutates_scene": True,
        "requires_live_preview": True,
        "requires_selection": True,
    },
    "shade_smooth_selected": {
        "description": "Shade selected mesh polygons smooth and optionally add weighted normals",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_bevel_and_subsurf": {
        "description": "Add a bounded bevel/subdivision/weighted-normal refinement stack",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_wheel_assembly": {
        "description": "Create a tire/rim wheel assembly from primitives",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_panel_seams": {
        "description": "Add simple curve panel seams around a mesh object's bounds",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_window_materials": {
        "description": "Create glass material and optional window panels for a mesh object's bounds",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "apply_vehicle_refinement_template": {
        "description": "Apply a bounded vehicle detail kit with wheels, windows, seams, lights, and smoothing",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "apply_product_refinement_template": {
        "description": "Apply a bounded product presentation kit with material polish, smoothing, staging, callouts, and optional turntable",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "apply_character_refinement_template": {
        "description": "Apply a bounded character blockout/detail kit with body polish, head, eyes, shoulder marker, and optional guides",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_studio_product_stage": {
        "description": "Create a bounded studio/product presentation stage around a target object",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_dimension_callouts": {
        "description": "Add non-destructive dimension/ruler callouts around a target object's bounds",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "apply_lighting_preset": {
        "description": "Create a bounded production lighting rig around a target object",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_material_palette": {
        "description": "Create a bounded material palette and optional swatch objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_product_turntable_setup": {
        "description": "Create product staging, turntable animation, and camera orbit around a target",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "organize_scene_for_production": {
        "description": "Link scene objects into production-oriented collections without deleting source links",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_track_to_constraint": {
        "description": "Add a Track To constraint from selected object(s) to a target object",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_light": {
        "description": "Add a light object to the live scene",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "add_camera": {
        "description": "Add a camera object and set it as active",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_scene_frame_range": {
        "description": "Set timeline frame range, current frame, and FPS",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "set_active_camera": {
        "description": "Set an existing camera object as the active scene camera",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "animate_selected_transform": {
        "description": "Create simple transform keyframes for selected objects",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "create_camera_orbit": {
        "description": "Create a keyframed camera orbit rig around a target object",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "commit_preview": {
        "description": "Commit the current live preview transaction",
        "mutates_scene": True,
    },
    "revert_preview": {
        "description": "Revert the current live preview transaction",
        "mutates_scene": True,
    },
    "draft_script": {
        "description": "Stage generated Blender Python, or auto-run it after static checks when a Blender-side external script trust window is active",
        "mutates_scene": True,
        "has_side_effects": True,
        "requires_approval": True,
    },
    "run_approved_script": {
        "description": "Run a pending script with a one-time approval token or an active Blender-side trust window",
        "mutates_scene": True,
        "has_side_effects": True,
        "requires_approval": True,
        "external_only": True,
        "supports_headless": False,
        "timeout_seconds": 120,
        "permissions": ["scene:read", "scene:mutate", "script:run"],
        "input_schema": {
            "type": "object",
            "properties": {
                "approval_token": {
                    "type": "string",
                    "description": (
                        "Optional one-time token copied from Blender after the user approves external execution. "
                        "Omit this, or pass an empty string, only while a Blender-side external script trust "
                        "grant is active."
                    ),
                }
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "message": {"type": "string"},
                "stdout": {"type": "string"},
                "log_datablock": {"type": "string"},
                "checkpoint": DEFAULT_OUTPUT_SCHEMA,
            },
            "required": ["ok"],
            "additionalProperties": True,
        },
    },
}


def _risk_level(contract):
    if contract.get("risk_level"):
        return str(contract["risk_level"])
    if contract.get("requires_approval"):
        return "approval"
    if contract.get("mutates_scene"):
        return "preview"
    return "read"


def _permissions(contract):
    configured = contract.get("permissions")
    if configured:
        return [str(item) for item in configured]
    if contract.get("requires_approval"):
        return ["scene:read", "script:stage"]
    if contract.get("mutates_scene"):
        permissions = ["scene:read", "scene:mutate"]
        if contract.get("requires_live_preview"):
            permissions.append("preview:write")
        return permissions
    return ["scene:read"]


def normalized_tool_contract(name, contract=None):
    raw = dict(contract if contract is not None else TOOL_CONTRACTS.get(name, {}))
    risk_level = _risk_level(raw)
    normalized = {
        "name": str(name),
        "title": str(raw.get("title") or str(name).replace("_", " ").title()),
        "description": str(raw.get("description") or ""),
        "mutates_scene": bool(raw.get("mutates_scene", False)),
        "requires_live_preview": bool(raw.get("requires_live_preview", False)),
        "requires_approval": bool(raw.get("requires_approval", False)),
        "has_side_effects": bool(raw.get("has_side_effects", raw.get("mutates_scene", False))),
        "requires_selection": bool(raw.get("requires_selection", False)),
        "supports_headless": bool(raw.get("supports_headless", not raw.get("mutates_scene", False))),
        "risk_level": risk_level,
        "timeout_seconds": int(raw.get("timeout_seconds") or DEFAULT_TOOL_TIMEOUT_SECONDS),
        "permissions": _permissions(raw),
        "output_schema": raw.get("output_schema") or DEFAULT_OUTPUT_SCHEMA,
    }
    for key, value in raw.items():
        normalized.setdefault(key, value)
    return normalized


def output_schema_for_tool(name):
    return normalized_tool_contract(name).get("output_schema") or DEFAULT_OUTPUT_SCHEMA


def mcp_annotations_for_tool(name):
    contract = normalized_tool_contract(name)
    mutates = bool(contract["mutates_scene"])
    side_effects = bool(contract["has_side_effects"])
    approval = bool(contract["requires_approval"])
    destructive = bool(contract.get("destructive", False))
    return {
        "mutatesScene": mutates,
        "hasSideEffects": side_effects,
        "requiresApproval": approval,
        "requiresLivePreview": bool(contract["requires_live_preview"]),
        "riskLevel": contract["risk_level"],
        "permissions": list(contract["permissions"]),
        "readOnlyHint": not side_effects,
        "destructiveHint": destructive,
        "idempotentHint": False,
        "openWorldHint": False,
    }


def list_tool_contracts():
    return {
        "bridge_version": BRIDGE_VERSION,
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "tools": {
            name: normalized_tool_contract(name, contract)
            for name, contract in TOOL_CONTRACTS.items()
        },
    }


def register():
    pass


def unregister():
    pass
