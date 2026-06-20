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
        "long_running": True,
        "duration_hint": "Usually seconds for helper-only animation; can take longer when capture_playblast or repair recapture is enabled.",
        "timeout_recovery": {
            "recoverable": True,
            "poll_after_seconds": 5,
            "status_tool": "blender_bridge_status",
            "resource_tool": "get_visual_evidence_resources",
            "message": "If the client times out, wait briefly, check bridge status, then inspect visual evidence resources and audit logs before rerunning.",
        },
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
        "long_running": True,
        "duration_hint": "Usually seconds for helper-backed animation; can take longer when the workflow captures or reviews visual evidence.",
        "timeout_recovery": {
            "recoverable": True,
            "poll_after_seconds": 5,
            "status_tool": "blender_bridge_status",
            "resource_tool": "get_visual_evidence_resources",
            "message": "If the client times out, wait briefly, check bridge status, then inspect visual evidence resources and audit logs before rerunning.",
        },
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
        "duration_hint": "Normally a few seconds. Oversized image batches are pixel-budgeted and may skip extra frame inspection to keep the bridge responsive.",
        "timeout_recovery": {
            "recoverable": True,
            "poll_after_seconds": 5,
            "status_tool": "blender_bridge_status",
            "resource_tool": "get_visual_evidence_resources",
            "message": "If review times out, wait for the bridge to become responsive, inspect the latest playblast metadata/audit log, and rerun with fewer or smaller frames if needed.",
        },
    },
    "review_inspection_renders_against_brief": {
        "description": "Review diagnostic object render metadata and image evidence against a prompt contract",
        "mutates_scene": False,
        "duration_hint": "Normally a few seconds. Oversized image batches are pixel-budgeted and may skip extra image inspection to keep the bridge responsive.",
        "timeout_recovery": {
            "recoverable": True,
            "poll_after_seconds": 5,
            "status_tool": "blender_bridge_status",
            "resource_tool": "get_visual_evidence_resources",
            "message": "If review times out, wait for the bridge to become responsive, inspect the latest inspection-render metadata/audit log, and rerun with fewer or smaller images if needed.",
        },
    },
    "repair_animation_from_findings": {
        "description": "Create targeted non-mutating repair operations with executable helper tool-call payloads",
        "mutates_scene": False,
    },
    "run_animation_repair_loop": {
        "description": "Apply bounded animation repair operations and re-run playblast/brief review",
        "mutates_scene": True,
        "long_running": True,
        "duration_hint": "Usually seconds to a minute depending on repair count and whether playblast recapture is enabled.",
        "timeout_recovery": {
            "recoverable": True,
            "poll_after_seconds": 5,
            "status_tool": "blender_bridge_status",
            "resource_tool": "get_visual_evidence_resources",
            "message": "If the client times out, wait briefly, check bridge status, then inspect visual evidence resources and audit logs before rerunning repairs.",
        },
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
    "list_poly_haven_categories": {
        "description": "List Poly Haven catalog categories for HDRIs, textures, and models without importing assets",
        "mutates_scene": False,
        "permissions": ["network"],
        "supports_headless": True,
        "timeout_seconds": 30,
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_type": {"type": "string", "enum": ["all", "hdris", "textures", "models"]},
                "timeout": {"type": "integer", "description": "HTTP timeout in seconds. Defaults to 15."},
            },
            "additionalProperties": False,
        },
    },
    "search_poly_haven_assets": {
        "description": "Search Poly Haven's CC0 asset catalog and return page/file API URLs without downloading or importing assets",
        "mutates_scene": False,
        "permissions": ["network"],
        "supports_headless": True,
        "timeout_seconds": 30,
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
    "inspect_poly_haven_asset_files": {
        "description": "Fetch and summarize Poly Haven's file tree for one asset without downloading or importing",
        "mutates_scene": False,
        "permissions": ["network"],
        "supports_headless": True,
        "timeout_seconds": 30,
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
    "download_poly_haven_asset": {
        "description": "Download/cache selected Poly Haven HDRI, texture, or model files plus dependencies with checksum validation",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["network", "files:write"],
        "supports_headless": True,
        "timeout_seconds": 300,
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
    "import_poly_haven_asset": {
        "description": "Download/cache and import a Poly Haven asset into Blender: HDRIs become a preview world, textures become a material, and models import through Blender importers",
        "mutates_scene": True,
        "requires_live_preview": True,
        "has_side_effects": True,
        "permissions": ["network", "files:write", "scene:mutate", "preview:write"],
        "supports_headless": True,
        "timeout_seconds": 300,
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
    "search_sketchfab_models": {
        "description": "Search Sketchfab's public model catalog and return viewer/license metadata without downloading or importing assets",
        "mutates_scene": False,
        "permissions": ["network"],
        "supports_headless": True,
        "timeout_seconds": 30,
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
    "download_sketchfab_model": {
        "description": "Use a Sketchfab API token to fetch temporary GLTF download info, cache the archive, and extract an importable model file",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["network", "files:write"],
        "supports_headless": True,
        "timeout_seconds": 300,
        "input_schema": {
            "type": "object",
            "properties": {
                "uid": {"type": "string"},
                "api_token": {"type": "string", "description": "Optional per-call Sketchfab API token. Redacted in audit logs."},
                "token_env_var": {
                    "type": "string",
                    "enum": ["SKETCHFAB_API_TOKEN", "BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN"],
                    "description": "Sketchfab-specific environment variable to read when api_token is omitted. Defaults to SKETCHFAB_API_TOKEN.",
                },
                "model_password": {"type": "string"},
                "cache_dir": {"type": "string"},
                "timeout": {"type": "integer"},
            },
            "required": ["uid"],
            "additionalProperties": False,
        },
    },
    "import_sketchfab_model": {
        "description": "Use a Sketchfab API token to cache a downloadable model archive and import the extracted GLTF/GLB file into Blender preview",
        "mutates_scene": True,
        "requires_live_preview": True,
        "has_side_effects": True,
        "permissions": ["network", "files:write", "scene:mutate", "preview:write"],
        "supports_headless": True,
        "timeout_seconds": 300,
        "input_schema": {
            "type": "object",
            "properties": {
                "uid": {"type": "string"},
                "api_token": {"type": "string", "description": "Optional per-call Sketchfab API token. Redacted in audit logs."},
                "token_env_var": {
                    "type": "string",
                    "enum": ["SKETCHFAB_API_TOKEN", "BLENDER_AGENT_BRIDGE_SKETCHFAB_API_TOKEN"],
                    "description": "Sketchfab-specific environment variable to read when api_token is omitted. Defaults to SKETCHFAB_API_TOKEN.",
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
    "get_external_asset_cache_diagnostics": {
        "description": "Report cached/imported external assets, providers, licenses, source URLs, files, and imported Blender data-block names",
        "mutates_scene": False,
        "permissions": ["files:read"],
        "supports_headless": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "cache_dir": {"type": "string"},
                "max_assets": {"type": "integer"},
            },
            "additionalProperties": False,
        },
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
        "description": "Capture sampled low-resolution viewport frames across an animation range for visual review",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["scene:read", "files:write"],
        "supports_headless": False,
        "long_running": True,
        "duration_hint": "Synchronous viewport capture; rough estimate is about 1 second per sampled frame, with the default 12 low-resolution preview frames often around 10-20 seconds on large scenes.",
        "timeout_recovery": {
            "recoverable": True,
            "poll_after_seconds": 5,
            "status_tool": "blender_bridge_status",
            "resource_tool": "get_visual_evidence_resources",
            "message": "If the MCP client times out, the playblast may still finish. Wait, check bridge status, then read latest playblast metadata or audit logs before recapturing.",
        },
        "timeout_seconds": 120,
        "input_schema": {
            "type": "object",
            "properties": {
                "frame_start": {"type": "integer"},
                "frame_end": {"type": "integer"},
                "max_frames": {"type": "integer"},
                "max_bytes": {"type": "integer"},
                "quality": {"type": "string", "enum": ["preview", "low", "standard", "medium", "high", "hd", "source", "original", "full"]},
                "max_width": {"type": "integer"},
                "max_height": {"type": "integer"},
                "brief": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    "capture_object_inspection_renders": {
        "description": "Render diagnostic close-up PNGs of named objects from bounded inspection views and expose them as MCP resources",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["scene:read", "files:write"],
        "supports_headless": True,
        "long_running": True,
        "duration_hint": "Synchronous still renders; rough estimate is a few seconds per object/view at 800x600 and more for heavy scenes or high resolutions.",
        "timeout_recovery": {
            "recoverable": True,
            "poll_after_seconds": 5,
            "status_tool": "blender_bridge_status",
            "resource_tool": "get_visual_evidence_resources",
            "message": "If the MCP client times out, inspection renders may still finish. Wait, check bridge status, then read latest inspection-render metadata or audit logs before rerendering.",
        },
        "timeout_seconds": 180,
    },
    "get_blend_file_diagnostics": {
        "description": "Return blend-file diagnostics for save path, dirty state, backups, missing external files, linked libraries, and data-block usage summaries",
        "mutates_scene": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "max_items": {"type": "integer", "description": "Maximum external file/library entries to return"},
            },
            "additionalProperties": False,
        },
    },
    "save_blend_file": {
        "description": "Save the current .blend file, save-as to a new .blend path, or save a copy without changing the active file",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["scene:read", "files:write"],
        "long_running": True,
        "duration_hint": "Usually seconds, but large .blend files or network paths can take longer. The current file path changes only when copy=false and filepath targets a different .blend.",
        "timeout_recovery": {
            "recoverable": True,
            "poll_after_seconds": 5,
            "status_tool": "blender_bridge_status",
            "resource_tool": "get_blend_file_diagnostics",
            "message": "If saving times out, wait, call blender_bridge_status, then check get_blend_file_diagnostics and the target file before retrying.",
        },
        "timeout_seconds": 180,
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Optional .blend path. Omit to save the active file."},
                "copy": {"type": "boolean", "description": "Save a copy without changing the active blend filepath. Requires filepath."},
                "overwrite": {"type": "boolean", "description": "Allow replacing an existing target .blend file."},
                "create_dirs": {"type": "boolean", "description": "Create the target directory if missing. Defaults to true."},
            },
            "additionalProperties": False,
        },
    },
    "open_blend_file": {
        "description": "Open an existing .blend file after explicit discard confirmation, creating a checkpoint first by default",
        "mutates_scene": True,
        "has_side_effects": True,
        "destructive": True,
        "risk_level": "destructive",
        "permissions": ["scene:read", "scene:mutate", "files:read", "files:write"],
        "long_running": True,
        "duration_hint": "Usually seconds, but large .blend files can take longer. The active Blender session is replaced.",
        "timeout_recovery": {
            "recoverable": True,
            "poll_after_seconds": 5,
            "status_tool": "blender_bridge_status",
            "resource_tool": "get_blend_file_diagnostics",
            "message": "If opening times out, wait, call blender_bridge_status, then check get_blend_file_diagnostics before opening another file.",
        },
        "timeout_seconds": 300,
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Existing .blend file path to open."},
                "confirm_discard_current": {"type": "boolean", "description": "Required true; opening replaces the active session."},
                "create_checkpoint": {"type": "boolean", "description": "Save a checkpoint of the current file before opening. Defaults to true."},
                "require_checkpoint": {"type": "boolean", "description": "Abort if checkpoint creation fails. Defaults to true."},
                "checkpoint_dir": {"type": "string", "description": "Optional checkpoint output directory."},
                "load_ui": {"type": "boolean", "description": "Load UI layout from the opened .blend when supported. Defaults to false."},
            },
            "required": ["filepath", "confirm_discard_current"],
            "additionalProperties": False,
        },
    },
    "create_new_blender_project": {
        "description": "Create a new Blender project folder and .blend file after explicit discard confirmation, with optional standard subfolders",
        "mutates_scene": True,
        "has_side_effects": True,
        "destructive": True,
        "risk_level": "destructive",
        "permissions": ["scene:read", "scene:mutate", "files:write"],
        "long_running": True,
        "duration_hint": "Usually seconds. The active Blender session is replaced by a fresh startup scene and immediately saved.",
        "timeout_recovery": {
            "recoverable": True,
            "poll_after_seconds": 5,
            "status_tool": "blender_bridge_status",
            "resource_tool": "get_blend_file_diagnostics",
            "message": "If new-project creation times out, wait, call blender_bridge_status, then check get_blend_file_diagnostics and the target project folder before retrying.",
        },
        "timeout_seconds": 300,
        "input_schema": {
            "type": "object",
            "properties": {
                "project_dir": {"type": "string", "description": "Parent or final project directory. Required unless filepath is supplied."},
                "project_name": {"type": "string", "description": "Project name used for folder/filename when filepath is omitted."},
                "filepath": {"type": "string", "description": "Optional explicit target .blend path."},
                "template": {"type": "string", "enum": ["default", "empty", "factory_startup"], "description": "Startup scene template. Defaults to default."},
                "create_standard_dirs": {"type": "boolean", "description": "Create assets, refs, renders, and exports folders. Defaults to true."},
                "standard_dirs": {"type": "array", "items": {"type": "string"}, "description": "Optional custom project subfolders."},
                "overwrite": {"type": "boolean", "description": "Allow replacing an existing target .blend file."},
                "create_dirs": {"type": "boolean", "description": "Create the project directory if missing. Defaults to true."},
                "confirm_discard_current": {"type": "boolean", "description": "Required true; new project replaces the active session."},
                "create_checkpoint": {"type": "boolean", "description": "Save a checkpoint of the current file before creating the new project. Defaults to true."},
                "require_checkpoint": {"type": "boolean", "description": "Abort if checkpoint creation fails. Defaults to true."},
                "checkpoint_dir": {"type": "string", "description": "Optional checkpoint output directory."},
            },
            "required": ["confirm_discard_current"],
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
    "get_visual_evidence_resources": {
        "description": "Return a compact inventory of latest viewport, playblast, inspection render, thumbnail, and render-job MCP resources",
        "mutates_scene": False,
        "input_schema": {
            "type": "object",
            "properties": {
                "include_unavailable": {"type": "boolean", "description": "Include resource families with no latest artifact yet. Defaults to true."},
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
    "set_viewport_view": {
        "description": "Set the first interactive 3D viewport to an axis, camera, or user view and optionally frame an object without changing scene data",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["ui:navigate"],
        "supports_headless": False,
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
        "long_running": True,
        "duration_hint": "Small guarded still renders are usually seconds. Large synchronous renders are blocked by default; use start_render_job for timeout-safe high-resolution output.",
        "timeout_recovery": {
            "recoverable": True,
            "poll_after_seconds": 5,
            "status_tool": "blender_bridge_status",
            "resource_tool": "get_visual_evidence_resources",
            "recommended_tool": "start_render_job",
            "message": "If the MCP client times out, wait, check bridge status, then inspect latest render-thumbnail metadata or use start_render_job for a timeout-safe rerun.",
        },
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
                "allow_blocking_render": {"type": "boolean", "description": "Allow a large synchronous still render. Defaults to false; large previews should use start_render_job."},
            },
            "additionalProperties": False,
        },
    },
    "start_render_job": {
        "description": "Start a long-running background Blender render job and return immediately with a job id, rough ETA, and status polling guidance. Auto quality keeps playblast/preview/review jobs low-res unless quality/resolution is specified.",
        "mutates_scene": False,
        "has_side_effects": True,
        "permissions": ["scene:read", "files:write", "process:start"],
        "supports_headless": True,
        "returns_background_job": True,
        "duration_hint": "Returns quickly, then the background render may run from seconds to hours. Use the returned estimated_duration and poll_after_seconds.",
        "timeout_recovery": {
            "recoverable": True,
            "poll_after_seconds": 5,
            "status_tool": "blender_bridge_status",
            "resource_tool": "get_visual_evidence_resources",
            "message": "If startup times out, check bridge status and latest render-job metadata before starting another job.",
        },
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
                "quality": {"type": "string", "enum": ["auto", "preview", "low", "standard", "medium", "high", "hd", "final", "full", "production", "1080p"]},
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
    "set_rig_custom_property_keyframes": {
        "description": "Key existing scalar rig custom properties such as IK/FK or space switches with preview rollback",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "get_rig_pose_library_details": {
        "description": "Inspect rig-compatible pose-library/action candidates, markers, matched bones, channels, and suggested application calls",
        "mutates_scene": False,
    },
    "apply_rig_pose_from_action": {
        "description": "Apply/key a sampled pose from an existing rig action or pose-library marker with preview rollback",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "apply_rig_pose_marker": {
        "description": "Resolve and apply/key a named rig pose-library marker, optionally without requiring the source action name",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "apply_rig_action_clip": {
        "description": "Copy and assign an existing rig action clip to an armature with preview rollback",
        "mutates_scene": True,
        "requires_live_preview": True,
    },
    "offset_rig_limb_controls": {
        "description": "Apply keyed limb-control offsets and optional space-switch keys with preview rollback",
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
        "long_running": bool(raw.get("long_running", False)),
        "returns_background_job": bool(raw.get("returns_background_job", False)),
        "duration_hint": str(raw.get("duration_hint") or ""),
        "timeout_recovery": raw.get("timeout_recovery") if isinstance(raw.get("timeout_recovery"), dict) else {},
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
        "timeoutSeconds": int(contract["timeout_seconds"]),
        "longRunningHint": bool(contract.get("long_running", False)),
        "returnsBackgroundJob": bool(contract.get("returns_background_job", False)),
        "durationHint": str(contract.get("duration_hint") or ""),
        "timeoutRecovery": dict(contract.get("timeout_recovery") or {}),
        "readOnlyHint": not side_effects,
        "destructiveHint": destructive,
        "idempotentHint": False,
        "openWorldHint": "network" in contract["permissions"],
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


def _schema_types(schema):
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return set(str(item) for item in schema_type)
    if isinstance(schema_type, str):
        return {schema_type}
    return set()


def _matches_json_type(value, schema_type):
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return True


def _integer_schema_value(schema, key):
    value = schema.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def validate_arguments(value, schema, path="$"):
    """Validate a value against the JSON Schema subset used by this project.

    Dependency-free and bpy-free so both the in-Blender bridge and the
    standalone stdio MCP server can enforce the same tool contract. Returns a
    list of human-readable error strings (empty when valid).
    """

    if not isinstance(schema, dict):
        return []
    errors = []
    schema_types = _schema_types(schema)
    if schema_types and not any(_matches_json_type(value, item) for item in schema_types):
        errors.append(f"{path}: expected {', '.join(sorted(schema_types))}")
        return errors
    if "enum" in schema and value not in schema.get("enum", []):
        errors.append(f"{path}: expected one of {schema.get('enum')}")
        return errors
    if isinstance(value, dict):
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: required property is missing")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key}: additional property is not allowed")
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(validate_arguments(value[key], child_schema, f"{path}.{key}"))
    if isinstance(value, list):
        min_items = _integer_schema_value(schema, "minItems")
        max_items = _integer_schema_value(schema, "maxItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} item(s)")
        if max_items is not None and len(value) > max_items:
            errors.append(f"{path}: expected at most {max_items} item(s)")
        if isinstance(schema.get("items"), dict):
            item_schema = schema["items"]
            for index, item in enumerate(value):
                errors.extend(validate_arguments(item, item_schema, f"{path}[{index}]"))
    if isinstance(value, str):
        min_length = _integer_schema_value(schema, "minLength")
        max_length = _integer_schema_value(schema, "maxLength")
        if min_length is not None and len(value) < min_length:
            errors.append(f"{path}: expected at least {min_length} character(s)")
        if max_length is not None and len(value) > max_length:
            errors.append(f"{path}: expected at most {max_length} character(s)")
    return errors


def register():
    pass


def unregister():
    pass
