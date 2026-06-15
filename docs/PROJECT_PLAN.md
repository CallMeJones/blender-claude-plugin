# Project Plan

## Working Name

Blender Agent Bridge

## North Star

Let a Blender user ask Claude in Blender, or connect Codex/Claude Code/other MCP-capable agents externally, to understand, critique, and modify the active scene. The assistant surface should combine structured scene inspection, viewport vision, Blender Python scripting, documentation lookup, and safe editing helpers so changing objects, materials, lights, cameras, and animations feels straightforward.

## Evidence From Current Docs

- Anthropic tool use supports client tools where Claude returns a structured tool call, the application executes it, then sends back a tool result.
- Anthropic vision supports image inputs through API requests, which fits viewport screenshots and preview renders.
- Anthropic Files API can avoid repeated upload of frequently reused files/images, but it is currently beta and has retention implications.
- Prompt caching can reduce cost and latency for stable system prompts, tool definitions, and possibly documentation excerpts.
- Blender 4.2+ extensions use `blender_manifest.toml`, can bundle Python wheels, and must declare resource permissions such as network and files access.
- Blender Python exposes panels, operators, add-on preferences, scene data, object data, animation data, and render/viewport operations through `bpy`.

## MVP Scope

The first milestone should be useful but controlled:

- 3D View sidebar panel with a prompt box, response area, and run controls.
- Add-on preferences for API key, model, privacy defaults, and execution mode.
- Claude Messages API integration using Blender-compatible Python.
- Scene summary generation for selected objects and overall scene state.
- Layered context bundles that describe Blender version, mode, scene graph, selection, render settings, and animation state before Claude writes code.
- Optional viewport screenshot sent as an image input.
- Live preview mode for approved low-risk helper changes, with immediate viewport/timeline redraw and revert/commit controls.
- Script proposal flow where Claude drafts Blender Python but the user approves before execution.
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

User asks, "What is in this scene and how can I improve the lighting?" The add-on sends a structured scene digest plus optional screenshot. Claude returns analysis and suggestions.

2. Make A Small Change

User asks, "Add a warm key light and a cool rim light." Claude proposes a script. The add-on previews it. User approves. The add-on saves an undo point and executes.

3. Create An Object

User asks, "Make a stylized low-poly spaceship from primitives." Claude inspects units, selection, and collections, then proposes creation code. User approves and can undo.

4. Build An Animation

User asks, "Animate the camera orbiting this product over 120 frames." Claude reads selected object bounds and timeline settings, proposes camera/path/keyframe code, then executes after approval.

5. Use Blender Docs

User asks for a geometry nodes or modifier workflow. Claude calls `search_blender_docs` for relevant API references before writing code.

6. Make Safe Scripted Changes

User asks for a change. Claude first inspects context, retrieves docs for unfamiliar APIs, drafts a change plan, then uses either safe helper tools or a proposed script. The add-on checks the proposal, shows the expected changes, saves recovery state, and runs only after approval.

7. See Changes Immediately

User asks, "Make this object red and animate it bouncing." Claude uses safe helper calls for material and keyframes. The add-on applies each approved helper action to the live scene, updates the viewport/timeline, and keeps a visible preview transaction that can be committed or reverted.

8. Work Progressively Like An Agent

User clears the input and asks a follow-up such as, "now add the lighting pass." The add-on sends the current scene context plus compact `Claude Agent Memory`, so Claude can continue the same scene/object/animation goal while treating the open Blender scene as the source of truth.

9. Connect From An External Agent

User starts the `External Bridge` in Blender and copies the MCP config into a compatible client. The external agent lists Blender tools/resources, reads scene context, and calls the same bounded helpers/scripts through Blender instead of importing `bpy` directly.

## Tool Surface

Expose Claude to narrow client tools rather than raw Python first:

- `inspect_scene`: returns scene, collections, selected objects, camera, lights, timeline, and render settings.
- `list_scene_objects`: returns object names, types, selection state, visibility, collections, and locations.
- `get_object_details`: returns deeper details for named objects.
- `get_animation_details`: returns actions, f-curves, keyframes, constraints, drivers, and timeline details.
- `get_material_node_details`: returns material slots, shader node summaries, and image texture references.
- `get_geometry_nodes_details`: returns geometry-node modifier and node-group summaries.
- `get_shader_nodes_details`: returns material shader-node summaries for selected or named materials.
- `get_rigging_details`: returns armatures, bones, pose constraints, object constraints, and drivers.
- `get_shape_key_details`: returns shape-key blocks, values, limits, and drivers.
- `get_curve_text_details`: returns curve/text object properties and spline/text summaries.
- `get_simulation_details`: returns particle/simulation modifiers and particle settings summaries.
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
- `draft_script`: stores proposed code without running it.
- `run_approved_script`: only runs code after explicit user approval.
- `undo_last_action`: calls Blender undo for the last approved execution.
- `save_checkpoint`: saves a copy of the current `.blend` before risky work.
- `agent_memory`: compact running project context stored locally in `Claude Agent Memory`.

## Milestones

### Milestone 0: Project Skeleton

- Create Blender extension folder and manifest.
- Add a minimal panel, preferences, and operator.
- Confirm install and enable in Blender 4.2+ or current installed Blender.

Acceptance:

- Extension can be installed from disk.
- Sidebar panel appears in the 3D View.
- Preferences persist local configuration.

### Milestone 1: Text Chat + Scene Context

- Implement API transport.
- Implement context bundle generation.
- Implement scene, selection, object, material, render, and animation digests.
- Send user prompt plus structured scene context.
- Display Claude response in Blender UI.

Acceptance:

- Claude can answer questions about selected objects and scene settings.
- Large scenes are summarized without sending full geometry by default.
- Claude can ask for deeper object/material/animation details through tools instead of guessing.

Status: Initial scene context, per-project agent memory, token-aware context planning, sidebar char/token estimates, and read-only detail retrieval tools are implemented.
Deep world-model inspection is now available for geometry nodes, shader nodes, rigging/constraints/drivers, shape keys, curves/text, simulations, collection/view-layer organization, render/camera settings, and compositor nodes.
Short acknowledgements such as `ok` and the `Continue` button now continue the current agent task from memory/current scene rather than acting as script approval.
The sidebar now has persistent `Claude Chat History`, clears the input after send, shows recent chat turns, and groups pending work in an Action Center.

### Milestone 2: Screenshot/Vision Context

- Add viewport screenshot capture.
- Allow user to include current viewport image.
- Compress/resize images to stay within API limits.

Acceptance:

- Claude can comment on visible composition, object placement, materials, and framing.
- User can toggle screenshot inclusion per prompt.

Status: Viewport screenshot attachment is implemented with a user toggle, project/session-scoped capture storage, maximum byte limit, API-only image blocks, transcript-safe metadata, MCP capture resources for external clients, and explicit PNG downscaling/re-save when a capture exceeds the request byte budget. Broader visual QA and animation/playblast review remain later work.

### Milestone 3: Approved Script Execution

- Add script preview, approval, execution, logs, and undo.
- Add static checks and blocked operation warnings.
- Save checkpoint before high-risk execution.

Acceptance:

- User can inspect generated Python before running.
- Add-on can create and modify Blender objects.
- Failures show readable errors and do not silently corrupt state.

Status: Initial approval-gated script flow is implemented. Claude can stage generated Python with `draft_script`; the sidebar shows pending script status, risk, intent, expected changes, static issues/warnings, and Run/Reject controls; static checks block obvious risky imports/calls; execution pushes a Blender undo point when possible, saves a timestamped `.blend` checkpoint when enabled, and records stdout/errors in a local Text datablock. Failed scripts can be sent back to Claude with `Repair Script`.
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
Model refinement helpers are now implemented for shade smoothing, bevel/subdivision stacks, wheel assemblies, panel seams, window/glass panels, and a first vehicle refinement template.
The agent loop now uses request-specific tool schema selection so Claude receives a compact task-relevant subset instead of the whole growing toolbox.

### Milestone 4: Docs-Aware Coding

- Implement docs search using official Blender Python docs.
- Add version-aware docs links.
- Cache stable docs snippets where practical.
- Add a docs-first policy for unfamiliar APIs before script generation.
- Add curated local snippets/templates for common object, material, camera, light, modifier, constraint, and animation operations.

Acceptance:

- Claude can look up API details before drafting code.
- Responses cite the docs snippets used in the local transcript/log.
- Scripts use current Blender API names and avoid outdated examples.

Status: Docs cache is implemented as a version-keyed local JSON cache with curated snippets, official Blender URL candidates, citation records/reporting, and an optional full Python API zip downloader/indexer. Official Manual search URL fallback exists for non-API workflow concepts; full Blender Manual indexing remains later work.

### Milestone 4.5: Safe Editing Helpers

- Implement allowlisted helper functions for frequent edits.
- Let Claude prefer helper calls over arbitrary Python for simple changes.
- Add expected-change previews for helper calls.

Acceptance:

- Simple object, material, transform, camera, light, and keyframe changes do not require arbitrary generated Python.
- Helper calls are reversible through undo/checkpoint flow.

Status: Safe editing helpers now cover the original simple edits plus advanced bounded helpers, refinement helpers, object visibility/display, animation controls, rollback manifests, and generic preview change reports that summarize expected live-helper changes and rollback coverage.

### Milestone 5: Animation Workflows

- Add richer timeline, f-curve, action, camera, and constraint summaries.
- Add animation-specific script templates/checks.

Acceptance:

- Claude can create simple object, material, light, and camera animations.
- Generated animations can be previewed and undone.

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

Status: External bridge is implemented. Blender exposes a localhost JSON bridge, and `mcp_server.py` implements MCP lifecycle, compact catalog search/schema/invoke, tool wrappers, resources, prompts, pagination, JSON Schema validation, trust status, and diagnostics over stdio. The sidebar can start/stop the bridge and copy versioned client config. Real-client smoke is still required after install/reload or tool-surface changes.

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

#### Milestone 7D: Animation-Aware Scene Understanding

- Deepen scene inspection for advanced animation context.
- Include rig controls, bones, IK/FK chains, constraints, drivers, actions, NLA tracks, contact surfaces, object scale/units, mass/weight hints, cameras, shot framing, pose libraries, shape keys, cloth, rigid-body, and particle systems.
- Reuse the existing context planner so this detail is retrieved on demand instead of always sent in every prompt.

Acceptance:

- The agent can inspect where animation data actually lives: object transforms, data blocks, shape keys, materials, constraints, drivers, NLA, and rig controls.
- The agent can avoid common wrong edits such as keyframing the mesh object when a rig control should be animated.
- The context planner exposes deeper animation context only when the request needs it.

#### Milestone 7E: Physics, Contact, And Prompt Validators

- Add validators that check the generated animation against both the brief and physical plausibility.
- Detect foot/object sliding, contact penetration, impossible acceleration, center-of-mass problems, collision/intersection issues, missing required actions, wrong object counts, camera framing failures, overly linear motion, incorrect frame ranges, and missing settle after impact.
- Use Blender physics/simulation where appropriate, then bake and inspect results rather than relying only on language-model judgment.

Candidate tools:

- `analyze_contact_sliding`
- `analyze_center_of_mass`
- `analyze_collision_penetration`
- `compare_animation_to_brief`

Acceptance:

- The validator can tell whether a requested action happened, whether it happened the requested number of times, and whether the camera kept the subject visible.
- Physics-heavy prompts can use Blender simulation when helper-generated keyframes are not enough.
- Validation results are structured enough to drive targeted repairs.

#### Milestone 7F: Playblast Review And Repair Loop

- Add a contract loop: prompt -> brief -> user-visible interpretation -> generate -> evaluate -> repair.
- Add playblast or viewport-preview capture for animation review.
- Compare the playblast, animation data, and scene state against the prompt contract.
- Generate focused repair operations rather than starting over when only part of the animation is wrong.

Candidate tools:

- `create_animation_playblast`
- `review_playblast_against_brief`
- `repair_animation_from_findings`

Acceptance:

- The agent can repair prompt drift such as wrong bounce count, camera losing the subject, missing scale change, or absent follow-through.
- The repair loop preserves successful parts of the animation.
- The user sees concise review findings and can commit or revert the repaired preview.

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

## Open Questions

- Should the Anthropic API transport stay inside Blender, or move to the companion bridge once the tool loop grows?
- How much autonomy should the default mode allow: suggest-only, approval-required, or limited autonomous tools?
- How strict should the default docs-first rule be before Claude is allowed to generate Blender Python?
- Which changes are safe enough for immediate live preview, and which must stay preview-only until explicit approval?

## User Decisions Captured

- Blender target is 5.1.
- Use a Blender extension plus local companion bridge/MCP surface over time.
- Use direct Anthropic API for MVP with provider-shaped internal interfaces.
- Read the API key from `ANTHROPIC_API_KEY`.
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
