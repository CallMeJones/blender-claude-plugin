# Project Plan

## Working Name

Blender Agent Bridge

## North Star

Make Blender Agent Bridge the safe, production-shaped bridge between Blender and external AI agents. Blender should provide structured scene inspection, viewport/render/playblast evidence, Blender Python staging, documentation lookup, safe editing helpers, preview rollback, approvals, checkpoints, and MCP resources. External clients should host the model/provider and decide what to send to their own LLMs.

## Evidence From Current Docs

- Modern MCP-capable agent clients support structured tool calls where the client asks Blender Agent Bridge to execute bounded operations and then consumes structured tool results.
- Modern multimodal agent clients can use image resources for viewport screenshots, preview renders, and playblast frames when the bridge exposes them.
- External client hosts can decide whether to upload, cache, or retain visual resources; Blender Agent Bridge should expose resources and metadata without owning provider retention policy.
- Prompt caching can reduce cost and latency for stable system prompts, tool definitions, and possibly documentation excerpts.
- Blender 4.2+ extensions use `blender_manifest.toml`, can bundle Python wheels, and must declare resource permissions such as network and files access.
- Blender Python exposes panels, operators, add-on preferences, scene data, object data, animation data, and render/viewport operations through `bpy`.

## MVP Scope

The first milestone should be useful but controlled:

- 3D View sidebar panel for bridge status, MCP config, context capture, script approvals, trust controls, preview commit/revert, docs status, and diagnostics.
- Add-on preferences for bridge settings, local paths, privacy defaults, and execution mode.
- No in-add-on LLM provider transport; external MCP clients host Anthropic/OpenAI/Gemini/etc. connections.
- Scene summary generation for selected objects and overall scene state.
- Layered context bundles that describe Blender version, mode, scene graph, selection, render settings, and animation state before external agents choose helpers or scripts.
- Optional viewport screenshot exposed as local metadata/resources.
- Live preview mode for approved low-risk helper changes, with immediate viewport/timeline redraw and revert/commit controls.
- Script proposal flow where external agents draft Blender Python through `draft_script`, but the user approves before execution unless session script trust is active.
- Undo/checkpoint support before running generated scripts.
- Version-aware docs search tool pointed at official Blender Python docs.
- Simple editing helpers/templates for common object, material, camera, light, and keyframe changes.
- Optional localhost bridge plus stdio MCP server so external agents can inspect resources and call Blender tools.

## Non-Goals For MVP

- Fully autonomous multi-step scene editing without confirmation.
- Perfect Python sandboxing. Python sandboxing inside Blender should be treated as unsafe by default.
- Marketplace-ready polish.
- Full mesh/vertex export for large scenes.
- Real-time viewport control or direct mouse/keyboard computer-use automation.

## Core User Flows

1. Ask About Scene

User asks, "What is in this scene and how can I improve the lighting?" An external agent reads a structured scene digest plus optional screenshot resources and returns analysis and suggestions.

2. Make A Small Change

User asks, "Add a warm key light and a cool rim light." An external agent uses safe helper tools when possible, or stages a script for approval when helper tools are not expressive enough. The add-on saves an undo point/checkpoint before risky execution.

3. Create An Object

User asks, "Make a stylized low-poly spaceship from primitives." An external agent inspects units, selection, and collections, then uses bounded creation helpers or stages approved Python. The user can undo or restore checkpointed work.

4. Build An Animation

User asks, "Animate the camera orbiting this product over 120 frames." An external agent reads selected object bounds and timeline settings, then uses camera/path/keyframe helpers before considering approved Python.

5. Use Blender Docs

User asks for a geometry nodes or modifier workflow. The external agent calls `search_blender_docs` for relevant API references before staging code.

6. Make Safe Scripted Changes

User asks for a change. The external agent first inspects context, retrieves docs for unfamiliar APIs, drafts a change plan, then uses either safe helper tools or a proposed script. The add-on checks the proposal, shows the expected changes, saves recovery state, and runs only after approval or active script trust.

7. See Changes Immediately

User asks, "Make this object red and animate it bouncing." The external agent uses safe helper calls for material and keyframes. The add-on applies each approved helper action to the live scene, updates the viewport/timeline, and keeps a visible preview transaction that can be committed or reverted.

8. Work Progressively Like An Agent

User asks a follow-up such as, "now add the lighting pass." The external agent reads the current scene context plus compact `Blender Agent Bridge Memory`, so it can continue the same scene/object/animation goal while treating the open Blender scene as the source of truth.

9. Connect From An External Agent

User starts the `External Bridge` in Blender and copies the MCP config into a compatible client. The external agent lists Blender tools/resources, reads scene context, and calls the same bounded helpers/scripts through Blender instead of importing `bpy` directly.

## Tool Surface

Expose external agents to narrow client tools rather than raw Python first:

- `inspect_scene`: returns scene, collections, selected objects, camera, lights, timeline, and render settings.
- `list_scene_objects`: returns object names, types, selection state, visibility, collections, and locations.
- `get_object_details`: returns deeper details for named objects.
- `get_animation_details`: returns actions, f-curves, keyframes, constraints, drivers, and timeline details.
- `create_animation_brief`: creates a structured animation prompt contract.
- `create_timing_chart`: creates an animator-style timing and blocking chart.
- `block_key_poses`: applies key poses from a chart through reversible preview.
- `add_breakdown_pose`: inserts an in-between pose between two keyed poses.
- `set_pose_hold`: repeats keyed values to create a hold.
- `create_motion_arc`: creates a sampled in-scene motion arc guide.
- `sample_animation_state`: samples object transforms across frames for objective review.
- `analyze_motion_arcs`: checks sampled motion paths and path length.
- `analyze_fcurve_spacing`: checks key spacing, interpolation, and mechanical value spacing.
- `analyze_pose_clarity`: checks keyed pose count, holds, and transform readability.
- `analyze_animation_principles`: checks keyed data against the prompt contract and animation principles.
- `analyze_contact_sliding`: detects object sliding while in contact with a plane.
- `analyze_collision_penetration`: detects sampled bounding-box intersections.
- `analyze_camera_framing`: checks whether animated subjects stay inside a camera-safe region.
- `compare_animation_to_brief`: compares sampled animation state against the prompt contract.
- `review_playblast_against_brief`: combines playblast metadata and current animation state review.
- `repair_animation_from_findings`: turns structured findings into targeted non-mutating repair suggestions.
- `get_material_node_details`: returns material slots, shader node summaries, and image texture references.
- `get_geometry_nodes_details`: returns geometry-node modifier and node-group summaries.
- `get_shader_nodes_details`: returns material shader-node summaries for selected or named materials.
- `get_rigging_details`: returns armatures, bones, pose constraints, object constraints, and drivers.
- `get_shape_key_details`: returns shape-key blocks, values, limits, and drivers.
- `get_curve_text_details`: returns curve/text object properties and spline/text summaries.
- `get_simulation_details`: returns rigid-body, particle, point-cache, and simulation bake summaries.
- `inspect_simulation_bake`: samples evaluated simulation state across a bounded frame range and reports cache/bake readiness without persistent cache mutation.
- `stage_persistent_simulation_bake`: stages a fixed-template scene-wide persistent point-cache bake script for explicit Blender-side approval or active script trust.
- `get_collection_layer_details`: returns collection tree, collection visibility, and view-layer summaries.
- `get_render_camera_compositor_details`: returns render settings, active camera, world settings, and compositor nodes.
- `capture_viewport`: captures the interactive viewport/window when available and returns metadata plus a local PNG artifact path.
- `search_blender_docs`: returns targeted snippets and links from official docs.
- `plan_scene_change`: creates a user-readable plan before code or tool execution.
- `select_objects`: selects named objects and optionally sets the active object.
- `set_current_frame`: sets the current playhead frame.
- `set_selected_location_delta`: moves selected objects by a relative offset.
- `set_selected_transform`: sets selected object location, rotation, and/or scale.
- `create_primitive`: creates bounded mesh primitives.
- `assign_material_to_selected`: creates or assigns a material to selected mesh objects.
- `assign_emission_material_to_selected`: creates a new emission material node setup for selected mesh objects.
- `create_collection`: creates or finds a scene collection.
- `link_selected_to_collection`: links selected objects to a named collection.
- `add_modifier_to_selected`: adds bounded BEVEL, SUBSURF, SOLIDIFY, or ARRAY modifiers to selected mesh objects.
- `create_shader_material`: creates or updates a Principled BSDF material and optionally assigns it to selected mesh objects.
- `add_geometry_nodes_modifier`: adds a valid passthrough Geometry Nodes modifier and starter node group.
- `create_shape_key`: creates or updates a mesh shape key value.
- `animate_shape_key`: keyframes a mesh shape key over a frame range.
- `create_text_object`: creates text objects with transform, alignment, size, and simple material.
- `create_curve_path`: creates 3D curve paths from points with optional bevel/material.
- `add_particle_system_to_selected`: adds bounded particle systems to selected mesh objects.
- `create_basic_armature`: creates a simple one-bone armature object.
- `add_copy_transform_constraint`: adds Copy Location/Rotation/Scale/Transforms constraints to selected objects.
- `set_render_settings`: sets render engine, resolution, FPS, frame range, and transparency.
- `set_camera_settings`: sets camera lens, sensor width, and depth-of-field settings.
- `set_world_background`: sets the scene world background color.
- `shade_smooth_selected`: smooths selected mesh polygons and can add weighted normals.
- `add_bevel_and_subsurf`: adds a bounded detail modifier stack to selected meshes.
- `create_wheel_assembly`: creates tire/rim wheel assemblies from primitives.
- `add_panel_seams`: adds simple dark curve seams around a mesh body's bounds.
- `add_window_materials`: creates/assigns blue glass and optional window panels.
- `apply_vehicle_refinement_template`: applies a bounded vehicle detail kit with smoothing, wheels, glass, seams, headlights, and taillights.
- `apply_product_refinement_template`: applies a bounded product presentation kit with material polish, smoothing, staging, callouts, and optional turntable setup.
- `apply_character_refinement_template`: applies a bounded character blockout/detail kit with body polish, head/neck/eyes, shoulder marker, and optional gesture guides.
- `create_studio_product_stage`: creates a bounded floor/backdrop/key-fill-rim-light/camera presentation setup around a target.
- `add_dimension_callouts`: adds width/depth/height curve and text callouts around a target's bounds.
- `apply_lighting_preset`: creates bounded product/gallery/dramatic area-light rigs around a target.
- `create_material_palette`: creates production palette materials and optional swatch cubes.
- `create_product_turntable_setup`: creates optional staging, target rotation, and orbit camera for product review.
- `organize_scene_for_production`: links objects into production collections without deleting original links.
- `add_track_to_constraint`: adds a Track To constraint from selected objects to a target.
- `add_light`: creates a light object.
- `add_camera`: creates a camera and makes it active.
- `set_scene_frame_range`: adjusts timeline range/current frame/FPS.
- `set_active_camera`: sets an existing camera object as the active scene camera.
- `animate_selected_transform`: creates simple transform keyframes for selected objects.
- `create_camera_orbit`: creates a keyframed camera orbit rig around a target object.
- `commit_preview`: accepts the current live preview changes.
- `revert_preview`: rolls back the current live preview changes.
- `draft_script`: stores proposed code without running it by default; auto-runs after static checks while an external script trust window is active.
- `run_approved_script`: only runs code after explicit user approval.
- `undo_last_action`: calls Blender undo for the last approved execution.
- `save_checkpoint`: saves a copy of the current `.blend` before risky work.
- `agent_memory`: compact running project context stored locally in `Blender Agent Bridge Memory`.

## Milestones

### Milestone 0: Project Skeleton

- Create Blender extension folder and manifest.
- Add a minimal panel, preferences, and operator.
- Confirm install and enable in Blender 4.2+ or current installed Blender.

Acceptance:

- Extension can be installed from disk.
- Sidebar panel appears in the 3D View.
- Preferences persist local configuration.

### Milestone 1: Scene Context And External Agent Grounding

- Implement context bundle generation.
- Implement scene, selection, object, material, render, and animation digests.
- Expose structured scene context to external clients through the bridge.
- Display bridge status, context summaries, and tool/script results in Blender UI.

Acceptance:

- External agents can answer questions about selected objects and scene settings from bridge context.
- Large scenes are summarized without sending full geometry by default.
- External agents can ask for deeper object/material/animation details through tools instead of guessing.

Status: Initial scene context, per-project agent memory, token-aware context planning, sidebar char/token estimates, and read-only detail retrieval tools are implemented.
Deep world-model inspection is now available for geometry nodes, shader nodes, rigging/constraints/drivers, shape keys, curves/text, simulations, collection/view-layer organization, render/camera settings, and compositor nodes.
The sidebar no longer hosts provider chat. It now focuses on bridge status, MCP config, script/action approvals, context capture, memory, docs, and diagnostics.

### Milestone 2: Screenshot/Vision Context

- Add viewport screenshot capture.
- Allow user to include current viewport image.
- Compress/resize images to stay within API limits.

Acceptance:

- External agents can comment on visible composition, object placement, materials, and framing when viewport resources are enabled.
- User can toggle screenshot inclusion per prompt.

Status: Viewport screenshot attachment is implemented with a user toggle, project/session-scoped capture storage, maximum byte limit, API-only image blocks, transcript-safe metadata, MCP capture resources for external clients, and explicit PNG downscaling/re-save when a capture exceeds the request byte budget. Initial animation playblast frame capture is now scaffolded as sampled viewport PNG resources for MCP clients. Broader visual QA and automated animation review remain later work.

### Milestone 3: Approved Script Execution

- Add script preview, approval, execution, logs, and undo.
- Add static checks and blocked operation warnings.
- Save checkpoint before high-risk execution.

Acceptance:

- User can inspect generated Python before running.
- Add-on can create and modify Blender objects.
- Failures show readable errors and do not silently corrupt state.

Status: Initial approval-gated script flow is implemented. External agents can stage generated Python with `draft_script`; the sidebar shows pending script status, risk, intent, expected changes, static issues/warnings, and Run/Reject controls; static checks block obvious risky imports/calls; execution pushes a Blender undo point when possible, saves a timestamped `.blend` checkpoint when enabled, and records stdout/errors in a local Text datablock. Failed scripts expose traceback/log context locally so external clients can draft a corrected script. When the user grants a runtime external script trust window, `draft_script` auto-runs staged scripts that pass static checks, and `run_approved_script` remains available for already staged scripts.
Tool-loop calls now have a larger output budget for complete `draft_script.code` payloads, and the dispatcher tolerates common alternate script field names before reporting missing code.

### Milestone 3.5: Live Preview Transactions

- Add a preview transaction manager around helper-based changes.
- Force viewport/timeline redraw after each applied preview step.
- Add commit, revert, and undo controls in the sidebar.
- Apply animation keyframes immediately and optionally jump/scrub to changed frames.

Acceptance:

- Low-risk material, transform, light, camera, and keyframe changes visibly update the scene as soon as the helper call executes.
- Users can revert the preview without manually unwinding each change.
- Riskier generated scripts still require explicit approval before mutating the scene.

Status: Initial tool loop implemented for scene object listing, object selection, playhead changes, selected-object movement, absolute transform edits, primitive creation, material assignment, emission material assignment, collection creation/linking, bounded modifier creation, Track To constraints, timeline setup, active camera selection, selected-object transform keyframes, light creation, camera creation, camera orbit creation, scene inspection, docs lookup scaffold, commit, and revert.
Advanced helper coverage is now implemented for Principled shader material setup, Geometry Nodes starter modifiers, shape key creation/animation, text objects, curve paths, bounded particles, basic armatures, copy-transform constraints, render settings, camera settings, and world background colors. These tools still use the reversible live-preview transaction; complex custom node graphs, production rigs, and simulation setups remain approval-gated Python.
Model refinement helpers are now implemented for shade smoothing, bevel/subdivision stacks, wheel assemblies, panel seams, window/glass panels, and bounded vehicle, product, and character refinement templates.
The bridge now uses request-specific tool schema selection so external agents receive a compact task-relevant subset instead of the whole growing toolbox.

### Milestone 4: Docs-Aware Coding

- Implement docs search using official Blender Python docs.
- Add version-aware docs links.
- Cache stable docs snippets where practical.
- Add a docs-first policy for unfamiliar APIs before script generation.
- Add curated local snippets/templates for common object, material, camera, light, modifier, constraint, and animation operations.

Acceptance:

- External agents can look up API details before drafting code.
- Responses cite the docs snippets used in the local transcript/log.
- Scripts use current Blender API names and avoid outdated examples.

Status: Docs cache is implemented as a version-keyed local JSON cache with curated snippets, official Blender URL candidates, citation records/reporting, and optional full Python API plus Blender Manual HTML zip downloaders/indexers. Search reports now include searched-index counts, source breakdowns, citation refs, and explicit fallback status.

### Milestone 4.5: Safe Editing Helpers

- Implement allowlisted helper functions for frequent edits.
- Let external agents prefer helper calls over arbitrary Python for simple changes.
- Add expected-change previews for helper calls.

Acceptance:

- Simple object, material, transform, camera, light, and keyframe changes do not require arbitrary generated Python.
- Helper calls are reversible through undo/checkpoint flow.

Status: Safe editing helpers now cover the original simple edits plus advanced bounded helpers, refinement helpers, vehicle/product/character production kits, object visibility/display, animation controls, rollback manifests, and domain-aware preview change reports that summarize expected live-helper changes and rollback coverage. Optional visual QA is covered by a background render smoke for the product and character refinement kits, with keepable artifacts via `CLAUDE_BLENDER_VISUAL_QA_DIR`.

### Milestone 5: Animation Workflows

- Add richer timeline, f-curve, action, camera, and constraint summaries.
- Add animation-specific script templates/checks.
- Add sampled playblast frame capture for visual animation review.

Acceptance:

- External agents can create simple object, material, light, and camera animations through helper tools.
- Generated animations can be previewed, sampled for visual review, and undone.

Status: Baseline animation workflows are implemented for transforms, object bounce, material/light properties, path following, interpolation, retiming, cycles, preview ranges, turntables, pulse/reveal/staggered motion, camera orbits, and sampled playblast frame capture exposed through MCP resources. The later timing/blocking, animation-principles review, physics/contact validation, visual review, and repair-loop work moved into Milestone 7A-7H and is now tracked there.

### Milestone 5.5: External Bridge And MCP

- Add a localhost-only bridge inside Blender.
- Add a dependency-free stdio MCP server that forwards tools/resources to the running bridge.
- Expose scene status/context, transcript, and tool contracts as resources.
- Add sidebar controls to start/stop the bridge and copy MCP client config.
- Keep generated Python approval-gated inside Blender even when requested by an external client.

Acceptance:

- External MCP clients can discover Blender tools and resources.
- Read-only scene inspection works from outside Blender.
- Live-helper tool calls route through the same preview/revert system.
- The bridge is off by default, binds only to `127.0.0.1`, and can require a bearer token.

Status: External bridge is implemented. Blender exposes a localhost JSON bridge, and `mcp_server.py` implements MCP lifecycle, compact catalog search/schema/invoke, tool wrappers, resources, prompts, pagination, JSON Schema validation, trust status, and diagnostics over stdio. Official Blender Lab parity is partially covered with blend-file diagnostics, workspace/layout inspection, workspace and viewport navigation helpers, render-thumbnail PNG resources, and async render jobs that run long renders in a background Blender process with pollable metadata/frame/log resources. The sidebar can start/stop the bridge and copy versioned client config. The GitHub Pages extension repository install path has been verified from a clean temporary Blender profile. Live MCP-client smoke is still required after install/reload or tool-surface changes because it depends on a running Blender bridge and client-side tool-cache refresh.

### Milestone 6: Packaging And QA

- Validate extension manifest.
- Bundle or avoid third-party dependencies.
- Add repeatable test scenes and smoke tests.

Acceptance:

- Extension package validates with Blender's extension command.
- Install docs and safety notes are clear.

### Milestone 7: Intent-Correct Advanced Animation

Milestone 7 should move beyond simple keyframe helpers into an animation workflow that understands the user's intent, applies human animation principles, validates the result, and repairs prompt drift. The goal is not just "make something move"; it is "make the motion satisfy the user's brief in a way an animator would recognize."

Solo can be an optional companion integration for durable memory, style profiles, project knowledge, and correction history, but it should not be required to complete or ship Milestone 7. Blender remains responsible for scene execution, preview/playblast, physics/simulation, and final edits. The core animation workflow should run from Blender scene context and local agent memory alone, with Solo adding cross-session memory when available.

#### Milestone 7A: Animation Brief And Prompt Contract

- Turn each animation prompt into a structured brief before editing the scene.
- Capture subject, action, motivation, style, camera, timing, physics, constraints, and success criteria.
- Ask short clarifying questions when prompt intent is under-specified.
- For clear prompts, produce a compact user-visible interpretation before generation.
- Preserve prompt requirements as a checklist that later validation can test.

Acceptance:

- A prompt such as "make the red ball bounce three times and get smaller each bounce" becomes an explicit contract with object, count, timing, scale, camera, and validation criteria.
- The agent can distinguish ambiguity that needs user input from detail that can be inferred safely.
- The prompt contract is available to the generation, validation, and repair steps.

Status: Complete for the current milestone scope. `create_animation_brief` is implemented as a non-mutating prompt-contract helper that resolves subjects, timing, counts, secondary scale/visibility/brightness requirements, assumptions, ambiguities, success criteria, and validation-plan flags from the current Blender context. The agent loop preflights animation generation prompts with this brief, carries the contract into generation context, and returns a concise clarifying question before model generation when the brief is ambiguous.

#### Milestone 7B: Timing Charts And Blocking Tools

- Add tools for animator-style blocking before spline/f-curve polish.
- Support key poses, holds, breakdowns, spacing notes, motion arcs, and frame-by-frame beat plans.
- Represent timing charts as structured data that helper tools can execute.
- Keep blocking edits reversible through the live-preview transaction system.

Candidate tools:

- `create_animation_brief`
- `create_timing_chart`
- `block_key_poses`
- `add_breakdown_pose`
- `set_pose_hold`
- `create_motion_arc`

Acceptance:

- The agent can create readable blocking for common actions such as jumps, throws, impacts, turns, camera moves, and reveal animations.
- Generated blocking uses clear keyframes and holds before adding interpolation polish.
- Users can preview, commit, or revert the blocking pass.

Status: Core helper set is implemented. `create_timing_chart` creates read-only structured pose/hold/breakdown plans; `block_key_poses`, `add_breakdown_pose`, `set_pose_hold`, and `create_motion_arc` support reversible animator-style blocking, holds, breakdowns, and in-scene arc visualization for selected or named objects.

#### Milestone 7C: Animation Principles Evaluator

- Add a principles layer that reasons about staging, anticipation, squash and stretch, timing and spacing, arcs, slow in/out, follow-through, overlap, secondary action, pose clarity, silhouette, weight, contact points, center of mass, and line of action.
- Store principle decisions as structured metadata, not only prose in the prompt.
- Evaluate generated animation against the principle plan.

Candidate tools:

- `analyze_motion_arcs`
- `analyze_fcurve_spacing`
- `analyze_pose_clarity`
- `analyze_animation_principles`

Acceptance:

- A simple "happy jump" includes anticipation, launch, arc, landing squash, overshoot, and settle.
- The evaluator can identify missing anticipation, overly linear motion, unclear pose staging, or absent settle after impact.
- Findings can feed the repair loop without losing the original prompt contract.

Status: Initial data-level evaluator is implemented. `analyze_motion_arcs`, `analyze_fcurve_spacing`, `analyze_pose_clarity`, and `analyze_animation_principles` inspect keyed transform data against the animation brief and timing chart, returning structured findings for arcs, timing/spacing, pose clarity, anticipation, squash/stretch, contact/weight, secondary action, and settle.

#### Milestone 7D: Animation-Aware Scene Understanding

- Deepen scene inspection for advanced animation context.
- Include rig controls, bones, IK/FK chains, constraints, drivers, actions, NLA tracks, contact surfaces, object scale/units, mass/weight hints, cameras, shot framing, pose libraries, shape keys, cloth, rigid-body, and particle systems.
- Reuse the existing context planner so this detail is retrieved on demand instead of always sent in every prompt.

Acceptance:

- The agent can inspect where animation data actually lives: object transforms, data blocks, shape keys, materials, constraints, drivers, NLA, and rig controls.
- The agent can avoid common wrong edits such as keyframing the mesh object when a rig control should be animated.
- The context planner exposes deeper animation context only when the request needs it.

Status: Deeper animation-aware routing context is implemented. `get_animation_scene_context` summarizes likely edit targets, rig-driven meshes, armatures, pose-bone/control-candidate hints, shape-key targets, object/data/material animation ownership, action slots when available, keyed channel ranges, pose marker / pose-library candidates, drivers, constraints, NLA counts, physics/simulation hints, contact-surface candidates, and camera readiness. Subject routing now reports the recommended animation owner and routing confidence so agents can avoid keyframing a mesh when rig controls, shape keys, material data, or camera settings are the better target. `get_rigging_details` also returns richer control hints and pose-library candidates. Remaining 7D polish is real rig fixture testing across IK/FK-heavy characters and pose-library workflows.

#### Milestone 7E: Physics, Contact, And Prompt Validators

- Add validators that check the generated animation against both the brief and physical plausibility.
- Detect foot/object sliding, contact penetration, impossible acceleration, center-of-mass problems, collision/intersection issues, missing required actions, wrong object counts, camera framing failures, overly linear motion, incorrect frame ranges, and missing settle after impact.
- Use Blender physics/simulation where appropriate, then bake and inspect results rather than relying only on language-model judgment.

Candidate tools:

- `analyze_contact_sliding`
- `analyze_center_of_mass`
- `analyze_collision_penetration`
- `analyze_motion_physics`
- `compare_animation_to_brief`

Acceptance:

- The validator can tell whether a requested action happened, whether it happened the requested number of times, and whether the camera kept the subject visible.
- Physics-heavy prompts can use Blender simulation when helper-generated keyframes are not enough.
- Validation results are structured enough to drive targeted repairs.

Status: Stronger partial. Existing read-only validators cover sampled animation state, contact sliding against a contact plane, sampled bounding-box penetration, camera framing, brief comparison, sampled speed/acceleration spikes through `analyze_motion_physics`, center-of-mass/support footprint checks through `analyze_center_of_mass`, requested repeated-action count estimation, secondary scale-change checks, keyframe frame-range checks, and final settle diagnostics. `compare_animation_to_brief` now runs contact, motion-physics, and center/support checks when the brief requests contact validation, and emits repairable findings for wrong count, missing scale change, missing settle, and weak frame-range coverage. Simulation bake inspection is now surfaced through richer `get_simulation_details` output for rigid-body worlds, rigid bodies, particle systems, simulation modifiers, point-cache frame ranges, baked/unbaked cache counts, and repair-oriented cautions. `inspect_simulation_bake` now samples evaluated simulation state across a bounded frame range, restores the original frame, and reports cache/bake readiness without mutating persistent point caches. `stage_persistent_simulation_bake` now provides the explicit user-approved persistent bake path by staging a fixed-template scene-wide point-cache bake script that can auto-run only under active external script trust; requested object names limit inspection and range preparation, not Blender's bake-all operator scope. `analyze_center_of_mass` now prefers convex-hull support footprints from support objects' world-space bounds and can use weighted child-mesh bounds for rig/character subjects, so rotated supports, narrow supports, and articulated body-part layouts are not overestimated by a single axis-aligned object box. `review_playblast_against_brief` now adds conservative visual repeated-action count evidence from foreground subject center extrema when playblast samples are dense enough, and mismatches feed the same repair-planning path as data-level count findings. Remaining 7E work is richer biomechanical COM heuristics for production rigs and real-client smoke on the persistent bake approval/trust path.

#### Milestone 7F: Playblast Review And Repair Loop

- Add a contract loop: prompt -> brief -> user-visible interpretation -> generate -> evaluate -> repair.
- Add playblast or viewport-preview capture for animation review.
- Compare the playblast, animation data, and scene state against the prompt contract.
- Generate focused repair operations rather than starting over when only part of the animation is wrong.

Candidate tools:

- `capture_animation_playblast`
- `capture_object_inspection_renders`
- `review_playblast_against_brief`
- `repair_animation_from_findings`
- `run_animation_repair_loop`

Acceptance:

- The agent can repair prompt drift such as wrong bounce count, camera losing the subject, missing scale change, or absent follow-through.
- The repair loop preserves successful parts of the animation.
- The user sees concise review findings and can commit or revert the repaired preview.

Status: Playblast- and inspection-render-aware review, repair planning, and bounded repair-loop execution are implemented. `review_playblast_against_brief` normalizes playblast frame evidence, checks frame resource availability, frame coverage, undersampling, compact pixel digests, visual-subject interpretation, visual frame-to-frame motion deltas, and visual repeated-action count hints against the brief, combines that with current animation-state comparison, and returns structured repair operations. `review_inspection_renders_against_brief` normalizes diagnostic object-render evidence, checks missing/weak required views, includes the same visual-subject interpretation summary, and returns repair operations for focused `capture_object_inspection_renders` recapture when visual-detail evidence is missing or insufficient. `repair_animation_from_findings` maps findings to targeted helper calls with arguments, executable `tool_call` payloads, preview/commit flags, source-finding references, playblast-derived `target_frames` / `target_frame_range` metadata, inspection-render recapture arguments, count-repair bounce helpers, center/support pose holds, rig-control inspection, rig pose holds through `set_rig_pose_hold`, and frame-range retiming suggestions. `run_animation_repair_loop` applies a bounded allowlisted subset of those operations through safe helper tools, skips operations that need more planning, optionally requests a fresh playblast after mutating repairs, and re-runs review without bypassing the existing preview commit/revert model. Smoke coverage now includes an IK/FK-style rig with control, pole, pose-library, and constraint-target evidence. Remaining polish is deeper production-rig repair helpers where a simple control-bone hold may need IK/FK switch awareness or limb-specific controls.

#### Milestone 7G: Optional Solo-Backed Style And Project Memory

- Use Solo to remember user animation preferences, style profiles, project-specific animation rules, prior corrections, reusable animation briefs/templates, character/rig facts, and failed interpretations that should not repeat.
- Treat Solo as a durable companion memory and planning surface around Blender, not as a Blender execution backend.
- Keep local Blender agent memory for immediate scene/session continuity and use Solo for cross-session project memory.
- Include privacy and availability states in the UI: connected, unavailable, disabled, or limited.

Acceptance:

- Milestone 7A-7F can be implemented, tested, and shipped without Solo.
- When Solo is connected and enabled, the agent can retrieve relevant style/project memory before creating the animation brief.
- When Solo is unavailable, the agent continues with local Blender context and local agent memory without blocking the animation workflow.
- User corrections such as "when I say punchy, I mean fast anticipation and a hard impact" can become reusable future context.
- Solo memory never contains secrets, raw credentials, API keys, or hidden private content.

#### Milestone 7H: Animation Workflow Orchestration And MCP Client Guidance

Real-client testing showed that a connected MCP client can successfully inspect Blender and iterate with the user, but may still skip the intended Milestone 7 helper workflow and fall back to `draft_script` / `run_approved_script` too early. This produces useful Blender edits, but it bypasses animation briefs, timing charts, preview-safe helper transactions, structured validation, and repair loops.

- Add stronger agent and MCP guidance: for animation requests, prefer `plan_animation_workflow`, `get_animation_scene_context`, `create_animation_brief`, `create_timing_chart`, `block_key_poses`, evaluator tools, and repair-loop tools before `draft_script`.
- Add a higher-level orchestration tool for common animation workflows, such as `plan_animation_workflow`, `create_animation_from_brief`, or a focused `create_progressive_bounce_animation`, that runs or plans the brief -> timing chart -> helper blocking -> validation -> repair planning path.
- Make the orchestrator report whether changes are true live-preview helper edits, checkpoint-backed script edits, or read-only plans, so the client cannot incorrectly claim "commit/revert preview" for arbitrary approved scripts.
- Add real-client smoke prompts that verify Claude/Codex-style MCP clients choose the helper workflow for common animation requests instead of script-first execution.
- Use the real bounce test as a fixture: "Make the cube bounce twice over 72 frames, getting smaller each bounce. Check it against the brief and leave it as a preview."
- Use the aircraft underside/landing-gear inspection case as a visual-evidence fixture: the client should call `capture_object_inspection_renders` for diagnostic renders instead of drafting temporary camera/render Python.

Acceptance:

- For common animation prompts, external MCP clients follow the Milestone 7 helper path before considering arbitrary Python.
- If a helper path cannot represent the request, the client can escalate to `draft_script`, but the response clearly labels the result as checkpoint-backed rather than live-preview helper state.
- The orchestrator can produce a pending preview for at least one full start-to-finish animation workflow, then run structured validation and return commit/revert guidance.
- Real-client testing demonstrates that model behavior matches the intended workflow, not just that individual tools exist.

Status: Orchestration, guidance, and routing reliability are implemented in code and smoke tests. `plan_animation_workflow` is a read-only Milestone 7 entry point that creates the animation brief, animation-aware scene context, timing chart, ordered helper/evaluator/repair tool-call payloads, and explicit `draft_script` fallback rules. `run_animation_workflow` executes common helper-backed workflows such as bounce/turntable/reveal/pulse, runs structured evaluator review, optionally captures playblast evidence, optionally applies bounded repair operations, and reports live-preview state, helper gaps, skipped calls, findings, and repair plans. `run_animation_task` is the compact one-input MCP wrapper for common animation prompts. Compact MCP mode exposes the animation planner/runner/task tools directly; catalog ranking boosts animation workflow tools for bounce, jump, keyframe, pose, timing, arc, settle, squash/stretch, playblast, f-curve, spacing, and contact prompts; generic selected-object helpers and `draft_script` are down-ranked unless the prompt explicitly asks for script/Python/custom code. `draft_script` now has an animation guardrail that asks clients to use `run_animation_workflow` first unless helpers cannot express the work. The real bounce fixture routes through `create_progressive_bounce_animation`, which keys repeated bounce motion plus decreasing scale in a live-preview transaction. A first-class `capture_object_inspection_renders` plus `review_inspection_renders_against_brief` path covers diagnostic render-to-inspect behavior that real clients previously handled with ad hoc scripts, and rig repair findings now route to `get_rigging_details` plus `set_rig_pose_hold` instead of generic object-transform holds. Async render jobs now include `assemble_render_job_video` and `validate_render_job_output`, so clients can turn completed PNG sequences into MP4s and verify outputs without shell/imageio fallback. The fresh GitHub Pages extension install path is verified; remaining 7H work is manual real-client smoke with a running Blender bridge after install/reload, because external MCP clients may cache older tool lists or ranking behavior.

## Open Questions

- Which client-host integrations should be documented first after MCP: Claude Desktop, Claude Code, Codex, Cursor, or a small standalone example?
- How much autonomy should the default mode allow: suggest-only, approval-required, or limited autonomous tools?
- How strict should the default docs-first rule be before external agents are allowed to generate Blender Python?
- Which changes are safe enough for immediate live preview, and which must stay preview-only until explicit approval?

## User Decisions Captured

- Blender target is 5.1.
- Use a Blender extension plus local companion bridge/MCP surface over time.
- Keep LLM provider clients and API keys out of the production add-on.
- Apply safe helper changes immediately in the live Blender scene.
- Generated arbitrary Python always requires approval.
- Save checkpoints before risky changes when enabled.
- Deletes may happen through helper/script flows, with undo/revert support.
- Import/export requires approval.
- Docs lookup should use local cache first, official web docs second.
- Screenshot context is controlled by a toggle.
- User should be able to choose sidebar or floating UI eventually.
- Live helper changes should show logs/status only, not pause for a plan.
- Milestone 7 should not require Solo. Solo is an optional durable-memory enhancement for advanced animation style, project rules, reusable briefs, and correction history; Blender remains the execution layer, and the core animation workflow should run without Solo.
