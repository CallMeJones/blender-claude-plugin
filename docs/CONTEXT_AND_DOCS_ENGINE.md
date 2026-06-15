# Context And Docs Engine

## Goal

Claude should understand the active Blender environment well enough to make simple changes confidently and complex changes carefully. The add-on should give Claude a layered world model, version-aware documentation, and safe editing tools before asking it to write raw Blender Python.

## Mental Model For Claude

Claude should treat Blender as a live graph of data-blocks, not just a viewport image:

- Scenes contain collections, objects, cameras, lights, world settings, render settings, and timeline settings.
- Objects have stable names during a session, object types, transforms, dimensions, data-blocks, modifiers, constraints, materials, custom properties, and animation data.
- Mesh, curve, armature, camera, light, text, and empty objects need different APIs.
- Animation may live on object transforms, material node values, camera settings, constraint influences, shape keys, drivers, and actions.
- Operators can require context/mode, while direct data API changes are often more predictable.

The assistant should prefer direct data API changes for generated scripts unless an operator is clearly safer or required.

## Context Bundle

Each user request should build a request-specific bundle:

```text
context_bundle
  context_plan
  environment
  scene_summary
  selection_summary
  active_object_detail
  relevant_object_details
  animation_summary
  material_summary
  render_and_camera_summary
  world_model_summary
  visual_context
  available_tools
  privacy_redactions
  _attachments (API-only, stripped from transcripts)
```

### Environment

- Blender version and Python version.
- Active mode: object, edit mesh, pose, sculpt, etc.
- Active workspace and area type when available.
- Platform and extension permissions.
- Render engine and color management.

### Scene Summary

- Scene name, units, frame range, current frame, FPS.
- Collection tree with counts by object type.
- Cameras, lights, world settings, render resolution.
- Total object count and selected object count.

### Selection Summary

- Active object and selected objects.
- Object type, transform, dimensions, bounds.
- Modifier, constraint, material, and animation presence.
- Library/link status and locked/hidden/selectable state.

### Deeper Details

Use follow-up tools for detailed data:

- `inspect_scene(include_visual)`
- `list_scene_objects(type_filter, max_objects)`
- `get_object_details(object_names, selected_only, max_objects)`
- `get_material_node_details(material_names, selected_only, max_materials, max_nodes)`
- `get_animation_details(object_names, action_names, max_actions, max_keyframes_per_curve)`
- `get_geometry_nodes_details(object_names, max_objects)`
- `get_shader_nodes_details(material_names, selected_only, max_materials)`
- `get_rigging_details(object_names, max_objects)`
- `get_shape_key_details(object_names, max_objects)`
- `get_curve_text_details(object_names, max_objects)`
- `get_simulation_details(object_names, max_objects)`
- `get_collection_layer_details(max_depth)`
- `get_render_camera_compositor_details()`
- `search_blender_docs(query)`

This lets Claude ask for more when needed without dumping the whole file into every request.

### Deep World Model

`world_model.py` adds compact read-only coverage for Blender systems that are expensive or risky to send wholesale:

- geometry-node modifiers and node groups;
- shader node trees and material drivers;
- armatures, bones, pose constraints, object constraints, and drivers;
- mesh shape keys;
- curve and text object data;
- particle/simulation modifiers;
- collection hierarchy and view layers;
- render, camera, world, and compositor settings.

The prompt planner includes only a small `world_model_summary` by default and points Claude to the specific deep tools when a task needs details. This keeps token use low while giving the agent enough local reach to inspect complex scenes before drafting Python.

## Docs Engine

The docs engine should be version-aware and official-source-first.

### Sources

- Blender Python API: `docs.blender.org/api/<version>/`
- Blender manual extension docs: `docs.blender.org/manual/<version>/`
- Blender source/developer docs only when API docs are insufficient.

### Query Flow

1. Detect the local Blender version.
2. Search the local docs cache first.
3. Convert likely API symbols into targeted docs queries.
4. Search the full local Python API index when it exists.
5. Return concise cached snippets and official Blender source URLs.
6. Return official docs search/index URLs when the local cache has no targeted match.

Current implementation: `docs_index.py` seeds a local JSON cache with targeted snippets for transforms, materials, lights, cameras, constraints, timeline settings, keyframes, Blender 5.1 layered Actions, and extension manifests. It can also download Blender's official versioned Python API zip, safely extract it, parse HTML pages, and build a compact `full_index.json`. Search results include compact citation records and a `citation_report` string that can be copied into transcript/status output when docs influenced code.

The cache layout is:

```text
<docs_cache_dir>/
  blender_docs_5.1.json
  5.1/
    blender_python_reference_5_1.zip
    html/
    full_index.json
```

The search tool returns only top matching snippets and URLs. It never sends the whole docs cache to Claude.

## Context Budgeting

`context_planner.py` first builds a prompt-aware request bundle. It includes the current scene, selection, active object, visual metadata, agent memory, and relevant material/animation summaries when the prompt needs them. It adds a `context_plan` field that tells Claude what was included or omitted, plus a rough `ceil(chars / 4)` token estimate shown in the sidebar.

`context_budget.py` then applies hard text-size guards before API calls:

- context bundle JSON is compacted before `initial_messages()`;
- `_attachments` are omitted from text context and sent only as image blocks;
- large strings/lists/deep structures are truncated;
- docs search returns at most a small set of snippets;
- tool results are capped before being sent back into the Claude tool loop.

This keeps the local docs cache, project memory, screenshots, and large Blender scenes from killing the LLM request with oversized context.

`anthropic_client.select_blender_tool_definitions()` also applies a tool-schema budget. The full tool catalog remains available locally, but each request sends only a core inspection/docs set plus task-matched groups such as materials, animation, camera/render, geometry nodes, rigging, particles, curves/text, advanced creation, refinement, or vehicle tools. The agent loop writes a compact `tool_selection` block into the request context so Claude knows which tools were exposed and roughly how many schema tokens they cost.

### Docs-First Rule

Claude should call `search_blender_docs` before drafting scripts when:

- The task uses unfamiliar Blender APIs.
- The task involves animation data, drivers, geometry nodes, node trees, armatures, or modal/context-sensitive operators.
- The proposed script uses `bpy.ops`.
- The user asks for a workflow that may differ across Blender versions.

## Safe Editing Layer

Simple changes should go through allowlisted helper tools instead of arbitrary generated scripts.

Initial helpers:

- `list_scene_objects(type_filter, max_objects)`
- `capture_viewport(max_bytes)`: captures the interactive viewport/window when UI is available and returns metadata plus the local PNG artifact path. Normal Claude visual prompts should still use the Viewport context toggle, which can attach the image block directly.
- `select_objects(object_names, active_object_name, extend)`
- `set_current_frame(frame)`
- `create_primitive(primitive_type, name, location, rotation, scale)`
- `create_empty(name, location, rotation, scale, empty_display_type)`
- `set_object_visibility(object_names, hide_viewport, hide_render, hide_select)`
- `set_object_display(object_names, display_type, show_name, show_wire, show_in_front, color)`
- `set_selected_location_delta(delta)`
- `set_selected_transform(location, rotation, scale)`
- `assign_material_to_selected(name, color)`
- `add_light(light_type, name, location, energy, color)`
- `add_camera(name, location, rotation, lens)`
- `set_scene_frame_range(frame_start, frame_end, current_frame, fps)`
- `set_active_camera(camera_name)`
- `animate_selected_transform(frame_start, frame_end, location_start, location_end, rotation_start, rotation_end, scale_start, scale_end)`
- `create_camera_orbit(target_name, frame_start, frame_end, radius, height, name)`
- `add_modifier(object_name, type, settings)`
- `create_shader_material(name, base_color, metallic, roughness, alpha, emission_color, emission_strength)`
- `add_geometry_nodes_modifier(name, node_group_name)`
- `create_shape_key(object_name, key_name, value)`
- `animate_shape_key(object_name, key_name, frame_start, frame_end, value_start, value_end)`
- `create_text_object(name, body, location, rotation, scale, size)`
- `create_curve_path(name, points, bevel_depth, cyclic)`
- `add_particle_system_to_selected(name, count, frame_start, frame_end, lifetime)`
- `create_basic_armature(name, location, rotation)`
- `add_copy_transform_constraint(target_name, constraint_type)`
- `set_render_settings(engine, resolution, fps, frame_start, frame_end, film_transparent)`
- `set_camera_settings(camera_name, lens, dof_enabled, focus_object_name, aperture_fstop)`
- `set_world_background(color)`
- `shade_smooth_selected(add_weighted_normals)`
- `add_bevel_and_subsurf(bevel_width, bevel_segments, subsurf_levels)`
- `create_wheel_assembly(name, location, radius, tire_thickness, axis)`
- `add_panel_seams(target_name, bevel_depth)`
- `add_window_materials(target_name, material_name, color, create_panels)`
- `apply_vehicle_refinement_template(target_name, detail_level)`
- `create_studio_product_stage(target_name, stage_name, floor, backdrop, lighting, camera)`
- `add_dimension_callouts(target_name, unit_label, include_width, include_depth, include_height)`
- `apply_lighting_preset(target_name, preset, rig_name)`
- `create_material_palette(palette_name, palette, create_swatches, assign_to_selected)`
- `create_product_turntable_setup(target_name, frame_start, frame_end, revolutions, setup_name)`
- `organize_scene_for_production(collection_prefix, selected_only)`

Helpers should validate inputs and return structured results. Claude can still propose Python for advanced operations, but the default path for common edits should be helper-first.

The advanced helpers are intentionally bounded. They create useful starter states and simple edits without exposing arbitrary node graph, rig, or simulation mutation. When Claude needs a custom geometry-node network, production rig, compositor graph, destructive mesh operation, import/export, or complex simulation setup, it should draft approved Python after inspecting context and docs.
Reusable refinement templates should stay bounded and composable. The first template is vehicle-focused; product and character kits should follow the same pattern: inspect bounds, add tasteful primitive/curve/material details, preserve preview rollback, and escalate to approved Python for topology-heavy work.

## Script Drafting Protocol

For generated Python, Claude should produce:

```text
intent
target_objects
expected_changes
risk_level
docs_used
script
undo_notes
```

The add-on should show these fields before execution. The script runner should parse and check the code before allowing approval.

## Live Preview Context

When live preview is enabled, Claude should know:

- Which helper tools are allowed to mutate the scene immediately.
- Whether the current preview transaction is pending, committed, reverted, or failed.
- Which objects, materials, actions, cameras, and lights changed in the transaction.
- Whether animation edits should jump to changed frames or preserve the current frame.

Claude should prefer immediate helper calls for low-risk visible changes and reserve generated Python for operations helpers cannot express.

## Viewport Image Context

When the `Viewport` toggle is enabled, `viewport_capture.py` tries to capture a PNG from the active Blender UI area and attach it to the Anthropic request as an image block. If the capture exceeds the configured byte budget, the add-on downscales and re-saves the PNG with Blender's image API before attaching it. The context bundle keeps only metadata such as capture method, local path, media type, dimensions, resize status, byte size, project/session ids, and MCP capture resource URIs in transcript-visible text.

By default, saved `.blend` files store viewport captures beside the project in `.claude_blender/captures/<session_id>`. Unsaved or unwritable projects fall back to `~/.claude_blender/captures/<project_id>/<session_id>`, and a custom capture cache preference acts as a custom base directory with the same project/session partitioning. The MCP bridge exposes `blender://captures/latest`, `blender://captures/latest/metadata`, and exact `blender://captures/{capture_id}` resources. Treat project-local captures as generated runtime artifacts; ignore `.claude_blender/captures/` in source control unless a project intentionally keeps visual QA evidence.

If Blender is running headless or the screenshot operator fails, the visual context records `requested: true` and `available: false` without blocking the prompt.

## Guarded Execution

The runner should:

- Compile the script before showing it as runnable.
- Reject blocked imports and dangerous calls.
- Warn on deletes, file writes, network/process usage, broad scene edits, mode changes, and long loops.
- Push an undo step and optionally save a checkpoint.
- Execute in Blender's main thread.
- Capture output and errors.
- Return execution results to Claude so it can repair failures.

## What Makes Scripting Feel Easy

The user should be able to ask naturally:

- "Make this object chrome and add a warm rim light."
- "Animate the selected object bouncing from frame 1 to 80."
- "Create a camera orbit around this product."
- "Add labels pointing to these parts."

Claude should not need to ask the user for API details. It should inspect the scene, retrieve docs if needed, choose a helper or script, and present a clear change plan.
