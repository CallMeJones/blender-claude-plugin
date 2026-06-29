# Context And Docs Engine

## Goal

External agents should understand the active Blender environment well enough to make simple changes confidently and complex changes carefully. The add-on gives agents a layered world model, version-aware documentation, and safe editing tools before they write raw Blender Python.

## Mental Model For Agents

Agents should treat Blender as a live graph of data-blocks, not just a viewport image:

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
- `inspect_simulation_bake(object_names, frame_start, frame_end, sample_count, max_objects)`
- `stage_persistent_simulation_bake(object_names, frame_start, frame_end, clear_existing, include_scene_rigid_body_world)`
- `get_collection_layer_details(max_depth)`
- `get_render_camera_compositor_details()`
- `search_blender_docs(query)`

This lets external agents ask for more when needed without dumping the whole file into every request.

### Deep World Model

`world_model.py` adds compact read-only coverage for Blender systems that are expensive or risky to send wholesale:

- geometry-node modifiers and node groups;
- shader node trees and material drivers;
- armatures, bones, pose constraints, object constraints, and drivers;
- mesh shape keys;
- curve and text object data;
- rigid-body, particle, point-cache, evaluated simulation samples, and simulation bake state;
- collection hierarchy and view layers;
- render, camera, world, and compositor settings.

The prompt planner includes only a small `world_model_summary` by default and points external agents to the specific deep tools when a task needs details. This keeps token use low while giving the agent enough local reach to inspect complex scenes before drafting Python.

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

Current implementation: `docs_index.py` seeds a local JSON cache with targeted snippets for transforms, materials, lights, cameras, constraints, timeline settings, keyframes, Blender 5.1 layered Actions, and extension manifests. It can also download Blender's official versioned Python API zip and official Manual HTML zip, safely extract them, parse HTML pages, and build compact `full_index.json` and `manual_index.json` files. Search results include citation refs, source breakdowns, searched-index reporting, and a `citation_report` string that can be copied into transcript/status output when docs influenced code.

The cache layout is:

```text
<docs_cache_dir>/
  blender_docs_5.1.json
  5.1/
    blender_python_reference_5_1.zip
    blender_manual_html.zip
    html/
    full_index.json
    manual_html/
    manual_index.json
```

The search tool returns only top matching snippets and URLs. It never exposes the whole docs cache to external clients.

## Context Budgeting

`context_planner.py` first builds a prompt-aware request bundle. It includes the current scene, selection, active object, visual metadata, and relevant material/animation summaries when the prompt needs them. It adds a `context_plan` field that tells external clients what was included or omitted, plus a rough `ceil(chars / 4)` token estimate shown in the sidebar.

`context_budget.py` then applies hard text-size guards before context is exposed to clients:

- context bundle JSON is compacted before use;
- `_attachments` are omitted from text context and exposed only through explicit resources or client-selected image handling;
- large strings/lists/deep structures are truncated;
- docs search returns at most a small set of snippets;
- tool results are capped before being returned through the bridge.

This keeps the local docs cache, screenshots, and large Blender scenes from killing the LLM request with oversized context.

`agent_tools.select_blender_tool_definitions()` also applies a tool-schema budget. The full tool catalog remains available locally, but compact surfaces can expose a core inspection/docs set plus task-matched groups such as materials, animation, 2D/storyboard, procedural 3D, simulation setup, camera/render, geometry nodes, rigging, particles, curves/text, advanced creation, refinement, or vehicle tools.

### Docs-First Rule

Agents should call `search_blender_docs` before drafting scripts when:

- The task uses unfamiliar Blender APIs.
- The task involves animation data, drivers, geometry nodes, node trees, armatures, or modal/context-sensitive operators.
- The proposed script uses `bpy.ops`.
- The user asks for a workflow that may differ across Blender versions.

## Safe Editing Layer

Simple changes should go through allowlisted helper tools instead of arbitrary generated scripts.

Initial helpers:

- `list_scene_objects(type_filter, max_objects)`
- `capture_viewport(max_bytes)`: captures the interactive viewport/window when UI is available and returns metadata plus the local PNG artifact path. External clients can use the Viewport context toggle or explicit MCP image resources when visual evidence is needed.
- `capture_object_inspection_renders(object_names, views, frame, resolution_x, resolution_y, lens, distance_factor, camera_name, note)`: renders bounded diagnostic close-up PNGs of named objects, such as underside or side views, and returns metadata plus MCP image resource URIs.
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
- `get_animation_scene_context(object_names, selected_only, max_objects)`
- `create_animation_brief(prompt, subject_names, frame_start, frame_end)`
- `create_timing_chart(prompt, brief, subject_names, frame_start, frame_end, beats)`
- `plan_animation_workflow(prompt, subject_names, frame_start, frame_end, mode, brief, timing_chart, playblast, findings)`
- `run_animation_workflow(prompt, subject_names, frame_start, frame_end, mode, brief, timing_chart, playblast, findings, apply_generation, run_review, capture_playblast, apply_repairs)`
- `run_animation_task(prompt)`
- `create_progressive_bounce_animation(object_name, frame_start, frame_end, axis, distance, cycles, scale_end_factor, interpolation)`
- `block_key_poses(object_names, poses, selected_only, interpolation)`
- `add_breakdown_pose(object_names, frame, previous_frame, next_frame, factor, location, rotation, scale, paths)`
- `set_pose_hold(object_names, frame, hold_frames, paths)`
- `set_rig_pose_hold(armature_name, bone_names, frame, hold_frames, paths)`
- `set_rig_custom_property_keyframes(armature_name, property_targets, frame, hold_frames)`
- `create_motion_arc(object_names, frame_start, frame_end, sample_step)`
- `analyze_motion_arcs(object_names, frame_start, frame_end, max_samples)`
- `analyze_fcurve_spacing(object_names, paths)`
- `analyze_pose_clarity(object_names)`
- `analyze_animation_principles(object_names, brief, timing_chart, frame_start, frame_end)`
- `sample_animation_state(object_names, frame_start, frame_end, sample_step)`
- `analyze_contact_sliding(object_names, frame_start, frame_end, contact_z, contact_tolerance, sliding_tolerance)`
- `analyze_collision_penetration(object_names, frame_start, frame_end, tolerance)`
- `analyze_center_of_mass(object_names, support_object_names, frame_start, frame_end, support_margin, contact_tolerance)`
- `analyze_camera_framing(object_names, camera_name, frame_start, frame_end, margin)`
- `analyze_motion_physics(object_names, frame_start, frame_end, sample_step, max_speed, max_acceleration)`
- `compare_animation_to_brief(brief, prompt, subject_names, frame_start, frame_end)`
- `review_playblast_against_brief(playblast, brief, prompt)`
- `review_inspection_renders_against_brief(inspection_render, brief, prompt)`
- `repair_animation_from_findings(findings, brief)`
- `run_animation_repair_loop(playblast, brief, prompt, findings, repair_operations, max_iterations, max_operations)`
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
- `plan_advanced_scene_workflow(prompt, domains, target_objects)`
- `get_2d_animation_details(max_items)`
- `create_storyboard_panels(panel_count, columns, panel_width, panel_height, frame_start, frame_step)`
- `create_2d_cutout_layer(name, location, size, frame_start, frame_end, location_end, text)`
- `apply_procedural_array_stack(object_names, count, relative_offset, bevel_width, bevel_segments)`
- `create_procedural_object_kit(template, name_prefix, location, count, radius, spacing, height)`
- `create_camera_dolly_animation(camera_name, target_name, frame_start, frame_end, start_location, end_location, lens_start, lens_end)`
- `create_directed_animation_shot(shot_type, object_names, frame_start, frame_end, travel_axis, travel_distance)`
- `add_cloth_simulation_to_selected(object_names, quality, mass)`
- `shade_smooth_selected(add_weighted_normals)`
- `add_bevel_and_subsurf(bevel_width, bevel_segments, subsurf_levels)`
- `create_wheel_assembly(name, location, radius, tire_thickness, axis)`
- `add_panel_seams(target_name, bevel_depth)`
- `add_window_materials(target_name, material_name, color, create_panels)`
- `apply_vehicle_refinement_template(target_name, detail_level)`
- `apply_product_refinement_template(target_name, style, include_stage, include_callouts, include_turntable)`
- `apply_character_refinement_template(target_name, character_style, detail_level, create_guides)`
- `create_studio_product_stage(target_name, stage_name, floor, backdrop, lighting, camera)`
- `add_dimension_callouts(target_name, unit_label, include_width, include_depth, include_height)`
- `apply_lighting_preset(target_name, preset, rig_name)`
- `create_material_palette(palette_name, palette, create_swatches, assign_to_selected)`
- `create_product_turntable_setup(target_name, frame_start, frame_end, revolutions, setup_name)`
- `organize_scene_for_production(collection_prefix, selected_only)`

Helpers should validate inputs and return structured results. External agents can still propose Python for advanced operations, but the default path for common edits should be helper-first.

`get_animation_scene_context` is the first Milestone 7D routing layer. It does not replace deep detail tools; it summarizes likely animation ownership so external agents can choose the right next inspection before editing. It flags rig-driven objects, likely rig control bones, shape-key deformation targets, material or shader animation, object/data/action owners, action slots and keyed channel ranges when available, pose-marker/pose-library candidates, constraints, drivers, NLA tracks, simulation/rigid-body hints, likely contact surfaces, and camera readiness, then returns subject routing with animation-owner recommendations and routing confidence plus recommended detail tools such as `get_rigging_details`, `get_shape_key_details`, `get_animation_details`, `get_simulation_details`, `inspect_simulation_bake`, and `get_render_camera_compositor_details`.

`inspect_simulation_bake` is the safe simulation inspection path before an agent reaches for custom Python. It samples evaluated rigid-body/particle/simulation state across a bounded frame range, restores the original scene frame, returns object center/bounds samples, includes `get_simulation_details` cache metadata, and reports that persistent point-cache baking was not performed. This gives the client concrete bake/cache evidence without mutating persistent simulation caches or writing disk caches behind the user's back. `stage_persistent_simulation_bake` is the explicit persistent-bake path: it stages a fixed-template scene-wide `bpy.ops.ptcache.bake_all(bake=True)` script for Blender-side approval/trust and does not ask clients to invent bake Python. Requested object names limit inspection and cache-range preparation, but Blender's bake-all operator remains scene-wide. `analyze_center_of_mass` uses convex-hull support footprints from support objects' world-space bounds when available, and character subjects can use weighted child-mesh bounds for a better articulated center-of-mass proxy, so rotated supports and rigged body-part layouts do not get reduced to a single misleading object origin or axis-aligned box.

The advanced helpers are intentionally bounded. They create useful starter states and simple edits without exposing arbitrary node graph, rig, compositor, or persistent simulation mutation. `plan_advanced_scene_workflow` is the broad routing entry point for advanced 3D, 2D/storyboard, advanced animation, simulation setup, compositor/render, and script-heavy requests. 2D helpers currently cover storyboard/animatic panels and cutout layers; procedural helpers cover reversible object-kit templates including kitbash, radial/scatter/product, mechanical-joint, and control-panel generators plus non-destructive modifier stacks; directed-shot helpers cover common camera/reveal/path/turntable/crane/truck shots. Compositor support is inspection/planning-first until node-tree rollback exists. When an external agent needs a custom geometry-node network, production rig, compositor graph, destructive mesh operation, import/export, custom Grease Pencil stroke editing, or complex simulation setup, it should draft approved Python after inspecting context and docs.
Reusable refinement templates should stay bounded and composable. Vehicle, product, and character kits inspect bounds, add tasteful primitive/curve/material details, preserve preview rollback, and escalate to approved Python for topology-heavy work.

## Script Drafting Protocol

For generated Python, external agents should produce:

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

When live preview is enabled, external agents should know:

- Which helper tools are allowed to mutate the scene immediately.
- Whether the current preview transaction is pending, committed, reverted, or failed.
- Which objects, materials, actions, cameras, and lights changed in the transaction.
- Whether animation edits should jump to changed frames or preserve the current frame.

External agents should prefer immediate helper calls for low-risk visible changes and reserve generated Python for operations helpers cannot express.

## Viewport Image Context

When the `Viewport` toggle is enabled, `viewport_capture.py` tries to capture a PNG from the active Blender UI area and expose it as bounded visual evidence for external clients. If the capture exceeds the configured byte budget, the add-on downscales and re-saves the PNG with Blender's image API before exposing it. The context bundle keeps only metadata such as capture method, local path, media type, dimensions, resize status, byte size, project/session ids, and MCP capture resource URIs in transcript-visible text.

By default, saved `.blend` files store viewport captures beside the project in `.claude_blender/captures/<session_id>`. Unsaved or unwritable projects fall back to Blender's extension user-data directory, with `~/.claude_blender/captures/<project_id>/<session_id>` kept only as a non-extension runtime fallback. A custom capture cache preference acts as a custom base directory with the same project/session partitioning. The MCP bridge exposes `blender://captures/latest`, `blender://captures/latest/metadata`, and exact `blender://captures/{capture_id}` resources. Treat project-local captures as generated runtime artifacts; ignore `.claude_blender/captures/` in source control unless a project intentionally keeps visual QA evidence.

If Blender is running headless or the screenshot operator fails, the visual context records `requested: true` and `available: false` without blocking the prompt.

`capture_animation_playblast` uses the same storage model to capture sampled viewport PNG frames across an animation range. It defaults to low-resolution preview evidence capped at 640x360 so animation review stays quick; pass `quality`, `max_width`, or `max_height` only when higher fidelity is needed. It writes a playblast metadata manifest with frame resource URIs such as `blender://playblasts/{playblast_id}/frames/{frame}`. Before each screenshot it advances the scene frame, updates the view layer, and flushes the viewport draw path where Blender allows it; each frame record includes `captured_scene_frame` so clients can sanity-check sampled frame evidence. This is the first visual QA path for animation review: agents can compare visible sampled poses against the brief, timing, spacing, staging, arcs, and contact expectations. `review_playblast_against_brief` turns that metadata into frame-level visual evidence, coverage findings, compact pixel digests, visual-subject interpretation, frame-to-frame motion deltas, conservative visual repeated-action count evidence, and repair operations. The visual interpretation summarizes foreground coverage, normalized subject bounds, cropped/tiny/no-subject reads, and detail strength so clients can ask for targeted recapture instead of guessing from filenames alone. Playblast-derived repair operations now carry `target_frames` and `target_frame_range` metadata so an MCP client can see which sampled frames or uncovered frame spans motivated the repair. `run_animation_task` is the compact one-input MCP route for common animation prompts; internally it calls the Milestone 7 planner/runner path. `run_animation_workflow` wraps the same path with more controls: plan the brief/scene/timing workflow, execute allowlisted helper generation such as bounce/turntable/reveal/pulse/progressive bounce, run structured evaluator review, optionally capture playblast evidence, and optionally hand repair operations to `run_animation_repair_loop`. Review-only prompts route to the evaluator path even when the brief is too ambiguous for generation. `create_progressive_bounce_animation` covers prompts where the subject should bounce repeatedly while shrinking over the shot. `run_animation_repair_loop` can then execute a bounded set of those operations through safe helper tools, request a fresh playblast after mutating repairs, and re-run the review while leaving helper changes in the existing preview/commit workflow. Rig-driven pose repair follows an inspect-then-edit path: `repair_animation_from_findings` can propose `get_rigging_details`, `set_rig_custom_property_keyframes`, and `set_rig_pose_hold` when a finding references rig controls, pose clarity, contact, support, or weight. The rig repair planner scores control candidates with IK/FK/pole, constraint-target, limb-region, and support/contact hints, returns rig-targeting metadata, detects IK/FK and space-switch custom properties, surfaces pose-library/action candidates, keys existing scalar switch properties through preview-safe helpers, and avoids generic object-transform holds when rig controls are the better edit owner. Capture requires an interactive Blender window and fails soft in background mode.

`capture_object_inspection_renders` is the focused render-evidence path for object details that a viewport screenshot or playblast may not show well. It creates a temporary camera, frames each named object from bounded diagnostic views such as `front_below`, `underside`, and `side`, writes PNGs under the same project/session capture cache, restores the original frame/camera/render settings, removes the temporary camera, and exposes images through resources such as `blender://inspection-renders/{render_id}/images/{image_id}`. Use it when a model needs visual inspection before repair, for example landing gear, undersides, occluded parts, silhouette defects, or small material/modeling issues. `review_inspection_renders_against_brief` turns that metadata into visual-detail findings, checks missing/weak required views, includes the same visual-subject interpretation summary, and can produce `capture_object_inspection_renders` repair operations for targeted recapture.

Long final-quality renders use `start_render_job` instead of approval-gated Python or blocking still/render helpers. The tool saves a temporary `.blend` copy, launches a background Blender process, and returns a `job_id`, rough estimate, and poll interval before the MCP request can time out. `quality=auto` keeps final renders at final-quality defaults, but playblast/preview/review/draft job names or notes default to a low-resolution preview profile unless the caller passes `quality`, `resolution_x`, `resolution_y`, or `samples`. `get_render_job_status` reports status, elapsed time, frame rate, estimated remaining time, frame counts, progress, output paths, log tails, and exact frame resource URIs under `blender://render-jobs/{job_id}/...`; `cancel_render_job` stops tracked jobs. For PNG sequences, `assemble_render_job_video` starts a background MP4 assembly pass and `validate_render_job_output` checks frame completeness, MP4 presence/size, and useful resource URIs before the client reports success. This is the intended route for 1080p/4K animation renders, frame sequences, MP4 quality checks, render previews, or high-sample playblasts. Large `render_scene_thumbnail` requests are guarded and should be rerouted to `start_render_job` unless the client explicitly sets `allow_blocking_render`.

Production-helper visual QA has a separate background-safe path: `tests/smoke_refinement_visual_qa.py` renders tiny PNG stills for the product and character refinement kits and checks that the output is not blank. Set `CLAUDE_BLENDER_VISUAL_QA_DIR` to keep those render artifacts and their manifest for manual inspection.

## Guarded Execution

The runner should:

- Compile the script before showing it as runnable.
- Reject blocked imports and dangerous calls.
- Warn on deletes, file writes, network/process usage, broad scene edits, mode changes, and long loops.
- Push an undo step and optionally save a checkpoint.
- Execute in Blender's main thread.
- Capture output and errors.
- Return execution results to the external client so it can repair failures.

## What Makes Scripting Feel Easy

The user should be able to ask naturally:

- "Make this object chrome and add a warm rim light."
- "Animate the selected object bouncing from frame 1 to 80."
- "Create a camera orbit around this product."
- "Add labels pointing to these parts."

Agents should inspect the scene, retrieve docs if needed, choose a helper or script, and present a clear change plan without Blender hosting a provider chat loop.
