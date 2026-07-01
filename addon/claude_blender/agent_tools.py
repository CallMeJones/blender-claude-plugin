"""Provider-neutral tool catalog and routing hints for external agents."""

from __future__ import annotations

import json

try:
    from . import bridge_protocol, helper_routing, script_analysis
except ImportError:  # Allows direct imports from addon/claude_blender.
    import bridge_protocol
    import helper_routing
    import script_analysis


AGENT_GUIDANCE = (
    "You are an external agent connected to Blender Agent Bridge. Use the provided scene context and Blender tools. "
    "Read context_plan before acting. It explains which scene details were included or omitted to stay within the request budget. "
    "If omitted details matter, call inspect_scene, get_object_details, get_animation_details, get_animation_scene_context, get_material_node_details, get_geometry_nodes_details, get_shader_nodes_details, get_rigging_details, get_shape_key_details, get_curve_text_details, get_simulation_details, inspect_simulation_bake, get_collection_layer_details, get_render_camera_compositor_details, get_blend_file_diagnostics, get_workspace_layout, get_visual_evidence_resources, capture_viewport, capture_animation_playblast, capture_object_inspection_renders, render_scene_thumbnail, start_render_job, get_render_job_status, assemble_render_job_video, validate_render_job_output, or search_blender_docs instead of guessing. "
    "For .blend lifecycle work, use get_blend_file_diagnostics before save/open/new decisions. Never invent durable file paths: ask the user for any new project folder, save-as/save-copy filepath, or open filepath; set user_confirmed_path=true only when the path came from the user or a file picker. Bound edits may save the active .blend path without a new filepath. Use autosave_current_blend_file only for already-bound saved .blend files. "
    "When target objects are unclear, use list_scene_objects and select_objects before applying selected-object tools. "
    "When the user asks to change the scene, use safe helper tools first so Blender changes immediately. "
    "Use direct Blender data concepts: objects, collections, materials, cameras, lights, actions, keyframes. "
    "For broad multi-step scene, asset, animation, and evidence work, call plan_director_workflow first to get an ordered helper/evidence/preview plan without mutating the scene. For advanced 3D, 2D/storyboard, animation, simulation, compositor/render, asset-import, or script-heavy tasks, call plan_advanced_scene_workflow first when the helper path is not obvious. It returns domain-specific helpers and script fallback boundaries. "
    "For scene building and layout, prefer create_primitive, create_empty, duplicate_selected_objects, parent_selected_to_empty, align_selected_objects, distribute_selected_objects, set_object_visibility, set_object_display, assign_material_to_selected, assign_emission_material_to_selected, create_shader_material, create_text_object, create_curve_path, create_collection, link_selected_to_collection, add_light, add_camera, add_modifier_to_selected, add_geometry_nodes_modifier, apply_procedural_array_stack, create_procedural_object_kit, add_track_to_constraint, add_copy_transform_constraint, create_basic_armature, add_particle_system_to_selected, add_cloth_simulation_to_selected, set_render_settings, set_camera_settings, and set_world_background. create_shader_material includes bounded material presets; add_geometry_nodes_modifier includes passthrough, transform, join-geometry, set-position, and subdivide-mesh starter templates. "
    "For 2D, storyboard, animatic, cutout, or motion-graphics work, inspect first with get_2d_animation_details, then prefer create_storyboard_panels, create_2d_cutout_layer, create_camera_dolly_animation, capture_animation_playblast, and render jobs before drafting custom Grease Pencil or SVG Python. "
    "For model refinement and production presentation, prefer shade_smooth_selected, add_bevel_and_subsurf, apply_procedural_array_stack, create_procedural_object_kit, create_wheel_assembly, add_panel_seams, add_window_materials, apply_vehicle_refinement_template, apply_product_refinement_template, apply_character_refinement_template, create_studio_product_stage, add_dimension_callouts, apply_lighting_preset, create_material_palette, create_product_turntable_setup, prepare_imported_asset_presentation, and organize_scene_for_production when they fit the task. create_procedural_object_kit includes kitbash, radial/scatter/product, mechanical-joint, control-panel, studio-prop, mechanical-part, modular-wall-panel, and pipe-run templates for bounded prop generation before custom mesh scripts. "
    "For shape-key animation, prefer create_shape_key and animate_shape_key before drafting Python. "
    "For quick animation playblasts and visual review, use low-resolution preview defaults unless the user explicitly asks for HD/final/1080p/4K quality. For long-running or high-resolution renders, frame sequences, 1080p/4K previews, or MP4 quality checks, use start_render_job and poll get_render_job_status instead of blocking render_scene_thumbnail, capture tools, or draft_script; report the returned rough estimate/poll interval to the user; use assemble_render_job_video for PNG sequences and validate_render_job_output before reporting success; use cancel_render_job if the user wants to stop it. If a render, playblast, or visual-review tool times out, treat it as recoverable: wait the returned poll_after_seconds, call blender_bridge_status, inspect get_visual_evidence_resources and the audit log, and only rerun if no artifact/result appears. "
    "For simulation setup, prefer add_cloth_simulation_to_selected or add_particle_system_to_selected for bounded setup, then inspect with get_simulation_details or inspect_simulation_bake. For persistent simulation/cache bakes or cache-freeing operations, use stage_persistent_simulation_bake for a fixed approval-gated script. Session-wide external script trust is not enough for bpy.ops.fluid.* or bpy.ops.ptcache.* bake/free operators; they require explicit one-time user approval. Do not hand the user a checkpoint or recovery .blend path unless you just verified that it exists and is restorable through checkpoint metadata, diagnostics, or a filesystem check. "
    "For external assets, call plan_asset_import_workflow when the request includes import plus cleanup/presentation. Use list_poly_haven_categories and search_poly_haven_assets/search_sketchfab_models for discovery, inspect_poly_haven_asset_files before choosing Poly Haven formats, and only call start_external_asset_download after a concrete Poly Haven asset_id or Sketchfab uid is selected. Poll get_external_asset_job_status until completed or failed. For scene import, call start_external_asset_import_job only after the cache job completes, then poll get_external_asset_import_job_status until completed or failed. After import completes, call prepare_imported_asset_presentation with imported_object_names from the import result to organize, fill missing materials, and build a bounded studio/turntable setup before visual evidence capture. Use download_poly_haven_asset, import_poly_haven_asset, download_sketchfab_model, import_sketchfab_model, and import_external_asset_job_result only for explicit synchronous fallback/debug cases. Use get_external_asset_cache_diagnostics to report cached/imported assets. Sketchfab API tokens must be provided per call or through the MCP server environment, not Blender preferences. "
    "For animation generation, review, or repair, call run_animation_task for simple prompt-in/task-out use, or call plan_animation_workflow first when you need manual control of the generated workflow. plan_animation_workflow returns the brief, scene routing, timing chart, ordered helper calls, evaluator calls, repair calls, and script fallback rules. For common helper-backed generation, call run_animation_workflow to execute the plan, review the result, optionally capture playblast evidence, and leave changes in preview. Use any animation_brief in context as the prompt contract; otherwise call create_animation_brief first when the prompt needs an explicit contract, success criteria, or later validation. Call get_animation_scene_context before advanced animation in scenes with rigs, constraints, drivers, shape keys, physics, or unclear edit targets so you know whether to animate object transforms, rig controls, shape keys, materials, physics, or camera settings. Use create_timing_chart, block_key_poses, add_breakdown_pose, set_pose_hold, set_rig_pose_hold, get_rig_pose_library_details, apply_rig_pose_from_action, apply_rig_pose_marker, apply_rig_action_clip, offset_rig_limb_controls, set_rig_custom_property_keyframes, create_directed_animation_shot, create_camera_dolly_animation, and create_motion_arc for animator-style blocking before spline/f-curve polish; use rig pose/action helpers only after identifying armature controls, pose-library candidates, or existing scalar IK/FK/space properties through rig inspection or repair metadata. Then use analyze_animation_principles plus focused analyzers to check timing, spacing, arcs, pose clarity, anticipation, squash/stretch, contact, center-of-mass support, speed/acceleration plausibility, simulation cache readiness, and settle before repair; use inspect_simulation_bake before persistent bake decisions, and use stage_persistent_simulation_bake when the user intentionally wants a persistent point-cache bake. Use capture_animation_playblast and review_playblast_against_brief when visual frame evidence matters; use capture_object_inspection_renders and review_inspection_renders_against_brief when close-up object detail evidence matters; if review or repair tools return repair_operations, prefer run_animation_repair_loop for bounded helper repair and review-again behavior, or execute relevant tool_call name/input entries deliberately when manual control is needed. Then prefer set_scene_frame_range, set_animation_preview_range, animate_selected_transform, animate_object_bounce, create_progressive_bounce_animation, animate_material_property, animate_light_property, create_follow_path_animation, create_turntable_animation, create_pulse_animation, create_reveal_animation, create_staggered_motion, create_directed_animation_shot, set_action_interpolation, retime_actions, add_action_cycles, clear_animation, create_camera_dolly_animation, and create_camera_orbit. "
    "For complex scene builds that need many objects or more than about eight helper calls, stage one cohesive Blender Python script with draft_script instead of making a long chain of helper calls. "
    "Use draft_script for custom or larger advanced scene scripts when static checks pass; helper overlap should be treated as advice. Use draft_privileged_script for custom external asset or project-file lifecycle scripts that need declared filesystem, network, asset-import, or project-file capabilities. Privileged scripts require a manifest and never auto-run under normal external script trust. Persistent simulation/cache bakes stay on their dedicated one-time approval path. If the user has granted external script trust, draft_script may auto-run after static checks. "
    "When calling draft_script or draft_privileged_script, put the complete Python source in the code field. Do not put script code in final chat text for the user to paste manually. "
    "If draft_script reports that code is missing, retry once with a shorter complete script in the code field. "
    "A drafted script runs only when draft_script reports auto_ran true or the user explicitly approves it in Blender, so do not claim it executed from staging alone. "
    "Before drafting unfamiliar or version-sensitive Python, search_blender_docs for the relevant Blender API. "
    "Do not suggest destructive changes without clearly warning the user. "
    "Do not invent dimensions, materials, object names, or animation details. "
    "If a value is absent, say it is not available in the context. "
    "For low-risk changes, call tools instead of merely explaining what should be done. "
    "Leave live preview changes pending for the user; do not call commit_preview or revert_preview unless the user explicitly asks. "
    "Generated arbitrary Python is approval-gated by default and must be drafted through draft_script or draft_privileged_script. "
    "When tool work is complete, provide a concise final summary of what changed and what remains pending."
)


def estimate_request_chars(*, messages=None, tools=None, system=AGENT_GUIDANCE):
    payload = {
        "system": system,
        "messages": messages or [],
        "tools": tools or [],
    }
    return len(json.dumps(payload, sort_keys=True))


def blender_tool_definitions():
    return [
        {
            "name": "inspect_scene",
            "description": "Inspect the current Blender scene and selected objects. Use before acting if context may be stale.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "include_visual": {"type": "boolean", "description": "Whether viewport image context was requested"}
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "capture_viewport",
            "description": "Capture the current Blender viewport/window and return visual context metadata plus a local artifact path. Use when an external agent needs explicit screenshot evidence or MCP-readable image resources.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "max_bytes": {
                        "type": "integer",
                        "description": "Maximum PNG bytes to keep after resizing/compression. Defaults to the add-on preference.",
                    }
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "capture_animation_playblast",
            "description": "Capture sampled low-resolution viewport frames across an animation range and return playblast metadata plus MCP frame resource URIs for visual animation review. Defaults to preview quality capped at 640x360; request quality/max_width/max_height only when higher fidelity is needed. Requires an interactive Blender window and fails soft in background mode. This is synchronous and roughly 1 second per sampled frame; if it times out, wait and check blender_bridge_status/latest playblast metadata before recapturing.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "max_frames": {
                        "type": "integer",
                        "description": "Maximum sampled frames to capture from the animation range. Defaults to 12.",
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": "Maximum PNG bytes per sampled frame after resizing/compression.",
                    },
                    "quality": {
                        "type": "string",
                        "enum": ["preview", "low", "standard", "medium", "high", "hd", "source", "original", "full"],
                        "description": "Frame-size preset. Defaults to preview/low at 640x360; source/original keeps viewport dimensions.",
                    },
                    "max_width": {
                        "type": "integer",
                        "description": "Optional maximum stored frame width. Overrides the quality preset.",
                    },
                    "max_height": {
                        "type": "integer",
                        "description": "Optional maximum stored frame height. Overrides the quality preset.",
                    },
                    "brief": {
                        "type": "string",
                        "description": "Short animation intent or prompt contract to store with the playblast metadata.",
                    },
                    "shading": {
                        "type": "string",
                        "enum": bridge_protocol.PLAYBLAST_SHADING_MODES,
                        "description": "Optional viewport shading for the capture. Defaults to the current viewport; use MATERIAL or RENDERED to review materials and lighting instead of flat solid shading.",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "capture_object_inspection_renders",
            "description": "Render diagnostic close-up PNGs of named objects from bounded inspection views, then return metadata plus MCP image resource URIs. Use when visual object details need rendered evidence, such as undersides, side views, occluded parts, or model defects. This is synchronous and may take a few seconds per object/view; if it times out, wait and check blender_bridge_status/latest inspection-render metadata before recapturing.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Objects or root objects to render. Children are included when computing bounds.",
                    },
                    "views": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["front_below", "underside", "side", "front", "rear", "top"],
                        },
                        "description": "Diagnostic view names. Defaults to front_below and side.",
                    },
                    "frame": {"type": "integer", "description": "Frame to render. Defaults to the current frame."},
                    "resolution_x": {"type": "integer", "description": "PNG width. Defaults to 800."},
                    "resolution_y": {"type": "integer", "description": "PNG height. Defaults to 600."},
                    "lens": {"type": "number", "description": "Temporary camera lens in mm. Defaults to 50."},
                    "distance_factor": {
                        "type": "number",
                        "description": "Camera distance as a multiple of target bounding radius. Defaults to 3.",
                    },
                    "camera_name": {"type": "string"},
                    "note": {"type": "string", "description": "Short reason stored in the render metadata."},
                },
                "required": ["object_names"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_blend_file_diagnostics",
            "description": "Inspect blend-file health: saved path, dirty state, backups, missing external files, linked libraries, and data-block usage summaries.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "max_items": {"type": "integer", "description": "Maximum external file/library entries to return."},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "save_blend_file",
            "description": "Save the current .blend, save-as to a human-confirmed .blend path, or save a copy without changing the active file. Refuses accidental overwrite unless overwrite=true.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Optional .blend path. Omit to save the active file."},
                    "copy": {"type": "boolean", "description": "Save a copy without changing the active filepath. Requires filepath."},
                    "overwrite": {"type": "boolean", "description": "Allow replacing an existing target .blend file."},
                    "create_dirs": {"type": "boolean", "description": "Create the target directory if missing. Defaults to true."},
                    "user_confirmed_path": {"type": "boolean", "description": "Required true for save-as/save-copy. Set only after the user provides the filepath."},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "open_blend_file",
            "description": "Open an existing user-confirmed .blend file. This replaces the active Blender session, so confirm_discard_current and user_confirmed_path must be true; creates a checkpoint first by default.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Existing .blend file path to open."},
                    "confirm_discard_current": {"type": "boolean", "description": "Required true; opening replaces the active session."},
                    "create_checkpoint": {"type": "boolean", "description": "Save a checkpoint before opening. Defaults to true."},
                    "require_checkpoint": {"type": "boolean", "description": "Abort if checkpoint creation fails. Defaults to true."},
                    "checkpoint_dir": {"type": "string"},
                    "load_ui": {"type": "boolean", "description": "Load UI layout from the opened file when supported. Defaults to false."},
                    "user_confirmed_path": {"type": "boolean", "description": "Required true. Set only after the user provides the filepath."},
                },
                "required": ["filepath", "confirm_discard_current", "user_confirmed_path"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_new_blender_project",
            "description": "Create a new Blender project folder and .blend file at a user-confirmed path. This replaces the active Blender session, so confirm_discard_current and user_confirmed_path must be true; creates a checkpoint first by default.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Parent or final project directory. Required unless filepath is supplied."},
                    "project_name": {"type": "string", "description": "Project name used for folder/filename when filepath is omitted."},
                    "filepath": {"type": "string", "description": "Optional explicit target .blend path."},
                    "template": {"type": "string", "enum": ["default", "empty", "factory_startup"]},
                    "create_standard_dirs": {"type": "boolean", "description": "Create assets, refs, renders, and exports folders. Defaults to true."},
                    "standard_dirs": {"type": "array", "items": {"type": "string"}},
                    "overwrite": {"type": "boolean", "description": "Allow replacing an existing target .blend file."},
                    "create_dirs": {"type": "boolean", "description": "Create the project directory if missing. Defaults to true."},
                    "confirm_discard_current": {"type": "boolean", "description": "Required true; new project replaces the active session."},
                    "create_checkpoint": {"type": "boolean", "description": "Save a checkpoint before creating the new project. Defaults to true."},
                    "require_checkpoint": {"type": "boolean", "description": "Abort if checkpoint creation fails. Defaults to true."},
                    "checkpoint_dir": {"type": "string"},
                    "user_confirmed_path": {"type": "boolean", "description": "Required true. Set only after the user provides the project_dir or filepath."},
                },
                "required": ["confirm_discard_current", "user_confirmed_path"],
                "additionalProperties": False,
            },
        },
        {
            "name": "autosave_current_blend_file",
            "description": "Autosave the current open .blend in place. It has no filepath argument and refuses unsaved scenes.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "force": {"type": "boolean", "description": "Save even when the file is not dirty, the interval has not elapsed, or live preview changes are pending. Defaults to false."},
                    "reason": {"type": "string", "description": "Short reason for the autosave."},
                    "respect_enabled": {"type": "boolean", "description": "Skip if the autosave preference is disabled. Defaults to false."},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_workspace_layout",
            "description": "Return JSON for Blender workspaces, windows, screens, and UI areas. Use before workspace/view navigation or UI diagnostics.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "max_workspaces": {"type": "integer"},
                    "max_areas": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_visual_evidence_resources",
            "description": "Return a compact inventory of latest MCP-readable viewport captures, playblasts, inspection renders, render thumbnails, and render jobs. Use when an agent needs to know what visual/render evidence exists and which resource URIs can be read.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "include_unavailable": {
                        "type": "boolean",
                        "description": "Include resource families with no latest artifact yet. Defaults to true.",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "jump_to_workspace",
            "description": "Switch the active Blender window to a named workspace/tab. Requires an interactive Blender UI and fails soft in background mode.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "workspace_name": {"type": "string"},
                },
                "required": ["workspace_name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_viewport_view",
            "description": "Set the first 3D viewport to an axis, camera, or user view and optionally frame an object. Requires an interactive Blender UI and fails soft in background mode.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "view": {"type": "string", "enum": ["front", "back", "left", "right", "top", "bottom", "camera", "user"]},
                    "frame_object_name": {"type": "string", "description": "Optional object to frame after changing view."},
                    "use_orthographic": {"type": "boolean", "description": "Use orthographic axis views when possible. Defaults to true."},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "focus_object_in_viewport",
            "description": "Frame a named object in the first 3D viewport and optionally select it. Requires an interactive Blender UI and fails soft in background mode.",
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
        {
            "name": "render_scene_thumbnail",
            "description": "Render a small PNG from the scene camera or a named camera, then return metadata plus exact MCP image resource URIs. Use for render evidence, thumbnails, and client-readable still output. Large synchronous renders are guarded; use start_render_job for timeout-safe high-resolution output.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Optional PNG output path. Defaults to the project/session capture cache."},
                    "frame": {"type": "integer", "description": "Frame to render. Defaults to current frame."},
                    "resolution_x": {"type": "integer", "description": "PNG width. Defaults to 512."},
                    "resolution_y": {"type": "integer", "description": "PNG height. Defaults to 512."},
                    "camera_name": {"type": "string", "description": "Optional camera object name. Defaults to active scene camera."},
                    "note": {"type": "string", "description": "Short reason stored in thumbnail metadata."},
                    "allow_blocking_render": {"type": "boolean", "description": "Allow a large synchronous still render. Defaults to false; large previews should use start_render_job."},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "start_render_job",
            "description": "Start a long-running render or playblast job in a background Blender process and return immediately with a job id, rough ETA, and polling guidance. Auto quality keeps final renders high quality but defaults playblast/preview/review/draft jobs to low resolution unless quality or resolution is specified. Use for 1080p/4K, high-sample, full-frame-range renders, frame sequences, or MP4 quality checks instead of blocking render tools or draft_script.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "resolution_x": {"type": "integer", "description": "Output width. Defaults to auto quality profile: 640 for playblast/preview/review jobs, 1920 for final renders."},
                    "resolution_y": {"type": "integer", "description": "Output height. Defaults to auto quality profile: 360 for playblast/preview/review jobs, 1080 for final renders."},
                    "resolution_percentage": {"type": "integer", "description": "Render percentage. Defaults to 100."},
                    "samples": {"type": "integer", "description": "Cycles/Eevee render samples. Defaults to auto quality profile: low for playblast/preview/review jobs, higher for final renders."},
                    "quality": {
                        "type": "string",
                        "enum": ["auto", "preview", "low", "standard", "medium", "high", "hd", "final", "full", "production", "1080p"],
                        "description": "Defaulting profile when resolution/samples are omitted. Auto uses low-res for playblast/preview/review/draft jobs and final-quality defaults otherwise.",
                    },
                    "fps": {"type": "integer"},
                    "camera_name": {"type": "string", "description": "Optional camera object to render from. Timeline camera markers still work when no camera is passed."},
                    "output_kind": {"type": "string", "enum": ["frames", "video", "mp4"], "description": "Use frames for PNG sequences with progress counts, or video/mp4 for direct MP4 output."},
                    "job_name": {"type": "string"},
                    "note": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_render_job_status",
            "description": "Poll a background render job for status, frame progress, output paths, latest frame resource URI, log tail, and completion state.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "cancel_render_job",
            "description": "Cancel a tracked background render job started by this Blender bridge session.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "assemble_render_job_video",
            "description": "Assemble a completed PNG frame-sequence render job into an MP4 in a background Blender process, then poll get_render_job_status for completion.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "fps": {"type": "integer", "description": "Optional output FPS. Defaults to the render job FPS."},
                    "output_path": {"type": "string", "description": "Optional MP4 path. Relative paths resolve inside the render job folder."},
                    "quality": {"type": "string", "enum": ["LOWEST", "LOW", "MEDIUM", "HIGH", "PERC_LOSSLESS", "LOSSLESS"], "description": "Blender FFmpeg quality. Defaults to HIGH."},
                    "overwrite": {"type": "boolean", "description": "Overwrite an existing MP4. Defaults to true."},
                    "allow_partial": {"type": "boolean", "description": "Allow assembly before every expected frame is present. Defaults to false."},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "validate_render_job_output",
            "description": "Validate render job frame completeness, MP4 presence/size, and useful output resource URIs before reporting a render as done.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "require_video": {"type": "boolean", "description": "Require MP4 output. Defaults to true."},
                    "min_video_size_bytes": {"type": "integer", "description": "Minimum acceptable MP4 size. Defaults to 1 byte."},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_object_details",
            "description": "Fetch deeper read-only details for named objects, selected objects, or the active object.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional object names to inspect",
                    },
                    "selected_only": {
                        "type": "boolean",
                        "description": "Inspect current selected objects when object_names is empty",
                    },
                    "max_objects": {
                        "type": "integer",
                        "description": "Maximum objects to return",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "list_scene_objects",
            "description": "List objects in the current scene with names, types, selection state, visibility, collections, and locations.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "type_filter": {
                        "type": "string",
                        "description": "Optional Blender object type such as MESH, CAMERA, LIGHT, EMPTY",
                    },
                    "max_objects": {
                        "type": "integer",
                        "description": "Maximum objects to return",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_animation_details",
            "description": "Fetch read-only scene, object, action, f-curve, and keyframe details for animation planning.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional object names whose actions should be inspected",
                    },
                    "action_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional action names to inspect",
                    },
                    "max_actions": {
                        "type": "integer",
                        "description": "Maximum actions to return",
                    },
                    "max_keyframes_per_curve": {
                        "type": "integer",
                        "description": "Maximum keyframes to show per f-curve",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_animation_scene_context",
            "description": "Build read-only animation-aware scene context that identifies likely edit targets, rig-driven objects, rig control candidates, shape keys, constraints, drivers, NLA, physics/simulation hints, contact surfaces, camera readiness, hardening risk flags, required pre-mutation inspections, and recommended deeper inspection/review tools.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional objects to inspect. Defaults to the scene unless selected_only is true.",
                    },
                    "selected_only": {
                        "type": "boolean",
                        "description": "Inspect only selected objects when object_names is empty.",
                    },
                    "max_objects": {
                        "type": "integer",
                        "description": "Maximum objects to summarize.",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_animation_brief",
            "description": "Create a structured animation prompt contract with subjects, action, timing, assumptions, ambiguities, success criteria, and validation checks. Does not mutate the scene.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The user's animation request or concise animation intent to formalize.",
                    },
                    "subject_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional existing Blender object names to treat as animated subjects. Defaults to the current selection.",
                    },
                    "action": {"type": "string", "description": "Optional explicit primary action if the prompt is ambiguous."},
                    "style": {"type": "string", "description": "Optional style/read such as playful, heavy, snappy, or cinematic."},
                    "camera": {"type": "string", "description": "Optional camera name or framing requirement."},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "constraints": {"type": "array", "items": {"type": "string"}},
                    "success_criteria": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_timing_chart",
            "description": "Create a read-only animator-style timing chart from a prompt or animation brief, with key poses, contacts, holds, breakdowns, and spacing notes.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "brief": {"type": "object"},
                    "subject_names": {"type": "array", "items": {"type": "string"}},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "beats": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "frame": {"type": "integer"},
                                "label": {"type": "string"},
                                "role": {"type": "string"},
                                "hold_frames": {"type": "integer"},
                                "notes": {"type": "array", "items": {"type": "string"}},
                            },
                            "additionalProperties": False,
                        },
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "plan_animation_workflow",
            "description": "Plan the Milestone 7 animation workflow for generation, review, or repair. Returns a brief, animation-aware scene context, timing chart, ordered helper/evaluator/repair tool calls, and explicit draft_script fallback rules. Does not mutate the scene.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The user's animation generation, review, or repair request.",
                    },
                    "subject_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional existing Blender object names to treat as animated subjects.",
                    },
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "mode": {
                        "type": "string",
                        "enum": ["generate", "review", "repair", "full"],
                        "description": "Workflow focus. full includes generation and validation guidance.",
                    },
                    "selected_only": {"type": "boolean"},
                    "max_objects": {"type": "integer"},
                    "brief": {"type": "object", "description": "Optional existing animation brief."},
                    "timing_chart": {"type": "object", "description": "Optional existing timing chart."},
                    "playblast": {"type": "object", "description": "Optional existing playblast metadata."},
                    "findings": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Optional evaluator findings to plan repair calls.",
                    },
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        },
        {
            "name": "run_animation_workflow",
            "description": "Execute the Milestone 7 helper-backed animation workflow for common requests, then run structured review and optional bounded repair. May leave live preview changes pending for commit/revert.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The user's animation generation, review, or repair request."},
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
                    "apply_generation": {"type": "boolean", "description": "Whether to execute allowlisted generation helpers from the workflow. Defaults to true."},
                    "run_review": {"type": "boolean", "description": "Whether to run structured evaluator review after generation. Defaults to true."},
                    "capture_playblast": {"type": "boolean", "description": "Whether to request sampled viewport frames during review. Defaults to false for headless-safe use."},
                    "apply_repairs": {"type": "boolean", "description": "Whether to execute bounded repair operations from evaluator findings. Defaults to false."},
                    "max_generation_steps": {"type": "integer"},
                    "max_repair_iterations": {"type": "integer"},
                    "max_repair_operations": {"type": "integer"},
                    "recapture_after_repair": {"type": "boolean"},
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        },
        {
            "name": "run_animation_task",
            "description": "One-input animation entry point for MCP clients. Routes the prompt through the Milestone 7 planner/runner workflow before any draft_script fallback.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The user's animation generation, review, or repair request.",
                    },
                },
                "required": ["prompt"],
                "additionalProperties": False,
            },
        },
        {
            "name": "analyze_motion_arcs",
            "description": "Read-only analysis of sampled keyed location motion arcs for selected or named objects.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "max_samples": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "analyze_fcurve_spacing",
            "description": "Read-only analysis of transform key spacing, segment distances, and interpolation choices.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "paths": {"type": "array", "items": {"type": "string", "enum": ["location", "rotation_euler", "scale"]}},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "analyze_pose_clarity",
            "description": "Read-only analysis of keyed pose count, transform readability, and detected holds.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "analyze_animation_principles",
            "description": "Evaluate keyed animation against core animation principles and the prompt contract. Returns structured findings that can feed repair.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "prompt": {"type": "string"},
                    "brief": {"type": "object"},
                    "timing_chart": {"type": "object"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "sample_animation_state",
            "description": "Sample selected or named object transforms across an animation range for objective review.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "sample_step": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "analyze_contact_sliding",
            "description": "Detect sliding while animated object bounds are near a contact plane.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "sample_step": {"type": "integer"},
                    "contact_z": {"type": "number"},
                    "contact_tolerance": {"type": "number"},
                    "sliding_tolerance": {"type": "number"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "analyze_collision_penetration",
            "description": "Detect sampled world bounding-box intersections between animated objects.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "sample_step": {"type": "integer"},
                    "tolerance": {"type": "number"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "analyze_center_of_mass",
            "description": "Check sampled subject centers against support-surface footprints for balance, weight, and contact plausibility.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "support_object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "sample_step": {"type": "integer"},
                    "support_margin": {"type": "number"},
                    "contact_tolerance": {"type": "number"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "analyze_camera_framing",
            "description": "Check whether animated subjects stay inside a camera-safe region.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "camera_name": {"type": "string"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "sample_step": {"type": "integer"},
                    "margin": {"type": "number"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "analyze_motion_physics",
            "description": "Check sampled speed and acceleration for physically implausible spikes in Blender units.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "sample_step": {"type": "integer"},
                    "max_speed": {"type": "number"},
                    "max_acceleration": {"type": "number"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "compare_animation_to_brief",
            "description": "Compare current animation samples and framing against a structured animation brief or prompt.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "brief": {"type": "object"},
                    "prompt": {"type": "string"},
                    "subject_names": {"type": "array", "items": {"type": "string"}},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "review_playblast_against_brief",
            "description": "Review playblast visual frame evidence, compact pixel motion evidence, and current animation state against a prompt contract. Returns structured findings and repair_operations with executable tool_call name/input pairs.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "playblast": {"type": "object"},
                    "brief": {"type": "object"},
                    "prompt": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "review_inspection_renders_against_brief",
            "description": "Review diagnostic object render evidence against a prompt contract. Returns visual-detail findings and repair_operations, including focused recapture calls when views or image evidence are missing.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "inspection_render": {"type": "object"},
                    "brief": {"type": "object"},
                    "prompt": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "repair_animation_from_findings",
            "description": "Turn structured animation findings into focused repair operations with suggested helper tool arguments and executable tool_call name/input pairs. Does not mutate the scene.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "findings": {"type": "array", "items": {"type": "object"}},
                    "brief": {"type": "object"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "run_animation_repair_loop",
            "description": "Apply a bounded set of animation repair_operations through safe helper tools, optionally recapture playblast evidence, and re-run review_playblast_against_brief. May leave preview changes pending for commit/revert.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "playblast": {"type": "object"},
                    "brief": {"type": "object"},
                    "prompt": {"type": "string"},
                    "findings": {"type": "array", "items": {"type": "object"}},
                    "repair_operations": {"type": "array", "items": {"type": "object"}},
                    "max_iterations": {
                        "type": "integer",
                        "description": "Maximum review/repair iterations. Defaults to 2.",
                    },
                    "max_operations": {
                        "type": "integer",
                        "description": "Maximum helper operations to execute. Defaults to 4.",
                    },
                    "apply_mutating_repairs": {
                        "type": "boolean",
                        "description": "Whether to execute preview-safe mutating repair helpers. Defaults to true.",
                    },
                    "recapture_after_mutation": {
                        "type": "boolean",
                        "description": "Whether to request a fresh playblast after mutating repairs before final review. Defaults to true.",
                    },
                    "allowed_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional allowlist of repair helper tool names for this loop.",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_material_node_details",
            "description": "Fetch read-only material node and link details for named or selected-object materials.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "material_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional material names to inspect",
                    },
                    "selected_only": {
                        "type": "boolean",
                        "description": "Use materials on selected objects when material_names is empty",
                    },
                    "max_materials": {
                        "type": "integer",
                        "description": "Maximum materials to return",
                    },
                    "max_nodes": {
                        "type": "integer",
                        "description": "Maximum nodes per material",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_geometry_nodes_details",
            "description": "Fetch read-only Geometry Nodes modifier and node-group summaries for named objects or all objects with Geometry Nodes.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "max_objects": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_shader_nodes_details",
            "description": "Fetch read-only shader node-tree, node, link, and driver summaries for materials.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "material_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "max_materials": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_rigging_details",
            "description": "Fetch read-only armature, bone, pose-bone, constraint, and driver summaries.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "max_objects": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_shape_key_details",
            "description": "Fetch read-only mesh shape key blocks, values, ranges, relative keys, and shape-key drivers.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "max_objects": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_curve_text_details",
            "description": "Fetch read-only curve and text object data including splines, bevels, text body preview, alignment, and materials.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "max_objects": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_simulation_details",
            "description": "Fetch read-only rigid-body, particle, point-cache, and simulation bake summaries for cloth, fluid, soft body, dynamic paint, and particles.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "max_objects": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "inspect_simulation_bake",
            "description": "Sample evaluated simulation state across a bounded frame range and report cache/bake readiness without mutating persistent point caches.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "sample_count": {"type": "integer"},
                    "max_objects": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "stage_persistent_simulation_bake",
            "description": "Stage a fixed-template scene-wide persistent simulation point-cache bake script for explicit user approval. Persistent bake/free operators do not auto-run under session-wide external script trust.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "clear_existing": {"type": "boolean"},
                    "include_scene_rigid_body_world": {"type": "boolean"},
                    "auto_run_if_trusted": {
                        "type": "boolean",
                        "description": "Compatibility option only; explicit-approval-only bake/free scripts remain staged even when external script trust is active.",
                    },
                    "max_objects": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_collection_layer_details",
            "description": "Fetch read-only collection tree, collection membership, visibility flags, and view-layer pass summaries.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "max_depth": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_render_camera_compositor_details",
            "description": "Fetch read-only render settings, active camera settings, world settings, and compositor node summaries.",
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "set_selected_location_delta",
            "description": "Move selected Blender objects by a delta in Blender units. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "delta": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "[x, y, z] movement delta in Blender units",
                    },
                    "label": {"type": "string"},
                },
                "required": ["delta"],
                "additionalProperties": False,
            },
        },
        {
            "name": "select_objects",
            "description": "Select named objects and optionally set the active object. Use before selected-object helper tools when needed.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Object names to select",
                    },
                    "active_object_name": {
                        "type": "string",
                        "description": "Optional object to make active",
                    },
                    "extend": {
                        "type": "boolean",
                        "description": "Keep existing selection instead of replacing it",
                    },
                },
                "required": ["object_names"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_current_frame",
            "description": "Set the current scene frame/playhead for inspection or preview.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "frame": {"type": "integer"},
                },
                "required": ["frame"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_selected_transform",
            "description": "Set absolute transform values on selected Blender objects. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Optional absolute [x, y, z] location in Blender units",
                    },
                    "rotation": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Optional absolute Euler rotation in radians",
                    },
                    "scale": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Optional absolute [x, y, z] scale",
                    },
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_primitive",
            "description": "Create a mesh primitive in the current scene. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "primitive_type": {
                        "type": "string",
                        "enum": ["CUBE", "UV_SPHERE", "ICO_SPHERE", "CYLINDER", "CONE", "PLANE", "TORUS"],
                    },
                    "name": {"type": "string"},
                    "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "rotation": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Euler rotation in radians",
                    },
                    "scale": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "label": {"type": "string"},
                },
                "required": ["primitive_type", "name", "location", "rotation", "scale"],
                "additionalProperties": False,
            },
        },
        {
            "name": "assign_material_to_selected",
            "description": "Create or update a material and assign it to selected mesh objects. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Material name"},
                    "color": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 4,
                        "description": "RGBA color components from 0 to 1",
                    },
                    "label": {"type": "string"},
                },
                "required": ["name", "color"],
                "additionalProperties": False,
            },
        },
        {
            "name": "assign_emission_material_to_selected",
            "description": "Create a new emission material node setup and assign it to selected mesh objects. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Material name"},
                    "color": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 4,
                        "description": "RGBA color components from 0 to 1",
                    },
                    "strength": {"type": "number", "description": "Emission strength"},
                    "label": {"type": "string"},
                },
                "required": ["name", "color", "strength"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_collection",
            "description": "Create or find a collection in the current scene. Applies immediately with preview revert support for newly created collections.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "link_selected_to_collection",
            "description": "Link selected objects to a named collection without deleting existing links. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "collection_name": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["collection_name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "add_modifier_to_selected",
            "description": "Add a bounded common modifier to selected mesh objects. Supports BEVEL, SUBSURF, SOLIDIFY, and ARRAY. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "modifier_type": {"type": "string", "enum": ["BEVEL", "SUBSURF", "SOLIDIFY", "ARRAY"]},
                    "name": {"type": "string"},
                    "amount": {"type": "number", "description": "Width/thickness value for BEVEL or SOLIDIFY"},
                    "segments": {"type": "integer", "description": "Bevel segments"},
                    "levels": {"type": "integer", "description": "Subdivision levels"},
                    "count": {"type": "integer", "description": "Array count"},
                    "relative_offset": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Array relative offset [x, y, z]",
                    },
                    "label": {"type": "string"},
                },
                "required": ["modifier_type", "name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_shader_material",
            "description": "Create or update a Principled BSDF material from explicit values or bounded presets such as brushed metal, matte plastic, clear glass, emissive accent, or matte ceramic. Optionally assigns it to selected mesh objects and applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "preset": {
                        "type": "string",
                        "enum": [
                            "custom",
                            "brushed_metal",
                            "matte_plastic",
                            "clear_glass",
                            "emissive_accent",
                            "matte_ceramic",
                            "rubber_black",
                            "warm_wood",
                            "screen_glow",
                        ],
                    },
                    "base_color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "metallic": {"type": "number"},
                    "roughness": {"type": "number"},
                    "alpha": {"type": "number"},
                    "emission_color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "emission_strength": {"type": "number"},
                    "assign_to_selected": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "add_geometry_nodes_modifier",
            "description": "Add a valid Geometry Nodes modifier and starter node group to selected mesh objects. Templates include passthrough, transform, join geometry, set position, and subdivide mesh. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "node_group_name": {"type": "string"},
                    "template": {"type": "string", "enum": ["passthrough", "transform", "join_geometry", "set_position", "subdivide_mesh"]},
                    "selected_only": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_shape_key",
            "description": "Create or update a shape key value on a mesh object. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "key_name": {"type": "string"},
                    "value": {"type": "number"},
                    "label": {"type": "string"},
                },
                "required": ["key_name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "animate_shape_key",
            "description": "Keyframe a shape key value over a frame range. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "key_name": {"type": "string"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "value_start": {"type": "number"},
                    "value_end": {"type": "number"},
                    "create_if_missing": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "required": ["key_name", "frame_start", "frame_end"],
                "additionalProperties": False,
            },
        },
        {
            "name": "animate_object_bounce",
            "description": "Create repeated location keyframes that bounce one object along an axis. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "axis": {"type": "string", "enum": ["X", "Y", "Z"]},
                    "distance": {"type": "number"},
                    "cycles": {"type": "integer", "minimum": 1, "maximum": 24},
                    "interpolation": {"type": "string", "enum": ["CONSTANT", "LINEAR", "BEZIER"]},
                    "label": {"type": "string"},
                },
                "required": ["frame_start", "frame_end"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_progressive_bounce_animation",
            "description": "Create repeated bounce keyframes plus decreasing scale keys for one object. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "axis": {"type": "string", "enum": ["X", "Y", "Z"]},
                    "distance": {"type": "number"},
                    "cycles": {"type": "integer", "minimum": 1, "maximum": 24},
                    "scale_end_factor": {"type": "number"},
                    "interpolation": {"type": "string", "enum": ["CONSTANT", "LINEAR", "BEZIER"]},
                    "label": {"type": "string"},
                },
                "required": ["frame_start", "frame_end"],
                "additionalProperties": False,
            },
        },
        {
            "name": "animate_material_property",
            "description": "Keyframe a Principled material socket such as base color, emission strength, roughness, metallic, or alpha. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "material_name": {"type": "string"},
                    "object_name": {"type": "string"},
                    "property_name": {
                        "type": "string",
                        "enum": [
                            "base_color",
                            "diffuse_color",
                            "color",
                            "emission_color",
                            "emission",
                            "emission_strength",
                            "glow",
                            "roughness",
                            "metallic",
                            "alpha",
                        ],
                    },
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "value_start": {
                        "oneOf": [
                            {"type": "number"},
                            {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                        ]
                    },
                    "value_end": {
                        "oneOf": [
                            {"type": "number"},
                            {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                        ]
                    },
                    "create_if_missing": {"type": "boolean"},
                    "interpolation": {"type": "string", "enum": ["CONSTANT", "LINEAR", "BEZIER"]},
                    "label": {"type": "string"},
                },
                "required": ["property_name", "frame_start", "frame_end"],
                "additionalProperties": False,
            },
        },
        {
            "name": "animate_light_property",
            "description": "Keyframe a light data property such as energy, color, shadow softness, spot size, or spot blend. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "light_name": {"type": "string"},
                    "property_name": {
                        "type": "string",
                        "enum": ["energy", "intensity", "color", "colour", "shadow_soft_size", "spot_size", "spot_blend"],
                    },
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "value_start": {
                        "oneOf": [
                            {"type": "number"},
                            {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                        ]
                    },
                    "value_end": {
                        "oneOf": [
                            {"type": "number"},
                            {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                        ]
                    },
                    "interpolation": {"type": "string", "enum": ["CONSTANT", "LINEAR", "BEZIER"]},
                    "label": {"type": "string"},
                },
                "required": ["property_name", "frame_start", "frame_end"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_follow_path_animation",
            "description": "Animate an object along an existing curve or a new curve built from path points. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "path_name": {"type": "string"},
                    "path_points": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    },
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "constraint_name": {"type": "string"},
                    "follow_curve": {"type": "boolean"},
                    "interpolation": {"type": "string", "enum": ["CONSTANT", "LINEAR", "BEZIER"]},
                    "label": {"type": "string"},
                },
                "required": ["frame_start", "frame_end"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_action_interpolation",
            "description": "Set keyframe interpolation and optional easing for named actions or object-owned actions. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action_names": {"type": "array", "items": {"type": "string"}},
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "interpolation": {
                        "type": "string",
                        "enum": [
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
                        ],
                    },
                    "easing": {"type": "string", "enum": ["AUTO", "EASE_IN", "EASE_OUT", "EASE_IN_OUT"]},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "retime_actions",
            "description": "Scale existing action keyframes into a new frame range. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action_names": {"type": "array", "items": {"type": "string"}},
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "snap_to_integer": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "required": ["frame_start", "frame_end"],
                "additionalProperties": False,
            },
        },
        {
            "name": "add_action_cycles",
            "description": "Add cycles modifiers to action f-curves so an animation loops. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action_names": {"type": "array", "items": {"type": "string"}},
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "mode_before": {"type": "string", "enum": ["NONE", "REPEAT", "REPEAT_OFFSET", "MIRROR"]},
                    "mode_after": {"type": "string", "enum": ["NONE", "REPEAT", "REPEAT_OFFSET", "MIRROR"]},
                    "replace_existing": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "clear_animation",
            "description": "Clear object, data, shape-key, and optionally material animation from selected or named objects. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "include_object_animation": {"type": "boolean"},
                    "include_data_animation": {"type": "boolean"},
                    "include_shape_key_animation": {"type": "boolean"},
                    "include_material_animation": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "set_animation_preview_range",
            "description": "Set scene preview playback range and optionally move the playhead. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "current_frame": {"type": "integer"},
                    "use_preview_range": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "required": ["frame_start", "frame_end"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_turntable_animation",
            "description": "Create a simple rotating product/object turntable animation. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "axis": {"type": "string", "enum": ["X", "Y", "Z"]},
                    "revolutions": {"type": "number"},
                    "add_cycles": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "required": ["frame_start", "frame_end"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_pulse_animation",
            "description": "Create a scale pulse and optional emission-strength pulse for an object. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "scale_factor": {"type": "number"},
                    "emission_strength_end": {"type": "number"},
                    "label": {"type": "string"},
                },
                "required": ["frame_start", "frame_end"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_reveal_animation",
            "description": "Create a scale reveal and optional material alpha fade. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "scale_start": {"type": "number"},
                    "scale_end": {"type": "number"},
                    "fade_material": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "required": ["frame_start", "frame_end"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_staggered_motion",
            "description": "Create staggered location animation across selected or named objects. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "frame_start": {"type": "integer"},
                    "duration": {"type": "integer"},
                    "frame_step": {"type": "integer"},
                    "location_delta": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "interpolation": {
                        "type": "string",
                        "enum": [
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
                        ],
                    },
                    "label": {"type": "string"},
                },
                "required": ["frame_start"],
                "additionalProperties": False,
            },
        },
        {
            "name": "block_key_poses",
            "description": "Block animator-style keyed transform poses for selected or named objects. Use this after create_timing_chart when you have concrete pose transforms. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "poses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "frame": {"type": "integer"},
                                "label": {"type": "string"},
                                "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                                "rotation": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                                "rotation_euler": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                                "scale": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                                "hold_frames": {"type": "integer"},
                            },
                            "additionalProperties": False,
                        },
                    },
                    "interpolation": {
                        "type": "string",
                        "enum": [
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
                        ],
                    },
                    "label": {"type": "string"},
                },
                "required": ["poses"],
                "additionalProperties": False,
            },
        },
        {
            "name": "add_breakdown_pose",
            "description": "Add a keyed breakdown pose between surrounding key poses, optionally using explicit transform values. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "frame": {"type": "integer"},
                    "previous_frame": {"type": "integer"},
                    "next_frame": {"type": "integer"},
                    "factor": {"type": "number"},
                    "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "rotation": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "scale": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "paths": {"type": "array", "items": {"type": "string", "enum": ["location", "rotation_euler", "scale"]}},
                    "interpolation": {
                        "type": "string",
                        "enum": [
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
                        ],
                    },
                    "label": {"type": "string"},
                },
                "required": ["frame"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_pose_hold",
            "description": "Duplicate a keyed pose for a hold so contact, staging, or hero poses read before polish. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "frame": {"type": "integer"},
                    "hold_frames": {"type": "integer"},
                    "paths": {"type": "array", "items": {"type": "string", "enum": ["location", "rotation_euler", "scale"]}},
                    "interpolation": {
                        "type": "string",
                        "enum": [
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
                        ],
                    },
                    "label": {"type": "string"},
                },
                "required": ["frame"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_rig_pose_hold",
            "description": "Duplicate pose-bone transforms on named armature control bones for a hold. Use for rig-driven characters/props after inspecting rig controls. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "armature_name": {"type": "string"},
                    "bone_names": {"type": "array", "items": {"type": "string"}},
                    "frame": {"type": "integer"},
                    "hold_frames": {"type": "integer"},
                    "paths": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale"],
                        },
                    },
                    "interpolation": {
                        "type": "string",
                        "enum": [
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
                        ],
                    },
                    "label": {"type": "string"},
                },
                "required": ["armature_name", "frame"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_rig_custom_property_keyframes",
            "description": "Key existing scalar rig custom properties, such as IK/FK or space switches, over a short hold window. Use only for properties found by rig inspection or repair metadata. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "armature_name": {"type": "string"},
                    "property_targets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "owner_type": {
                                    "type": "string",
                                    "enum": ["object", "armature_data", "pose_bone"],
                                },
                                "owner_name": {"type": "string"},
                                "property_name": {"type": "string"},
                                "value": {"type": ["number", "boolean"]},
                            },
                            "required": ["owner_type", "property_name"],
                            "additionalProperties": False,
                        },
                    },
                    "frame": {"type": "integer"},
                    "hold_frames": {"type": "integer"},
                    "interpolation": {
                        "type": "string",
                        "enum": [
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
                        ],
                    },
                    "label": {"type": "string"},
                },
                "required": ["armature_name", "property_targets", "frame"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_rig_pose_library_details",
            "description": "Inspect rig-compatible pose-library/action candidates for an armature, including pose markers, matched bones/channels, frame ranges, and suggested apply calls. Use before applying production rig poses or clips.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "armature_name": {"type": "string"},
                    "action_names": {"type": "array", "items": {"type": "string"}},
                    "bone_names": {"type": "array", "items": {"type": "string"}},
                    "paths": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale"],
                        },
                    },
                    "max_actions": {"type": "integer"},
                },
                "required": ["armature_name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "apply_rig_pose_from_action",
            "description": "Sample an existing rig action or pose-library marker and apply/key that pose onto matching armature controls. Use for production rigs after get_rigging_details surfaces pose_library_candidates. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "armature_name": {"type": "string"},
                    "action_name": {"type": "string"},
                    "pose_marker": {"type": "string"},
                    "source_frame": {"type": "integer"},
                    "target_frame": {"type": "integer"},
                    "frame": {"type": "integer"},
                    "hold_frames": {"type": "integer"},
                    "bone_names": {"type": "array", "items": {"type": "string"}},
                    "paths": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale"],
                        },
                    },
                    "key_pose": {"type": "boolean"},
                    "interpolation": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["armature_name", "action_name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "apply_rig_pose_marker",
            "description": "Resolve a rig pose-library marker to the best matching source action, then apply/key it onto matching armature controls. Use when the marker name is known but the source action may be ambiguous. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "armature_name": {"type": "string"},
                    "action_name": {"type": "string"},
                    "pose_marker": {"type": "string"},
                    "target_frame": {"type": "integer"},
                    "frame": {"type": "integer"},
                    "hold_frames": {"type": "integer"},
                    "bone_names": {"type": "array", "items": {"type": "string"}},
                    "paths": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale"],
                        },
                    },
                    "key_pose": {"type": "boolean"},
                    "interpolation": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["armature_name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "apply_rig_action_clip",
            "description": "Copy an existing rig action, retime it to a target frame range, and assign the copy to an armature without editing the source action. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "armature_name": {"type": "string"},
                    "action_name": {"type": "string"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "source_frame_start": {"type": "integer"},
                    "source_frame_end": {"type": "integer"},
                    "interpolation": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["armature_name", "action_name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "offset_rig_limb_controls",
            "description": "Apply small keyed offsets to named IK/FK/pole limb controls and optionally key existing space-switch properties. Use for targeted rig contact, support, and limb-space repair after rig inspection. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "armature_name": {"type": "string"},
                    "control_offsets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "bone_name": {"type": "string"},
                                "location_delta": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                                "rotation_delta": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                                "scale_multiplier": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                            },
                            "required": ["bone_name"],
                            "additionalProperties": False,
                        },
                    },
                    "bone_names": {"type": "array", "items": {"type": "string"}},
                    "location_delta": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "rotation_delta": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "scale_multiplier": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "property_targets": {"type": "array", "items": {"type": "object"}},
                    "frame": {"type": "integer"},
                    "hold_frames": {"type": "integer"},
                    "interpolation": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["armature_name", "frame"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_motion_arc",
            "description": "Create preview curve objects from sampled object locations so motion arcs are visible in the scene. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "sample_step": {"type": "integer"},
                    "name_prefix": {"type": "string"},
                    "bevel_depth": {"type": "number"},
                    "color": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_text_object",
            "description": "Create a text object with transform, alignment, size, and optional simple material. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "body": {"type": "string"},
                    "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "rotation": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "scale": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "size": {"type": "number"},
                    "align_x": {"type": "string", "enum": ["LEFT", "CENTER", "RIGHT", "JUSTIFY", "FLUSH"]},
                    "align_y": {"type": "string", "enum": ["CENTER", "TOP", "BOTTOM"]},
                    "material_name": {"type": "string"},
                    "color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "label": {"type": "string"},
                },
                "required": ["name", "body", "location", "rotation", "scale"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_curve_path",
            "description": "Create a 3D poly curve path from points with optional bevel and material. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "points": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    },
                    "bevel_depth": {"type": "number"},
                    "cyclic": {"type": "boolean"},
                    "material_name": {"type": "string"},
                    "color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "label": {"type": "string"},
                },
                "required": ["name", "points"],
                "additionalProperties": False,
            },
        },
        {
            "name": "add_particle_system_to_selected",
            "description": "Add a bounded particle system to selected mesh objects. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "count": {"type": "integer"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "lifetime": {"type": "number"},
                    "particle_size": {"type": "number"},
                    "label": {"type": "string"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_basic_armature",
            "description": "Create a simple one-bone armature object. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "rotation": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "show_in_front": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "required": ["name", "location", "rotation"],
                "additionalProperties": False,
            },
        },
        {
            "name": "add_copy_transform_constraint",
            "description": "Add a Copy Location/Rotation/Scale/Transforms constraint from selected object(s) to a target. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "constraint_type": {"type": "string", "enum": ["COPY_LOCATION", "COPY_ROTATION", "COPY_SCALE", "COPY_TRANSFORMS"]},
                    "name": {"type": "string"},
                    "influence": {"type": "number"},
                    "label": {"type": "string"},
                },
                "required": ["target_name", "constraint_type"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_render_settings",
            "description": "Set render engine, resolution, FPS, frame range, and transparency. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "engine": {"type": "string"},
                    "resolution": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                    "fps": {"type": "integer"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "film_transparent": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "set_camera_settings",
            "description": "Set camera lens, sensor width, and depth-of-field settings. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "camera_name": {"type": "string"},
                    "lens": {"type": "number"},
                    "sensor_width": {"type": "number"},
                    "dof_enabled": {"type": "boolean"},
                    "focus_object_name": {"type": "string"},
                    "aperture_fstop": {"type": "number"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "set_world_background",
            "description": "Set the scene world background color. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "label": {"type": "string"},
                },
                "required": ["color"],
                "additionalProperties": False,
            },
        },
        {
            "name": "plan_advanced_scene_workflow",
            "description": "Plan a helper-first workflow for advanced 3D, 2D/storyboard, animation, simulation, asset import, compositor/render, and script-fallback work. Does not mutate the scene.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "domains": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "2d_storyboard",
                                "procedural_3d",
                                "advanced_animation",
                                "simulation_setup",
                                "asset_import",
                                "compositor_render",
                            ],
                        },
                    },
                    "target_objects": {"type": "array", "items": {"type": "string"}},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "plan_asset_import_workflow",
            "description": "Plan the async external-asset discovery, download/cache, queued import, post-import organization, staging, and visual-evidence workflow. Does not mutate the scene.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "provider": {"type": "string", "enum": ["", "poly_haven", "sketchfab"]},
                    "asset_id": {"type": "string"},
                    "uid": {"type": "string"},
                    "target_object_name": {"type": "string"},
                    "presentation_preset": {"type": "string"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "plan_director_workflow",
            "description": "Plan a multi-step director workflow across inspection, optional asset import, creation, animation/review/repair, evidence capture, and commit/revert decision points. Does not mutate the scene.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "target_objects": {"type": "array", "items": {"type": "string"}},
                    "deliverables": {"type": "array", "items": {"type": "string"}},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "get_2d_animation_details",
            "description": "Inspect 2D/storyboard context: Grease Pencil-like objects, text, curves, flat mesh layers, camera, timeline, render, and compositor status. Does not mutate the scene.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "max_items": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_storyboard_panels",
            "description": "Create a reversible 2D storyboard/animatic board with panel cards, borders, shot labels, frame ranges, and optional orthographic camera. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "panel_count": {"type": "integer", "minimum": 1, "maximum": 24},
                    "columns": {"type": "integer", "minimum": 1, "maximum": 24},
                    "panel_width": {"type": "number"},
                    "panel_height": {"type": "number"},
                    "gap": {"type": "number"},
                    "name_prefix": {"type": "string"},
                    "frame_start": {"type": "integer"},
                    "frame_step": {"type": "integer"},
                    "background_color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "border_color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "text_color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "create_camera": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_2d_cutout_layer",
            "description": "Create a flat 2D cutout layer with optional transform keyframes and label text. Use for motion graphics, animatics, and cutout animation. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "size": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    "color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "location_end": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "rotation_end": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "scale_end": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "text": {"type": "string"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "apply_procedural_array_stack",
            "description": "Apply a bounded procedural modeling stack to mesh objects: array, bevel, and optional weighted normals. Use before custom geometry-node or mesh-edit scripts. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "count": {"type": "integer", "minimum": 1, "maximum": 1000},
                    "relative_offset": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "bevel_width": {"type": "number"},
                    "bevel_segments": {"type": "integer", "minimum": 1, "maximum": 32},
                    "add_weighted_normals": {"type": "boolean"},
                    "name_prefix": {"type": "string"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_procedural_object_kit",
            "description": "Create a reversible procedural object kit from bounded templates such as kitbash towers, radial arrays, scatter grids, product stacks, product display rigs, mechanical joints, mechanical assemblies, control panels, studio prop sets, mechanical parts, modular wall panels, or pipe runs. Use before custom mesh or geometry-node scripts.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "template": {
                        "type": "string",
                        "enum": [
                            "kitbash_tower",
                            "radial_array",
                            "scatter_grid",
                            "product_stack",
                            "product_display_rig",
                            "mechanical_joint",
                            "mechanical_assembly",
                            "control_panel",
                            "studio_prop_set",
                            "mechanical_part",
                            "modular_wall_panel",
                            "pipe_run",
                        ],
                    },
                    "name_prefix": {"type": "string"},
                    "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "count": {"type": "integer", "minimum": 1, "maximum": 80},
                    "radius": {"type": "number"},
                    "spacing": {"type": "number"},
                    "height": {"type": "number"},
                    "primary_color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "accent_color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "add_detail_modifiers": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_camera_dolly_animation",
            "description": "Create a camera dolly/shot move with location keyframes, optional target tracking, and optional lens keyframes. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "camera_name": {"type": "string"},
                    "target_name": {"type": "string"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "start_location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "end_location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "lens_start": {"type": "number"},
                    "lens_end": {"type": "number"},
                    "interpolation": {
                        "type": "string",
                        "enum": [
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
                        ],
                    },
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_directed_animation_shot",
            "description": "Create a reversible director-style animation shot template: camera push reveal, orbit reveal, product turntable, path slide, staggered reveal, storyboard dolly, crane reveal, or truck slide.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "shot_type": {
                        "type": "string",
                        "enum": [
                            "camera_push_reveal",
                            "orbit_reveal",
                            "product_turntable",
                            "path_slide",
                            "staggered_reveal",
                            "storyboard_dolly",
                            "crane_reveal",
                            "truck_slide",
                        ],
                    },
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "travel_axis": {"type": "string", "enum": ["X", "Y", "Z"]},
                    "travel_distance": {"type": "number"},
                    "scale_start": {"type": "number"},
                    "scale_end": {"type": "number"},
                    "rotation_revolutions": {"type": "number"},
                    "camera_name": {"type": "string"},
                    "target_name": {"type": "string"},
                    "create_camera": {"type": "boolean"},
                    "lens_start": {"type": "number"},
                    "lens_end": {"type": "number"},
                    "interpolation": {
                        "type": "string",
                        "enum": [
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
                        ],
                    },
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "add_cloth_simulation_to_selected",
            "description": "Add a bounded Cloth simulation modifier to selected or named mesh objects without baking caches. Inspect and bake explicitly after setup. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "name": {"type": "string"},
                    "quality": {"type": "integer", "minimum": 1, "maximum": 30},
                    "mass": {"type": "number"},
                    "tension_stiffness": {"type": "number"},
                    "compression_stiffness": {"type": "number"},
                    "shear_stiffness": {"type": "number"},
                    "air_damping": {"type": "number"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_empty",
            "description": "Create an empty helper object with transform and display settings. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "rotation": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Euler rotation in radians",
                    },
                    "scale": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "empty_display_type": {"type": "string", "enum": ["PLAIN_AXES", "ARROWS", "SINGLE_ARROW", "CIRCLE", "CUBE", "SPHERE", "CONE", "IMAGE"]},
                    "empty_display_size": {"type": "number"},
                    "select_new": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_object_visibility",
            "description": "Set viewport, render, or selection visibility flags for named or selected objects. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "hide_viewport": {"type": "boolean"},
                    "hide_render": {"type": "boolean"},
                    "hide_select": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "set_object_display",
            "description": "Set object viewport display type, name/wire/in-front flags, display color, and empty display settings. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "object_names": {"type": "array", "items": {"type": "string"}},
                    "selected_only": {"type": "boolean"},
                    "display_type": {"type": "string", "enum": ["TEXTURED", "SOLID", "WIRE", "BOUNDS"]},
                    "show_name": {"type": "boolean"},
                    "show_wire": {"type": "boolean"},
                    "show_in_front": {"type": "boolean"},
                    "color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "empty_display_type": {"type": "string", "enum": ["PLAIN_AXES", "ARROWS", "SINGLE_ARROW", "CIRCLE", "CUBE", "SPHERE", "CONE", "IMAGE"]},
                    "empty_display_size": {"type": "number"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "duplicate_selected_objects",
            "description": "Duplicate selected objects with optional unique data, offset, animation copy, and selecting the new duplicates. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name_prefix": {"type": "string"},
                    "offset": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "linked_data": {"type": "boolean"},
                    "copy_animation": {"type": "boolean"},
                    "select_new": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "parent_selected_to_empty",
            "description": "Create an empty at the selected objects' center or a provided location, then parent selected objects to it while preserving world transforms. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "empty_display_type": {"type": "string", "enum": ["PLAIN_AXES", "ARROWS", "CUBE", "SPHERE"]},
                    "keep_transform": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "align_selected_objects",
            "description": "Align selected object locations on one axis using the active object, min, max, center, or an explicit value. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "axis": {"type": "string", "enum": ["X", "Y", "Z"]},
                    "mode": {"type": "string", "enum": ["ACTIVE", "MIN", "MAX", "CENTER", "VALUE"]},
                    "value": {"type": "number"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "distribute_selected_objects",
            "description": "Evenly distribute selected object locations along one axis between existing or provided start/end positions. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "axis": {"type": "string", "enum": ["X", "Y", "Z"]},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "shade_smooth_selected",
            "description": "Shade selected mesh polygons smooth and optionally add a Weighted Normal modifier. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "add_weighted_normals": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "add_bevel_and_subsurf",
            "description": "Add a bounded bevel, optional subdivision, and optional weighted-normal stack to selected mesh objects. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "bevel_width": {"type": "number"},
                    "bevel_segments": {"type": "integer"},
                    "subsurf_levels": {"type": "integer"},
                    "weighted_normals": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_wheel_assembly",
            "description": "Create a tire and rim wheel assembly at a location. Useful for vehicle detailing. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "radius": {"type": "number"},
                    "tire_thickness": {"type": "number"},
                    "axis": {"type": "string", "enum": ["X", "Y", "Z"]},
                    "tire_material_name": {"type": "string"},
                    "rim_material_name": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["name", "location"],
                "additionalProperties": False,
            },
        },
        {
            "name": "add_panel_seams",
            "description": "Add simple dark curve panel seams around a target mesh object's bounds. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "seam_material_name": {"type": "string"},
                    "bevel_depth": {"type": "number"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "add_window_materials",
            "description": "Create/update a translucent glass material, assign it to window-like objects, and optionally create simple window panels around a target mesh. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "material_name": {"type": "string"},
                    "color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "create_panels": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "apply_vehicle_refinement_template",
            "description": "Apply a bounded vehicle detail kit around a target mesh: smoothing, bevels, wheels, window panels, seams, headlights, and taillights. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "detail_level": {"type": "string", "enum": ["low", "medium", "high"]},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "apply_product_refinement_template",
            "description": "Apply a bounded product presentation kit around a target: material polish, smoothing/bevels, optional studio stage, dimension callouts, and optional turntable. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "style": {"type": "string", "enum": ["studio", "catalog", "premium"]},
                    "include_stage": {"type": "boolean"},
                    "include_callouts": {"type": "boolean"},
                    "include_turntable": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "apply_character_refinement_template",
            "description": "Apply a bounded character presentation kit around a target mesh: body polish, simple head/neck/eyes, shoulder marker, and optional gesture guides. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "character_style": {"type": "string", "enum": ["neutral", "toon"]},
                    "detail_level": {"type": "string", "enum": ["low", "medium", "high"]},
                    "create_guides": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_studio_product_stage",
            "description": "Create a production-style product presentation stage around a target object: floor, backdrop, key/fill/rim area lights, target empty, and optional camera. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "stage_name": {"type": "string"},
                    "floor": {"type": "boolean"},
                    "backdrop": {"type": "boolean"},
                    "lighting": {"type": "boolean"},
                    "camera": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "add_dimension_callouts",
            "description": "Add non-destructive dimension/ruler callouts around a target object's bounds for width, depth, and height. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "unit_label": {"type": "string"},
                    "include_width": {"type": "boolean"},
                    "include_depth": {"type": "boolean"},
                    "include_height": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "apply_lighting_preset",
            "description": "Create a bounded production lighting preset around a target object. Presets include product_softbox, dramatic_rim, and gallery_even. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "preset": {"type": "string", "enum": ["product_softbox", "dramatic_rim", "gallery_even"]},
                    "rig_name": {"type": "string"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_material_palette",
            "description": "Create a bounded production material palette, optional swatch cubes, and optional assignment to selected mesh objects. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "palette_name": {"type": "string"},
                    "palette": {"type": "string", "enum": ["product_neutral", "automotive", "cinematic"]},
                    "create_swatches": {"type": "boolean"},
                    "assign_to_selected": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "create_product_turntable_setup",
            "description": "Create a product turntable setup around a target: optional stage, rotating target animation, and orbit camera. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "revolutions": {"type": "number"},
                    "radius": {"type": "number"},
                    "height": {"type": "number"},
                    "setup_name": {"type": "string"},
                    "create_stage": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "prepare_imported_asset_presentation",
            "description": "Organize imported asset objects, fill missing mesh materials without overwriting imported materials, create a bounded studio/turntable presentation setup, and leave the result in preview. Use after an external asset import job completes.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "imported_object_names": {"type": "array", "items": {"type": "string"}},
                    "target_object_name": {"type": "string"},
                    "selected_only": {"type": "boolean"},
                    "use_active_fallback": {"type": "boolean"},
                    "collection_prefix": {"type": "string"},
                    "presentation_preset": {"type": "string", "enum": ["studio", "catalog", "turntable", "lookdev"]},
                    "assign_material_if_missing": {"type": "boolean"},
                    "create_stage": {"type": "boolean"},
                    "create_turntable": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "organize_scene_for_production",
            "description": "Link scene or selected objects into production-oriented type collections without deleting original links. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "collection_prefix": {"type": "string"},
                    "selected_only": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "add_track_to_constraint",
            "description": "Add a Track To constraint from selected object(s) to a target object. Useful for cameras/lights looking at a target. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "name": {"type": "string"},
                    "track_axis": {
                        "type": "string",
                        "enum": ["TRACK_X", "TRACK_Y", "TRACK_Z", "TRACK_NEGATIVE_X", "TRACK_NEGATIVE_Y", "TRACK_NEGATIVE_Z"],
                    },
                    "up_axis": {"type": "string", "enum": ["UP_X", "UP_Y", "UP_Z"]},
                    "influence": {"type": "number"},
                    "label": {"type": "string"},
                },
                "required": ["target_name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "add_light",
            "description": "Add a light to the current Blender scene. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "light_type": {"type": "string", "enum": ["POINT", "SUN", "SPOT", "AREA"]},
                    "name": {"type": "string"},
                    "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "energy": {"type": "number"},
                    "color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "label": {"type": "string"},
                },
                "required": ["light_type", "name", "location", "energy", "color"],
                "additionalProperties": False,
            },
        },
        {
            "name": "add_camera",
            "description": "Add a camera and make it the active scene camera. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "rotation": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Euler rotation in radians",
                    },
                    "lens": {"type": "number"},
                    "label": {"type": "string"},
                },
                "required": ["name", "location", "rotation", "lens"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_scene_frame_range",
            "description": "Set the scene timeline frame range, current frame, and optionally FPS. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "current_frame": {"type": "integer"},
                    "fps": {"type": "integer"},
                    "label": {"type": "string"},
                },
                "required": ["frame_start", "frame_end"],
                "additionalProperties": False,
            },
        },
        {
            "name": "set_active_camera",
            "description": "Set an existing camera object as the active scene camera. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "camera_name": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["camera_name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "animate_selected_transform",
            "description": "Create simple transform keyframes for selected objects using a preview action. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "location_start": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "location_end": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "rotation_start": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Euler rotation in radians",
                    },
                    "rotation_end": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Euler rotation in radians",
                    },
                    "scale_start": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "scale_end": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                    "label": {"type": "string"},
                },
                "required": ["frame_start", "frame_end"],
                "additionalProperties": False,
            },
        },
        {
            "name": "create_camera_orbit",
            "description": "Create a camera orbit rig around a target object and keyframe it over a frame range. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "target_name": {"type": "string"},
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "radius": {"type": "number"},
                    "height": {"type": "number"},
                    "name": {"type": "string"},
                    "lens": {"type": "number"},
                    "label": {"type": "string"},
                },
                "required": ["target_name", "frame_start", "frame_end", "radius", "height", "name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "search_blender_docs",
            "description": "Search cached/official Blender docs. Use before unfamiliar or version-sensitive APIs.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_poly_haven_categories",
            "description": "List Poly Haven catalog categories for HDRIs, textures, and models. Returns metadata only; it does not download or import assets.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "asset_type": {"type": "string", "enum": ["all", "hdris", "textures", "models"]},
                    "timeout": {"type": "integer", "description": "HTTP timeout in seconds. Defaults to 15."},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "search_poly_haven_assets",
            "description": "Search Poly Haven's CC0 asset catalog and return source URLs plus API file URLs. Returns metadata only; it does not download or import assets.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional local text filter over returned asset names, ids, and categories."},
                    "asset_type": {"type": "string", "enum": ["all", "hdris", "textures", "models"]},
                    "category": {"type": "string", "description": "Optional Poly Haven category slug."},
                    "limit": {"type": "integer", "description": "Maximum assets to return. Defaults to 20, max 50."},
                    "timeout": {"type": "integer", "description": "HTTP timeout in seconds. Defaults to 15."},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "inspect_poly_haven_asset_files",
            "description": "Fetch and summarize the available Poly Haven files for one asset, including resolutions, formats, sizes, hashes, and include dependencies. Does not download or import.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                "required": ["asset_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "download_poly_haven_asset",
            "description": "Synchronous fallback: download and cache selected Poly Haven HDRI, texture, or model files with checksum validation. Does not mutate the Blender scene. For normal client workflows, prefer start_external_asset_download and poll get_external_asset_job_status.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string"},
                    "asset_type": {"type": "string", "enum": ["", "all", "hdris", "textures", "models"]},
                    "resolution": {"type": "string"},
                    "file_format": {"type": "string"},
                    "map_types": {"type": "array", "items": {"type": "string"}},
                    "include_dependencies": {"type": "boolean"},
                    "cache_dir": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                "required": ["asset_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "import_poly_haven_asset",
            "description": "Synchronous fallback: download/cache and import a Poly Haven asset into Blender preview. HDRIs create a world, textures create/assign a material, and models use Blender importers. For normal client workflows, use start_external_asset_download, poll get_external_asset_job_status, then start_external_asset_import_job.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string"},
                    "asset_type": {"type": "string", "enum": ["", "all", "hdris", "textures", "models"]},
                    "resolution": {"type": "string"},
                    "file_format": {"type": "string"},
                    "map_types": {"type": "array", "items": {"type": "string"}},
                    "target_object_name": {"type": "string"},
                    "cache_dir": {"type": "string"},
                    "timeout": {"type": "integer"},
                    "label": {"type": "string"},
                },
                "required": ["asset_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "search_sketchfab_models",
            "description": "Search Sketchfab's public model catalog and return viewer, author, license, thumbnail, and downloadability metadata. Returns metadata only; it does not download or import assets.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "downloadable": {"type": "boolean", "description": "Filter for downloadable models. Defaults to true."},
                    "staffpicked": {"type": "boolean"},
                    "animated": {"type": "boolean"},
                    "limit": {"type": "integer", "description": "Maximum models to return. Defaults to 20, max 50."},
                    "timeout": {"type": "integer", "description": "HTTP timeout in seconds. Defaults to 15."},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "download_sketchfab_model",
            "description": "Synchronous fallback: use a Sketchfab API token to fetch temporary GLTF download info, cache the archive, and extract an importable model file. Does not mutate the Blender scene. For normal client workflows, prefer start_external_asset_download and poll get_external_asset_job_status.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "uid": {"type": "string"},
                    "api_token": {"type": "string", "description": "Optional per-call Sketchfab API token. Redacted in audit logs."},
                    "token_env_var": {
                        "type": "string",
                        "enum": ["SKETCHFAB_API_TOKEN", "BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN"],
                        "description": "Sketchfab API token environment variable to read when api_token is omitted. Defaults to SKETCHFAB_API_TOKEN and falls back to the bridge-specific name.",
                    },
                    "model_password": {"type": "string"},
                    "cache_dir": {"type": "string"},
                    "timeout": {"type": "integer"},
                },
                "required": ["uid"],
                "additionalProperties": False,
            },
        },
        {
            "name": "import_sketchfab_model",
            "description": "Synchronous fallback: use a Sketchfab API token to cache a downloadable model archive and import the extracted GLTF/GLB file into Blender preview. For normal client workflows, use start_external_asset_download, poll get_external_asset_job_status, then start_external_asset_import_job.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "uid": {"type": "string"},
                    "api_token": {"type": "string", "description": "Optional per-call Sketchfab API token. Redacted in audit logs."},
                    "token_env_var": {
                        "type": "string",
                        "enum": ["SKETCHFAB_API_TOKEN", "BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN"],
                        "description": "Sketchfab API token environment variable to read when api_token is omitted. Defaults to SKETCHFAB_API_TOKEN and falls back to the bridge-specific name.",
                    },
                    "model_password": {"type": "string"},
                    "cache_dir": {"type": "string"},
                    "timeout": {"type": "integer"},
                    "label": {"type": "string"},
                },
                "required": ["uid"],
                "additionalProperties": False,
            },
        },
        {
            "name": "start_external_asset_download",
            "description": "Default client path: start an asynchronous external asset download/cache job for Poly Haven or Sketchfab. Use this for any normal asset download/cache or import request. Returns immediately with a job id; poll get_external_asset_job_status until completed or failed, then queue scene import with start_external_asset_import_job.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "enum": ["poly_haven", "sketchfab"]},
                    "asset_id": {"type": "string", "description": "Poly Haven asset id."},
                    "uid": {"type": "string", "description": "Sketchfab model uid."},
                    "asset_type": {"type": "string", "enum": ["", "all", "hdris", "textures", "models"]},
                    "resolution": {"type": "string"},
                    "file_format": {"type": "string"},
                    "map_types": {"type": "array", "items": {"type": "string"}},
                    "include_dependencies": {"type": "boolean"},
                    "api_token": {"type": "string", "description": "Optional per-call Sketchfab API token. Redacted in audit logs and not persisted to job metadata."},
                    "token_env_var": {
                        "type": "string",
                        "enum": ["SKETCHFAB_API_TOKEN", "BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN"],
                        "description": "Sketchfab API token environment variable to read when api_token is omitted.",
                    },
                    "model_password": {"type": "string"},
                    "cache_dir": {"type": "string"},
                    "timeout": {"type": "integer"},
                    "job_name": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["provider"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_external_asset_job_status",
            "description": "Poll an asynchronous external asset download/cache job for status, progress, cached manifest path, and import readiness. When completed and the user wants scene import, call start_external_asset_import_job.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "cancel_external_asset_job",
            "description": "Cancel an asynchronous external asset download/cache job. Subprocess jobs are terminated; in-process compatibility jobs stop cooperatively.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "import_external_asset_job_result",
            "description": "Synchronous fallback: import a completed external asset download/cache job result into Blender preview using the cached manifest. For normal client workflows, prefer start_external_asset_import_job and poll get_external_asset_import_job_status.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "target_object_name": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "start_external_asset_import_job",
            "description": "Default client path after a completed asset download/cache job: queue Blender main-thread import and return immediately with a pollable import job id. Poll get_external_asset_import_job_status until completed or failed.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Legacy alias for source_job_id."},
                    "source_job_id": {"type": "string", "description": "Completed external asset download/cache job id."},
                    "manifest_path": {"type": "string", "description": "Optional cached asset manifest path when no source_job_id is supplied."},
                    "target_object_name": {"type": "string"},
                    "label": {"type": "string"},
                },
                "anyOf": [
                    {"required": ["source_job_id"]},
                    {"required": ["job_id"]},
                    {"required": ["manifest_path"]},
                ],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_external_asset_import_job_status",
            "description": "Poll a queued external asset import job for queued/running/completed/failed/cancelled status and import result details. Use this after start_external_asset_import_job before reporting import success.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "cancel_external_asset_import_job",
            "description": "Cancel a queued external asset import job. Imports already running on Blender's main thread cannot be interrupted safely.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "delete_external_asset_job",
            "description": "Delete completed, failed, or cancelled external asset job metadata/log files. Dry-run by default.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "dry_run": {"type": "boolean"},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_external_asset_cache_diagnostics",
            "description": "Report cached/imported external assets, providers, licenses, source URLs, files, and imported Blender data-block names.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "cache_dir": {"type": "string"},
                    "max_assets": {"type": "integer"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "prune_external_asset_cache",
            "description": "Preview or delete old/excess external asset cache directories by age or total size. Dry-run by default.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "cache_dir": {"type": "string"},
                    "max_age_days": {"type": "integer"},
                    "max_total_bytes": {"type": "integer"},
                    "dry_run": {"type": "boolean"},
                    "include_imported": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "draft_script",
            "description": (
                "Stage Blender Python in a Text datablock for explicit user approval, or auto-run after static checks when external script trust is active. "
                "Use only when safe helper tools cannot express the requested scene, animation, material, or rig change. "
                "Blocked scripts are refused even while external script trust is active."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "Plain-language reason for the script",
                    },
                    "expected_changes": {
                        "type": "string",
                        "description": "Visible scene/data changes the user should expect if they approve it",
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Risk estimate based on scope, destructiveness, and API uncertainty",
                    },
                    "target_objects": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Object or datablock names the script intends to touch",
                    },
                    "code": {
                        "type": "string",
                        "maxLength": script_analysis.MAX_SCRIPT_CHARS,
                        "description": "Complete Blender Python script to stage for approval",
                    },
                },
                "required": ["intent", "expected_changes", "risk_level", "code"],
                "additionalProperties": False,
            },
        },
        {
            "name": "draft_privileged_script",
            "description": (
                "Stage custom Blender Python for external asset or project-file workflows that need declared filesystem, network, asset-import, or project-file capabilities. "
                "Requires an explicit approval manifest with paths/URLs/actions. Never auto-runs under normal external script trust; the user must run it in Blender or issue a one-time external approval token."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "script_kind": {
                        "type": "string",
                        "enum": ["external_asset", "project_file", "asset_project_file"],
                        "description": "Privileged workflow class that determines default capabilities and approval checks.",
                    },
                    "intent": {"type": "string", "description": "Plain-language reason for the privileged script"},
                    "expected_changes": {
                        "type": "string",
                        "description": "Visible scene, file, asset-cache, or project-file changes the user should expect",
                    },
                    "approval_summary": {
                        "type": "string",
                        "description": "Concise approval manifest explaining why helper tools are insufficient and what the script may touch",
                    },
                    "capabilities": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["filesystem", "network", "asset_import", "project_file"]},
                        "description": "Requested elevated capabilities. Defaults are inferred from script_kind and merged with this list.",
                    },
                    "declared_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Files, directories, cache locations, or .blend paths the script may read/write/open/save",
                    },
                    "declared_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Network URLs, API endpoints, providers, or asset sources the script may contact",
                    },
                    "destructive_actions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Expected overwrite, open, delete, import, save, or discard operations. Use an empty list only when none are expected.",
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Risk estimate based on file/network/project impact. Defaults to high.",
                    },
                    "target_objects": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Object or datablock names the script intends to touch",
                    },
                    "code": {
                        "type": "string",
                        "maxLength": script_analysis.MAX_SCRIPT_CHARS,
                        "description": "Complete privileged Blender Python script to stage for approval",
                    },
                },
                "required": [
                    "script_kind",
                    "intent",
                    "expected_changes",
                    "approval_summary",
                    "declared_paths",
                    "declared_urls",
                    "destructive_actions",
                    "code",
                ],
                "additionalProperties": False,
            },
        },
        {
            "name": "commit_preview",
            "description": "Commit the current live preview transaction.",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "revert_preview",
            "description": "Revert the current live preview transaction.",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    ]


TOOL_SCHEMA_CHAR_BUDGET = 32000

_CORE_TOOL_NAMES = {
    "inspect_scene",
    "list_scene_objects",
    "get_object_details",
    "search_blender_docs",
    "get_blend_file_diagnostics",
}

_FALLBACK_TOOL_NAMES = {"draft_script"}
_PRIVILEGED_FALLBACK_TOOL_NAMES = {"draft_privileged_script"}

_TOOL_GROUPS = {
    "project_files": {
        "get_blend_file_diagnostics",
        "save_blend_file",
        "open_blend_file",
        "create_new_blender_project",
        "autosave_current_blend_file",
    },
    "selection": {"select_objects", "set_current_frame", "get_workspace_layout", "jump_to_workspace", "set_viewport_view", "focus_object_in_viewport"},
    "basic_edit": {
        "select_objects",
        "set_selected_location_delta",
        "set_selected_transform",
        "create_primitive",
        "create_empty",
        "set_object_visibility",
        "set_object_display",
        "assign_material_to_selected",
        "create_collection",
        "link_selected_to_collection",
        "add_modifier_to_selected",
        "duplicate_selected_objects",
        "parent_selected_to_empty",
        "align_selected_objects",
        "distribute_selected_objects",
    },
    "materials": {
        "get_material_node_details",
        "get_shader_nodes_details",
        "assign_material_to_selected",
        "assign_emission_material_to_selected",
        "create_shader_material",
        "animate_material_property",
        "add_window_materials",
    },
    "animation": {
        "plan_advanced_scene_workflow",
        "get_animation_details",
        "get_animation_scene_context",
        "create_animation_brief",
        "create_timing_chart",
        "plan_animation_workflow",
        "run_animation_workflow",
        "run_animation_task",
        "create_directed_animation_shot",
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
        "inspect_simulation_bake",
        "stage_persistent_simulation_bake",
        "compare_animation_to_brief",
        "review_playblast_against_brief",
        "review_inspection_renders_against_brief",
        "repair_animation_from_findings",
        "run_animation_repair_loop",
        "set_current_frame",
        "set_scene_frame_range",
        "animate_selected_transform",
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
        "create_camera_dolly_animation",
        "create_directed_animation_shot",
        "create_camera_orbit",
        "capture_animation_playblast",
        "animate_shape_key",
        "create_2d_cutout_layer",
    },
    "camera_render": {
        "get_render_camera_compositor_details",
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
        "add_light",
        "add_camera",
        "set_active_camera",
        "create_camera_orbit",
        "create_camera_dolly_animation",
        "create_studio_product_stage",
        "apply_lighting_preset",
        "create_product_turntable_setup",
        "prepare_imported_asset_presentation",
        "create_turntable_animation",
        "set_render_settings",
        "set_camera_settings",
        "set_world_background",
        "animate_light_property",
    },
    "deep_inspect": {
        "plan_advanced_scene_workflow",
        "get_2d_animation_details",
        "get_blend_file_diagnostics",
        "get_workspace_layout",
        "get_visual_evidence_resources",
        "get_animation_scene_context",
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
        "capture_viewport",
        "capture_animation_playblast",
        "capture_object_inspection_renders",
        "render_scene_thumbnail",
        "start_render_job",
        "get_render_job_status",
        "cancel_render_job",
        "assemble_render_job_video",
        "validate_render_job_output",
        "run_animation_task",
        "run_animation_workflow",
        "run_animation_repair_loop",
    },
    "external_assets": {
        "plan_director_workflow",
        "plan_asset_import_workflow",
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
    },
    "advanced_create": {
        "plan_director_workflow",
        "plan_advanced_scene_workflow",
        "plan_asset_import_workflow",
        "get_2d_animation_details",
        "create_storyboard_panels",
        "create_2d_cutout_layer",
        "apply_procedural_array_stack",
        "create_shader_material",
        "add_geometry_nodes_modifier",
        "create_shape_key",
        "create_animation_brief",
        "create_timing_chart",
        "run_animation_task",
        "run_animation_workflow",
        "analyze_animation_principles",
        "run_animation_repair_loop",
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
        "create_camera_dolly_animation",
        "create_text_object",
        "create_curve_path",
        "create_empty",
        "add_particle_system_to_selected",
        "add_cloth_simulation_to_selected",
        "create_basic_armature",
        "add_copy_transform_constraint",
        "create_studio_product_stage",
        "add_dimension_callouts",
        "apply_lighting_preset",
        "create_material_palette",
        "create_product_turntable_setup",
        "prepare_imported_asset_presentation",
        "apply_product_refinement_template",
        "apply_character_refinement_template",
        "organize_scene_for_production",
        "duplicate_selected_objects",
        "parent_selected_to_empty",
        "align_selected_objects",
        "distribute_selected_objects",
    },
    "refinement": {
        "shade_smooth_selected",
        "add_bevel_and_subsurf",
        "apply_procedural_array_stack",
        "add_panel_seams",
        "add_window_materials",
        "create_studio_product_stage",
        "add_dimension_callouts",
        "apply_lighting_preset",
        "create_material_palette",
        "create_product_turntable_setup",
        "prepare_imported_asset_presentation",
        "apply_product_refinement_template",
        "apply_character_refinement_template",
        "organize_scene_for_production",
    },
    "vehicle": {
        "shade_smooth_selected",
        "add_bevel_and_subsurf",
        "create_wheel_assembly",
        "add_panel_seams",
        "add_window_materials",
        "apply_vehicle_refinement_template",
        "create_studio_product_stage",
        "add_dimension_callouts",
        "apply_lighting_preset",
        "create_material_palette",
        "create_product_turntable_setup",
        "organize_scene_for_production",
        "create_shader_material",
        "add_light",
        "add_camera",
        "set_camera_settings",
    },
    "product": {
        "shade_smooth_selected",
        "add_bevel_and_subsurf",
        "create_studio_product_stage",
        "add_dimension_callouts",
        "apply_lighting_preset",
        "create_material_palette",
        "create_product_turntable_setup",
        "prepare_imported_asset_presentation",
        "apply_product_refinement_template",
        "organize_scene_for_production",
        "set_render_settings",
        "set_camera_settings",
    },
    "character": {
        "shade_smooth_selected",
        "add_bevel_and_subsurf",
        "create_basic_armature",
        "add_copy_transform_constraint",
        "create_text_object",
        "create_curve_path",
        "apply_character_refinement_template",
        "create_studio_product_stage",
        "apply_lighting_preset",
        "organize_scene_for_production",
    },
    "rigging": {
        "get_rigging_details",
        "set_rig_pose_hold",
        "set_rig_custom_property_keyframes",
        "get_rig_pose_library_details",
        "apply_rig_pose_from_action",
        "apply_rig_pose_marker",
        "apply_rig_action_clip",
        "offset_rig_limb_controls",
        "create_basic_armature",
        "add_track_to_constraint",
        "add_copy_transform_constraint",
    },
    "curves_text": {"get_curve_text_details", "create_text_object", "create_curve_path", "create_follow_path_animation"},
    "advanced_workflow": {
        "plan_director_workflow",
        "plan_advanced_scene_workflow",
        "plan_asset_import_workflow",
        "get_2d_animation_details",
        "get_geometry_nodes_details",
        "get_simulation_details",
        "get_render_camera_compositor_details",
        "capture_viewport",
        "capture_animation_playblast",
        "get_visual_evidence_resources",
        "plan_animation_workflow",
        "run_animation_workflow",
    },
    "two_d_storyboard": {
        "plan_advanced_scene_workflow",
        "get_2d_animation_details",
        "create_storyboard_panels",
        "create_2d_cutout_layer",
        "create_camera_dolly_animation",
        "create_directed_animation_shot",
        "capture_animation_playblast",
        "render_scene_thumbnail",
        "start_render_job",
    },
    "procedural_3d": {
        "plan_advanced_scene_workflow",
        "get_geometry_nodes_details",
        "apply_procedural_array_stack",
        "create_procedural_object_kit",
        "add_geometry_nodes_modifier",
        "shade_smooth_selected",
        "add_bevel_and_subsurf",
        "organize_scene_for_production",
    },
    "simulation_setup": {
        "plan_advanced_scene_workflow",
        "get_simulation_details",
        "add_cloth_simulation_to_selected",
        "add_particle_system_to_selected",
        "inspect_simulation_bake",
        "stage_persistent_simulation_bake",
    },
    "particles": {"get_simulation_details", "inspect_simulation_bake", "stage_persistent_simulation_bake", "add_particle_system_to_selected", "add_cloth_simulation_to_selected"},
    "geometry_nodes": {"plan_advanced_scene_workflow", "get_geometry_nodes_details", "add_geometry_nodes_modifier", "apply_procedural_array_stack", "create_procedural_object_kit"},
    "preview_control": {"commit_preview", "revert_preview"},
}

_GROUP_KEYWORDS = {
    "selection": {"select", "selected", "active", "frame", "playhead", "inspect", "workspace", "tab", "focus", "viewport focus", "front view", "top view", "camera view"},
    "basic_edit": {"make", "create", "add", "move", "scale", "rotate", "transform", "object", "primitive", "empty", "marker", "collection", "duplicate", "copy", "parent", "align", "distribute", "layout", "arrange", "hide", "unhide", "visibility", "visible", "display", "wireframe", "show name", "in front"},
    "materials": {"material", "shader", "color", "colour", "red", "blue", "green", "metal", "metallic", "chrome", "glass", "emission", "glow", "window"},
    "animation": {"animate", "animation", "animation brief", "prompt contract", "success criteria", "timing chart", "key pose", "key poses", "hold", "breakdown", "keyframe", "timeline", "frame", "orbit", "dolly", "camera move", "crane", "truck", "bounce", "driver", "motion", "motion arc", "arc", "follow path", "path", "retime", "interpolation", "easing", "loop", "cycles", "turntable", "pulse", "reveal", "stagger", "playblast", "timing", "spacing", "blocking", "anticipation", "squash", "stretch", "settle", "follow-through", "principles", "center of mass", "support", "contact sliding", "simulation", "physics bake", "persistent bake", "directed shot", "shot template"},
    "camera_render": {"camera", "render", "render job", "render output", "output resource", "quality check", "thumbnail", "still", "mp4", "video assembly", "assemble video", "validate render", "1080p", "4k", "frame sequence", "samples", "light", "lighting", "world", "background", "dof", "depth of field", "lens", "compositor", "compositing", "post process", "alpha", "transparent", "resolution", "intensity", "studio", "product stage", "presentation", "close-up", "closeup", "underside"},
    "project_files": {"save", "save as", "save-as", "save copy", "autosave", "auto save", "open blend", "open file", "load blend", "new project", "create project", "blend file", ".blend", "project folder", "project directory", "checkpoint"},
    "deep_inspect": {"inspect", "analyze", "analyse", "summarize", "summary", "details", "world model", "what", "list", "screenshot", "viewport", "visual", "visual evidence", "evidence resource", "resource uri", "image", "capture", "playblast", "review", "diagnostic", "diagnostics", "missing external", "linked library", "linked libraries", "blend file", "data-block", "datablock", "backup", "workspace", "layout json", "underside", "gear"},
    "external_assets": {"asset", "assets", "asset catalog", "asset library", "external asset", "external assets", "asset cache", "cache diagnostics", "poly haven", "polyhaven", "sketchfab", "hdri", "hdris", "environment map", "texture", "textures", "model library", "download model", "download asset", "import model", "import asset", "import hdri", "import texture", "sketchfab uid"},
    "advanced_create": {"advanced", "advanced 3d", "advanced 2d", "geometry nodes", "geometry-node", "node network", "shape key", "text", "curve", "particle", "armature", "constraint", "rig", "driver", "callout", "dimension", "label", "palette", "swatch", "organize", "collection", "cutout", "storyboard", "animatic", "procedural array", "object kit", "kit", "kitbash", "scatter grid", "radial array", "mechanical", "mechanical part", "joint", "control panel", "modular", "wall panel", "pipe run", "prop generator", "directed shot", "shot template"},
    "refinement": {"refine", "polish", "smooth", "high poly", "high-poly", "detail", "bevel", "subdivision", "subsurf", "seam", "panel", "dimension", "callout", "stage", "palette", "lighting", "modifier stack"},
    "vehicle": {"car", "vehicle", "truck", "wheel", "tire", "tyre", "rim", "headlight", "taillight", "windshield", "door", "grille"},
    "product": {"product", "catalog", "catalogue", "packshot", "presentation", "hero shot", "studio shot"},
    "character": {"character", "humanoid", "person", "head", "face", "eyes", "shoulder", "body", "toon", "avatar"},
    "rigging": {"rig", "armature", "bone", "constraint", "copy location", "copy rotation", "track to", "pose library", "pose marker", "ik", "fk", "space switch", "limb", "pole"},
    "curves_text": {"curve", "path", "text", "label", "spline"},
    "advanced_workflow": {"advanced workflow", "advanced 3d", "advanced 2d", "advanced animation", "director", "director workflow", "helper path", "helper gap", "which tools", "what tools", "workflow plan"},
    "two_d_storyboard": {"2d", "two dimensional", "storyboard", "animatic", "storyboard panel", "storyboard panels", "2d panel", "2d panels", "cutout", "cut-out", "motion graphic", "motion graphics", "grease pencil", "grease-pencil", "2d animation"},
    "procedural_3d": {"procedural", "procedural 3d", "array stack", "modifier stack", "scatter", "scatter grid", "kitbash", "object kit", "kit", "radial array", "mechanical", "mechanical joint", "mechanical part", "control panel", "modular", "wall panel", "pipe run", "hard surface", "hard-surface", "non destructive", "non-destructive"},
    "simulation_setup": {"cloth", "cloth sim", "cloth simulation", "simulation setup", "physics setup", "sim setup"},
    "particles": {"particle", "particles", "simulation", "sim", "physics", "bake", "persistent bake", "cache", "point cache", "spark", "dust", "cloth"},
    "geometry_nodes": {"geometry node", "geometry-node", "geometry nodes", "geometry-node network", "node network", "node group", "procedural array", "array stack", "radial array"},
    "preview_control": {"commit", "revert", "undo", "cancel preview", "accept preview"},
}

def _tool_map():
    return {tool["name"]: tool for tool in blender_tool_definitions()}


def _tool_order():
    return [tool["name"] for tool in blender_tool_definitions()]


def _selection_text(prompt, context_bundle):
    parts = [str(prompt or "")]
    bundle = context_bundle or {}
    plan = bundle.get("context_plan")
    if isinstance(plan, dict):
        parts.append(" ".join(str(item) for item in plan.get("included", [])[:20]))
        parts.append(" ".join(str(item) for item in plan.get("omitted", [])[:20]))
    scene = bundle.get("scene_summary")
    if isinstance(scene, dict):
        parts.append(str(scene.get("object_counts_by_type") or ""))
    return "\n".join(parts).lower()


def _contains_keyword(text, keywords):
    return any(keyword in text for keyword in keywords)


def _is_continuation_prompt(prompt):
    normalized = str(prompt or "").strip().lower()
    return normalized in {"ok", "okay", "continue", "go on", "do it", "yes", "yep", "keep going"}


def _schema_chars(tools):
    return len(json.dumps(tools, sort_keys=True))


def select_blender_tool_definitions(prompt="", context_bundle=None, *, max_schema_chars=TOOL_SCHEMA_CHAR_BUDGET):
    """Return request-relevant tool schemas plus selection metadata."""

    full_map = _tool_map()
    selected = set(_CORE_TOOL_NAMES)
    text = _selection_text(prompt, context_bundle)
    matched_groups = []

    if _is_continuation_prompt(prompt):
        for group in ("selection", "basic_edit", "materials", "animation", "camera_render", "advanced_create", "advanced_workflow", "two_d_storyboard", "procedural_3d", "refinement"):
            selected.update(_TOOL_GROUPS[group])
            matched_groups.append(group)
    else:
        for group, keywords in _GROUP_KEYWORDS.items():
            if _contains_keyword(text, keywords):
                selected.update(_TOOL_GROUPS[group])
                matched_groups.append(group)

    if helper_routing.should_include_draft_script(text, matched_groups):
        selected.update(_FALLBACK_TOOL_NAMES)
    if helper_routing.should_include_privileged_script(text, matched_groups):
        selected.update(_PRIVILEGED_FALLBACK_TOOL_NAMES)

    if not selected.intersection(TOOL_FUNCTIONS_FOR_MUTATION_COMPAT):
        selected.update({"select_objects"})

    ordered_names = [name for name in _tool_order() if name in selected and name in full_map]
    tools = [full_map[name] for name in ordered_names]

    budget = max(4000, int(max_schema_chars or TOOL_SCHEMA_CHAR_BUDGET))
    protected = set(_CORE_TOOL_NAMES)
    for group in matched_groups:
        if group in {"vehicle", "product", "character", "refinement", "camera_render", "rigging", "curves_text", "particles", "geometry_nodes", "external_assets", "advanced_workflow", "two_d_storyboard", "procedural_3d", "simulation_setup"}:
            protected.update(_TOOL_GROUPS.get(group, set()))
    if "animation" in matched_groups:
        protected.update(
            {
                "create_animation_brief",
                "plan_advanced_scene_workflow",
                "get_animation_scene_context",
                "create_timing_chart",
                "plan_animation_workflow",
                "run_animation_workflow",
                "run_animation_task",
                "capture_viewport",
                "capture_animation_playblast",
                "capture_object_inspection_renders",
                "get_visual_evidence_resources",
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
                "create_camera_dolly_animation",
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
                "inspect_simulation_bake",
                "stage_persistent_simulation_bake",
                "compare_animation_to_brief",
                "review_playblast_against_brief",
                "review_inspection_renders_against_brief",
                "repair_animation_from_findings",
                "run_animation_repair_loop",
                "set_scene_frame_range",
                "set_animation_preview_range",
                "animate_selected_transform",
                "animate_object_bounce",
                "create_progressive_bounce_animation",
                "animate_material_property",
                "animate_light_property",
                "create_follow_path_animation",
                "create_turntable_animation",
                "create_pulse_animation",
                "create_reveal_animation",
                "create_staggered_motion",
                "set_action_interpolation",
                "retime_actions",
                "add_action_cycles",
                "clear_animation",
                "create_2d_cutout_layer",
            }
        )
    if "deep_inspect" in matched_groups:
        protected.update(
            {
                "capture_viewport",
                "capture_animation_playblast",
                "capture_object_inspection_renders",
                "get_visual_evidence_resources",
                "review_playblast_against_brief",
                "review_inspection_renders_against_brief",
                "repair_animation_from_findings",
                "run_animation_repair_loop",
            }
        )
    if "draft_script" in selected:
        protected.add("draft_script")
    if "draft_privileged_script" in selected:
        protected.add("draft_privileged_script")
    while _schema_chars(tools) > budget:
        removable_index = next(
            (index for index in range(len(ordered_names) - 1, -1, -1) if ordered_names[index] not in protected),
            None,
        )
        if removable_index is None:
            break
        ordered_names.pop(removable_index)
        tools.pop(removable_index)

    selected_names = [tool["name"] for tool in tools]
    omitted_names = [name for name in _tool_order() if name not in selected_names]
    metadata = {
        "selected_tool_names": selected_names,
        "omitted_tool_names": omitted_names,
        "selected_tool_count": len(selected_names),
        "available_tool_count": len(full_map),
        "schema_chars": _schema_chars(tools),
        "estimated_schema_tokens": int((_schema_chars(tools) + 3) / 4),
        "matched_groups": sorted(set(matched_groups)),
        "budget_chars": budget,
    }
    return tools, metadata


TOOL_FUNCTIONS_FOR_MUTATION_COMPAT = {
    "set_selected_location_delta",
    "set_selected_transform",
    "create_primitive",
    "create_empty",
    "set_object_visibility",
    "set_object_display",
    "assign_material_to_selected",
    "assign_emission_material_to_selected",
    "create_shader_material",
    "plan_director_workflow",
    "plan_asset_import_workflow",
    "plan_advanced_scene_workflow",
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
    "run_animation_workflow",
    "run_animation_task",
    "create_directed_animation_shot",
    "run_animation_repair_loop",
    "create_turntable_animation",
    "create_pulse_animation",
    "create_reveal_animation",
    "create_staggered_motion",
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
    "create_storyboard_panels",
    "create_2d_cutout_layer",
    "apply_procedural_array_stack",
    "create_procedural_object_kit",
    "create_camera_dolly_animation",
    "create_directed_animation_shot",
    "add_cloth_simulation_to_selected",
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
    "cancel_external_asset_import_job",
    "delete_external_asset_job",
    "get_external_asset_cache_diagnostics",
    "prune_external_asset_cache",
    "duplicate_selected_objects",
    "parent_selected_to_empty",
    "align_selected_objects",
    "distribute_selected_objects",
    "shade_smooth_selected",
    "add_bevel_and_subsurf",
    "create_studio_product_stage",
    "add_dimension_callouts",
    "apply_lighting_preset",
    "create_material_palette",
    "create_product_turntable_setup",
    "prepare_imported_asset_presentation",
    "organize_scene_for_production",
    "apply_vehicle_refinement_template",
    "apply_product_refinement_template",
    "apply_character_refinement_template",
    "draft_script",
}


def blender_tool_definitions_for_request(prompt="", context_bundle=None, *, max_schema_chars=TOOL_SCHEMA_CHAR_BUDGET):
    tools, _metadata = select_blender_tool_definitions(
        prompt=prompt,
        context_bundle=context_bundle,
        max_schema_chars=max_schema_chars,
    )
    return tools


def register():
    pass


def unregister():
    pass
