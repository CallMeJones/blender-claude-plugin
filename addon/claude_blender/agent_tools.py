"""Provider-neutral tool catalog and routing hints for external agents."""

from __future__ import annotations

import json


AGENT_GUIDANCE = (
    "You are an external agent connected to Blender Agent Bridge. Use the provided scene context and Blender tools. "
    "If agent_memory is enabled, treat it as the running project thread so the user can work progressively across prompts. "
    "Use prior goals, attempted steps, and remaining tasks from agent_memory, but treat the current Blender scene context as authoritative if they conflict. "
    "Read context_plan before acting. It explains which scene details were included or omitted to stay within the request budget. "
    "If omitted details matter, call inspect_scene, get_object_details, get_animation_details, get_animation_scene_context, get_material_node_details, get_geometry_nodes_details, get_shader_nodes_details, get_rigging_details, get_shape_key_details, get_curve_text_details, get_simulation_details, get_collection_layer_details, get_render_camera_compositor_details, get_blend_file_diagnostics, get_workspace_layout, capture_viewport, capture_animation_playblast, capture_object_inspection_renders, render_scene_thumbnail, start_render_job, get_render_job_status, assemble_render_job_video, validate_render_job_output, or search_blender_docs instead of guessing. "
    "When target objects are unclear, use list_scene_objects and select_objects before applying selected-object tools. "
    "When the user asks to change the scene, use safe helper tools first so Blender changes immediately. "
    "Use direct Blender data concepts: objects, collections, materials, cameras, lights, actions, keyframes. "
    "For scene building and layout, prefer create_primitive, create_empty, duplicate_selected_objects, parent_selected_to_empty, align_selected_objects, distribute_selected_objects, set_object_visibility, set_object_display, assign_material_to_selected, assign_emission_material_to_selected, create_shader_material, create_text_object, create_curve_path, create_collection, link_selected_to_collection, add_light, add_camera, add_modifier_to_selected, add_geometry_nodes_modifier, add_track_to_constraint, add_copy_transform_constraint, create_basic_armature, add_particle_system_to_selected, set_render_settings, set_camera_settings, and set_world_background. "
    "For model refinement and production presentation, prefer shade_smooth_selected, add_bevel_and_subsurf, create_wheel_assembly, add_panel_seams, add_window_materials, apply_vehicle_refinement_template, apply_product_refinement_template, apply_character_refinement_template, create_studio_product_stage, add_dimension_callouts, apply_lighting_preset, create_material_palette, create_product_turntable_setup, and organize_scene_for_production when they fit the task. "
    "For shape-key animation, prefer create_shape_key and animate_shape_key before drafting Python. "
    "For long-running or high-resolution renders, playblasts, frame sequences, or MP4 quality checks, use start_render_job and poll get_render_job_status instead of draft_script; use assemble_render_job_video for PNG sequences and validate_render_job_output before reporting success; use cancel_render_job if the user wants to stop it. "
    "For animation generation, review, or repair, call run_animation_task for simple prompt-in/task-out use, or call plan_animation_workflow first when you need manual control of the generated workflow. plan_animation_workflow returns the brief, scene routing, timing chart, ordered helper calls, evaluator calls, repair calls, and script fallback rules. For common helper-backed generation, call run_animation_workflow to execute the plan, review the result, optionally capture playblast evidence, and leave changes in preview. Use any animation_brief in context as the prompt contract; otherwise call create_animation_brief first when the prompt needs an explicit contract, success criteria, or later validation. Call get_animation_scene_context before advanced animation in scenes with rigs, constraints, drivers, shape keys, physics, or unclear edit targets so you know whether to animate object transforms, rig controls, shape keys, materials, physics, or camera settings. Use create_timing_chart, block_key_poses, add_breakdown_pose, set_pose_hold, set_rig_pose_hold, and create_motion_arc for animator-style blocking before spline/f-curve polish; use set_rig_pose_hold only after identifying armature control bones. Then use analyze_animation_principles plus focused analyzers to check timing, spacing, arcs, pose clarity, anticipation, squash/stretch, contact, center-of-mass support, speed/acceleration plausibility, and settle before repair. Use capture_animation_playblast and review_playblast_against_brief when visual frame evidence matters; use capture_object_inspection_renders and review_inspection_renders_against_brief when close-up object detail evidence matters; if review or repair tools return repair_operations, prefer run_animation_repair_loop for bounded helper repair and review-again behavior, or execute relevant tool_call name/input entries deliberately when manual control is needed. Then prefer set_scene_frame_range, set_animation_preview_range, animate_selected_transform, animate_object_bounce, create_progressive_bounce_animation, animate_material_property, animate_light_property, create_follow_path_animation, create_turntable_animation, create_pulse_animation, create_reveal_animation, create_staggered_motion, set_action_interpolation, retime_actions, add_action_cycles, clear_animation, and create_camera_orbit. "
    "For complex scene builds that need many objects or more than about eight helper calls, stage one cohesive Blender Python script with draft_script instead of making a long chain of helper calls. "
    "When helper tools cannot express the requested edit, use draft_script to stage Blender Python for user approval; if the user has granted external script trust, draft_script may auto-run after static checks. "
    "When calling draft_script, put the complete Python source in the code field. Do not put script code in final chat text for the user to paste manually. "
    "If draft_script reports that code is missing, retry once with a shorter complete script in the code field. "
    "A drafted script runs only when draft_script reports auto_ran true or the user explicitly approves it in Blender, so do not claim it executed from staging alone. "
    "Before drafting unfamiliar or version-sensitive Python, search_blender_docs for the relevant Blender API. "
    "Do not suggest destructive changes without clearly warning the user. "
    "Do not invent dimensions, materials, object names, or animation details. "
    "If a value is absent, say it is not available in the context. "
    "For low-risk changes, call tools instead of merely explaining what should be done. "
    "Leave live preview changes pending for the user; do not call commit_preview or revert_preview unless the user explicitly asks. "
    "Generated arbitrary Python is approval-gated by default and must be drafted through draft_script. "
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
            "description": "Capture sampled viewport frames across an animation range and return playblast metadata plus MCP frame resource URIs for visual animation review. Requires an interactive Blender window and fails soft in background mode.",
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
                    "brief": {
                        "type": "string",
                        "description": "Short animation intent or prompt contract to store with the playblast metadata.",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "capture_object_inspection_renders",
            "description": "Render diagnostic close-up PNGs of named objects from bounded inspection views, then return metadata plus MCP image resource URIs. Use when visual object details need rendered evidence, such as undersides, side views, occluded parts, or model defects. Cleans up the temporary camera and restores render settings.",
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
            "description": "Inspect blend-file health: saved path, backups, missing external files, linked libraries, and data-block usage summaries.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "max_items": {"type": "integer", "description": "Maximum external file/library entries to return."},
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
            "description": "Render a small PNG from the scene camera or a named camera, then return metadata plus exact MCP image resource URIs. Use for render evidence, thumbnails, and client-readable still output.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Optional PNG output path. Defaults to the project/session capture cache."},
                    "frame": {"type": "integer", "description": "Frame to render. Defaults to current frame."},
                    "resolution_x": {"type": "integer", "description": "PNG width. Defaults to 512."},
                    "resolution_y": {"type": "integer", "description": "PNG height. Defaults to 512."},
                    "camera_name": {"type": "string", "description": "Optional camera object name. Defaults to active scene camera."},
                    "note": {"type": "string", "description": "Short reason stored in thumbnail metadata."},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "start_render_job",
            "description": "Start a long-running render or playblast job in a background Blender process and return immediately with a job id. Use for 1080p/4K, high-sample, full-frame-range renders, frame sequences, or MP4 quality checks instead of draft_script.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "frame_start": {"type": "integer"},
                    "frame_end": {"type": "integer"},
                    "resolution_x": {"type": "integer", "description": "Output width. Defaults to 1920."},
                    "resolution_y": {"type": "integer", "description": "Output height. Defaults to 1080."},
                    "resolution_percentage": {"type": "integer", "description": "Render percentage. Defaults to 100."},
                    "samples": {"type": "integer", "description": "Cycles/Eevee render samples. Defaults to 64."},
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
            "description": "Build read-only animation-aware scene context that identifies likely edit targets, rig-driven objects, rig control candidates, shape keys, constraints, drivers, NLA, physics/simulation hints, contact surfaces, camera readiness, and recommended deeper inspection tools.",
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
            "description": "Create or update a Principled BSDF material and optionally assign it to selected mesh objects. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "base_color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "metallic": {"type": "number"},
                    "roughness": {"type": "number"},
                    "alpha": {"type": "number"},
                    "emission_color": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 4},
                    "emission_strength": {"type": "number"},
                    "assign_to_selected": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "required": ["name", "base_color"],
                "additionalProperties": False,
            },
        },
        {
            "name": "add_geometry_nodes_modifier",
            "description": "Add a valid passthrough Geometry Nodes modifier and node group to selected mesh objects. Applies immediately with preview revert support.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "node_group_name": {"type": "string"},
                    "selected_only": {"type": "boolean"},
                    "label": {"type": "string"},
                },
                "required": ["name", "node_group_name"],
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
            "name": "draft_script",
            "description": (
                "Stage Blender Python in a Text datablock for explicit user approval, or auto-run after static checks when external script trust is active. "
                "Use only when safe helper tools cannot express the requested scene, animation, material, or rig change. "
                "Blocked scripts are refused even during a trust window."
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
                        "description": "Complete Blender Python script to stage for approval",
                    },
                },
                "required": ["intent", "expected_changes", "risk_level", "code"],
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

_TOOL_GROUPS = {
    "selection": {"select_objects", "set_current_frame", "get_workspace_layout", "jump_to_workspace", "focus_object_in_viewport"},
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
        "create_motion_arc",
        "create_camera_orbit",
        "capture_animation_playblast",
        "animate_shape_key",
    },
    "camera_render": {
        "get_render_camera_compositor_details",
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
        "create_studio_product_stage",
        "apply_lighting_preset",
        "create_product_turntable_setup",
        "create_turntable_animation",
        "set_render_settings",
        "set_camera_settings",
        "set_world_background",
        "animate_light_property",
    },
    "deep_inspect": {
        "get_blend_file_diagnostics",
        "get_workspace_layout",
        "get_animation_scene_context",
        "get_geometry_nodes_details",
        "get_shader_nodes_details",
        "get_rigging_details",
        "get_shape_key_details",
        "get_curve_text_details",
        "get_simulation_details",
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
    "advanced_create": {
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
        "create_motion_arc",
        "create_text_object",
        "create_curve_path",
        "create_empty",
        "add_particle_system_to_selected",
        "create_basic_armature",
        "add_copy_transform_constraint",
        "create_studio_product_stage",
        "add_dimension_callouts",
        "apply_lighting_preset",
        "create_material_palette",
        "create_product_turntable_setup",
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
        "add_panel_seams",
        "add_window_materials",
        "create_studio_product_stage",
        "add_dimension_callouts",
        "apply_lighting_preset",
        "create_material_palette",
        "create_product_turntable_setup",
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
        "create_basic_armature",
        "add_track_to_constraint",
        "add_copy_transform_constraint",
    },
    "curves_text": {"get_curve_text_details", "create_text_object", "create_curve_path", "create_follow_path_animation"},
    "particles": {"get_simulation_details", "add_particle_system_to_selected"},
    "geometry_nodes": {"get_geometry_nodes_details", "add_geometry_nodes_modifier"},
    "preview_control": {"commit_preview", "revert_preview"},
}

_GROUP_KEYWORDS = {
    "selection": {"select", "selected", "active", "frame", "playhead", "inspect", "workspace", "tab", "focus", "viewport focus"},
    "basic_edit": {"make", "create", "add", "move", "scale", "rotate", "transform", "object", "primitive", "empty", "marker", "collection", "duplicate", "copy", "parent", "align", "distribute", "layout", "arrange", "hide", "unhide", "visibility", "visible", "display", "wireframe", "show name", "in front"},
    "materials": {"material", "shader", "color", "colour", "red", "blue", "green", "metal", "metallic", "chrome", "glass", "emission", "glow", "window"},
    "animation": {"animate", "animation", "animation brief", "prompt contract", "success criteria", "timing chart", "key pose", "key poses", "hold", "breakdown", "keyframe", "timeline", "frame", "orbit", "bounce", "driver", "motion", "motion arc", "arc", "follow path", "path", "retime", "interpolation", "easing", "loop", "cycles", "turntable", "pulse", "reveal", "stagger", "playblast", "timing", "spacing", "blocking", "anticipation", "squash", "stretch", "settle", "follow-through", "principles", "center of mass", "support", "contact sliding"},
    "camera_render": {"camera", "render", "render job", "quality check", "thumbnail", "still", "mp4", "video assembly", "assemble video", "validate render", "1080p", "4k", "frame sequence", "samples", "light", "lighting", "world", "background", "dof", "depth of field", "lens", "compositor", "resolution", "intensity", "studio", "product stage", "presentation", "close-up", "closeup", "underside"},
    "deep_inspect": {"inspect", "analyze", "analyse", "summarize", "summary", "details", "world model", "what", "list", "screenshot", "viewport", "visual", "image", "capture", "playblast", "review", "diagnostic", "diagnostics", "missing external", "linked library", "linked libraries", "blend file", "data-block", "datablock", "backup", "workspace", "layout json", "underside", "gear"},
    "advanced_create": {"geometry nodes", "shape key", "text", "curve", "particle", "armature", "constraint", "rig", "driver", "callout", "dimension", "label", "palette", "swatch", "organize", "collection"},
    "refinement": {"refine", "polish", "smooth", "high poly", "high-poly", "detail", "bevel", "subdivision", "subsurf", "seam", "panel", "dimension", "callout", "stage", "palette", "lighting"},
    "vehicle": {"car", "vehicle", "truck", "wheel", "tire", "tyre", "rim", "headlight", "taillight", "windshield", "door", "grille"},
    "product": {"product", "catalog", "catalogue", "packshot", "presentation", "hero shot", "studio shot"},
    "character": {"character", "humanoid", "person", "head", "face", "eyes", "shoulder", "body", "toon", "avatar"},
    "rigging": {"rig", "armature", "bone", "constraint", "copy location", "copy rotation", "track to"},
    "curves_text": {"curve", "path", "text", "label", "spline"},
    "particles": {"particle", "particles", "simulation", "sim", "spark", "dust"},
    "geometry_nodes": {"geometry node", "geometry nodes", "node group"},
    "preview_control": {"commit", "revert", "undo", "cancel preview", "accept preview"},
}

_SCRIPT_FALLBACK_KEYWORDS = {
    "script",
    "python",
    "custom code",
    "custom python",
    "draft_script",
    "draft script",
    "helper tools cannot express",
    "helpers cannot express",
    "approved script",
}


def _tool_map():
    return {tool["name"]: tool for tool in blender_tool_definitions()}


def _tool_order():
    return [tool["name"] for tool in blender_tool_definitions()]


def _selection_text(prompt, context_bundle):
    parts = [str(prompt or "")]
    bundle = context_bundle or {}
    memory = bundle.get("agent_memory")
    if isinstance(memory, dict):
        parts.append(str(memory.get("memory") or "")[-4000:])
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
        for group in ("selection", "basic_edit", "materials", "animation", "camera_render", "advanced_create", "refinement"):
            selected.update(_TOOL_GROUPS[group])
            matched_groups.append(group)
    else:
        for group, keywords in _GROUP_KEYWORDS.items():
            if _contains_keyword(text, keywords):
                selected.update(_TOOL_GROUPS[group])
                matched_groups.append(group)

    if _contains_keyword(text, _SCRIPT_FALLBACK_KEYWORDS):
        selected.update(_FALLBACK_TOOL_NAMES)

    if not selected.intersection(TOOL_FUNCTIONS_FOR_MUTATION_COMPAT):
        selected.update({"select_objects"})

    ordered_names = [name for name in _tool_order() if name in selected and name in full_map]
    tools = [full_map[name] for name in ordered_names]

    budget = max(4000, int(max_schema_chars or TOOL_SCHEMA_CHAR_BUDGET))
    protected = set(_CORE_TOOL_NAMES)
    for group in matched_groups:
        if group in {"vehicle", "product", "character", "refinement", "camera_render", "rigging", "curves_text", "particles", "geometry_nodes"}:
            protected.update(_TOOL_GROUPS.get(group, set()))
    if "animation" in matched_groups:
        protected.update(
            {
                "create_animation_brief",
                "get_animation_scene_context",
                "create_timing_chart",
                "plan_animation_workflow",
                "run_animation_workflow",
                "run_animation_task",
                "block_key_poses",
                "add_breakdown_pose",
                "set_pose_hold",
                "set_rig_pose_hold",
                "create_motion_arc",
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
            }
        )
    if "draft_script" in selected:
        protected.add("draft_script")
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
    "run_animation_repair_loop",
    "create_turntable_animation",
    "create_pulse_animation",
    "create_reveal_animation",
    "create_staggered_motion",
    "block_key_poses",
    "add_breakdown_pose",
    "set_pose_hold",
    "set_rig_pose_hold",
    "create_motion_arc",
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
